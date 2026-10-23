import json
import logging
import keyring
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from app.config import APP_NAME, get_credentials_file
from app.db import get_setting, set_setting

log = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]
LEGACY_KEY = "google_oauth_token"
TOKEN_KEY_PREFIX = "oauth_token:"
ACCOUNTS_SETTING = "oauth_accounts"


def _keyring_get(user: str) -> str | None:
    try:
        return keyring.get_password(APP_NAME, user)
    except keyring.errors.KeyringError as e:
        log.error("Keyring unavailable: %s", e)
        return None


def _keyring_set(user: str, value: str) -> bool:
    try:
        keyring.set_password(APP_NAME, user, value)
        return True
    except keyring.errors.KeyringError as e:
        log.error("Keyring unavailable: %s", e)
        return False


def get_stored_accounts() -> list[str]:
    raw = get_setting(ACCOUNTS_SETTING, "[]")
    try:
        emails = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return [e.strip() for e in emails if isinstance(e, str) and e.strip()]


def _register_account(account: str):
    accounts = get_stored_accounts()
    if account not in accounts:
        accounts.append(account)
        set_setting(ACCOUNTS_SETTING, json.dumps(accounts))


def remove_account(account: str) -> bool:
    """Forgets an account: drops the stored token and the account list entry."""
    account = (account or "").strip()
    if not account:
        return False
    accounts = get_stored_accounts()
    if account in accounts:
        accounts.remove(account)
        set_setting(ACCOUNTS_SETTING, json.dumps(accounts))
    try:
        keyring.delete_password(APP_NAME, f"{TOKEN_KEY_PREFIX}{account}")
    except Exception as e:
        log.warning("Could not delete token for %s: %s", account, e)
    return True


def _store_account_token(account: str, creds: Credentials) -> bool:
    if not _keyring_set(f"{TOKEN_KEY_PREFIX}{account}", creds.to_json()):
        return False
    _register_account(account)
    return True


def _resolve_account_email(creds: Credentials) -> str | None:
    try:
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        email = service.users().getProfile(userId="me").execute().get("emailAddress")
        return email.strip().lower() if email else None
    except Exception:
        log.exception("Could not resolve account email from credentials")
        return None


def _load_creds_for(account: str) -> Credentials | None:
    stored_json = _keyring_get(f"{TOKEN_KEY_PREFIX}{account}")
    if not stored_json:
        return None
    try:
        return Credentials.from_authorized_user_info(json.loads(stored_json), SCOPES)
    except (ValueError, KeyError):
        log.error("Corrupt stored token for %s", account)
        return None


def is_authenticated() -> bool:
    return bool(get_stored_accounts()) or bool(_keyring_get(LEGACY_KEY))


def get_gmail_service_for(account: str, interactive: bool = True):
    creds = _load_creds_for(account)
    from_flow = False

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                log.error("Token refresh failed for %s", account)
                creds = None
        if not creds:
            if not interactive:
                return None
            creds = _run_interactive_flow()
            if not creds:
                return None
            from_flow = True

    if from_flow:
        # The browser may have signed into a different Google account than the
        # one this stored entry belongs to; never file those creds under it.
        actual = _resolve_account_email(creds)
        if not actual or actual != account.strip().lower():
            log.error("OAuth email %s does not match stored account %s", actual, account)
            return None

    if not _store_account_token(account, creds):
        log.error("Could not persist refreshed token for %s", account)

    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def _run_interactive_flow() -> Credentials | None:
    """Runs the browser OAuth flow. Blocks the calling thread."""
    credentials_file = get_credentials_file()
    if not credentials_file.exists():
        log.error("credentials.json missing; cannot run OAuth flow")
        return None
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_file), SCOPES)
        return flow.run_local_server(port=0, timeout_seconds=300)
    except Exception:
        log.exception("OAuth flow failed")
        return None


def connect_account() -> str | None:
    """Interactive OAuth for an additional account. Returns its email or None."""
    creds = _run_interactive_flow()
    if not creds:
        return None

    if not creds.valid and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception:
            log.exception("Token refresh after OAuth failed")
            return None

    email = _resolve_account_email(creds)
    if not email:
        return None

    if not _store_account_token(email, creds):
        log.error("Could not persist token for %s (keyring failure)", email)
        return None

    log.info("Connected account: %s", email)
    return email


def migrate_legacy_token() -> bool:
    """Moves the pre-multi-account single token under its owner's email."""
    stored_json = _keyring_get(LEGACY_KEY)
    if not stored_json:
        return False
    try:
        creds = Credentials.from_authorized_user_info(json.loads(stored_json), SCOPES)
        if not creds.valid and creds.refresh_token:
            creds.refresh(Request())
        email = _resolve_account_email(creds)
        if not email:
            return False
        if not _store_account_token(email, creds):
            log.error("Could not persist migrated token for %s; keeping legacy entry", email)
            return False
        keyring.delete_password(APP_NAME, LEGACY_KEY)
        log.info("Migrated legacy OAuth token to per-account storage for %s", email)
        return True
    except Exception:
        log.exception("Legacy token migration failed; keeping legacy entry")
        return False
