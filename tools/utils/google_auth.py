import os
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


def create_service(client_secret_file, api_name, api_version, *scopes, prefix=""):
    creds = None
    working_dir = os.getcwd()
    token_dir = "tokens"
    token_file = f"token_{api_name}_{api_version}{prefix}.json"

    if not os.path.exists(os.path.join(working_dir, token_dir)):
        os.mkdir(os.path.join(working_dir, token_dir))

    try:
        if os.path.exists(os.path.join(working_dir, token_dir, token_file)):
            creds = Credentials.from_authorized_user_file(
                os.path.join(working_dir, token_dir, token_file), scopes
            )
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    client_secret_file, scopes
                )
                creds = flow.run_local_server(port=0)
            with open(os.path.join(working_dir, token_dir, token_file), "w") as token:
                token.write(creds.to_json())
    except Exception as e:
        print(f"{e}\nFailed to obtain credentials")
        os.remove(os.path.join(working_dir, token_dir, token_file))
        return None

    try:
        service = build(api_name, api_version, credentials=creds)
        return service
    except Exception as e:
        print(f"{e}\nFailed to create service for {api_name} {api_version}.")
        os.remove(os.path.join(working_dir, token_dir, token_file))
        return None


def create_calendar_service():
    client_secret_file = "credentials.json"
    api_name = "calendar"
    api_version = "v3"
    scopes = ["https://www.googleapis.com/auth/calendar"]
    return create_service(client_secret_file, api_name, api_version, *scopes)


def create_gmail_service():
    client_secret_file = "credentials.json"
    api_name = "gmail"
    api_version = "v1"
    scopes = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
    ]
    return create_service(client_secret_file, api_name, api_version, *scopes)
