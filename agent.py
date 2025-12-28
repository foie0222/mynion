"""Strands Agent with Google Calendar MCP Tools via AgentCore Gateway.

This agent integrates with AgentCore Gateway to provide calendar operations.
OAuth authentication is handled via AgentCore Identity with USER_FEDERATION flow.

Architecture (Strands王道パターン):
1. Tool Discovery: MCPClient fetches tool definitions from AgentCore Gateway
2. Tool Execution: Wrapper layer handles OAuth token injection
3. Auth Flow: Returns AUTH_REQUIRED (state transition) when user not authenticated

The agent does NOT define tools with @tool decorator directly. Instead:
- Tools are discovered dynamically from the MCP Gateway
- A wrapper layer intercepts tool calls to handle OAuth
- If authentication is required, AUTH_REQUIRED is returned as a result (not exception)
- Slack integration shows auth button, user clicks, callback stores token
- Tool call is retried after successful authentication

Reference:
- https://strandsagents.com/latest/user-guide/concepts/tools/mcp-tools/
- https://dev.classmethod.jp/articles/amazon-bedrock-agentcore-gateway-lambda-tool/
"""

import asyncio
import contextlib
import contextvars
import json
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel
from strands import Agent, tool
from strands.tools.mcp import MCPClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Strands Agent Server", version="1.0.0")

# AgentCore Gateway URL for Calendar tools
CALENDAR_GATEWAY_URL = os.environ.get("CALENDAR_GATEWAY_URL", "")

# OAuth Credential Provider name (created via AgentCore Identity)
OAUTH_PROVIDER_NAME = os.environ.get("OAUTH_PROVIDER_NAME", "GoogleCalendarProvider")

# Google Calendar API scopes
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

# Context variable for current user_id during request processing
# This allows tools to access user_id without it being a tool parameter
current_user_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_user_id", default="default"
)

# Store for pending OAuth sessions (user_id -> auth_url)
# In production, this should be stored in DynamoDB or similar
pending_auth_sessions: dict[str, str] = {}


@dataclass
class AuthRequired:
    """Response indicating authentication is required.

    This is returned as a tool RESULT, not raised as an exception.
    The Slack integration should display this as a button for the user.
    """

    auth_url: str
    state: str
    tool_name: str
    scopes: list[str]
    message: str = "Google Calendar認証が必要です。以下のリンクをクリックして認証してください。"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON response."""
        return {
            "auth_required": True,
            "auth_url": self.auth_url,
            "state": self.state,
            "tool_name": self.tool_name,
            "scopes": self.scopes,
            "message": self.message,
        }


class OAuthTokenManager:
    """Manages OAuth tokens for users via AgentCore Identity."""

    def __init__(self, oauth_provider: str, scopes: list[str]):
        self.oauth_provider = oauth_provider
        self.scopes = scopes
        # Cache for tokens (user_id -> token)
        # In production, use DynamoDB or similar
        self._token_cache: dict[str, str] = {}

    async def get_token(self, user_id: str) -> tuple[str | None, str | None]:
        """Get OAuth token for user, or return auth URL if not authenticated.

        Args:
            user_id: User identifier for OAuth session

        Returns:
            Tuple of (access_token, auth_url). One will be None.
            - If authenticated: (token, None)
            - If not authenticated: (None, auth_url)
        """
        # Check cache first
        if user_id in self._token_cache:
            return self._token_cache[user_id], None

        try:
            from bedrock_agentcore.services.identity import IdentityClient

            region = os.environ.get("AWS_REGION", "ap-northeast-1")
            client = IdentityClient(region)

            # Get workload identity token
            workload_token_resp = client.get_workload_access_token(
                workload_name=os.environ.get("WORKLOAD_NAME", "default"),
                user_id=user_id,
            )
            workload_token = workload_token_resp.get("token")

            if not workload_token:
                logger.error("Failed to get workload identity token")
                return None, None

            # Try to get OAuth token
            auth_url = None

            async def capture_auth_url(url: str) -> None:
                nonlocal auth_url
                auth_url = url
                pending_auth_sessions[user_id] = url

            try:
                token = await client.get_token(
                    provider_name=self.oauth_provider,
                    scopes=self.scopes,
                    agent_identity_token=workload_token,
                    auth_flow="USER_FEDERATION",
                    on_auth_url=capture_auth_url,
                )
                # Cache the token
                self._token_cache[user_id] = token
                return token, None
            except Exception:
                if auth_url:
                    logger.info(f"OAuth authentication required for user {user_id}")
                    return None, auth_url
                raise

        except ImportError:
            logger.warning("bedrock-agentcore SDK not available, OAuth disabled")
            return None, None
        except Exception as e:
            logger.error(f"Error getting OAuth token: {e}", exc_info=True)
            return None, None

    def get_token_sync(self, user_id: str) -> tuple[str | None, str | None]:
        """Synchronous wrapper for get_token."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.get_token(user_id))
                    return future.result()
            else:
                return asyncio.run(self.get_token(user_id))
        except Exception as e:
            logger.error(f"Error in get_token_sync: {e}", exc_info=True)
            return None, None

    def invalidate_token(self, user_id: str) -> None:
        """Invalidate cached token for user (e.g., on 401 error)."""
        self._token_cache.pop(user_id, None)


class MCPToolWithOAuth:
    """MCP Tool wrapper that handles OAuth authentication.

    This class:
    1. Discovers tools from MCPClient (AgentCore Gateway)
    2. Creates Strands-compatible tool functions with @tool decorator
    3. Injects OAuth token into tool calls
    4. Returns AUTH_REQUIRED when user needs to authenticate
    """

    def __init__(
        self,
        mcp_client: MCPClient,
        token_manager: OAuthTokenManager,
    ):
        self.mcp_client = mcp_client
        self.token_manager = token_manager
        self._tools_cache: list[Any] | None = None

    def list_mcp_tools(self) -> list[Any]:
        """Get tool definitions from the MCP Gateway."""
        if self._tools_cache is not None:
            return self._tools_cache

        try:
            self._tools_cache = self.mcp_client.list_tools_sync()
            for t in self._tools_cache:
                logger.info(f"Discovered MCP tool: {t.tool_name}")
            return self._tools_cache
        except Exception as e:
            logger.error(f"Failed to list MCP tools: {e}", exc_info=True)
            return []

    def call_tool(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool with OAuth token injection.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments (excluding access_token)

        Returns:
            Tool result or AUTH_REQUIRED response
        """
        # Get user_id from context
        user_id = current_user_id.get()

        # Step 1: Get OAuth token
        token, auth_url = self.token_manager.get_token_sync(user_id)

        # Step 2: If auth required, return AUTH_REQUIRED as result (not exception)
        if auth_url:
            state = str(uuid.uuid4())
            return AuthRequired(
                auth_url=auth_url,
                state=state,
                tool_name=tool_name,
                scopes=self.token_manager.scopes,
            ).to_dict()

        if not token:
            return {"error": "OAuth認証に失敗しました。管理者にお問い合わせください。"}

        # Step 3: Execute tool with token
        try:
            # Inject access_token into arguments
            args_with_token = {**arguments, "access_token": token}

            result = self.mcp_client.call_tool_sync(
                tool_use_id=str(uuid.uuid4()),
                name=tool_name,
                arguments=args_with_token,
            )

            # Parse result - MCPToolResult can have various formats
            result_dict: dict[str, Any]
            if hasattr(result, "structuredContent"):
                structured = getattr(result, "structuredContent", None)
                if structured:
                    result_dict = dict(structured)
                    return result_dict
            if hasattr(result, "content"):
                content = getattr(result, "content", None)
                if content:
                    for content_item in content:
                        if hasattr(content_item, "text"):
                            text = getattr(content_item, "text", "")
                            try:
                                result_dict = json.loads(text)
                                return result_dict
                            except json.JSONDecodeError:
                                return {"result": text}
            # Fallback
            if hasattr(result, "__iter__"):
                result_dict = dict(result)
                return result_dict
            return {"result": str(result)}

        except Exception as e:
            error_str = str(e).lower()
            # Step 4: Handle 401/unauthorized - invalidate token and return AUTH_REQUIRED
            if "401" in error_str or "unauthorized" in error_str or "authentication" in error_str:
                self.token_manager.invalidate_token(user_id)
                _, auth_url = self.token_manager.get_token_sync(user_id)
                if auth_url:
                    state = str(uuid.uuid4())
                    return AuthRequired(
                        auth_url=auth_url,
                        state=state,
                        tool_name=tool_name,
                        scopes=self.token_manager.scopes,
                        message="認証トークンが期限切れです。再度認証してください。",
                    ).to_dict()

            logger.error(f"Error executing tool {tool_name}: {e}", exc_info=True)
            return {"error": str(e)}


# Global instances
_mcp_client: MCPClient | None = None
_token_manager: OAuthTokenManager | None = None
_mcp_tool_wrapper: MCPToolWithOAuth | None = None


def get_mcp_tool_wrapper() -> MCPToolWithOAuth | None:
    """Get or create MCP tool wrapper with OAuth handling."""
    global _mcp_client, _token_manager, _mcp_tool_wrapper

    if _mcp_tool_wrapper is not None:
        return _mcp_tool_wrapper

    if not CALENDAR_GATEWAY_URL:
        logger.info("CALENDAR_GATEWAY_URL not set, skipping calendar tools")
        return None

    try:
        logger.info(f"Connecting to Calendar Gateway: {CALENDAR_GATEWAY_URL}")
        _mcp_client = MCPClient(lambda: streamablehttp_client(CALENDAR_GATEWAY_URL))
        _mcp_client.start()

        _token_manager = OAuthTokenManager(
            oauth_provider=OAUTH_PROVIDER_NAME,
            scopes=CALENDAR_SCOPES,
        )

        _mcp_tool_wrapper = MCPToolWithOAuth(
            mcp_client=_mcp_client,
            token_manager=_token_manager,
        )

        # Log discovered tools
        tools = _mcp_tool_wrapper.list_mcp_tools()
        logger.info(f"Discovered {len(tools)} tools from Gateway")

        return _mcp_tool_wrapper
    except Exception as e:
        logger.error(f"Failed to initialize MCP tool wrapper: {e}", exc_info=True)
        return None


def create_strands_tools(wrapper: MCPToolWithOAuth) -> list[Any]:
    """Create Strands-compatible tool functions from MCP tools.

    Each MCP tool is wrapped with a function decorated with @tool
    that handles OAuth and calls the MCP tool via the wrapper.
    """
    mcp_tools = wrapper.list_mcp_tools()
    strands_tools: list[Any] = []

    for mcp_tool in mcp_tools:
        tool_name = mcp_tool.tool_name
        tool_desc = mcp_tool.tool_spec.get("description", f"Execute {tool_name}")

        # Create wrapper function for this tool
        # Note: We use a closure to capture tool_name
        def make_tool_func(name: str, desc: str) -> Any:
            @tool
            def tool_func(**kwargs: Any) -> dict[str, Any]:
                """Dynamic tool function that wraps MCP tool call with OAuth."""
                return wrapper.call_tool(name, kwargs)

            # Update function metadata using object.__setattr__ to bypass type restrictions
            # The @tool decorator returns a DecoratedFunctionTool which wraps the function
            with contextlib.suppress(AttributeError):
                tool_func.name = name.replace("-", "_").replace("___", "_")  # type: ignore[attr-defined]
            return tool_func

        strands_tools.append(make_tool_func(tool_name, tool_desc))
        logger.info(f"Created Strands tool: {tool_name}")

    return strands_tools


def initialize_agent() -> Agent:
    """Initialize the Strands agent with dynamically discovered calendar tools.

    Tools are fetched from the AgentCore Gateway via MCPClient.
    Each tool is wrapped with OAuth handling.
    """
    wrapper = get_mcp_tool_wrapper()

    if wrapper:
        tools = create_strands_tools(wrapper)
        if tools:
            logger.info(f"Initializing agent with {len(tools)} calendar tools")
            return Agent(tools=tools)

    logger.warning("Initializing agent without calendar tools")
    return Agent()


# Initialize Strands agent
strands_agent = initialize_agent()


class InvocationRequest(BaseModel):
    input: dict[str, Any]


class InvocationResponse(BaseModel):
    output: dict[str, Any]


@app.post("/invocations", response_model=InvocationResponse)
async def invoke_agent(request: InvocationRequest):
    try:
        user_message = request.input.get("prompt", "")
        user_id = request.input.get("user_id", "default")

        if not user_message:
            raise HTTPException(
                status_code=400,
                detail="No prompt found in input. Please provide a 'prompt' key in the input.",
            )

        # Set user_id in context for tools to access
        token = current_user_id.set(user_id)
        try:
            result = strands_agent(user_message)
            response = {"message": result.message, "timestamp": datetime.now(UTC).isoformat()}
            return InvocationResponse(output=response)
        finally:
            current_user_id.reset(token)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent processing failed: {str(e)}") from e


@app.get("/ping")
async def ping():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
