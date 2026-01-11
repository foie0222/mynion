"""
Mynion Agent for AgentCore Runtime.

This agent integrates with:
- AgentCore Gateway for Calendar MCP tools (CUSTOM_JWT auth via Cognito)
- AgentCore Identity for Google Calendar OAuth authentication
"""

import json
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any, cast

import boto3
import httpx
from bedrock_agentcore.identity.auth import requires_access_token
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mcp.client.streamable_http import streamablehttp_client
from strands import Agent
from strands.tools.mcp import MCPClient

# Gateway configuration from environment variables
GATEWAY_ENDPOINT = os.getenv(
    "AGENTCORE_GATEWAY_ENDPOINT",
    "https://mynion-calendar-gateway-zqgb38xjtt.gateway.bedrock-agentcore.ap-northeast-1.amazonaws.com/mcp",
)
AWS_REGION = os.getenv("AWS_REGION", "ap-northeast-1")
COGNITO_SECRET_NAME = os.getenv("COGNITO_SECRET_NAME", "mynion-gateway-cognito")
GOOGLE_CREDENTIAL_PROVIDER = os.getenv("GOOGLE_CREDENTIAL_PROVIDER", "GoogleCalendarProvider")

# Cache for tokens
_cognito_token_cache: dict[str, Any] = {}
_google_token_cache: dict[str, str | None] = {"token": None, "auth_url": None}


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


def _store_auth_url(url: str) -> None:
    """Store the auth URL for later retrieval."""
    _google_token_cache["auth_url"] = url


async def _get_google_token() -> str | None:
    """Try to get Google OAuth token, returns None if auth required."""
    # Check cache first
    if _google_token_cache.get("token"):
        return _google_token_cache["token"]

    try:

        @requires_access_token(
            provider_name=GOOGLE_CREDENTIAL_PROVIDER,
            scopes=["https://www.googleapis.com/auth/calendar"],
            auth_flow="USER_FEDERATION",
            on_auth_url=_store_auth_url,
            force_authentication=False,
        )
        async def fetch_token(*, access_token: str) -> str:
            return access_token

        token = await fetch_token()
        _google_token_cache["token"] = token
        _google_token_cache["auth_url"] = None
        return cast(str, token)
    except Exception:
        # Auth required - URL should be stored via on_auth_url callback
        return None


def get_google_token_sync() -> str | None:
    """Synchronously get Google OAuth token."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, _get_google_token())
            return future.result()
    else:
        return asyncio.run(_get_google_token())


class AuthInjectingMCPClient(MCPClient):
    """MCPClient that automatically injects Google OAuth token into calendar tool calls."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._auth_error: str | None = None

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
            # Try to get Google OAuth token
            token = get_google_token_sync()

            if token is None:
                # Auth required - return auth URL as error
                auth_url = _google_token_cache.get("auth_url")
                if auth_url:
                    self._auth_error = f"[認証が必要です] Google Calendar へのアクセスを許可してください: {auth_url}"
                else:
                    self._auth_error = (
                        "Google Calendar の認証が必要ですが、認証URLを取得できませんでした。"
                    )

                # Return a result that indicates auth is needed
                return MCPToolResult(
                    toolUseId=tool_use_id,
                    content=[{"text": self._auth_error}],
                    status="error",
                )

            # Inject token into arguments
            arguments["access_token"] = token

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
            # Try to get Google OAuth token
            token = await _get_google_token()

            if token is None:
                # Auth required - return auth URL as error
                auth_url = _google_token_cache.get("auth_url")
                if auth_url:
                    self._auth_error = f"[認証が必要です] Google Calendar へのアクセスを許可してください: {auth_url}"
                else:
                    self._auth_error = (
                        "Google Calendar の認証が必要ですが、認証URLを取得できませんでした。"
                    )

                return MCPToolResult(
                    toolUseId=tool_use_id,
                    content=[{"text": self._auth_error}],
                    status="error",
                )

            # Inject token into arguments
            arguments["access_token"] = token

        return await super().call_tool_async(tool_use_id, name, arguments, read_timeout_seconds)


# Initialize MCP client for AgentCore Gateway with auth injection
mcp_client: AuthInjectingMCPClient | None = None
if GATEWAY_ENDPOINT:
    mcp_client = AuthInjectingMCPClient(
        lambda: cognito_auth_streamablehttp_client(GATEWAY_ENDPOINT),
    )

# System prompt for the agent
SYSTEM_PROMPT = """あなたは Mynion というSlackアシスタントです。ユーザーの質問に日本語で答えてください。

重要: calendar___ で始まるツール（calendar___get_events, calendar___create_event など）を使う際、
access_token パラメータは自動的に注入されます。ユーザーにトークンを求めないでください。
カレンダー関連の質問には、直接ツールを呼び出して回答してください。"""

# Initialize Strands agent with MCP tools from Gateway
# Tools are defined on Gateway side, agent.py just handles auth injection
strands_agent = Agent(
    tools=[mcp_client] if mcp_client else [],
    system_prompt=SYSTEM_PROMPT,
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

    try:
        # Let the LLM decide which tools to use
        # Auth is handled transparently by AuthInjectingMCPClient
        agent_result = strands_agent(user_message)
        yield {"message": agent_result.message, "status": "success"}
    except Exception as e:
        yield {"error": str(e), "status": "error"}


if __name__ == "__main__":
    app.run()
