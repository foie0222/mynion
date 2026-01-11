"""
Mynion Agent for AgentCore Runtime.

This agent integrates with:
- AgentCore Gateway for Calendar MCP tools (CUSTOM_JWT auth via Cognito)
- AgentCore Identity for Google Calendar OAuth authentication
"""

import contextvars
import json
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, cast

import boto3
import httpx
from bedrock_agentcore.identity.auth import requires_access_token
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

# Context variable for current user_id (used in OAuth callback URL construction)
_current_user_id: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "_current_user_id", default=None
)


class AuthRequiredError(Exception):
    """Raised when user authentication is required."""

    def __init__(self, auth_url: str):
        self.auth_url = auth_url
        super().__init__(f"認証が必要です: {auth_url}")


def _require_env(name: str) -> str:
    """Get required environment variable or raise RuntimeError."""
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"Environment variable '{name}' must be set.")
    return value


# Gateway configuration from environment variables
GATEWAY_ENDPOINT = _require_env("AGENTCORE_GATEWAY_ENDPOINT")
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
COGNITO_SECRET_NAME = _require_env("COGNITO_SECRET_NAME")
GOOGLE_CREDENTIAL_PROVIDER = _require_env("GOOGLE_CREDENTIAL_PROVIDER")
GOOGLE_OAUTH_CALLBACK_URL = _require_env("GOOGLE_OAUTH_CALLBACK_URL")

# Cache for tokens
_cognito_token_cache: dict[str, Any] = {}
_google_token_cache: dict[str, str | None] = {"token": None}


def get_cognito_credentials() -> dict[str, str]:
    """Get Cognito OAuth credentials from Secrets Manager."""
    client = boto3.client("secretsmanager", region_name=AWS_REGION)
    response = client.get_secret_value(SecretId=COGNITO_SECRET_NAME)
    return cast(dict[str, str], json.loads(response["SecretString"]))


def get_cognito_access_token() -> str:
    """Get access token from Cognito using client_credentials flow."""
    import time

    # Check cache
    if (
        _cognito_token_cache.get("token")
        and _cognito_token_cache.get("expires_at", 0) > time.time()
    ):
        return cast(str, _cognito_token_cache["token"])

    # Get credentials and fetch new token
    creds = get_cognito_credentials()
    response = httpx.post(
        creds["token_endpoint"],
        data={
            "grant_type": "client_credentials",
            "client_id": creds["client_id"],
            "client_secret": creds["client_secret"],
            "scope": creds["scope"],
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    response.raise_for_status()
    token_data = response.json()

    # Cache the token (with 5 minute buffer before expiry)
    access_token = cast(str, token_data["access_token"])
    _cognito_token_cache["token"] = access_token
    _cognito_token_cache["expires_at"] = time.time() + token_data.get("expires_in", 3600) - 300

    return access_token


@asynccontextmanager
async def cognito_auth_streamablehttp_client(endpoint: str):
    """Create an MCP client with Cognito Bearer token authentication."""
    token = get_cognito_access_token()
    headers = {"Authorization": f"Bearer {token}"}

    async with streamablehttp_client(endpoint, headers=headers) as streams:
        yield streams  # (read, write, get_session_id)


def _raise_auth_required(url: str) -> None:
    """Raise AuthRequiredError to stop polling and return auth URL immediately."""
    raise AuthRequiredError(url)


async def _get_google_token() -> str:
    """Get Google OAuth token, raises AuthRequiredError if auth needed."""
    # Check cache first
    if _google_token_cache.get("token"):
        return cast(str, _google_token_cache["token"])

    # Get user_id for Session Binding (passed via custom_state)
    user_id = _current_user_id.get()

    @requires_access_token(
        provider_name=GOOGLE_CREDENTIAL_PROVIDER,
        scopes=["https://www.googleapis.com/auth/calendar"],
        auth_flow="USER_FEDERATION",
        on_auth_url=_raise_auth_required,
        force_authentication=False,
        callback_url=GOOGLE_OAUTH_CALLBACK_URL,  # Plain URL, no query params
        custom_state=user_id,  # Pass user_id via custom_state for Session Binding
    )
    async def fetch_token(*, access_token: str) -> str:
        return access_token

    token = cast(str, await fetch_token())
    _google_token_cache["token"] = token
    return token


def get_google_token_sync() -> str:
    """Synchronously get Google OAuth token with context preservation.

    Raises:
        AuthRequiredError: If user authentication is required.
    """
    import asyncio
    import contextvars
    from concurrent.futures import ThreadPoolExecutor

    async def execute_async() -> str:
        return await _get_google_token()

    def execute() -> str:
        return asyncio.run(execute_async())

    # コンテキストを維持して別スレッドで実行
    with ThreadPoolExecutor() as executor:
        context = contextvars.copy_context()
        future = executor.submit(context.run, execute)
        return future.result()


class AuthInjectingMCPClient(MCPClient):
    """MCPClient that automatically injects Google OAuth token into calendar tool calls."""

    def call_tool_sync(
        self,
        tool_use_id: str,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
    ) -> Any:
        """Override to inject access_token for calendar tools."""
        from strands.tools.mcp.mcp_types import MCPToolResult

        # Check if this is a calendar tool that needs access_token
        if name.startswith("calendar___") and arguments is not None:
            try:
                token = get_google_token_sync()
                arguments["access_token"] = token
            except AuthRequiredError as e:
                return MCPToolResult(
                    toolUseId=tool_use_id,
                    content=[{"text": f"[認証が必要です] Google Calendar へのアクセスを許可してください: {e.auth_url}"}],
                    status="error",
                )

        return super().call_tool_sync(tool_use_id, name, arguments, read_timeout_seconds)

    async def call_tool_async(
        self,
        tool_use_id: str,
        name: str,
        arguments: dict[str, Any] | None = None,
        read_timeout_seconds: timedelta | None = None,
    ) -> Any:
        """Override to inject access_token for calendar tools."""
        from strands.tools.mcp.mcp_types import MCPToolResult

        # Check if this is a calendar tool that needs access_token
        if name.startswith("calendar___") and arguments is not None:
            try:
                token = await _get_google_token()
                arguments["access_token"] = token
            except AuthRequiredError as e:
                return MCPToolResult(
                    toolUseId=tool_use_id,
                    content=[{"text": f"[認証が必要です] Google Calendar へのアクセスを許可してください: {e.auth_url}"}],
                    status="error",
                )

        return await super().call_tool_async(tool_use_id, name, arguments, read_timeout_seconds)


# Initialize MCP client for AgentCore Gateway with auth injection
mcp_client: AuthInjectingMCPClient | None = None
if GATEWAY_ENDPOINT:
    mcp_client = AuthInjectingMCPClient(
        lambda: cognito_auth_streamablehttp_client(GATEWAY_ENDPOINT),
    )

# System prompt template for the agent
SYSTEM_PROMPT_TEMPLATE = """あなたは Mynion というSlackアシスタントです。ユーザーの質問に日本語で答えてください。

現在の日時: {current_datetime} (日本時間)

重要: calendar___ で始まるツール（calendar___get_events, calendar___create_event など）を使う際、
access_token パラメータは自動的に注入されます。ユーザーにトークンを求めないでください。
カレンダー関連の質問には、直接ツールを呼び出して回答してください。
「今日」「明日」などの相対的な日付は、上記の現在日時を基準に YYYY-MM-DD 形式に変換してください。"""


def _get_system_prompt() -> str:
    """Generate system prompt with current datetime."""
    jst = timezone(timedelta(hours=9))
    now = datetime.now(jst)
    current_datetime = now.strftime("%Y年%m月%d日 %H:%M")
    return SYSTEM_PROMPT_TEMPLATE.format(current_datetime=current_datetime)


def _create_agent() -> Agent:
    """Create a new agent with current datetime in system prompt."""
    return Agent(
        tools=[mcp_client] if mcp_client else [],
        system_prompt=_get_system_prompt(),
    )


# BedrockAgentCoreApp for handling runtime invocations
app = BedrockAgentCoreApp()


@app.entrypoint
async def agent_invocation(payload: dict[str, Any], context: Any) -> AsyncIterator[dict[str, Any]]:
    """Main entrypoint for agent invocations."""
    user_message = payload.get("prompt", "")
    if not user_message:
        yield {"error": "No prompt found in payload", "status": "error"}
        return

    # Extract user_id from payload for OAuth callback URL construction
    user_id = payload.get("user_id")
    if user_id:
        _current_user_id.set(user_id)
        logger.info(f"Set current user_id: {user_id}")

    try:
        # Create agent with current datetime in system prompt
        agent = _create_agent()

        # Let the LLM decide which tools to use
        # Auth is handled transparently by AuthInjectingMCPClient
        agent_result = agent(user_message)
        yield {"message": agent_result.message, "status": "success"}
    except Exception as e:
        yield {"error": str(e), "status": "error"}
    finally:
        # Clear user_id context after invocation
        _current_user_id.set(None)


if __name__ == "__main__":
    app.run()
