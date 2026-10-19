import json
import keyring
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from app.config import APP_NAME, CREDENTIALS_FILE

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
KEYRING_USER = "google_oauth_token"

def is_authenticated() -> bool:
    return bool(keyring.get_password(APP_NAME, KEYRING_USER))

def get_gmail_service(interactive: bool = True):
    creds = None
    stored_json = keyring.get_password(APP_NAME, KEYRING_USER)

    if stored_json:
        creds = Credentials.from_authorized_user_info(json.loads(stored_json), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not interactive:
                return None
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    "Missing credentials.json. Download Desktop OAuth client JSON from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        keyring.set_password(APP_NAME, KEYRING_USER, creds.to_json())

    # cache_discovery=False prevents google-api-python-client file cache memory leaks
    return build("gmail", "v1", credentials=creds, cache_discovery=False)
