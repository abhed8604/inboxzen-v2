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
                model_input TEXT,    -- 1500-char clean text sent to vllm-d3-lite
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

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)

        try:
            conn.execute("ALTER TABLE emails ADD COLUMN unread INTEGER DEFAULT 1;")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("ALTER TABLE emails ADD COLUMN account TEXT DEFAULT '';")
        except sqlite3.OperationalError:
            pass

        try:
            conn.execute("CREATE INDEX IF NOT EXISTS idx_emails_account ON emails(account);")
        except sqlite3.OperationalError:
            pass

        conn.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES ('triage_prompt', ?)",
            (DEFAULT_TRIAGE_PROMPT,)
        )

def get_triage_prompt() -> str:
    with get_db() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key = 'triage_prompt'").fetchone()
        return row["value"] if row else DEFAULT_TRIAGE_PROMPT

def set_triage_prompt(prompt: str):
    with get_db() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES ('triage_prompt', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (prompt.strip(),)
        )

def format_email_dict(row: dict) -> dict:
    item = dict(row)
    label = item.get("label") or "important"
    if label == "very_important":
        item["label_display"] = "Very Important"
    elif label == "important":
        item["label_display"] = "Important"
    elif label == "low_priority":
        item["label_display"] = "Low Priority"
    else:
        item["label_display"] = "Queued"

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
    with get_db() as conn:
        conn.execute("UPDATE emails SET unread = 0 WHERE id = ?", (email_id,))

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

def fetch_emails(
    tab: str = "important",
    query: str = "",
    unread_only: bool = False,
    account: str = "",
    limit: int = 100
) -> tuple[list[dict], dict]:
    with get_db() as conn:
        base_sql = "SELECT * FROM emails WHERE 1=1"
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

        if account:
            stats_sql = """
                SELECT 
                    COALESCE(SUM(label IN ('important', 'very_important')), 0),
                    COALESCE(SUM(label = 'low_priority'), 0),
                    COUNT(*),
                    COALESCE(SUM(unread = 1), 0)
                FROM emails
                WHERE account = ?
            """
            stats = conn.execute(stats_sql, (account.strip(),)).fetchone()
        else:
            stats_sql = """
                SELECT 
                    COALESCE(SUM(label IN ('important', 'very_important')), 0),
                    COALESCE(SUM(label = 'low_priority'), 0),
                    COUNT(*),
                    COALESCE(SUM(unread = 1), 0)
                FROM emails
            """
            stats = conn.execute(stats_sql).fetchone()

        counts = {
            "important": stats[0],
            "low_priority": stats[1],
            "all": stats[2],
            "unread": stats[3],
        }

    return emails, counts
