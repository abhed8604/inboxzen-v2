import datetime
import os
import sqlite3
from contextlib import contextmanager
from app.config import DB_PATH, DEFAULT_TRIAGE_PROMPT

LOW_CONFIDENCE_RELABEL_LIMIT = 0.60

@contextmanager
def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS emails (
                id TEXT PRIMARY KEY,
                thread_id TEXT,
                sender_name TEXT,
                sender_email TEXT,
                subject TEXT,
                date_str TEXT,
                timestamp INTEGER,
                model_input TEXT,    -- Clean body text sent to vllm-d3-lite (capped at MODEL_INPUT_CHARS)
                body_text TEXT,      -- Full plain-text email for in-app viewing
                body_html TEXT,      -- Full HTML email for sandboxed iframe viewing
                label TEXT,          -- 'very_important', 'important', 'low_priority', or NULL
                confidence REAL,
                prompt_hash TEXT,    -- Hash of the Markdown prompt used to classify
                unread INTEGER DEFAULT 1,
                account TEXT DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_emails_label_ts 
            ON emails(label, timestamp DESC);

            CREATE INDEX IF NOT EXISTS idx_emails_prompt_hash 
            ON emails(prompt_hash);

            CREATE INDEX IF NOT EXISTS idx_emails_unread
            ON emails(unread);

            CREATE INDEX IF NOT EXISTS idx_emails_account
            ON emails(account);

            CREATE VIRTUAL TABLE IF NOT EXISTS emails_fts USING fts5(
                sender_name, sender_email, subject, body_text,
                content='emails', content_rowid='rowid'
            );

            CREATE TRIGGER IF NOT EXISTS emails_fts_ai AFTER INSERT ON emails BEGIN
                INSERT INTO emails_fts(rowid, sender_name, sender_email, subject, body_text)
                VALUES (new.rowid, new.sender_name, new.sender_email, new.subject, new.body_text);
            END;

            CREATE TRIGGER IF NOT EXISTS emails_fts_ad AFTER DELETE ON emails BEGIN
                INSERT INTO emails_fts(emails_fts, rowid, sender_name, sender_email, subject, body_text)
                VALUES ('delete', old.rowid, old.sender_name, old.sender_email, old.subject, old.body_text);
            END;

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS local_reads (
                email_id TEXT PRIMARY KEY
            );

            CREATE TABLE IF NOT EXISTS sync_state (
                account TEXT PRIMARY KEY,
                initial_sync_done INTEGER NOT NULL DEFAULT 0,
                last_internal_ts INTEGER NOT NULL DEFAULT 0
            );
        """)

        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('triage_prompt', ?)",
            (DEFAULT_TRIAGE_PROMPT,)
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('compute_device', 'cpu')"
        )
        fts_migrated = conn.execute(
            "SELECT 1 FROM settings WHERE key = 'fts_migrated_v1'"
        ).fetchone()
        if not fts_migrated:
            conn.execute("INSERT INTO emails_fts(emails_fts) VALUES ('rebuild')")
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('fts_migrated_v1', '1')"
            )
        os.chmod(DB_PATH, 0o600)

        # One-time migration: accounts that already hold mail were synced
        # before sync_state existed, so treat them as initialized. Must be
        # one-time, or a partially finished first sync would be marked done.
        state_migrated = conn.execute(
            "SELECT 1 FROM settings WHERE key = 'sync_state_migrated_v1'"
        ).fetchone()
        if not state_migrated:
            conn.execute("""
                INSERT OR IGNORE INTO sync_state (account, initial_sync_done, last_internal_ts)
                SELECT account, 1,
                       MIN(COALESCE(MAX(timestamp), 0),
                           CAST(strftime('%s', 'now') AS INTEGER))
                FROM emails
                WHERE account IS NOT NULL AND account != ''
                GROUP BY account
            """)
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('sync_state_migrated_v1', '1')"
            )

        # One-time re-score of rows the old <60% fallback forced to "important".
        # Keep the visible label until the engine re-scores them, so mail never
        # vanishes from the feed during the upgrade.
        reset_done = conn.execute(
            "SELECT 1 FROM settings WHERE key = 'fallback_rescore_v2'"
        ).fetchone()
        if not reset_done:
            conn.execute(
                "UPDATE emails SET prompt_hash = NULL "
                "WHERE label = 'important' AND confidence IS NOT NULL AND confidence < ?",
                (LOW_CONFIDENCE_RELABEL_LIMIT,),
            )
            conn.execute(
                "INSERT INTO settings (key, value) VALUES ('fallback_rescore_v2', '1')"
            )

def get_setting(key: str, default: str = "") -> str:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default

def set_setting(key: str, value: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, str(value))
        )

LABEL_DISPLAY = {
    "very_important": "Very Important",
    "important": "Important",
    "low_priority": "Low Priority",
}

def format_email_dict(row: dict) -> dict:
    item = dict(row)
    item["label_display"] = LABEL_DISPLAY.get(item.get("label"), "Queued")

    item["unread"] = bool(item.get("unread", 0))
    item["account"] = item.get("account") or ""

    # Compute short date and full date
    ts = item.get("timestamp") or 0
    if ts:
        dt = datetime.datetime.fromtimestamp(ts)
        item["date_short"] = dt.strftime("%b %d")
        item["date_full"] = dt.strftime("%a %d %b, %H:%M")
    else:
        item["date_short"] = item.get("date_str", "")[:6]
        item["date_full"] = item.get("date_str", "")

    # Snippet: clean preview of message body without redundant header prefixes
    body = (item.get("body_text") or "").strip()
    if not body:
        raw = item.get("model_input") or ""
        lines = [l.strip() for l in raw.splitlines() if l.strip() and not l.lower().startswith(("from:", "subject:", "to:", "date:"))]
        body = " ".join(lines)
    item["snippet"] = " ".join(body[:1000].split())[:110]

    # Avatar initial
    sender_name = item.get("sender_name") or item.get("sender_email") or "User"
    item["avatar"] = sender_name.strip()[0].upper() if sender_name.strip() else "U"

    return item

def mark_email_read(email_id: str):
    """Marks locally-read so the Gmail mirror never flips it back to unread."""
    with get_db() as conn:
        conn.execute("UPDATE emails SET unread = 0 WHERE id = ?", (email_id,))
        conn.execute("INSERT OR IGNORE INTO local_reads (email_id) VALUES (?)", (email_id,))

def set_unread_states(account: str, unread_ids: set[str], read_ids: set[str]) -> int:
    """Bulk-mirrors Gmail read state; touches only rows in the wrong state."""
    changed = 0
    with get_db() as conn:
        for target, ids in ((1, unread_ids), (0, read_ids)):
            id_list = sorted(id for id in ids if id)
            for start in range(0, len(id_list), 500):
                chunk = id_list[start:start + 500]
                marks = ",".join("?" * len(chunk))
                cur = conn.execute(
                    f"UPDATE emails SET unread = ? WHERE account = ? AND unread != ? "
                    f"AND id IN ({marks})",
                    (target, account, target, *chunk),
                )
                changed += cur.rowcount
    return changed

def prune_missing_emails(account: str, keep_ids: set[str]) -> int:
    """Deletes rows for the account that are no longer in Gmail's inbox (archived/deleted there).

    Only call this when the full inbox was listed; otherwise rows beyond the
    sync window would be lost.
    """
    with get_db() as conn:
        ids = [r["id"] for r in conn.execute(
            "SELECT id FROM emails WHERE account = ?", (account,)
        ).fetchall()]
        stale = [i for i in ids if i not in keep_ids]
        if not stale:
            return 0
        removed = 0
        for start in range(0, len(stale), 500):
            chunk = stale[start:start + 500]
            marks = ",".join("?" * len(chunk))
            removed += conn.execute(
                f"DELETE FROM emails WHERE id IN ({marks})", chunk
            ).rowcount
        # Drop read-markers whose email is gone
        conn.execute("DELETE FROM local_reads WHERE email_id NOT IN (SELECT id FROM emails)")
        return removed

def get_sync_state(account: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute(
            "SELECT account, initial_sync_done, last_internal_ts "
            "FROM sync_state WHERE account = ?",
            (account,),
        ).fetchone()
        return dict(row) if row else None

def save_sync_state(account: str, initial_sync_done: bool, last_internal_ts: int):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO sync_state (account, initial_sync_done, last_internal_ts) "
            "VALUES (?, ?, ?) "
            "ON CONFLICT(account) DO UPDATE SET "
            "initial_sync_done = excluded.initial_sync_done, "
            "last_internal_ts = MAX(sync_state.last_internal_ts, excluded.last_internal_ts)",
            (account, 1 if initial_sync_done else 0, int(last_internal_ts or 0)),
        )

def get_feed_status() -> dict:
    """Cheap signature of the current inbox state for change detection."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(label IN ('important', 'very_important')), 0),
                COALESCE(SUM(label = 'very_important'), 0),
                COALESCE(SUM(label = 'low_priority'), 0),
                COUNT(*),
                COALESCE(SUM(unread = 1), 0),
                COALESCE(MAX(timestamp), 0)
            FROM emails
        """).fetchone()
    return {
        "important": row[0],
        "very_important": row[1],
        "low_priority": row[2],
        "total": row[3],
        "unread": row[4],
        "max_ts": row[5],
    }

def _counts_from_conn(conn, account: str = "") -> dict:
    where = " WHERE account = ?" if account else ""
    params = (account.strip(),) if account else ()
    stats = conn.execute(f"""
        SELECT
            COALESCE(SUM(label IN ('important', 'very_important')), 0),
            COALESCE(SUM(label = 'low_priority'), 0),
            COUNT(*),
            COALESCE(SUM(unread = 1), 0)
        FROM emails{where}
    """, params).fetchone()
    return {
        "important": stats[0],
        "low_priority": stats[1],
        "all": stats[2],
        "unread": stats[3],
    }

def get_counts(account: str = "") -> dict:
    with get_db() as conn:
        return _counts_from_conn(conn, account)

def get_email_by_id(email_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
        return format_email_dict(row) if row else None

def get_accounts(extra_accounts: list[str] | None = None) -> list[dict]:
    """Accounts with their mail counts, plus connected accounts that have not
    synced yet (so "Later" still leaves the new account visible)."""
    with get_db() as conn:
        rows = conn.execute("""
            SELECT 
                account,
                COUNT(*) as total,
                COALESCE(SUM(unread = 1), 0) as unread_count
            FROM emails
            WHERE account IS NOT NULL AND account != ''
            GROUP BY account
        """).fetchall()
    accounts = {r["account"]: dict(r) for r in rows}
    for account in extra_accounts or []:
        accounts.setdefault(account, {"account": account, "total": 0, "unread_count": 0})
    return sorted(accounts.values(), key=lambda a: (-a["total"], a["account"].lower()))

LIST_COLUMNS = (
    "id", "thread_id", "sender_name", "sender_email", "subject", "date_str",
    "timestamp", "model_input", "substr(body_text, 1, 1000) AS body_text",
    "label", "confidence", "prompt_hash", "unread", "account",
)  # body_html excluded (massive); body_text capped — only the 110-char snippet is shown

FEED_PAGE_SIZE = 50  # mails shown per page; the mirror keeps everything

def _page_numbers(current: int, pages: int, window: int = 2) -> list[int | None]:
    """Compact page list: first, last, and a window around the current page."""
    if pages <= 7:
        return list(range(1, pages + 1))
    numbers = {1, pages}
    for offset in range(-window, window + 1):
        if 1 <= current + offset <= pages:
            numbers.add(current + offset)
    result: list[int | None] = []
    previous = 0
    for number in sorted(numbers):
        if previous and number - previous > 1:
            result.append(None)
        result.append(number)
        previous = number
    return result

def _fts_query(query: str) -> str:
    terms = [t for t in query.strip().split() if any(c.isalnum() for c in t)]
    return " AND ".join(
        '"' + term.replace('"', '""') + '"*' for term in terms
    )

def fetch_emails(
    tab: str = "important",
    query: str = "",
    unread_only: bool = False,
    account: str = "",
    page: int = 1,
) -> tuple[list[dict], dict, dict]:
    with get_db() as conn:
        where = " WHERE 1=1"
        params: list = []

        if account:
            where += " AND account = ?"
            params.append(account.strip())

        if tab == "important":
            where += " AND label IN ('important', 'very_important')"
        elif tab == "low_priority":
            where += " AND label = 'low_priority'"
        # tab == "all": no label filter

        if unread_only:
            where += " AND unread = 1"

        if query:
            match = _fts_query(query)
            if match:
                where += " AND rowid IN (SELECT rowid FROM emails_fts WHERE emails_fts MATCH ?)"
                params.append(match)

        total = conn.execute(f"SELECT COUNT(*) FROM emails{where}", params).fetchone()[0]
        pages = max(1, (total + FEED_PAGE_SIZE - 1) // FEED_PAGE_SIZE)
        page = min(max(int(page or 1), 1), pages)
        offset = (page - 1) * FEED_PAGE_SIZE

        rows = conn.execute(
            f"SELECT {', '.join(LIST_COLUMNS)} FROM emails{where} "
            "ORDER BY timestamp DESC, rowid DESC LIMIT ? OFFSET ?",
            [*params, FEED_PAGE_SIZE, offset],
        ).fetchall()
        emails = [format_email_dict(r) for r in rows]

        counts = _counts_from_conn(conn, account)

    pager = {
        "page": page,
        "pages": pages,
        "total": total,
        "per_page": FEED_PAGE_SIZE,
        "start": offset + 1 if total else 0,
        "end": min(offset + FEED_PAGE_SIZE, total),
        "page_numbers": _page_numbers(page, pages),
    }
    return emails, counts, pager
