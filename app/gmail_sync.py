import asyncio
import base64
from email.utils import parsedate_to_datetime, parseaddr
try:
    from selectolax.lexbor import LexborHTMLParser as HTMLParser
except ImportError:
    from selectolax.parser import HTMLParser
import httpx
from app.auth import get_gmail_service
from app.config import compute_prompt_hash
from app.db import get_db, get_triage_prompt
from app.classifier import classify_email

sync_lock = asyncio.Lock()

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

    # Build 1500-char clean string for vllm-d3-lite
    if full_text:
        clean_for_model = " ".join(full_text.split())[:1500]
    elif full_html:
        tree = HTMLParser(full_html)
        for tag in tree.css("script, style, head, noscript"):
            tag.decompose()
        clean_for_model = tree.text(separator=" ", strip=True)[:1500]
        full_text = clean_for_model
    else:
        clean_for_model = snippet[:1500]
        full_text = snippet

    return clean_for_model, full_text, full_html

def fetch_new_messages_sync(max_results: int = 30, interactive: bool = True) -> int:
    try:
        service = get_gmail_service(interactive=interactive)
        if not service:
            return 0
    except Exception:
        return 0

    try:
        results = service.users().messages().list(
            userId="me", q="label:INBOX", maxResults=max_results
        ).execute()
    except Exception:
        return 0

    messages = results.get("messages", [])
    inserted = 0
    with get_db() as conn:
        for msg_meta in messages:
            msg_id = msg_meta["id"]
            exists = conn.execute("SELECT 1 FROM emails WHERE id = ?", (msg_id,)).fetchone()
            if exists:
                continue

            try:
                msg = service.users().messages().get(userId="me", id=msg_id, format="full").execute()
            except Exception:
                continue

            headers = {h["name"].lower(): h["value"] for h in msg["payload"].get("headers", [])}
            raw_from = headers.get("from", "Unknown")
            sender_name, sender_email = parseaddr(raw_from)
            sender_name = sender_name or sender_email or raw_from
            subject = headers.get("subject", "(No Subject)")
            date_str = headers.get("date", "")
            try:
                ts = int(parsedate_to_datetime(date_str).timestamp())
            except Exception:
                ts = int(msg.get("internalDate", 0)) // 1000

            model_input, body_text, body_html = extract_email_bodies(msg["payload"], msg.get("snippet", ""))
            is_unread = 1 if "UNREAD" in msg.get("labelIds", []) else 0

            conn.execute(
                """INSERT INTO emails 
                   (id, thread_id, sender_name, sender_email, subject, date_str, timestamp, model_input, body_text, body_html, label, confidence, prompt_hash, unread, account)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, ?)""",
                (
                    msg_id,
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
                    "abhed8604@gmail.com",
                )
            )
            inserted += 1
    return inserted

async def run_sync_and_classify(client: httpx.AsyncClient, fetch_gmail: bool = True, interactive: bool = True) -> dict:
    if sync_lock.locked():
        return {"status": "busy"}

    async with sync_lock:
        if fetch_gmail:
            await asyncio.to_thread(fetch_new_messages_sync, 30, interactive)

        triage_prompt = get_triage_prompt()
        current_hash = compute_prompt_hash(triage_prompt)

        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, sender_name, sender_email, subject, date_str, model_input "
                "FROM emails WHERE label IS NULL OR prompt_hash IS NULL OR prompt_hash != ? "
                "ORDER BY timestamp DESC LIMIT 50",
                (current_hash,)
            ).fetchall()
            pending = [dict(r) for r in rows]

        for item in pending:
            try:
                label, prob = await classify_email(client, item, triage_prompt)
                with get_db() as conn:
                    conn.execute(
                        "UPDATE emails SET label = ?, confidence = ?, prompt_hash = ? WHERE id = ?",
                        (label, prob, current_hash, item["id"])
                    )
            except httpx.RequestError:
                break
            except Exception:
                continue

        return {"status": "ok"}
