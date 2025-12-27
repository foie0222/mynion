"""
Lambda Worker for processing Slack events with AgentCore Runtime.

This function:
1. Receives events from Receiver Lambda
2. Invokes AgentCore Runtime with user identity headers
3. Handles OAuth authentication flow via AgentCore Identity
4. Sends responses back to Slack
"""

import json
import logging
import os
import re
import uuid
from typing import Any

import boto3
import httpx

from .agent_client import AgentCoreClient

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
secretsmanager_client = boto3.client("secretsmanager")

# Environment variables
SLACK_SECRET_ARN = os.environ.get("SLACK_SECRET_ARN", "")
AGENTCORE_RUNTIME_ID = os.environ.get("AGENTCORE_RUNTIME_ID", "")
AGENTCORE_RUNTIME_ENDPOINT = os.environ.get("AGENTCORE_RUNTIME_ENDPOINT", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

# Slack session namespace for UUID v5 generation (fixed, never change)
SLACK_SESSION_NAMESPACE = uuid.UUID("a1b2c3d4-e5f6-5678-9abc-def012345678")

# Cache for Slack credentials
_slack_credentials: dict[str, str] | None = None

# Cache for bot user ID (loaded once per container lifecycle)
_bot_user_id: str | None = None


def get_slack_credentials() -> dict[str, str]:
    """
    Get Slack credentials from Secrets Manager.
    Cached for container lifecycle to improve performance.

    Returns:
        Dict with SLACK_BOT_TOKEN and SLACK_SIGNING_SECRET
    """
    global _slack_credentials

    if _slack_credentials is not None:
        return _slack_credentials

    try:
        logger.info("Loading Slack credentials from Secrets Manager")
        response = secretsmanager_client.get_secret_value(SecretId=SLACK_SECRET_ARN)
        secret_string = response.get("SecretString", "{}")
        credentials: dict[str, str] = json.loads(secret_string)
        _slack_credentials = credentials
        logger.info("Slack credentials loaded successfully")
        return credentials
    except Exception as e:
        logger.error(f"Error loading Slack credentials: {str(e)}", exc_info=True)
        # Fallback to environment variables for local testing
        return {
            "SLACK_BOT_TOKEN": os.environ.get("SLACK_BOT_TOKEN", ""),
        }


class SlackClient:
    """Client for Slack API interactions."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = "https://slack.com/api"

    def post_message(self, channel: str, text: str, thread_ts: str | None = None) -> dict[str, Any]:
        """
        Post a message to Slack channel.

        Args:
            channel: Slack channel ID
            text: Message text
            thread_ts: Optional thread timestamp for threaded replies

        Returns:
            Slack API response
        """
        try:
            payload = {
                "channel": channel,
                "text": text,
            }

            if thread_ts:
                payload["thread_ts"] = thread_ts

            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/chat.postMessage",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=10.0,
                )

                response.raise_for_status()
                result: dict[str, Any] = response.json()

                if not result.get("ok"):
                    logger.error(f"Slack API error: {result.get('error')}")
                    raise Exception(f"Slack API error: {result.get('error')}")

                return result

        except Exception as e:
            logger.error(f"Error posting to Slack: {str(e)}", exc_info=True)
            raise

    def update_message(self, channel: str, ts: str, text: str) -> dict[str, Any]:
        """
        Update an existing message in Slack channel.

        Args:
            channel: Slack channel ID
            ts: Timestamp of the message to update
            text: New message text

        Returns:
            Slack API response
        """
        try:
            payload = {
                "channel": channel,
                "ts": ts,
                "text": text,
            }

            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/chat.update",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=10.0,
                )

                response.raise_for_status()
                result: dict[str, Any] = response.json()

                if not result.get("ok"):
                    logger.error(f"Slack API error: {result.get('error')}")
                    raise Exception(f"Slack API error: {result.get('error')}")

                return result

        except Exception as e:
            logger.error(f"Error updating Slack message: {str(e)}", exc_info=True)
            raise

    def get_bot_user_id(self) -> str:
        """
        Get the bot's user ID using auth.test API.

        Results are cached globally for the container lifecycle.
        Only successful results are cached; failures will be retried on next call.

        Returns:
            Bot user ID, or empty string if retrieval fails
        """
        global _bot_user_id

        # Return cached value if available
        if _bot_user_id is not None:
            return _bot_user_id

        try:
            with httpx.Client() as client:
                response = client.post(
                    f"{self.base_url}/auth.test",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=10.0,
                )

                response.raise_for_status()
                result: dict[str, Any] = response.json()

                if not result.get("ok"):
                    logger.error(f"Slack API error: {result.get('error')}")
                    return ""

                user_id: str = result.get("user_id", "")

                # Only cache successful results
                if user_id:
                    _bot_user_id = user_id

                return user_id

        except Exception as e:
            logger.error(f"Error getting bot user ID: {str(e)}", exc_info=True)
            return ""

    def get_thread_replies(self, channel: str, thread_ts: str) -> dict[str, Any]:
        """
        Get all replies in a thread using conversations.replies API.

        Args:
            channel: Slack channel ID
            thread_ts: Thread timestamp (parent message ts)

        Returns:
            Slack API response with messages
        """
        try:
            with httpx.Client() as client:
                response = client.get(
                    f"{self.base_url}/conversations.replies",
                    headers={
                        "Authorization": f"Bearer {self.bot_token}",
                    },
                    params={
                        "channel": channel,
                        "ts": thread_ts,
                        "limit": 5,
                    },
                    timeout=10.0,
                )

                response.raise_for_status()
                result: dict[str, Any] = response.json()

                if not result.get("ok"):
                    logger.error(f"Slack API error: {result.get('error')}")
                    return {"messages": []}

                return result

        except Exception as e:
            logger.error(f"Error getting thread replies: {str(e)}", exc_info=True)
            return {"messages": []}


def is_bot_in_thread(
    slack_client: SlackClient, channel: str, thread_ts: str, bot_user_id: str
) -> bool:
    """
    Check if the bot has participated in the thread.

    Args:
        slack_client: SlackClient instance
        channel: Slack channel ID
        thread_ts: Thread timestamp
        bot_user_id: Bot's user ID

    Returns:
        True if the bot has messages in the thread.
        False if the bot has no messages in the thread or if an error occurs
        while checking (errors are logged and not raised).
    """
    try:
        response = slack_client.get_thread_replies(channel, thread_ts)
        messages = response.get("messages", [])

        return any(msg.get("user") == bot_user_id for msg in messages)
    except Exception as e:
        logger.error(f"Error checking bot in thread: {str(e)}", exc_info=True)
        return False


def should_respond(
    slack_client: SlackClient,
    slack_event: dict[str, Any],
    bot_user_id: str,
    channel: str,
) -> bool:
    """
    Determine if the bot should respond to this event.

    The bot responds when:
    - The bot is mentioned in the message text
    - The message is a reply in a thread where the bot has previously participated

    Args:
        slack_client: SlackClient instance
        slack_event: Slack event data
        bot_user_id: Bot's user ID
        channel: Slack channel ID

    Returns:
        True if bot should respond, False otherwise
    """
    text = slack_event.get("text", "")
    thread_ts = slack_event.get("thread_ts")

    # Respond if mentioned
    if f"<@{bot_user_id}>" in text:
        return True

    # For thread replies, check if bot is participating
    return bool(thread_ts and is_bot_in_thread(slack_client, channel, thread_ts, bot_user_id))


def clean_message(text: str) -> str:
    """
    Remove bot mentions from message.

    Args:
        text: Raw message text

    Returns:
        Cleaned message
    """
    # Remove <@BOTID> mentions
    cleaned = re.sub(r"<@[A-Z0-9]+>", "", text).strip()
    return cleaned


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """
    Lambda Worker handler.

    Processes Slack events by:
    1. Extracting user message and identity
    2. Invoking AgentCore Runtime with user-specific headers
    3. Handling OAuth authentication requests
    4. Sending responses back to Slack

    Args:
        event: Event from Receiver Lambda
        context: Lambda context

    Returns:
        Processing result
    """
    try:
        logger.info(f"Worker received event: {json.dumps(event)}")

        # Get Slack credentials
        credentials = get_slack_credentials()
        slack_bot_token = credentials.get("SLACK_BOT_TOKEN", "")

        if not slack_bot_token:
            logger.error("SLACK_BOT_TOKEN not found in credentials")
            return {"statusCode": 500, "body": "Missing Slack credentials"}

        # Initialize Slack client
        slack_client = SlackClient(slack_bot_token)

        # Extract event data
        slack_event = event.get("event", {})
        user_id = event.get("user_id", "")
        team_id = event.get("team_id", "")
        channel_id = event.get("channel_id", "")
        thread_id = event.get("thread_id", "")

        # Get bot user ID for response filtering (cached)
        bot_user_id = slack_client.get_bot_user_id()
        if not bot_user_id:
            logger.error("Failed to get bot user ID")
            return {"statusCode": 500, "body": "Failed to get bot user ID"}

        # Check if bot should respond to this event
        if not should_respond(slack_client, slack_event, bot_user_id, channel_id):
            logger.info("Bot should not respond to this event, skipping")
            return {"statusCode": 200, "body": "Not responding"}

        # Event callback (app_mention, message, etc.)
        user_message = clean_message(slack_event.get("text", ""))
        thread_ts = slack_event.get("ts")  # Reply in thread

        if not user_message:
            logger.warning("Empty user message, skipping")
            return {"statusCode": 200, "body": "Empty message"}

        # Generate IDs for AgentCore
        agentcore_user_id = f"slack-{team_id}-{user_id}"

        # Generate session ID using UUID v5 (min 33 chars required by AgentCore)
        session_id = str(uuid.uuid5(SLACK_SESSION_NAMESPACE, thread_id))

        logger.info(f"Invoking AgentCore: user_id={agentcore_user_id}, session_id={session_id}")

        # Send "thinking" message first to provide immediate feedback
        thinking_response = slack_client.post_message(
            channel=channel_id,
            text="考え中...",
            thread_ts=thread_ts,
        )
        thinking_ts: str = thinking_response.get("ts", "")

        # Initialize AgentCore client
        agent_client = AgentCoreClient(
            endpoint_arn=AGENTCORE_RUNTIME_ENDPOINT,
            region=AWS_REGION,
        )

        # Invoke AgentCore Runtime
        result = agent_client.invoke_agent(
            user_id=agentcore_user_id,
            session_id=session_id,
            input_text=user_message,
        )

        # Extract agent response
        logger.info(f"Agent result: {json.dumps(result, default=str)}")

        if isinstance(result, str):
            # Streaming response - already a string
            agent_response = result if result else "応答がありませんでした。"
        else:
            # JSON response - extract text from nested structure:
            # {"output": {"message": {"content": [{"text": "..."}]}}}
            agent_response = (
                result.get("output", {})
                .get("message", {})
                .get("content", [{}])[0]
                .get("text", "応答がありませんでした。")
            )

        # Update the "thinking" message with actual response
        slack_client.update_message(
            channel=channel_id,
            ts=thinking_ts,
            text=agent_response,
        )

        logger.info("Successfully updated response in Slack")
        return {"statusCode": 200, "body": "Success"}

    except Exception as e:
        logger.error(f"Worker error: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": f"Worker error: {str(e)}"}
