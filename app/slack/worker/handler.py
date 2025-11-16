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
from typing import Any

import boto3
import httpx
from agent_client import AgentCoreClient

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

# Cache for Slack credentials
_slack_credentials: dict[str, str] | None = None


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
                result = response.json()

                if not result.get("ok"):
                    logger.error(f"Slack API error: {result.get('error')}")
                    raise Exception(f"Slack API error: {result.get('error')}")

                return result

        except Exception as e:
            logger.error(f"Error posting to Slack: {str(e)}", exc_info=True)
            raise

    def post_button_message(
        self, channel: str, text: str, button_text: str, button_url: str
    ) -> dict[str, Any]:
        """
        Post a message with a button (used for OAuth flow).

        Args:
            channel: Slack channel ID
            text: Message text
            button_text: Button label
            button_url: Button URL

        Returns:
            Slack API response
        """
        try:
            payload = {
                "channel": channel,
                "text": text,
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": text,
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": button_text,
                                },
                                "url": button_url,
                                "style": "primary",
                            }
                        ],
                    },
                ],
            }

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
                result = response.json()

                if not result.get("ok"):
                    logger.error(f"Slack API error: {result.get('error')}")
                    raise Exception(f"Slack API error: {result.get('error')}")

                return result

        except Exception as e:
            logger.error(f"Error posting button to Slack: {str(e)}", exc_info=True)
            raise


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

        # Extract user message
        if "command" in event:
            # Slash command
            user_message = event.get("text", "")
            thread_ts = None  # Slash commands don't have threads initially
        else:
            # Event callback (app_mention, message, etc.)
            user_message = slack_event.get("text", "")
            user_message = clean_message(user_message)
            thread_ts = slack_event.get("ts")  # Reply in thread

        if not user_message:
            logger.warning("Empty user message, skipping")
            return {"statusCode": 200, "body": "Empty message"}

        # Generate IDs for AgentCore
        # User ID for AgentCore Identity (token vault)
        agentcore_user_id = f"slack-{team_id}-{user_id}"

        # Session ID based on thread (1 thread = 1 session)
        session_id = f"slack-{thread_id}" if thread_id else f"slack-new-{user_id}"

        logger.info(f"Invoking AgentCore: user_id={agentcore_user_id}, session_id={session_id}")

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

        # Handle response
        if result.get("requires_auth"):
            # OAuth authentication required
            slack_client.post_button_message(
                channel=channel_id,
                text="認証が必要です。以下のボタンをクリックして認証してください。",
                button_text="認証する",
                button_url="https://example.com/oauth",  # TODO: Get actual OAuth URL
            )
        else:
            # Send agent response to Slack
            agent_response = result.get("output", "応答がありませんでした。")
            slack_client.post_message(
                channel=channel_id,
                text=agent_response,
                thread_ts=thread_ts,
            )

        logger.info("Successfully sent response to Slack")
        return {"statusCode": 200, "body": "Success"}

    except Exception as e:
        logger.error(f"Worker error: {str(e)}", exc_info=True)
        return {"statusCode": 500, "body": f"Worker error: {str(e)}"}
