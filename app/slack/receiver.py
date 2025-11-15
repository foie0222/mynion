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

        # Get headers (handle both direct and proxy integration formats)
        headers = event.get("headers", {})

        # Slack sends headers in lowercase
        slack_signature = headers.get("x-slack-signature", "")
        slack_request_timestamp = headers.get("x-slack-request-timestamp", "")

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

        # Handle slash commands
        if "command" in body:
            # Extract user and team IDs
            user_id = body.get("user_id", "")
            team_id = body.get("team_id", "")
            channel_id = body.get("channel_id", "")

            # For slash commands, generate a unique thread_id based on trigger_id
            # This creates a new session for each slash command invocation
            thread_id = body.get("trigger_id", "")

            # Prepare payload for Worker Lambda
            worker_payload = {
                "command": body.get("command", ""),
                "text": body.get("text", ""),
                "user_id": user_id,
                "team_id": team_id,
                "channel_id": channel_id,
                "thread_id": thread_id,
                "response_url": body.get("response_url", ""),
            }

            # Invoke Worker Lambda asynchronously
            logger.info(f"Invoking Worker Lambda for slash command: {worker_payload}")
            lambda_client.invoke(
                FunctionName=WORKER_LAMBDA_ARN,
                InvocationType="Event",
                Payload=json.dumps(worker_payload),
            )

            # Return immediate acknowledgment
            return {
                "statusCode": 200,
                "headers": {"Content-Type": "application/json"},
                "body": json.dumps(
                    {
                        "response_type": "in_channel",
                        "text": "処理中です。少々お待ちください...",
                    }
                ),
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
