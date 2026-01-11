"""
Calendar Lambda handler for Google Calendar operations.

This Lambda is invoked by AgentCore Gateway as a Lambda Target.
It receives the access_token from the Agent (which obtained it via @requires_access_token)
and uses it to call Google Calendar API.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Google Calendar API scope
SCOPES = ["https://www.googleapis.com/auth/calendar"]

# Delimiter used by AgentCore Gateway for tool names
TOOL_NAME_DELIMITER = "___"


def handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """
    Lambda handler for Calendar operations.

    Args:
        event: Input from AgentCore Gateway (inputSchema properties)
        context: Lambda context with AgentCore metadata

    Returns:
        Response with statusCode and body
    """
    try:
        # Extract tool name from context
        tool_name = _get_tool_name(context)
        logger.info(f"Processing tool: {tool_name}")
        logger.info(f"Event: {json.dumps(event)}")

        # Dispatch to appropriate handler
        if tool_name == "get_events":
            return get_events(event)
        elif tool_name == "create_event":
            return create_event(event)
        elif tool_name == "update_event":
            return update_event(event)
        elif tool_name == "delete_event":
            return delete_event(event)
        else:
            return _error_response(400, f"Unknown tool: {tool_name}")

    except HttpError as e:
        logger.error(f"Google API error: {e}")
        return _error_response(e.resp.status, str(e))
    except Exception as e:
        logger.error(f"Error processing request: {e}", exc_info=True)
        return _error_response(500, str(e))


def _get_tool_name(context: Any) -> str:
    """Extract tool name from Lambda context."""
    try:
        full_name: str = context.client_context.custom.get("bedrockAgentCoreToolName", "")
        # Tool name format: {target_name}___{tool_name}
        if TOOL_NAME_DELIMITER in full_name:
            parts = full_name.split(TOOL_NAME_DELIMITER)
            return str(parts[-1])
        return full_name
    except (AttributeError, KeyError):
        logger.warning("Could not extract tool name from context")
        return ""


def _get_calendar_service(access_token: str) -> Any:
    """Build Google Calendar API service."""
    creds = Credentials(token=access_token, scopes=SCOPES)
    return build("calendar", "v3", credentials=creds)


def _success_response(data: Any) -> dict[str, Any]:
    """Create a success response."""
    return {"statusCode": 200, "body": json.dumps(data, ensure_ascii=False, default=str)}


def _error_response(status_code: int, message: str) -> dict[str, Any]:
    """Create an error response."""
    return {"statusCode": status_code, "body": json.dumps({"error": message})}


def get_events(event: dict[str, Any]) -> dict[str, Any]:
    """
    Get calendar events for a specified date range.

    Args:
        event: {
            "access_token": str (required),
            "start_date": str (required, YYYY-MM-DD),
            "end_date": str (optional, YYYY-MM-DD)
        }
    """
    access_token = event.get("access_token")
    if not access_token:
        return _error_response(400, "access_token is required")

    start_date = event.get("start_date")
    if not start_date:
        return _error_response(400, "start_date is required")

    end_date = event.get("end_date", start_date)

    # Convert to RFC3339 format
    jst = timezone(timedelta(hours=9))
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=jst)
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(tzinfo=jst) + timedelta(days=1)

    time_min = start_dt.isoformat()
    time_max = end_dt.isoformat()

    logger.info(f"Fetching events from {time_min} to {time_max}")

    service = _get_calendar_service(access_token)
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )

    events = events_result.get("items", [])
    logger.info(f"Found {len(events)} events")

    # Format events for response
    formatted_events = []
    for e in events:
        start = e["start"].get("dateTime", e["start"].get("date"))
        end = e["end"].get("dateTime", e["end"].get("date"))
        formatted_events.append(
            {
                "id": e["id"],
                "title": e.get("summary", "(no title)"),
                "start": start,
                "end": end,
                "location": e.get("location"),
                "description": e.get("description"),
            }
        )

    return _success_response({"events": formatted_events, "count": len(formatted_events)})


def create_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Create a new calendar event.

    Args:
        event: {
            "access_token": str (required),
            "title": str (required),
            "start_time": str (required, ISO 8601),
            "end_time": str (optional, ISO 8601),
            "description": str (optional),
            "location": str (optional)
        }
    """
    access_token = event.get("access_token")
    if not access_token:
        return _error_response(400, "access_token is required")

    title = event.get("title")
    if not title:
        return _error_response(400, "title is required")

    start_time = event.get("start_time")
    if not start_time:
        return _error_response(400, "start_time is required")

    # Default end_time is 1 hour after start
    end_time = event.get("end_time")
    if not end_time:
        start_dt = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        end_dt = start_dt + timedelta(hours=1)
        end_time = end_dt.isoformat()

    calendar_event = {
        "summary": title,
        "start": {"dateTime": start_time, "timeZone": "Asia/Tokyo"},
        "end": {"dateTime": end_time, "timeZone": "Asia/Tokyo"},
    }

    if event.get("description"):
        calendar_event["description"] = event["description"]
    if event.get("location"):
        calendar_event["location"] = event["location"]

    logger.info(f"Creating event: {calendar_event}")

    service = _get_calendar_service(access_token)
    created_event = service.events().insert(calendarId="primary", body=calendar_event).execute()

    return _success_response(
        {
            "id": created_event["id"],
            "title": created_event.get("summary"),
            "start": created_event["start"].get("dateTime"),
            "end": created_event["end"].get("dateTime"),
            "link": created_event.get("htmlLink"),
        }
    )


def update_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Update an existing calendar event.

    Args:
        event: {
            "access_token": str (required),
            "event_id": str (required),
            "title": str (optional),
            "start_time": str (optional, ISO 8601),
            "end_time": str (optional, ISO 8601),
            "description": str (optional),
            "location": str (optional)
        }
    """
    access_token = event.get("access_token")
    if not access_token:
        return _error_response(400, "access_token is required")

    event_id = event.get("event_id")
    if not event_id:
        return _error_response(400, "event_id is required")

    service = _get_calendar_service(access_token)

    # Get existing event
    existing = service.events().get(calendarId="primary", eventId=event_id).execute()

    # Update fields
    if event.get("title"):
        existing["summary"] = event["title"]
    if event.get("start_time"):
        existing["start"] = {"dateTime": event["start_time"], "timeZone": "Asia/Tokyo"}
    if event.get("end_time"):
        existing["end"] = {"dateTime": event["end_time"], "timeZone": "Asia/Tokyo"}
    if event.get("description") is not None:
        existing["description"] = event["description"]
    if event.get("location") is not None:
        existing["location"] = event["location"]

    logger.info(f"Updating event {event_id}")

    updated_event = (
        service.events().update(calendarId="primary", eventId=event_id, body=existing).execute()
    )

    return _success_response(
        {
            "id": updated_event["id"],
            "title": updated_event.get("summary"),
            "start": updated_event["start"].get("dateTime"),
            "end": updated_event["end"].get("dateTime"),
            "link": updated_event.get("htmlLink"),
        }
    )


def delete_event(event: dict[str, Any]) -> dict[str, Any]:
    """
    Delete a calendar event.

    Args:
        event: {
            "access_token": str (required),
            "event_id": str (required)
        }
    """
    access_token = event.get("access_token")
    if not access_token:
        return _error_response(400, "access_token is required")

    event_id = event.get("event_id")
    if not event_id:
        return _error_response(400, "event_id is required")

    logger.info(f"Deleting event {event_id}")

    service = _get_calendar_service(access_token)
    service.events().delete(calendarId="primary", eventId=event_id).execute()

    return _success_response({"deleted": True, "event_id": event_id})
