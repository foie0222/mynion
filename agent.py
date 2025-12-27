"""Strands Agent with Google Calendar MCP Tools via AgentCore Gateway.

This agent integrates with AgentCore Gateway to provide calendar operations.
The Gateway uses authorizer_type=NONE, so no OAuth is needed for Gateway access.
OAuth for Google Calendar API is handled at the tool level via access_token parameter.
"""

import logging
import os
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI, HTTPException
from mcp.client.streamable_http import streamablehttp_client
from pydantic import BaseModel
from strands import Agent
from strands.tools.mcp import MCPClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Strands Agent Server", version="1.0.0")

# AgentCore Gateway URL for Calendar tools
CALENDAR_GATEWAY_URL = os.environ.get(
    "CALENDAR_GATEWAY_URL",
    "https://mynion-calendar-gateway-kujxv7yjpd.gateway.bedrock-agentcore.ap-northeast-1.amazonaws.com/mcp",
)


def create_calendar_mcp_client() -> MCPClient | None:
    """Create MCP client for Calendar Gateway.

    The Gateway uses authorizer_type=NONE, so no authentication is required
    for connecting to the Gateway itself.

    Returns:
        MCPClient connected to Calendar Gateway, or None if initialization fails.
    """
    try:
        logger.info(f"Connecting to Calendar Gateway: {CALENDAR_GATEWAY_URL}")

        # Gateway has authorizer_type=NONE, so we connect without auth headers
        client = MCPClient(lambda: streamablehttp_client(CALENDAR_GATEWAY_URL))
        client.start()

        logger.info("Calendar MCP client initialized successfully")
        return client
    except Exception as e:
        logger.error(f"Failed to initialize Calendar MCP client: {e}", exc_info=True)
        return None


def initialize_agent() -> Agent:
    """Initialize the Strands agent with calendar tools if available."""
    calendar_tools: list[Any] = []

    try:
        calendar_mcp_client = create_calendar_mcp_client()
        if calendar_mcp_client:
            calendar_tools = calendar_mcp_client.list_tools_sync()
            logger.info(f"Loaded {len(calendar_tools)} calendar tools from Gateway")
            for tool in calendar_tools:
                # MCPAgentTool uses tool_name and tool_spec attributes
                tool_desc = getattr(tool, "tool_spec", {}).get("description", "")[:50]
                logger.info(f"  - {tool.tool_name}: {tool_desc}...")
    except Exception as e:
        logger.error(f"Calendar tools not available: {e}", exc_info=True)

    if calendar_tools:
        logger.info("Initializing agent with calendar tools")
        return Agent(tools=calendar_tools)
    else:
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
