from agents import function_tool
from tools.utils.google_auth import create_calendar_service, create_gmail_service
import datetime
import base64
from email.message import EmailMessage


##################
# Calendar Tools #
##################
# calendar_service = create_calendar_service()


@function_tool
def list_calendar_list(max_capacity: int = 10) -> str:
    """
    List the user's Google Calendar lists.

    Returns:
        A string representation of the calendar lists.
    """
    try:
        next_page_token = None
        cap_tracker = 0
        calendar_info = []

        while True:
            calendar_list = (
                calendar_service.calendarList()
                .list(
                    maxResults=min(200, max_capacity - cap_tracker),
                    pageToken=next_page_token,
                )
                .execute()
            )
            next_page_token = calendar_list.get("nextPageToken", None)
            calendars = calendar_list.get("items", [])

            if not calendars or cap_tracker >= max_capacity or not next_page_token:
                break

            cap_tracker += len(calendars)

            for calendar in calendars:
                calendar_info.append(
                    f"ID: {calendar['id']}\nSummary: {calendar['summary']}\nDescription: {calendar.get('description', 'No Description')}\n---"
                )

        return "\n".join(calendar_info)
    except Exception as e:
        return f"Error listing calendar lists: {str(e)}"


@function_tool
def list_calendar_events(max_results: int = 10, calendar_id: str = "primary") -> str:
    """
    List upcoming events from the user's primary Google Calendar.

    Args:
        max_results: The maximum number of events to return. Defaults to 10.
        calendar_id: The ID of the calendar to fetch events from. Defaults to 'primary'.

    Returns:
        A string representation of the upcoming events.
    """
    try:
        next_page_token = None
        event_list = []
        cap_tracker = 0

        now = datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        ).isoformat()

        while True:
            events_result = (
                calendar_service.events()
                .list(
                    calendarId=calendar_id,
                    timeMin=now,
                    maxResults=min(20, max_results - cap_tracker),
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            next_page_token = events_result.get("nextPageToken", None)
            events = events_result.get("items", [])

            if not events or cap_tracker >= max_results or not next_page_token:
                break

            cap_tracker += len(events)

            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                event_list.append(f"{start} - {event['summary']}")

        return "\n".join(event_list)
    except Exception as e:
        return f"Error listing calendar events: {str(e)}"


@function_tool
def create_calendar_event(
    summary: str,
    start_time: str,
    end_time: str,
    description: str = "",
    calendar_id: str = "primary",
) -> str:
    """
    Create a new event in the user's primary Google Calendar.

    Args:
        calendar_id: The ID of the calendar where the event will be created.
        summary: The title of the event.
        start_time: The start time of the event in ISO format (e.g., '2023-10-27T10:00:00').
        end_time: The end time of the event in ISO format (e.g., '2023-10-27T11:00:00').
        description: A description of the event.

    Returns:
        A confirmation message with the link to the created event.
    """
    try:
        event = {
            "summary": summary,
            "description": description,
            "start": {
                "dateTime": start_time,
                "timeZone": "IST",
            },
            "end": {
                "dateTime": end_time,
                "timeZone": "IST",
            },
        }

        event = (
            calendar_service.events()
            .insert(calendarId=calendar_id, body=event)
            .execute()
        )
        return f"ID: {event.get('id')}\nTitle: {event.get('summary')}\nDescription: {event.get('description')}\nLink: {event.get('htmlLink')}"
    except Exception as e:
        return f"Error creating calendar event: {str(e)}"


def update_calendar_event(event_id, calendar_id="primary", **updates):
    """
    Update an existing event in the user's Google Calendar.

    Args:
        event_id: The ID of the event to update.
        calendar_id: The ID of the calendar where the event is located. Defaults to 'primary'.
        updates: Key-value pairs of fields to update (e.g., summary, start, end, description).
    Returns:
        A confirmation message with the link to the updated event.
    """
    try:
        event = (
            calendar_service.events()
            .get(calendarId=calendar_id, eventId=event_id)
            .execute()
        )

        for key, value in updates.items():
            event[key] = value

        event = (
            calendar_service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=event)
            .execute()
        )
        return f"Event updated! ID: {event.get('id')}\nTitle: {event.get('summary')}\nDescription: {event.get('description')}\nLink: {event.get('htmlLink')}"
    except Exception as e:
        return f"Error updating calendar event: {str(e)}"


def delete_calendar_event(event_id, calendar_id="primary"):
    """
    Delete an event from the user's Google Calendar.

    Args:
        event_id: The ID of the event to delete.
        calendar_id: The ID of the calendar where the event is located. Defaults to 'primary'.

    Returns:
        A confirmation message.
    """
    try:
        calendar_service.events().delete(
            calendarId=calendar_id, eventId=event_id
        ).execute()
        return f"Event with ID: {event_id} has been deleted."
    except Exception as e:
        return f"Error deleting calendar event: {str(e)}"


###############
# Gmail Tools #
###############


@function_tool
def read_recent_emails(max_results: int = 5) -> str:
    """
    Read recent emails from the user's inbox.

    Args:
        max_results: The maximum number of emails to retrieve. Defaults to 5.

    Returns:
        A string summary of the recent emails (Sender, Subject, Snippet).
    """
    try:
        service = create_gmail_service()
        results = (
            service.users()
            .messages()
            .list(userId="me", labelIds=["INBOX"], maxResults=max_results)
            .execute()
        )
        messages = results.get("messages", [])

        if not messages:
            return "No new messages."

        email_summaries = []
        for message in messages:
            msg = (
                service.users().messages().get(userId="me", id=message["id"]).execute()
            )
            headers = msg["payload"]["headers"]
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"), "No Subject"
            )
            sender = next(
                (h["value"] for h in headers if h["name"] == "From"), "Unknown Sender"
            )
            snippet = msg["snippet"]
            email_summaries.append(
                f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}\n---"
            )

        return "\n".join(email_summaries)
    except Exception as e:
        return f"Error reading emails: {str(e)}"


@function_tool
def create_draft_reply(to: str, subject: str, body: str) -> str:
    """
    Create a draft email reply.

    Args:
        to: The recipient's email address.
        subject: The subject of the email.
        body: The body content of the email.

    Returns:
        A confirmation message with the draft ID.
    """
    try:
        service = create_gmail_service()
        message = EmailMessage()
        message.set_content(body)
        message["To"] = to
        message["Subject"] = subject

        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {"message": {"raw": encoded_message}}

        draft = (
            service.users().drafts().create(userId="me", body=create_message).execute()
        )
        return f"Draft for {to} created. Id: {draft['id']}"
    except Exception as e:
        return f"Error creating draft: {str(e)}"
