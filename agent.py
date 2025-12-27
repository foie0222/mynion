"""Strands Agent with Google Calendar MCP Tools via AgentCore Gateway.

This agent integrates with AgentCore Gateway to provide calendar operations.
OAuth tokens are obtained via AgentCore Identity and passed to Gateway tools.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from bedrock_agentcore.identity.auth import requires_access_token
from fastapi import FastAPI, HTTPException
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel
from strands import Agent
from strands.tools.mcp import MCPClient

logger = logging.getLogger(__name__)

app = FastAPI(title="Strands Agent Server", version="1.0.0")

# AgentCore Gateway URL for Calendar tools
CALENDAR_GATEWAY_URL = os.environ.get(
    "CALENDAR_GATEWAY_URL",
    "https://mynion-calendar-gateway-kujxv7yjpd.gateway.bedrock-agentcore.ap-northeast-1.amazonaws.com/mcp",
)

# OAuth Credential Provider name for Google Calendar
GOOGLE_OAUTH_PROVIDER = os.environ.get(
    "GOOGLE_OAUTH_PROVIDER", "google-calendar-provider"
)


def create_calendar_mcp_client() -> MCPClient | None:
    """Create MCP client for Calendar Gateway with OAuth authentication.

    Returns:
        MCPClient connected to Calendar Gateway, or None if initialization fails.
    """
    try:
        # Get OAuth token for Gateway authentication (M2M for Gateway access)
        captured_token = None

        @requires_access_token(
            provider_name=os.environ.get("M2M_IDENTITY_NAME", ""),
            scopes=[],
            auth_flow="M2M",
        )
        def get_gateway_token(access_token: str = "") -> str:
            nonlocal captured_token
            captured_token = access_token
            return access_token

        get_gateway_token()

        if not captured_token:
            logger.warning("Failed to get M2M token for Gateway, calendar tools disabled")
            return None

        client = MCPClient(
            lambda: streamablehttp_client(
                CALENDAR_GATEWAY_URL,
                headers={"Authorization": f"Bearer {captured_token}"},
            )
        )
        client.start()
        logger.info("Calendar MCP client initialized successfully")
        return client
    except Exception as e:
        logger.warning(f"Failed to initialize Calendar MCP client: {e}")
        return None


# Initialize calendar MCP client (will be None if running outside AgentCore Runtime)
calendar_mcp_client: MCPClient | None = None

# Get calendar tools from Gateway (if available)
calendar_tools: list[Any] = []

try:
    calendar_mcp_client = create_calendar_mcp_client()
    if calendar_mcp_client:
        calendar_tools = calendar_mcp_client.list_tools_sync()
        logger.info(f"Loaded {len(calendar_tools)} calendar tools from Gateway")
except Exception as e:
    logger.warning(f"Calendar tools not available: {e}")

# Initialize Strands agent with calendar tools
strands_agent = Agent(tools=calendar_tools if calendar_tools else None)


class InvocationRequest(BaseModel):
    input: dict[str, Any]


class InvocationResponse(BaseModel):
    output: dict[str, Any]


@app.post("/invocations", response_model=InvocationResponse)
async def invoke_agent(request: InvocationRequest):
    try:
        user_message = request.input.get("prompt", "")
        if not user_message:
            raise HTTPException(
                status_code=400,
                detail="No prompt found in input. Please provide a 'prompt' key in the input.",
            )

        result = strands_agent(user_message)
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
