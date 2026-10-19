import asyncio
from contextlib import asynccontextmanager
import markdown
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import SYNC_INTERVAL_SECONDS, CREDENTIALS_FILE
from app.db import (
    init_db,
    get_db,
    get_triage_prompt,
    set_triage_prompt,
    fetch_emails,
    format_email_dict,
    mark_email_read,
    get_accounts,
)
from app.classifier import start_llama_server, is_llama_healthy, stop_llama_server
from app.gmail_sync import run_sync_and_classify

templates = Jinja2Templates(directory="app/templates")

async def auto_sync_loop(app: FastAPI):
    while True:
        try:
            await run_sync_and_classify(app.state.http_client, fetch_gmail=True, interactive=False)
        except Exception:
            pass
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.http_client = httpx.AsyncClient(limits=httpx.Limits(max_connections=5))
    await start_llama_server(app.state.http_client)
    sync_task = asyncio.create_task(auto_sync_loop(app))
    yield
    sync_task.cancel()
    await app.state.http_client.aclose()
    stop_llama_server()

app = FastAPI(title="InboxZen", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    tab: str = "important",
    q: str = "",
    unread: int = 0,
    account: str = "",
):
    unread_only = bool(unread)
    emails, counts = fetch_emails(tab=tab, query=q, unread_only=unread_only, account=account)
    http_client = getattr(request.app.state, "http_client", None)
    server_ok = await is_llama_healthy(http_client) if http_client else False
    first_email = emails[0] if emails else None
    accounts = get_accounts()
    has_credentials = CREDENTIALS_FILE.exists()
    current_theme = request.cookies.get("iz-theme", "dark")

    return templates.TemplateResponse(request, "index.html", {
        "emails": emails,
        "counts": counts,
        "current_tab": tab,
        "search_query": q,
        "unread_only": unread_only,
        "selected_email": first_email,
        "selected_account": account,
        "accounts": accounts,
        "has_credentials": has_credentials,
        "triage_prompt": get_triage_prompt(),
        "server_ok": server_ok,
        "current_theme": current_theme,
    })

@app.get("/emails", response_class=HTMLResponse)
async def list_emails_partial(
    request: Request,
    tab: str = "important",
    q: str = "",
    unread: int = 0,
    account: str = "",
):
    unread_only = bool(unread)
    emails, counts = fetch_emails(tab=tab, query=q, unread_only=unread_only, account=account)
    first_email = emails[0] if emails else None
    return templates.TemplateResponse(request, "partials/email_feed.html", {
        "emails": emails,
        "counts": counts,
        "current_tab": tab,
        "unread_only": unread_only,
        "selected_email": first_email,
        "selected_account": account,
    })

@app.get("/emails/{email_id}", response_class=HTMLResponse)
async def view_email_in_app(request: Request, email_id: str):
    mark_email_read(email_id)
    with get_db() as conn:
        row = conn.execute("SELECT * FROM emails WHERE id = ?", (email_id,)).fetchone()
    email_data = format_email_dict(row) if row else None
    return templates.TemplateResponse(request, "partials/email_view.html", {
        "email": email_data,
    })

@app.get("/api/engine/status")
async def engine_status(request: Request):
    http_client = getattr(request.app.state, "http_client", None)
    healthy = await is_llama_healthy(http_client) if http_client else False
    return JSONResponse({
        "healthy": healthy,
        "model": "vllm-d3-lite:Q8_0",
        "device": "GTX 1650 (4 GB)",
    })

@app.post("/sync", response_class=HTMLResponse)
async def manual_sync(
    request: Request,
    tab: str = Form("important"),
    q: str = Form(""),
    unread: int = Form(0),
    account: str = Form(""),
):
    await run_sync_and_classify(request.app.state.http_client, fetch_gmail=True)
    emails, counts = fetch_emails(tab=tab, query=q, unread_only=bool(unread), account=account)
    first_email = emails[0] if emails else None
    return templates.TemplateResponse(request, "partials/email_feed.html", {
        "emails": emails,
        "counts": counts,
        "current_tab": tab,
        "unread_only": bool(unread),
        "selected_email": first_email,
        "selected_account": account,
    })

@app.post("/rescan", response_class=HTMLResponse)
async def rescan_inbox(
    request: Request,
    tab: str = Form("important"),
    q: str = Form(""),
    unread: int = Form(0),
    account: str = Form(""),
):
    await run_sync_and_classify(request.app.state.http_client, fetch_gmail=False)
    emails, counts = fetch_emails(tab=tab, query=q, unread_only=bool(unread), account=account)
    first_email = emails[0] if emails else None
    return templates.TemplateResponse(request, "partials/email_feed.html", {
        "emails": emails,
        "counts": counts,
        "current_tab": tab,
        "unread_only": bool(unread),
        "selected_email": first_email,
        "selected_account": account,
    })

@app.post("/settings/prompt", response_class=HTMLResponse)
async def update_prompt(
    request: Request,
    triage_prompt: str = Form(...),
    tab: str = Form("important"),
    unread: int = Form(0),
    account: str = Form(""),
):
    set_triage_prompt(triage_prompt)
    asyncio.create_task(run_sync_and_classify(request.app.state.http_client, fetch_gmail=False))
    emails, counts = fetch_emails(tab=tab, unread_only=bool(unread), account=account)
    return templates.TemplateResponse(request, "partials/email_feed.html", {
        "emails": emails,
        "counts": counts,
        "current_tab": tab,
        "unread_only": bool(unread),
        "selected_account": account,
    })
