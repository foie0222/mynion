"""
Lambda handler for OAuth2 callback from AgentCore Identity.

This function handles the OAuth2 callback redirect from AgentCore Identity
and calls CompleteResourceTokenAuth to complete the session binding flow.

The callback URL is registered in Workload Identity's allowedResourceOauth2ReturnUrls.
"""

import logging
import os
from typing import Any

import boto3

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Environment variables
AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-1")

# Initialize AgentCore client
# Note: bedrock-agentcore is the data plane client
agentcore_client = boto3.client(
    "bedrock-agentcore",
    region_name=AWS_REGION,
)

# HTML templates for responses
SUCCESS_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>認証完了</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background-color: #f4f4f4;
        }
        .container {
            text-align: center;
            padding: 40px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .success-icon {
            font-size: 64px;
            margin-bottom: 20px;
        }
        h1 {
            color: #2e7d32;
            margin-bottom: 10px;
        }
        p {
            color: #666;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="success-icon">✓</div>
        <h1>認証が完了しました</h1>
        <p>このタブを閉じて、Slack に戻ってください。</p>
    </div>
</body>
</html>"""

# Note: CSS braces are doubled to escape them for .format()
ERROR_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>認証エラー</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            height: 100vh;
            margin: 0;
            background-color: #f4f4f4;
        }}
        .container {{
            text-align: center;
            padding: 40px;
            background: white;
            border-radius: 12px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }}
        .error-icon {{
            font-size: 64px;
            margin-bottom: 20px;
        }}
        h1 {{
            color: #c62828;
            margin-bottom: 10px;
        }}
        p {{
            color: #666;
        }}
        .error-detail {{
            margin-top: 20px;
            padding: 10px;
            background: #ffebee;
            border-radius: 4px;
            font-size: 14px;
            color: #c62828;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="error-icon">✗</div>
        <h1>認証エラー</h1>
        <p>認証処理中にエラーが発生しました。</p>
        <div class="error-detail">{error_message}</div>
        <p>もう一度お試しください。</p>
    </div>
</body>
</html>"""


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Handle OAuth2 callback from AgentCore Identity.

    AgentCore redirects to this endpoint after Google OAuth authorization completes.
    The redirect includes:
    - session_id: AgentCore's internal session identifier
    - state: custom_state passed during auth initiation (contains Slack user_id)

    Args:
        event: API Gateway event with query parameters
        context: Lambda context

    Returns:
        API Gateway response with HTML content
    """
    logger.info("OAuth callback handler invoked")
    logger.info(f"Event: {event}")

    try:
        # Extract query parameters
        query_params = event.get("queryStringParameters") or {}
        session_id = query_params.get("session_id")
        # user_id is passed via custom_state during auth initiation
        # AgentCore returns it as the standard OAuth2 'state' parameter
        user_id = query_params.get("state")

        logger.info(f"session_id: {session_id}, user_id (from state): {user_id}")

        # Validate required parameters
        if not session_id:
            logger.error("Missing session_id in callback")
            return _error_response("session_id が見つかりません")

        if not user_id:
            logger.error("Missing user_id in callback")
            return _error_response("user_id が見つかりません")

        # Call CompleteResourceTokenAuth to complete the session binding
        logger.info(f"Calling CompleteResourceTokenAuth for session: {session_id}")
        response = agentcore_client.complete_resource_token_auth(
            sessionUri=session_id,
            userIdentifier={"userId": user_id},
        )
        logger.info(f"CompleteResourceTokenAuth response: {response}")

        # Return success HTML
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "text/html; charset=utf-8",
            },
            "body": SUCCESS_HTML,
        }

    except agentcore_client.exceptions.ValidationException as e:
        logger.error(f"Validation error: {e}")
        return _error_response(f"検証エラー: {str(e)}")

    except agentcore_client.exceptions.AccessDeniedException as e:
        logger.error(f"Access denied: {e}")
        return _error_response("アクセスが拒否されました")

    except agentcore_client.exceptions.ResourceNotFoundException as e:
        logger.error(f"Resource not found: {e}")
        return _error_response("セッションが見つかりません。有効期限切れの可能性があります。")

    except Exception as e:
        logger.error(f"Unexpected error: {e}", exc_info=True)
        return _error_response(f"予期しないエラー: {str(e)}")


def _error_response(error_message: str) -> dict[str, Any]:
    """Generate error HTML response."""
    return {
        "statusCode": 400,
        "headers": {
            "Content-Type": "text/html; charset=utf-8",
        },
        "body": ERROR_HTML_TEMPLATE.format(error_message=error_message),
    }
