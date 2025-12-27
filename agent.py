"""Strands Agent with Google Calendar MCP Tools via AgentCore Gateway.

This agent integrates with AgentCore Gateway to provide calendar operations.
OAuth authentication is handled via AgentCore Identity with USER_FEDERATION flow.
"""

import asyncio
import logging
import os
import uuid
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
# Set CALENDAR_GATEWAY_URL environment variable to enable calendar tools.
# The Gateway URL is exported from the AgentCoreGatewayStack CDK stack.
# If not set, the agent will start without calendar tools.
CALENDAR_GATEWAY_URL = os.environ.get("CALENDAR_GATEWAY_URL", "")

# OAuth Credential Provider name (created via AgentCore Identity)
OAUTH_PROVIDER_NAME = os.environ.get("OAUTH_PROVIDER_NAME", "GoogleCalendarProvider")

# Google Calendar API scopes
CALENDAR_SCOPES = [
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

# Store for pending OAuth sessions (user_id -> auth_url)
# In production, this should be stored in DynamoDB or similar
pending_auth_sessions: dict[str, str] = {}

# Global MCP client
_mcp_client: MCPClient | None = None


def get_mcp_client() -> MCPClient | None:
    """Get or create MCP client for Calendar Gateway."""
    global _mcp_client
    if _mcp_client is not None:
        return _mcp_client

    if not CALENDAR_GATEWAY_URL:
        logger.info("CALENDAR_GATEWAY_URL not set, skipping calendar tools")
        return None

    try:
        logger.info(f"Connecting to Calendar Gateway: {CALENDAR_GATEWAY_URL}")
        _mcp_client = MCPClient(lambda: streamablehttp_client(CALENDAR_GATEWAY_URL))
        _mcp_client.start()
        logger.info("Calendar MCP client initialized successfully")
        return _mcp_client
    except Exception as e:
        logger.error(f"Failed to initialize Calendar MCP client: {e}", exc_info=True)
        return None


async def get_oauth_token(user_id: str) -> tuple[str | None, str | None]:
    """Get OAuth token for user, or return auth URL if not authenticated.

    Args:
        user_id: User identifier for OAuth session

    Returns:
        Tuple of (access_token, auth_url). One will be None.
        - If authenticated: (token, None)
        - If not authenticated: (None, auth_url)
    """
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
                provider_name=OAUTH_PROVIDER_NAME,
                scopes=CALENDAR_SCOPES,
                agent_identity_token=workload_token,
                auth_flow="USER_FEDERATION",
                on_auth_url=capture_auth_url,
            )
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


def get_oauth_token_sync(user_id: str) -> tuple[str | None, str | None]:
    """Synchronous wrapper for get_oauth_token."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures

            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, get_oauth_token(user_id))
                return future.result()
        else:
            return asyncio.run(get_oauth_token(user_id))
    except Exception as e:
        logger.error(f"Error in get_oauth_token_sync: {e}", exc_info=True)
        return None, None


# Calendar tools with OAuth integration
@tool
def list_calendar_events(
    user_id: str,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 10,
) -> dict[str, Any]:
    """List calendar events within a time range.

    Args:
        user_id: User identifier for OAuth authentication
        time_min: Start time in ISO format (default: now)
        time_max: End time in ISO format (default: 7 days from now)
        max_results: Maximum number of events to return (default: 10)

    Returns:
        Dictionary with events list or authentication URL if not authenticated
    """
    token, auth_url = get_oauth_token_sync(user_id)

    if auth_url:
        return {
            "requires_auth": True,
            "auth_url": auth_url,
            "message": "Google Calendar認証が必要です。以下のURLをクリックして認証してください。",
        }

    if not token:
        return {"error": "OAuth認証に失敗しました。"}

    # Call MCP tool with token
    client = get_mcp_client()
    if not client:
        return {"error": "Calendar Gateway is not available"}

    try:
        result = client.call_tool_sync(
            tool_use_id=str(uuid.uuid4()),
            name="calendar-tools___list_events",
            arguments={
                "access_token": token,
                "time_min": time_min,
                "time_max": time_max,
                "max_results": max_results,
            },
        )
        # MCPToolResult is a dict subclass with structuredContent
        if "structuredContent" in result:
            return result["structuredContent"]
        return dict(result)
    except Exception as e:
        logger.error(f"Error calling list_events: {e}", exc_info=True)
        return {"error": str(e)}


@tool
def create_calendar_event(
    user_id: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
    timezone: str = "Asia/Tokyo",
) -> dict[str, Any]:
    """Create a new calendar event.

    Args:
        user_id: User identifier for OAuth authentication
        summary: Event title
        start_time: Start time in ISO format (e.g., 2024-12-01T10:00:00+09:00)
        end_time: End time in ISO format
        description: Event description (optional)
        location: Event location (optional)
        timezone: Timezone for the event (default: Asia/Tokyo)

    Returns:
        Dictionary with created event details or authentication URL
    """
    token, auth_url = get_oauth_token_sync(user_id)

    if auth_url:
        return {
            "requires_auth": True,
            "auth_url": auth_url,
            "message": "Google Calendar認証が必要です。以下のURLをクリックして認証してください。",
        }

    if not token:
        return {"error": "OAuth認証に失敗しました。"}

    client = get_mcp_client()
    if not client:
        return {"error": "Calendar Gateway is not available"}

    try:
        result = client.call_tool_sync(
            tool_use_id=str(uuid.uuid4()),
            name="calendar-tools___create_event",
            arguments={
                "access_token": token,
                "summary": summary,
                "start_time": start_time,
                "end_time": end_time,
                "description": description,
                "location": location,
                "timezone": timezone,
            },
        )
        if "structuredContent" in result:
            return result["structuredContent"]
        return dict(result)
    except Exception as e:
        logger.error(f"Error calling create_event: {e}", exc_info=True)
        return {"error": str(e)}


@tool
def update_calendar_event(
    user_id: str,
    event_id: str,
    summary: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    description: str | None = None,
    location: str | None = None,
    timezone: str | None = None,
) -> dict[str, Any]:
    """Update an existing calendar event.

    Args:
        user_id: User identifier for OAuth authentication
        event_id: ID of the event to update
        summary: New event title (optional)
        start_time: New start time in ISO format (optional)
        end_time: New end time in ISO format (optional)
        description: New event description (optional)
        location: New event location (optional)
        timezone: Timezone for the event (optional)

    Returns:
        Dictionary with updated event details or authentication URL
    """
    token, auth_url = get_oauth_token_sync(user_id)

    if auth_url:
        return {
            "requires_auth": True,
            "auth_url": auth_url,
            "message": "Google Calendar認証が必要です。以下のURLをクリックして認証してください。",
        }

    if not token:
        return {"error": "OAuth認証に失敗しました。"}

    client = get_mcp_client()
    if not client:
        return {"error": "Calendar Gateway is not available"}

    try:
        params: dict[str, Any] = {
            "access_token": token,
            "event_id": event_id,
        }
        if summary is not None:
            params["summary"] = summary
        if start_time is not None:
            params["start_time"] = start_time
        if end_time is not None:
            params["end_time"] = end_time
        if description is not None:
            params["description"] = description
        if location is not None:
            params["location"] = location
        if timezone is not None:
            params["timezone"] = timezone

        result = client.call_tool_sync(
            tool_use_id=str(uuid.uuid4()),
            name="calendar-tools___update_event",
            arguments=params,
        )
        if "structuredContent" in result:
            return result["structuredContent"]
        return dict(result)
    except Exception as e:
        logger.error(f"Error calling update_event: {e}", exc_info=True)
        return {"error": str(e)}


@tool
def delete_calendar_event(user_id: str, event_id: str) -> dict[str, Any]:
    """Delete a calendar event.

    Args:
        user_id: User identifier for OAuth authentication
        event_id: ID of the event to delete

    Returns:
        Dictionary with deletion confirmation or authentication URL
    """
    token, auth_url = get_oauth_token_sync(user_id)

    if auth_url:
        return {
            "requires_auth": True,
            "auth_url": auth_url,
            "message": "Google Calendar認証が必要です。以下のURLをクリックして認証してください。",
        }

    if not token:
        return {"error": "OAuth認証に失敗しました。"}

    client = get_mcp_client()
    if not client:
        return {"error": "Calendar Gateway is not available"}

    try:
        result = client.call_tool_sync(
            tool_use_id=str(uuid.uuid4()),
            name="calendar-tools___delete_event",
            arguments={"access_token": token, "event_id": event_id},
        )
        if "structuredContent" in result:
            return result["structuredContent"]
        return dict(result)
    except Exception as e:
        logger.error(f"Error calling delete_event: {e}", exc_info=True)
        return {"error": str(e)}


def initialize_agent() -> Agent:
    """Initialize the Strands agent with calendar tools."""
    calendar_tools = [
        list_calendar_events,
        create_calendar_event,
        update_calendar_event,
        delete_calendar_event,
    ]

    # Check if MCP client is available
    client = get_mcp_client()
    if client:
        logger.info("Initializing agent with calendar tools (OAuth-enabled)")
    else:
        logger.warning("Initializing agent without calendar tools")
        calendar_tools = []

    if calendar_tools:
        return Agent(tools=calendar_tools)
    else:
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

        # Add user_id context to the message for tools
        context_message = f"[user_id: {user_id}] {user_message}"

        result = strands_agent(context_message)
        response = {"message": result.message, "timestamp": datetime.now(UTC).isoformat()}

        return InvocationResponse(output=response)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent processing failed: {str(e)}") from e


@app.get("/ping")
async def ping():
    return {"status": "healthy"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
