"""
Lambda Receiver for Slack events.

This function handles Slack events and immediately returns 200 OK within 3 seconds,
then asynchronously invokes the Worker Lambda for actual processing.
"""

import hashlib
import hmac
import json
import logging
import os
import time
from typing import Any

import boto3
import httpx

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
lambda_client = boto3.client("lambda")
secretsmanager_client = boto3.client("secretsmanager")

# Environment variables
SLACK_SECRET_ARN = os.environ.get("SLACK_SECRET_ARN", "")
WORKER_LAMBDA_ARN = os.environ.get("WORKER_LAMBDA_ARN", "")

# Cache for Slack credentials (loaded once per container lifecycle)
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
        logger.info(f"Loading Slack credentials from Secrets Manager: {SLACK_SECRET_ARN}")
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
            "SLACK_SIGNING_SECRET": os.environ.get("SLACK_SIGNING_SECRET", ""),
        }


class SlackClient:
    """Minimal Slack client for response filtering in receiver."""

    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = "https://slack.com/api"

    def get_bot_user_id(self) -> str:
        """
        Get the bot's user ID using auth.test API.

        Results are cached globally for the container lifecycle.
        Only successful results are cached.

        Returns:
            Bot user ID

        Raises:
            RuntimeError: When the bot user ID cannot be retrieved
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
                    error_msg = f"Slack API error: {result.get('error')}"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                user_id: str = result.get("user_id", "")
                if not user_id:
                    error_msg = "Slack API response missing user_id"
                    logger.error(error_msg)
                    raise RuntimeError(error_msg)

                # Cache successful result
                _bot_user_id = user_id
                return user_id

        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Error getting bot user ID: {str(e)}", exc_info=True)
            raise RuntimeError(f"Failed to get bot user ID: {str(e)}") from e

    def get_thread_replies(self, channel: str, thread_ts: str) -> dict[str, Any]:
        """
        Get recent replies in a thread using conversations.replies API.

        Retrieves up to 5 most recent messages to check bot participation.
        This limit balances API performance with detection accuracy for
        typical conversation threads.

        Args:
            channel: Slack channel ID
            thread_ts: Thread timestamp (parent message ts)

        Returns:
            Slack API response with messages.
            Returns {"messages": []} on error to allow graceful degradation.
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

    Returns:
        True if bot should respond, False otherwise
    """
    text = slack_event.get("text", "")
    thread_ts = slack_event.get("thread_ts")
    channel = slack_event.get("channel", "")

    # Ignore messages from the bot itself (prevents infinite loop)
    if slack_event.get("user") == bot_user_id:
        return False

    # Ignore messages with bot_id (other bots)
    if slack_event.get("bot_id"):
        return False

    # Respond if mentioned
    if f"<@{bot_user_id}>" in text:
        return True

    # For thread replies, check if bot is participating
    return bool(thread_ts and is_bot_in_thread(slack_client, channel, thread_ts, bot_user_id))


def verify_slack_request(event: dict[str, Any]) -> bool:
    """
    Verify that the request came from Slack using the signing secret.

    Args:
        event: Lambda event containing headers and body

    Returns:
        True if the request is valid, False otherwise
    """
    try:
        # Get Slack credentials
        credentials = get_slack_credentials()
        signing_secret = credentials.get("SLACK_SIGNING_SECRET", "")

        if not signing_secret:
            logger.error("SLACK_SIGNING_SECRET not found in credentials")
            return False

        headers = event.get("headers", {})
        slack_signature = headers.get("X-Slack-Signature", "")
        slack_request_timestamp = headers.get("X-Slack-Request-Timestamp", "")

        if not slack_signature or not slack_request_timestamp:
            logger.warning("Missing Slack signature or timestamp")
            return False

        # Prevent replay attacks (request older than 5 minutes)
        current_timestamp = int(time.time())
        if abs(current_timestamp - int(slack_request_timestamp)) > 60 * 5:
            logger.warning("Request timestamp is too old")
            return False

        # Get request body
        body = event.get("body", "")

        # Compute the signature
        sig_basestring = f"v0:{slack_request_timestamp}:{body}"
        computed_signature = (
            "v0="
            + hmac.new(
                signing_secret.encode(),
                sig_basestring.encode(),
                hashlib.sha256,
            ).hexdigest()
        )

        # Compare signatures
        if not hmac.compare_digest(computed_signature, slack_signature):
            logger.warning("Signature verification failed")
            return False

        return True

    except Exception as e:
        logger.error(f"Error verifying Slack request: {str(e)}", exc_info=True)
        return False


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    """
    Lambda Receiver handler.

    Responsibilities:
    1. Verify Slack signature
    2. Handle URL verification challenge
    3. Return 200 OK immediately (within 3 seconds)
    4. Asynchronously invoke Worker Lambda

    Args:
        event: API Gateway Lambda Proxy event
        context: Lambda context

    Returns:
        API Gateway response (200 OK)
    """
    try:
        logger.info(f"Received event: {json.dumps(event)}")

        # Verify Slack signature
        if not verify_slack_request(event):
            logger.error("Invalid Slack signature")
            return {
                "statusCode": 401,
                "body": json.dumps({"error": "Invalid signature"}),
            }

        # Parse request body
        body = event.get("body", "{}")
        if isinstance(body, str):
            body = json.loads(body)

        event_type = body.get("type")

        # Handle URL verification challenge (Slack setup)
        if event_type == "url_verification":
            logger.info("Handling URL verification challenge")
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"challenge": body.get("challenge")}),
            }

        # Handle event callback
        if event_type == "event_callback":
            slack_event = body.get("event", {})

            # Get Slack credentials for bot user ID check
            credentials = get_slack_credentials()
            slack_bot_token = credentials.get("SLACK_BOT_TOKEN", "")

            if not slack_bot_token:
                logger.error("SLACK_BOT_TOKEN not found, skipping response check")
                return {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"ok": True}),
                }

            # Check if bot should respond to this event
            slack_client = SlackClient(slack_bot_token)
            try:
                bot_user_id = slack_client.get_bot_user_id()
            except RuntimeError as e:
                logger.error(f"Failed to get bot user ID: {e}")
                return {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"ok": True}),
                }

            if not should_respond(slack_client, slack_event, bot_user_id):
                logger.info("Bot should not respond to this event, skipping")
                return {
                    "statusCode": 200,
                    "headers": {"Content-Type": "application/json"},
                    "body": json.dumps({"ok": True}),
                }

            # Extract user and team IDs for identity
            user_id = slack_event.get("user", "")
            team_id = body.get("team_id", "")
            channel_id = slack_event.get("channel", "")

            # Extract thread_id for session management
            # Use thread_ts if message is in a thread, otherwise use message ts (new thread)
            thread_id = slack_event.get("thread_ts") or slack_event.get("ts", "")

            # Prepare payload for Worker Lambda
            worker_payload = {
                "event": slack_event,
                "user_id": user_id,
                "team_id": team_id,
                "channel_id": channel_id,
                "thread_id": thread_id,
                "event_id": body.get("event_id", ""),
                "event_time": body.get("event_time", 0),
            }

            # Invoke Worker Lambda asynchronously (fire and forget)
            logger.info(f"Invoking Worker Lambda with payload: {worker_payload}")
            lambda_client.invoke(
                FunctionName=WORKER_LAMBDA_ARN,
                InvocationType="Event",  # Asynchronous invocation
                Payload=json.dumps(worker_payload),
            )

            # Return 200 OK immediately
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps({"ok": True}),
            }

        # Unknown event type
        logger.warning(f"Unknown event type: {event_type}")
        return {
            "statusCode": 200,
            "body": json.dumps({"ok": True}),
        }

    except Exception as e:
        logger.error(f"Error in receiver: {str(e)}", exc_info=True)
        # Still return 200 to Slack to avoid retries
        return {
            "statusCode": 200,
            "body": json.dumps({"ok": True}),
        }
