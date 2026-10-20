import datetime
import sqlite3
from contextlib import contextmanager
from app.config import DB_PATH, DEFAULT_TRIAGE_PROMPT

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

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS local_reads (
                email_id TEXT PRIMARY KEY
            );
        """)

        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('triage_prompt', ?)",
            (DEFAULT_TRIAGE_PROMPT,)
        )
        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('compute_device', 'cpu')"
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
    item["snippet"] = " ".join(body.split())[:110]

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

def get_feed_status() -> dict:
    """Cheap signature of the current inbox state for change detection."""
    with get_db() as conn:
        row = conn.execute("""
            SELECT
                COALESCE(SUM(label IN ('important', 'very_important')), 0),
                COALESCE(SUM(label = 'low_priority'), 0),
                COUNT(*),
                COALESCE(SUM(unread = 1), 0),
                COALESCE(MAX(timestamp), 0)
            FROM emails
        """).fetchone()
    return {
        "important": row[0],
        "low_priority": row[1],
        "total": row[2],
        "unread": row[3],
        "max_ts": row[4],
    }

def get_email_by_id(email_id: str) -> dict | None:
    with get_db() as conn:
        row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
        return format_email_dict(row) if row else None

def get_accounts() -> list[dict]:
    with get_db() as conn:
        rows = conn.execute("""
            SELECT 
                account,
                COUNT(*) as total,
                COALESCE(SUM(unread = 1), 0) as unread_count
            FROM emails
            WHERE account IS NOT NULL AND account != ''
            GROUP BY account
            ORDER BY total DESC
        """).fetchall()
        return [dict(r) for r in rows]

LIST_COLUMNS = (
    "id", "thread_id", "sender_name", "sender_email", "subject", "date_str",
    "timestamp", "model_input", "body_text", "label", "confidence",
    "prompt_hash", "unread", "account",
)  # body_html deliberately excluded: massive, only needed by the reader view

def fetch_emails(
    tab: str = "important",
    query: str = "",
    unread_only: bool = False,
    account: str = "",
    limit: int = 100
) -> tuple[list[dict], dict]:
    with get_db() as conn:
        base_sql = f"SELECT {', '.join(LIST_COLUMNS)} FROM emails WHERE 1=1"
        params: list = []

        if account:
            base_sql += " AND account = ?"
            params.append(account.strip())

        if tab == "important":
            base_sql += " AND label IN ('important', 'very_important')"
        elif tab == "low_priority":
            base_sql += " AND label = 'low_priority'"
        # tab == "all": no label filter

        if unread_only:
            base_sql += " AND unread = 1"

        if query:
            q_like = f"%{query.strip().lower()}%"
            base_sql += " AND (LOWER(sender_name) LIKE ? OR LOWER(sender_email) LIKE ? OR LOWER(subject) LIKE ? OR LOWER(model_input) LIKE ?)"
            params.extend([q_like, q_like, q_like, q_like])

        base_sql += " ORDER BY timestamp DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(base_sql, params).fetchall()
        emails = [format_email_dict(r) for r in rows]

        stats_where = " WHERE account = ?" if account else ""
        stats_params = (account.strip(),) if account else ()
        stats = conn.execute(f"""
            SELECT 
                COALESCE(SUM(label IN ('important', 'very_important')), 0),
                COALESCE(SUM(label = 'low_priority'), 0),
                COUNT(*),
                COALESCE(SUM(unread = 1), 0)
            FROM emails{stats_where}
        """, stats_params).fetchone()

        counts = {
            "important": stats[0],
            "low_priority": stats[1],
            "all": stats[2],
            "unread": stats[3],
        }

    return emails, counts
