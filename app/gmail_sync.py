import asyncio
import base64
import logging
from email.utils import parsedate_to_datetime, parseaddr
from selectolax.lexbor import LexborHTMLParser as HTMLParser
import httpx
from app.auth import (
    get_gmail_service_for,
    get_stored_accounts,
    connect_account,
)
from app.config import compute_prompt_hash, DEFAULT_TRIAGE_PROMPT, MODEL_INPUT_CHARS
from app.db import get_db, get_setting, set_unread_states, prune_missing_emails
from app.classifier import classify_email, ensure_engine_started
from app.html_sanitize import sanitize_email_html

log = logging.getLogger(__name__)

sync_lock = asyncio.Lock()
_rescan_lock = asyncio.Lock()

SYNC_PAGE_SIZE = 200
SYNC_CAP = 400

def extract_email_bodies(payload: dict, snippet: str) -> tuple[str, str, str]:
    """Returns (model_input_1500_chars, full_plain_text, full_html)."""
    plain_parts: list[str] = []
    html_parts: list[str] = []

    def walk(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data")
        if data:
            decoded = base64.urlsafe_b64decode(data).decode("utf-8", errors="ignore")
            if mime == "text/plain":
                plain_parts.append(decoded)
            elif mime == "text/html":
                html_parts.append(decoded)
        for sub in part.get("parts", []):
            walk(sub)

    walk(payload)
    full_text = "\n".join(plain_parts).strip()
    full_html = "\n".join(html_parts).strip()

    # Build the model-input string for vllm-d3-lite
    if full_text:
        clean_for_model = " ".join(full_text.split())[:MODEL_INPUT_CHARS]
    elif full_html:
        tree = HTMLParser(full_html)
        for tag in tree.css("script, style, head, noscript"):
            tag.decompose()
        clean_for_model = tree.text(separator=" ", strip=True)[:MODEL_INPUT_CHARS]
        full_text = clean_for_model
    else:
        clean_for_model = snippet[:MODEL_INPUT_CHARS]
        full_text = snippet

    return clean_for_model, full_text, full_html

def list_message_ids(service, query: str, cap: int) -> tuple[list[str], bool]:
    """Lists up to `cap` Gmail message ids (paginated).

    Returns (ids, covered) where covered means the whole matching set was
    seen — i.e. its size is strictly under cap, so id-absence is meaningful.
    """
    ids: list[str] = []
    page_token: str | None = None
    while True:
        kwargs = {"userId": "me", "q": query, "maxResults": min(SYNC_PAGE_SIZE, cap - len(ids))}
        if page_token:
            kwargs["pageToken"] = page_token
        results = service.users().messages().list(**kwargs).execute()
        ids.extend(m["id"] for m in results.get("messages", []))
        page_token = results.get("nextPageToken")
        if page_token is None:
            return ids, len(ids) < cap
        if len(ids) >= cap:
            return ids, False

def fetch_inbox_mirror_sync(interactive: bool = False) -> dict:
    """Mirrors the Gmail inbox for every stored account.

    Two cheap paginated list calls per account give the full picture:
      1. label:INBOX            -> what still belongs in the inbox
      2. label:INBOX unread     -> which of those are unread
    New mail is fetched with format=full GETs; read state is bulk-upserted;
    mail archived/deleted in Gmail is pruned (only when fully listed).
    """
    accounts = get_stored_accounts()

    if not accounts and interactive:
        email = connect_account()
        if email:
            accounts = [email]
        else:
            log.warning("Sync requested but no account is connected")
            return {"new": 0, "read_synced": 0, "pruned": 0}
    elif not accounts:
        return {"new": 0, "read_synced": 0, "pruned": 0}

    totals = {"new": 0, "read_synced": 0, "pruned": 0}
    for account in accounts:
        try:
            service = get_gmail_service_for(account, interactive=interactive)
        except Exception:
            log.exception("Could not build Gmail service for %s", account)
            continue
        if not service:
            log.warning("Skipping %s: token unavailable", account)
            continue

        try:
            stats = _mirror_account_inbox(service, account)
            for key in totals:
                totals[key] += stats.get(key, 0)
        except Exception:
            log.exception("Inbox mirror failed for %s", account)

    if totals["new"]:
        log.info("Mirror fetched %d new messages", totals["new"])
    if totals["read_synced"] or totals["pruned"]:
        log.info(
            "Mirror updated: %d read-state changes, %d pruned",
            totals["read_synced"], totals["pruned"],
        )
    return totals

def _mirror_account_inbox(service, account: str) -> dict:
    inbox_ids, inbox_covered = list_message_ids(service, "label:INBOX", SYNC_CAP)
    unread_ids, _ = list_message_ids(service, "label:INBOX label:unread", SYNC_CAP)
    inbox_set = set(inbox_ids)
    unread_set = set(unread_ids)

    stats = {"new": 0, "read_synced": 0, "pruned": 0}

    # 1. Insert messages we don't have yet
    with get_db() as conn:
        existing = {r["id"] for r in conn.execute(
            "SELECT id FROM emails WHERE account = ?", (account,)
        ).fetchall()}
        local_reads = {r["email_id"] for r in conn.execute("SELECT email_id FROM local_reads").fetchall()}
    to_fetch = [mid for mid in inbox_ids if mid not in existing]
    # One connection for the whole fetch loop: one commit instead of one per message
    with get_db() as conn:
        for msg_id in to_fetch:
            try:
                msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            except Exception:
                log.exception("Gmail get failed for %s (%s)", account, msg_id)
                continue
            stats["new"] += _insert_message(conn, msg, account)

    # 2. Mirror unread state. Locally-read mail wins over Gmail's UNREAD label
    #    (we run with a read-only scope and cannot push marks back).
    to_unread = unread_set - local_reads
    to_read = inbox_set - to_unread
    stats["read_synced"] = set_unread_states(account, to_unread, to_read)

    # 3. Prune mail archived/deleted in Gmail — only safe when we saw the whole inbox
    if inbox_covered:
        stats["pruned"] = prune_missing_emails(account, inbox_set)
    else:
        log.info(
            "Inbox for %s exceeds sync cap (%d+ messages); skipping prune", account, SYNC_CAP,
        )
    return stats

def _insert_message(conn, msg: dict, account: str) -> int:
    headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
    raw_from = headers.get("from", "Unknown")
    sender_name, sender_email = parseaddr(raw_from)
    sender_name = sender_name or sender_email or raw_from
    subject = headers.get("subject", "(No Subject)")
    date_str = headers.get("date", "")
    try:
        ts = int(parsedate_to_datetime(date_str).timestamp())
    except (TypeError, ValueError):
        ts = int(msg.get("internalDate", 0)) // 1000

    model_input, body_text, body_html = extract_email_bodies(msg["payload"], msg.get("snippet", ""))
    is_unread = 1 if "UNREAD" in msg.get("labelIds", []) else 0
    body_html = sanitize_email_html(body_html)

    conn.execute(
        """INSERT INTO emails
           (id, thread_id, sender_name, sender_email, subject, date_str, timestamp, model_input, body_text, body_html, label, confidence, prompt_hash, unread, account)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)""",
        (
            msg["id"],
            msg.get("threadId", ""),
            sender_name,
            sender_email.lower(),
            subject,
            date_str,
            ts,
            model_input,
            body_text,
            body_html,
            is_unread,
            account,
        )
    )
    return 1

async def run_sync_and_classify(
    client: httpx.AsyncClient,
    fetch_gmail: bool = True,
    interactive: bool = False,
) -> dict:
    # Best-effort busy bail: racing callers re-run sequentially otherwise
    if sync_lock.locked():
        return {"status": "busy"}
    await sync_lock.acquire()
    try:
        log.info("Sync started (fetch_gmail=%s)", fetch_gmail)
        sync_stats = {"new": 0, "read_synced": 0, "pruned": 0}
        if fetch_gmail:
            sync_stats = await asyncio.to_thread(fetch_inbox_mirror_sync, interactive)

        classified = await drain_classification(client, wake_engine=(sync_stats.get("new", 0) > 0))
        return {
            "status": "ok",
            "fetched": sync_stats.get("new", 0),
            "read_synced": sync_stats.get("read_synced", 0),
            "pruned": sync_stats.get("pruned", 0),
            "classified": classified,
        }
    finally:
        sync_lock.release()

async def drain_classification(client: httpx.AsyncClient, max_passes: int = 10, wake_engine: bool = True) -> int:
    """Classifies everything pending in batches of 50 until the queue is empty.

    An engine outage aborts the drain early (classify_batch breaks), and a
    pass that yields zero successful classifications stops the loop so
    permanently-failing rows can't spin forever. When wake_engine is False and
    no stale rows exist, the local LLM is never launched (lazy engine).
    """
    triage_prompt = get_setting("triage_prompt", DEFAULT_TRIAGE_PROMPT)
    current_hash = compute_prompt_hash(triage_prompt)
    classified_total = 0
    woke = False

    for _ in range(max_passes):
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, sender_name, sender_email, subject, date_str, model_input "
                "FROM emails WHERE label IS NULL OR prompt_hash IS NULL OR prompt_hash != ? "
                "ORDER BY timestamp DESC LIMIT 50",
                (current_hash,)
            ).fetchall()

        if not rows:
            break
        if not woke:
            if not wake_engine:
                break
            if not await ensure_engine_started(client):
                log.warning("Engine unavailable; classification deferred")
                break
            woke = True
        log.info("Classifying %d pending emails", len(rows))
        classified = await classify_batch(client, rows, triage_prompt, current_hash)
        classified_total += classified
        if not classified:
            break
    return classified_total

RESCAN_LIMIT = 100
RESCAN_STATE: dict = {"active": False, "phase": "", "processed": 0, "total": 0, "error": None}

async def rescan_last_items(client: httpx.AsyncClient, limit: int = RESCAN_LIMIT) -> dict:
    """Re-classifies the newest `limit` emails in the DB, ignoring existing
    labels/prompt hashes, and feeds progress into RESCAN_STATE."""
    global _rescan_lock
    if _rescan_lock.locked():
        return {"status": "busy"}
    await _rescan_lock.acquire()
    RESCAN_STATE.update(active=True, phase="starting-engine", processed=0, total=0, error=None)
    try:
        async with sync_lock:
            if not await ensure_engine_started(client):
                RESCAN_STATE.update(phase="done", error="Engine unavailable")
                log.warning("Rescan aborted: engine not available")
                return {"status": "error", "message": "Engine not available"}

            with get_db() as conn:
                rows = conn.execute(
                    "SELECT id, sender_name, sender_email, subject, date_str, model_input "
                    f"FROM emails ORDER BY timestamp DESC, rowid DESC LIMIT {int(limit)}"
                ).fetchall()
            RESCAN_STATE["total"] = len(rows)
            triage_prompt = get_setting("triage_prompt", DEFAULT_TRIAGE_PROMPT)
            current_hash = compute_prompt_hash(triage_prompt)
            RESCAN_STATE.update(phase="scanning", processed=0)

            for idx in range(0, len(rows), 50):
                chunk = rows[idx:idx + 50]
                await classify_batch(client, chunk, triage_prompt, current_hash)
                RESCAN_STATE["processed"] += len(chunk)

            RESCAN_STATE.update(phase="done", active=False)
            log.info("Rescan finished: %d emails processed", len(rows))
            return {"status": "ok", "processed": len(rows), "total": RESCAN_STATE["total"]}
    except Exception as e:
        log.exception("Rescan failed")
        RESCAN_STATE.update(phase="done", active=False, error=str(e))
        return {"status": "error", "message": str(e)}
    finally:
        _rescan_lock.release()

def get_rescan_progress() -> dict:
    return dict(RESCAN_STATE)

def reset_rescan_state():
    """Prepares the HUD for a new run; a live run (active=True) is left alone."""
    if not RESCAN_STATE["active"]:
        RESCAN_STATE.update(active=True, phase="starting-engine", processed=0, total=0, error=None)

async def classify_batch(
    client: httpx.AsyncClient,
    rows,
    triage_prompt: str,
    current_hash: str,
) -> int:
    """Classifies rows and persists label/confidence in one transaction."""
    classified = 0
    updates = []

    for item in rows:
        item = dict(item)
        try:
            label, prob = await classify_email(client, item, triage_prompt)
        except httpx.RequestError:
            log.warning("Engine unreachable; stopping classification batch")
            break
        except Exception:
            log.exception("Classification failed for %s", item.get("id"))
            continue
        updates.append((label, prob, current_hash, item["id"]))
        classified += 1

    if updates:
        with get_db() as conn:
            conn.executemany(
                "UPDATE emails SET label = ?, confidence = ?, prompt_hash = ? WHERE id = ?",
                updates,
            )
    return classified
