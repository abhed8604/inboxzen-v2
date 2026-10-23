import asyncio
import base64
import logging
import threading
from email.utils import parsedate_to_datetime, parseaddr
from selectolax.lexbor import LexborHTMLParser as HTMLParser
import httpx
from app.auth import (
    get_gmail_service_for,
    get_stored_accounts,
    connect_account,
)
from app.config import (
    compute_prompt_hash,
    DEFAULT_TRIAGE_PROMPT,
    MODEL_INPUT_CHARS,
    is_model_downloaded,
)
from app.db import (
    get_db,
    get_setting,
    get_sync_state,
    save_sync_state,
    set_unread_states,
    prune_missing_emails,
)
from app.classifier import classify_email, ensure_engine_started, engine_use
from app.html_sanitize import sanitize_email_html

log = logging.getLogger(__name__)

sync_lock = asyncio.Lock()
_rescan_lock = asyncio.Lock()
_active_job: str | None = None

SYNC_PAGE_SIZE = 200
FIRST_SYNC_CAP = 150  # newest inbox messages fetched for a brand-new account
SYNC_BATCH = 100      # Gmail batch endpoint limit

JOB_STATE: dict = {
    "active": False,
    "phase": "idle",
    "processed": 0,
    "total": 0,
    "fetched": 0,
    "failed": 0,
    "error": None,
}
_sync_cancel = threading.Event()


class SyncCancelled(Exception):
    """Raised at a checkpoint when the user asks a sync to stop."""


def sync_in_progress() -> bool:
    return _active_job == "sync"


def _sync_cancelled() -> bool:
    return _sync_cancel.is_set()


def request_sync_cancel() -> None:
    """Asks the running sync to stop at its next checkpoint."""
    _sync_cancel.set()
    if _active_job == "sync" and JOB_STATE["active"]:
        JOB_STATE["phase"] = "cancelling"


def get_sync_progress() -> dict:
    return dict(JOB_STATE)


def reset_sync_state() -> None:
    """Prepares the HUD for a new run; a live run is left alone."""
    if sync_lock.locked():
        return
    _sync_cancel.clear()
    JOB_STATE.update(
        active=True, phase="starting", processed=0, total=0,
        fetched=0, failed=0, error=None,
    )


def _sync_progress(processed: int, total: int) -> None:
    JOB_STATE["processed"] = processed
    JOB_STATE["total"] = total

def extract_email_bodies(payload: dict, snippet: str) -> tuple[str, str, str]:
    """Returns (model_input, full_plain_text, full_html)."""
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
        full_text = tree.text(separator=" ", strip=True)
        clean_for_model = full_text[:MODEL_INPUT_CHARS]
    else:
        clean_for_model = snippet[:MODEL_INPUT_CHARS]
        full_text = snippet

    return clean_for_model, full_text, full_html

def list_message_ids(service, query: str, cap: int | None = None) -> tuple[list[str], bool]:
    """Lists Gmail message ids (paginated).

    `cap=None` walks every matching page. With a cap, returns (ids, covered)
    where covered means the whole matching set was seen (size strictly under
    cap), so id-absence is meaningful.
    """
    ids: list[str] = []
    page_token: str | None = None
    while True:
        size = SYNC_PAGE_SIZE if cap is None else max(1, min(SYNC_PAGE_SIZE, cap - len(ids)))
        kwargs = {"userId": "me", "q": query, "maxResults": size}
        if page_token:
            kwargs["pageToken"] = page_token
        results = service.users().messages().list(**kwargs).execute()
        ids.extend(m["id"] for m in results.get("messages", []))
        page_token = results.get("nextPageToken")
        if page_token is None:
            return ids, (cap is None or len(ids) < cap)
        if cap is not None and len(ids) >= cap:
            return ids, False

def fetch_inbox_mirror_sync(
    interactive: bool = False,
    only_account: str = "",
) -> dict:
    """Mirrors the Gmail inbox for stored accounts.

    A brand-new account gets its newest 150 messages; after that only
    messages newer than the account's watermark are fetched. The full inbox
    id list is still read (ids only) so archived mail is pruned and read
    state stays in sync. Auto-sync skips accounts waiting for their first
    manual sync.
    """
    accounts = get_stored_accounts()
    if only_account:
        accounts = [account for account in accounts if account == only_account.strip()]

    if not accounts and interactive and not only_account:
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
        if _sync_cancelled():
            raise SyncCancelled()
        try:
            service = get_gmail_service_for(account, interactive=interactive)
        except Exception:
            log.exception("Could not build Gmail service for %s", account)
            continue
        if not service:
            log.warning("Skipping %s: token unavailable", account)
            continue

        try:
            stats = _mirror_account_inbox(service, account, allow_initial=interactive)
            if stats.get("skipped"):
                continue
            for key in totals:
                totals[key] += stats.get(key, 0)
        except SyncCancelled:
            raise
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

def _mirror_account_inbox(service, account: str, allow_initial: bool) -> dict:
    if _sync_cancelled():
        raise SyncCancelled()

    state = get_sync_state(account)
    initial = not state or not state.get("initial_sync_done")
    if initial and not allow_initial:
        log.info("Skipping first sync for %s until the user starts it", account)
        return {"new": 0, "read_synced": 0, "pruned": 0, "skipped": 1}

    watermark = int((state or {}).get("last_internal_ts") or 0)
    JOB_STATE["phase"] = "listing"

    if initial:
        # The one and only time we limit a sync: newest 150 messages.
        new_ids, inbox_covered = list_message_ids(service, "label:INBOX", FIRST_SYNC_CAP)
        inbox_ids = new_ids
        log.info("First sync for %s: newest %d messages", account, len(new_ids))
    else:
        # Full inbox ids are for pruning/read-state only; bodies are fetched
        # only for mail newer than the last synced message.
        inbox_ids, inbox_covered = list_message_ids(service, "label:INBOX")
        new_ids, _ = list_message_ids(
            service, f"label:INBOX after:{max(0, watermark - 1)}"
        )
    unread_ids, _ = list_message_ids(service, "label:INBOX label:unread")
    inbox_set = set(inbox_ids)
    unread_set = set(unread_ids)

    stats = {"new": 0, "read_synced": 0, "pruned": 0}

    # 1. Insert messages we don't have yet
    with get_db() as conn:
        existing = {r["id"] for r in conn.execute(
            "SELECT id FROM emails WHERE account = ?", (account,)
        ).fetchall()}
        local_reads = {r["email_id"] for r in conn.execute("SELECT email_id FROM local_reads").fetchall()}
    to_fetch = list(dict.fromkeys(mid for mid in new_ids if mid not in existing))
    JOB_STATE["total"] += len(to_fetch)
    JOB_STATE["phase"] = "syncing"
    newest_seen = watermark
    fetch_ok = True
    for start in range(0, len(to_fetch), SYNC_BATCH):
        if _sync_cancelled():
            raise SyncCancelled()
        chunk = to_fetch[start:start + SYNC_BATCH]
        fetched: list[dict] = []
        errors: list[str] = []

        def collect(request_id, response, exception, fetched=fetched, errors=errors):
            if exception is not None:
                errors.append(request_id)
                log.error("Gmail get failed for %s (%s): %s", account, request_id, exception)
                return
            if response is not None:
                fetched.append(response)

        batch = service.new_batch_http_request()
        for msg_id in chunk:
            batch.add(
                service.users().messages().get(userId="me", id=msg_id, format="full"),
                callback=collect,
            )
        try:
            batch.execute()
        except Exception:
            errors.append("batch")
            log.exception("Gmail batch failed for %s", account)
        if errors:
            fetch_ok = False
        # Network I/O is done: persist the chunk in one short transaction.
        added = 0
        with get_db() as conn:
            for msg in fetched:
                added += _insert_message(conn, msg, account)
                newest_seen = max(newest_seen, int(msg.get("internalDate", 0)) // 1000)
                JOB_STATE["processed"] += 1
        stats["new"] += added
        JOB_STATE["fetched"] += added

    if initial and not fetch_ok:
        # First sync is incomplete: leave it pending so the next run retries
        # the newest 150 instead of silently starting at a later watermark.
        log.warning("First sync for %s incomplete; will retry", account)
    else:
        # On a partial later sync keep the old watermark so missed ids are
        # listed again next time (existing ids are deduplicated).
        save_sync_state(account, True, newest_seen if fetch_ok else watermark)

    # 2. Mirror unread state. Locally-read mail wins over Gmail's UNREAD label
    #    (we run with a read-only scope and cannot push marks back).
    to_unread = unread_set - local_reads
    to_read = inbox_set - to_unread
    stats["read_synced"] = set_unread_states(account, to_unread, to_read)

    # 3. Prune mail archived/deleted in Gmail. The first sync only saw the
    #    newest 150, so absence there does not mean the mail was deleted.
    if not initial and inbox_covered:
        stats["pruned"] = prune_missing_emails(account, inbox_set)
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

    cur = conn.execute(
        """INSERT OR IGNORE INTO emails
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
    return 1 if cur.rowcount else 0

async def run_sync_and_classify(
    client: httpx.AsyncClient,
    fetch_gmail: bool = True,
    interactive: bool = False,
    queue: bool = False,
    only_account: str = "",
) -> dict:
    """Mirrors Gmail and classifies what is pending.

    `queue=True` (the manual Sync button) waits for a running sync instead of
    giving up, so the user is never told a sync started when it did not.
    Progress is mirrored into JOB_STATE for the HUD; Cancel raises
    SyncCancelled at the next batch checkpoint and keeps partial results.
    """
    if not queue and sync_lock.locked():
        return {"status": "busy"}
    await sync_lock.acquire()
    global _active_job
    _active_job = "sync"
    _sync_cancel.clear()
    JOB_STATE.update(
        active=True, phase="listing", processed=0, total=0,
        fetched=0, failed=0, error=None,
    )
    fetched = 0
    classified = 0
    try:
        log.info("Sync started (fetch_gmail=%s)", fetch_gmail)
        sync_stats = {"new": 0, "read_synced": 0, "pruned": 0}
        if fetch_gmail:
            sync_stats = await asyncio.to_thread(
                fetch_inbox_mirror_sync, interactive, only_account
            )
            fetched = sync_stats.get("new", 0)
            JOB_STATE["fetched"] = fetched

        JOB_STATE.update(phase="classifying", processed=0, total=0)
        classified, failed, aborted = await drain_classification(
            client,
            wake_engine=(sync_stats.get("new", 0) > 0),
            on_progress=_sync_progress,
            should_cancel=_sync_cancelled,
        )
        JOB_STATE["failed"] = failed
        if _sync_cancelled():
            JOB_STATE.update(phase="cancelled", active=False)
            log.info("Sync cancelled: %d new, %d classified", fetched, classified)
            return {"status": "cancelled", "fetched": fetched,
                    "classified": classified, "failed": failed}
        if aborted or (failed and not classified):
            message = "Engine unavailable" if aborted else f"Classification failed for {failed} emails"
            JOB_STATE.update(phase="error", active=False, error=message)
            log.error("Sync classification failed: %s", message)
            return {"status": "error", "fetched": fetched,
                    "classified": classified, "failed": failed, "message": message}
        JOB_STATE.update(phase="done", active=False)
        return {
            "status": "ok",
            "fetched": fetched,
            "read_synced": sync_stats.get("read_synced", 0),
            "pruned": sync_stats.get("pruned", 0),
            "classified": classified,
            "failed": failed,
        }
    except SyncCancelled:
        fetched = JOB_STATE["fetched"]
        JOB_STATE.update(phase="cancelled", active=False)
        log.info("Sync cancelled during mirror: %d new fetched", fetched)
        return {"status": "cancelled", "fetched": fetched, "classified": classified}
    except Exception as e:
        JOB_STATE.update(phase="error", active=False, error=str(e))
        raise
    finally:
        _active_job = None
        _sync_cancel.clear()
        sync_lock.release()


def rescan_in_progress() -> bool:
    return _rescan_lock.locked()


DRAIN_MAX_PASSES = 10

async def drain_classification(
    client: httpx.AsyncClient,
    wake_engine: bool = True,
    on_progress=None,
    should_cancel=None,
) -> tuple[int, int, bool]:
    async with engine_use():
        return await _drain_classification_inner(
            client, wake_engine=wake_engine,
            on_progress=on_progress, should_cancel=should_cancel,
        )


async def _drain_classification_inner(
    client: httpx.AsyncClient,
    wake_engine: bool = True,
    on_progress=None,
    should_cancel=None,
) -> tuple[int, int, bool]:
    """Classifies everything pending in batches of 50 until the queue is empty.

    An engine outage aborts the drain early (classify_batch breaks), and a
    pass that yields zero successful classifications stops the loop so
    permanently-failing rows can't spin forever. The engine is only launched
    when there is something to classify and the model is on disk, so the lazy
    "engine off until you need it" promise still holds.
    """
    triage_prompt = get_setting("triage_prompt", DEFAULT_TRIAGE_PROMPT)
    current_hash = compute_prompt_hash(triage_prompt)
    classified_total = 0
    failed_total = 0
    aborted = False
    woke = False

    with get_db() as conn:
        pending = conn.execute(
            "SELECT COUNT(*) FROM emails WHERE label IS NULL OR prompt_hash IS NULL OR prompt_hash != ?",
            (current_hash,)
        ).fetchone()[0]
    total = min(pending, DRAIN_MAX_PASSES * 50)
    if on_progress:
        on_progress(0, total)

    for _ in range(DRAIN_MAX_PASSES):
        if should_cancel and should_cancel():
            break
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
            if not wake_engine and not is_model_downloaded():
                break
            if not await ensure_engine_started(client):
                log.warning("Engine unavailable; classification deferred")
                break
            woke = True
        log.info("Classifying %d pending emails", len(rows))

        def item_done(done_in_batch: int):
            if on_progress:
                on_progress(classified_total + done_in_batch, total)

        classified, aborted, failed = await classify_batch(
            client, rows, triage_prompt, current_hash,
            should_cancel=should_cancel, on_item=item_done,
        )
        classified_total += classified
        failed_total += failed
        if on_progress:
            on_progress(classified_total, total)
        if aborted or not classified:
            break
    return classified_total, failed_total, aborted

RESCAN_LIMIT = -1
_rescan_cancel = threading.Event()
_rescan_pending = False


def request_rescan_cancel() -> None:
    """Asks the running rescan to stop at its next checkpoint."""
    _rescan_cancel.set()
    if _active_job == "rescan" and JOB_STATE["active"]:
        JOB_STATE["phase"] = "cancelling"


def _rescan_cancelled() -> bool:
    return _rescan_cancel.is_set()

async def rescan_last_items(
    client: httpx.AsyncClient,
    limit: int = RESCAN_LIMIT,
    queue: bool = False,
) -> dict:
    """Re-classifies up to `limit` newest emails in the DB (all when negative),
    ignoring existing labels/prompt hashes, and feeds progress into JOB_STATE."""
    global _rescan_pending, _active_job
    if _rescan_lock.locked():
        if not queue:
            return {"status": "busy"}
        if _rescan_pending:
            return {"status": "queued"}
        _rescan_pending = True
    try:
        await _rescan_lock.acquire()
    except BaseException:
        _rescan_pending = False
        raise
    _rescan_pending = False
    try:
        async with sync_lock:
            _active_job = "rescan"
            _rescan_cancel.clear()
            JOB_STATE.update(
                active=True, phase="starting-engine", processed=0,
                total=0, fetched=0, failed=0, error=None,
            )
            if _rescan_cancelled():
                JOB_STATE.update(phase="cancelled", active=False)
                return {"status": "cancelled", "processed": 0, "total": 0}
            async with engine_use():
                if not await ensure_engine_started(client):
                    JOB_STATE.update(phase="done", active=False, error="Engine unavailable")
                    log.warning("Rescan aborted: engine not available")
                    return {"status": "error", "message": "Engine not available"}
                if _rescan_cancelled():
                    JOB_STATE.update(phase="cancelled", active=False)
                    return {"status": "cancelled", "processed": 0, "total": 0}

                query = (
                    "SELECT id, sender_name, sender_email, subject, date_str, model_input "
                    "FROM emails ORDER BY timestamp DESC, rowid DESC"
                )
                if limit >= 0:
                    query += f" LIMIT {int(limit)}"
                with get_db() as conn:
                    rows = conn.execute(query).fetchall()
                JOB_STATE["total"] = len(rows)
                triage_prompt = get_setting("triage_prompt", DEFAULT_TRIAGE_PROMPT)
                current_hash = compute_prompt_hash(triage_prompt)
                JOB_STATE.update(phase="scanning", processed=0)

                def item_done(done: int):
                    JOB_STATE["processed"] = done

                classified, aborted, failed = await classify_batch(
                    client, rows, triage_prompt, current_hash,
                    should_cancel=_rescan_cancelled, on_item=item_done,
                )
                JOB_STATE["processed"] = classified
                JOB_STATE["failed"] = failed
                if not _rescan_cancelled() and aborted:
                    JOB_STATE.update(phase="done", active=False, error="Engine unavailable")
                    log.warning("Rescan aborted: engine went away")
                    return {"status": "error", "message": "Engine unavailable"}

                if _rescan_cancelled():
                    JOB_STATE.update(phase="cancelled", active=False)
                    log.info("Rescan cancelled: %d emails processed", JOB_STATE["processed"])
                    return {"status": "cancelled", "processed": JOB_STATE["processed"],
                            "total": JOB_STATE["total"]}

                if failed and not classified:
                    message = f"Classification failed for {failed} emails"
                    JOB_STATE.update(phase="done", active=False, error=message)
                    log.error("Rescan failed: %s", message)
                    return {"status": "error", "message": message}

                JOB_STATE.update(phase="done", active=False)
                log.info("Rescan finished: %d emails processed, %d failed",
                         JOB_STATE["processed"], JOB_STATE["failed"])
                return {"status": "ok", "processed": JOB_STATE["processed"],
                        "failed": JOB_STATE["failed"], "total": JOB_STATE["total"]}
    except Exception as e:
        log.exception("Rescan failed")
        JOB_STATE.update(phase="done", active=False, error=str(e))
        return {"status": "error", "message": str(e)}
    finally:
        _active_job = None
        _rescan_cancel.clear()
        _rescan_lock.release()

def get_rescan_progress() -> dict:
    return dict(JOB_STATE)

def reset_rescan_state():
    """Prepares the HUD for a new run; a live run (active=True) is left alone."""
    if not JOB_STATE["active"]:
        _rescan_cancel.clear()
        JOB_STATE.update(
            active=True, phase="starting-engine", processed=0,
            total=0, fetched=0, failed=0, error=None,
        )

async def classify_batch(
    client: httpx.AsyncClient,
    rows,
    triage_prompt: str,
    current_hash: str,
    should_cancel=None,
    on_item=None,
) -> tuple[int, bool, int]:
    """Classifies rows and persists label/confidence in one transaction.

    Returns (classified, aborted, failed); aborted is True when the engine
    went away or the user cancelled, so callers can stop a drain/rescan
    instead of reporting it as complete.
    """
    classified = 0
    aborted = False
    failed = 0
    updates = []

    for item in rows:
        if should_cancel and should_cancel():
            aborted = True
            break
        item = dict(item)
        try:
            label, prob = await classify_email(client, item, triage_prompt)
        except httpx.HTTPError:
            log.warning("Engine request failed; stopping classification batch")
            aborted = True
            break
        except Exception:
            failed += 1
            log.exception("Classification failed for %s", item.get("id"))
            continue
        updates.append((label, prob, current_hash, item["id"]))
        classified += 1
        if on_item:
            on_item(classified)

    if updates:
        with get_db() as conn:
            conn.executemany(
                "UPDATE emails SET label = ?, confidence = ?, prompt_hash = ? WHERE id = ?",
                updates,
            )
    return classified, aborted, failed
