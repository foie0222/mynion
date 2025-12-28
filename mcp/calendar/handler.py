"""Lambda handler for Google Calendar MCP tools.

This Lambda is invoked by AgentCore Gateway and provides calendar operations.
The tool name is passed via context.client_context.custom['bedrockAgentCoreToolName'].

Reference: https://dev.classmethod.jp/articles/amazon-bedrock-agentcore-gateway-lambda-tool/
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Tool name delimiter used by AgentCore Gateway (format: target_name__tool_name)
# Reference: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/gateway-tool-naming.html
TOOL_NAME_DELIMITER = "__"


def success_response(body: dict[str, Any]) -> dict[str, Any]:
    """Create a successful response in the format expected by AgentCore Gateway."""
    return {"statusCode": 200, "body": json.dumps(body)}


def error_response(
    status_code: int, error: str, message: str, **kwargs: Any
) -> dict[str, Any]:
    """Create an error response in the format expected by AgentCore Gateway."""
    body = {"error": error, "message": message, **kwargs}
    return {"statusCode": status_code, "body": json.dumps(body)}


def get_calendar_service(access_token: str) -> Any:
    """Create Google Calendar service with the provided access token."""
    credentials = Credentials(token=access_token)
    return build("calendar", "v3", credentials=credentials)


def list_events(
    access_token: str,
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 10,
) -> dict[str, Any]:
    """List calendar events within the specified time range.

    Args:
        access_token: Google OAuth access token
        time_min: Start time in ISO format (default: now)
        time_max: End time in ISO format (default: 7 days from now)
        max_results: Maximum number of events to return

    Returns:
        Dictionary with events list
    """
    service = get_calendar_service(access_token)

    # Default time range: now to 7 days from now
    if not time_min:
        time_min = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    if not time_max:
        time_max = (datetime.now(UTC) + timedelta(days=7)).isoformat().replace("+00:00", "Z")

    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
    formatted_events = []

    for event in events:
        start = event["start"].get("dateTime", event["start"].get("date"))
        end = event["end"].get("dateTime", event["end"].get("date"))
        formatted_events.append(
            {
                "id": event["id"],
                "summary": event.get("summary", "(No title)"),
                "start": start,
                "end": end,
                "location": event.get("location"),
                "description": event.get("description"),
            }
        )

    return {"events": formatted_events, "count": len(formatted_events)}


def create_event(
    access_token: str,
    summary: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
    timezone: str = "Asia/Tokyo",
) -> dict[str, Any]:
    """Create a new calendar event.

    Args:
        access_token: Google OAuth access token
        summary: Event title
        start_time: Start time in ISO format
        end_time: End time in ISO format
        description: Event description (optional)
        location: Event location (optional)
        timezone: Timezone for the event (default: Asia/Tokyo)

    Returns:
        Dictionary with created event details
    """
    service = get_calendar_service(access_token)

    event_body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": timezone},
        "end": {"dateTime": end_time, "timeZone": timezone},
    }

    if description:
        event_body["description"] = description
    if location:
        event_body["location"] = location

    event = service.events().insert(calendarId="primary", body=event_body).execute()

    return {
        "id": event["id"],
        "summary": event.get("summary"),
        "start": event["start"].get("dateTime"),
        "end": event["end"].get("dateTime"),
        "htmlLink": event.get("htmlLink"),
        "message": f"Event '{summary}' created successfully",
    }


def update_event(
    access_token: str,
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
        access_token: Google OAuth access token
        event_id: ID of the event to update
        summary: New event title (optional)
        start_time: New start time in ISO format (optional)
        end_time: New end time in ISO format (optional)
        description: New event description (optional)
        location: New event location (optional)
        timezone: Timezone for the event (optional, preserves original if not provided)

    Returns:
        Dictionary with updated event details
    """
    service = get_calendar_service(access_token)

    # Get existing event
    event = service.events().get(calendarId="primary", eventId=event_id).execute()

    # Update fields if provided
    if summary is not None:
        event["summary"] = summary
    if description is not None:
        event["description"] = description
    if location is not None:
        event["location"] = location
    if start_time:
        # Use provided timezone, or preserve original, or default to Asia/Tokyo
        tz = timezone or event.get("start", {}).get("timeZone", "Asia/Tokyo")
        event["start"] = {"dateTime": start_time, "timeZone": tz}
    if end_time:
        tz = timezone or event.get("end", {}).get("timeZone", "Asia/Tokyo")
        event["end"] = {"dateTime": end_time, "timeZone": tz}

    updated_event = (
        service.events().update(calendarId="primary", eventId=event_id, body=event).execute()
    )

    return {
        "id": updated_event["id"],
        "summary": updated_event.get("summary"),
        "start": updated_event["start"].get("dateTime"),
        "end": updated_event["end"].get("dateTime"),
        "htmlLink": updated_event.get("htmlLink"),
        "message": f"Event '{updated_event.get('summary')}' updated successfully",
    }


def delete_event(access_token: str, event_id: str) -> dict[str, Any]:
    """Delete a calendar event.

    Args:
        access_token: Google OAuth access token
        event_id: ID of the event to delete

    Returns:
        Dictionary with deletion confirmation
    """
    service = get_calendar_service(access_token)

    # Get event details before deletion for confirmation message
    event = service.events().get(calendarId="primary", eventId=event_id).execute()
    event_summary = event.get("summary", "(No title)")

    service.events().delete(calendarId="primary", eventId=event_id).execute()

    return {
        "id": event_id,
        "message": f"Event '{event_summary}' deleted successfully",
    }


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for AgentCore Gateway MCP tool invocations.

    The tool name is retrieved from context.client_context.custom['bedrockAgentCoreToolName'].
    Format: "target_name___tool_name" (e.g., "calendar-tools___list_events")

    Args:
        event: Input parameters from the tool invocation
        context: Lambda context with AgentCore metadata

    Returns:
        Response with statusCode and body
    """
    # Get tool name from context.client_context.custom['bedrockAgentCoreToolName']
    tool_name = None
    try:
        if hasattr(context, "client_context") and context.client_context:
            tool_name = context.client_context.custom["bedrockAgentCoreToolName"]
            # Remove Gateway Target prefix (e.g., "calendar-tools___list_events" -> "list_events")
            if TOOL_NAME_DELIMITER in tool_name:
                tool_name = tool_name[tool_name.index(TOOL_NAME_DELIMITER) + len(TOOL_NAME_DELIMITER) :]
    except (AttributeError, KeyError, TypeError) as e:
        print(f"Error accessing client_context: {e}")
        tool_name = None

    if not tool_name:
        return error_response(
            400,
            "Missing tool name",
            "Lambda must be invoked through AgentCore Gateway with bedrockAgentCoreToolName",
        )

    # Get OAuth access token from event arguments
    # access_token is passed as a tool parameter by the Agent
    access_token = event.get("access_token")
    if not access_token:
        return error_response(
            401,
            "Missing access token",
            "OAuth authentication required. Please provide access_token parameter.",
        )

    try:
        # Route to appropriate tool handler based on tool name
        if tool_name == "list_events":
            result = list_events(
                access_token=access_token,
                time_min=event.get("time_min"),
                time_max=event.get("time_max"),
                max_results=event.get("max_results", 10),
            )
        elif tool_name == "create_event":
            result = create_event(
                access_token=access_token,
                summary=event["summary"],
                start_time=event["start_time"],
                end_time=event["end_time"],
                description=event.get("description"),
                location=event.get("location"),
                timezone=event.get("timezone", "Asia/Tokyo"),
            )
        elif tool_name == "update_event":
            result = update_event(
                access_token=access_token,
                event_id=event["event_id"],
                summary=event.get("summary"),
                start_time=event.get("start_time"),
                end_time=event.get("end_time"),
                description=event.get("description"),
                location=event.get("location"),
                timezone=event.get("timezone"),
            )
        elif tool_name == "delete_event":
            result = delete_event(
                access_token=access_token,
                event_id=event["event_id"],
            )
        else:
            return error_response(400, "Unknown tool", f"Tool '{tool_name}' is not supported")

        return success_response(result)

    except HttpError as e:
        try:
            error_content = json.loads(e.content.decode("utf-8"))
            error_message = error_content.get("error", {}).get("message", "Unknown API error")
        except (json.JSONDecodeError, UnicodeDecodeError):
            error_message = "Google Calendar API request failed"
        return error_response(
            e.resp.status,
            "Google Calendar API error",
            error_message,
        )
    except KeyError as e:
        return error_response(
            400,
            "Missing required parameter",
            f"Required parameter missing: {e}",
        )
    except Exception as e:
        return error_response(500, "Internal error", str(e))
