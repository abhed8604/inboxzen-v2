import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import (
    SYNC_INTERVAL_SECONDS,
    CREDENTIALS_FILE,
    DEFAULT_TRIAGE_PROMPT,
    MODEL_DISPLAY_NAME,
    TRIAGE_PROMPT_MAX_CHARS,
    get_bundle_dir,
    is_model_downloaded,
    get_compute_device,
    has_nvidia_gpu,
    get_nvidia_gpu_name,
    is_cuda_installed,
    compute_prompt_hash,
    setup_logging,
)
from app import tasks
from app.db import (
    init_db,
    get_setting,
    set_setting,
    fetch_emails,
    get_email_by_id,
    mark_email_read,
    get_accounts,
    get_feed_status,
    get_db,
)
from app.classifier import (
    start_llama_server,
    is_llama_healthy,
    stop_llama_server,
    restart_llama_server,
    ensure_engine_alive,
    ensure_engine_started,
    classify_email,
    install_cuda_runtime,
    cuda_download_state,
    model_download_state,
    download_model_file,
    get_llama_last_error,
)
from app.auth import is_authenticated, get_stored_accounts, connect_account, migrate_legacy_token
from app.gmail_sync import (
    run_sync_and_classify,
    rescan_last_items,
    get_rescan_progress,
    reset_rescan_state,
    RESCAN_LIMIT,
)
templates = Jinja2Templates(directory=str(get_bundle_dir() / "app" / "templates"))
log = logging.getLogger(__name__)

async def engine_watchdog_loop(client):
    """Keeps llama-server alive between sessions (crash, OOM-kill, etc.)."""
    while True:
        await asyncio.sleep(60)
        try:
            await ensure_engine_alive(client)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Engine watchdog iteration failed")

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    log.info("InboxZen starting")
    init_db()
    app.state.http_client = httpx.AsyncClient(limits=httpx.Limits(max_connections=5))
    await asyncio.to_thread(migrate_legacy_token)
    tasks.spawn(engine_watchdog_loop(app.state.http_client))
    sync_task = asyncio.create_task(auto_sync_loop(app))
    yield
    sync_task.cancel()
    await tasks.cancel_all()
    await app.state.http_client.aclose()
    stop_llama_server()
    log.info("InboxZen stopped")

async def auto_sync_loop(app: FastAPI):
    while True:
        try:
            if is_authenticated():
                await run_sync_and_classify(app.state.http_client, fetch_gmail=True)
        except httpx.RequestError:
            log.warning("Auto-sync skipped: engine or network unavailable")
        except Exception:
            log.exception("Auto-sync failed")
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)

app = FastAPI(title="InboxZen", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(get_bundle_dir() / "app" / "static")), name="static")

# The app only ever talks to the local browser/webview. Anything else claiming
# our port (drive-by fetch, DNS rebinding via a foreign Host) must bounce.
_LOCAL_HOSTNAMES = {"127.0.0.1", "localhost", "::1"}

def loopback_guard_decision(request: Request) -> JSONResponse | None:
    host = request.headers.get("host", "")
    hostname = host.rsplit(":", 1)[0].strip("[]").lower()
    if hostname not in _LOCAL_HOSTNAMES:
        return JSONResponse({"status": "forbidden", "reason": "bad host"}, status_code=403)
    origin = request.headers.get("origin")
    if origin:
        origin_host = (urlparse(origin).hostname or "").lower()
        if origin_host not in _LOCAL_HOSTNAMES:
            return JSONResponse({"status": "forbidden", "reason": "bad origin"}, status_code=403)
    return None

@app.middleware("http")
async def loopback_guard(request: Request, call_next):
    decision = loopback_guard_decision(request)
    if decision:
        return decision
    return await call_next(request)

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
    server_ok = await is_llama_healthy(request.app.state.http_client)
    first_email = emails[0] if emails else None
    accounts = get_accounts()
    has_credentials = CREDENTIALS_FILE.exists()
    current_theme = request.cookies.get("iz-theme", "dark")
    onboarding_done = get_setting("onboarding_completed", "0") == "1"

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
        "triage_prompt": get_setting("triage_prompt", DEFAULT_TRIAGE_PROMPT),
        "server_ok": server_ok,
        "current_theme": current_theme,
        "show_onboarding": not onboarding_done,
        "compute_device": get_compute_device(),
        "has_nvidia": has_nvidia_gpu(),
        "gpu_name": get_nvidia_gpu_name(),
        "cuda_installed": is_cuda_installed(),
        "model_downloaded": is_model_downloaded(),
    })

def _feed_context(
    request: Request,
    tab: str,
    q: str,
    unread: int,
    account: str,
) -> dict:
    """Builds the shared context for all email_feed partial responses."""
    unread_only = bool(unread)
    emails, counts = fetch_emails(tab=tab, query=q, unread_only=unread_only, account=account)
    ctx = {
        "request": request,
        "emails": emails,
        "counts": counts,
        "current_tab": tab,
        "unread_only": unread_only,
        "search_query": q,
        "selected_email": emails[0] if emails else None,
        "selected_account": account,
    }
    return ctx

def _feed_template(ctx: dict):
    return templates.TemplateResponse(request=ctx["request"], name="partials/email_feed.html", context={
        k: v for k, v in ctx.items() if k != "request"
    })

@app.get("/emails", response_class=HTMLResponse)
async def list_emails_partial(
    request: Request,
    tab: str = "important",
    q: str = "",
    unread: int = 0,
    account: str = "",
):
    return _feed_template(_feed_context(request, tab, q, unread, account))

@app.get("/emails/{email_id}", response_class=HTMLResponse)
async def view_email_in_app(request: Request, email_id: str):
    email_data = get_email_by_id(email_id)
    return templates.TemplateResponse(request, "partials/email_view.html", {
        "email": email_data,
    })

@app.post("/emails/{email_id}/read")
async def mark_read_endpoint(email_id: str):
    mark_email_read(email_id)
    return {"status": "ok"}

@app.post("/emails/{email_id}/scan", response_class=HTMLResponse)
async def scan_email_endpoint(request: Request, email_id: str):
    """Re-classifies the currently open email and re-renders the reader panel."""
    email_data = get_email_by_id(email_id)
    if not email_data or not email_data.get("model_input"):
        return templates.TemplateResponse(request, "partials/email_view.html", {"email": email_data})
    client = request.app.state.http_client
    if await ensure_engine_started(client):
        triage_prompt = get_setting("triage_prompt", DEFAULT_TRIAGE_PROMPT)
        current_hash = compute_prompt_hash(triage_prompt)
        row = dict(email_data)
        try:
            label, prob = await classify_email(client, row, triage_prompt)
            with get_db() as conn:
                conn.execute(
                    "UPDATE emails SET label = ?, confidence = ?, prompt_hash = ? WHERE id = ?",
                    (label, prob, current_hash, email_id),
                )
        except Exception:
            log.exception("Scan failed for %s", email_id)
    email_data = get_email_by_id(email_id)
    return templates.TemplateResponse(request, "partials/email_view.html", {"email": email_data})

@app.get("/api/engine/status")
async def engine_status(request: Request):
    healthy = await is_llama_healthy(request.app.state.http_client)
    cached = is_model_downloaded()
    compute_dev = get_compute_device()
    gpu_name = get_nvidia_gpu_name()
    device_label = (gpu_name or "NVIDIA GPU") if compute_dev == "gpu" else "CPU"

    last_error = get_llama_last_error()
    download_state = model_download_state.get("status")
    if healthy:
        status = "ready"
        message = f"Online ({device_label})"
    elif not cached:
        if download_state == "downloading":
            status = "downloading"
            message = model_download_state.get("message") or "Downloading model (first launch)..."
        elif download_state == "error":
            status = "error"
            message = f"Model download failed: {model_download_state.get('error') or 'unknown error'}"
        else:
            status = "offline"
            message = "Model not on disk — download it in setup"
    elif last_error:
        status = "error"
        message = f"Engine Error: {last_error}"
    else:
        status = "offline"
        message = "Offline — engine loads when needed"

    return JSONResponse({
        "healthy": healthy,
        "status": status,
        "message": message,
        "model": MODEL_DISPLAY_NAME,
        "compute_device": compute_dev,
        "device": device_label,
    })

@app.post("/api/settings/compute")
async def update_compute_setting(request: Request, device: str = Form(...)):
    target = "gpu" if device == "gpu" else "cpu"
    if get_compute_device() == target:
        return JSONResponse({
            "status": "ok",
            "compute_device": target,
            "cuda_installed": is_cuda_installed(),
        })
    set_setting("compute_device", target)
    log.info("Compute device switched to %s; restarting engine", target)
    tasks.spawn(restart_llama_server(request.app.state.http_client))
    return JSONResponse({
        "status": "ok",
        "compute_device": target,
        "cuda_installed": is_cuda_installed(),
    })

@app.post("/api/onboarding/complete")
async def complete_onboarding_route(request: Request, device: str = Form("cpu")):
    target = "gpu" if device == "gpu" else "cpu"
    set_setting("compute_device", target)
    set_setting("onboarding_completed", "1")
    if target == "gpu" and is_cuda_installed():
        tasks.spawn(restart_llama_server(request.app.state.http_client))
    return JSONResponse({"status": "ok"})

@app.get("/api/cuda/status")
async def get_cuda_status():
    installed = is_cuda_installed()
    return JSONResponse({
        "installed": installed,
        "state": cuda_download_state,
    })

@app.post("/api/cuda/install")
async def install_cuda_endpoint():
    tasks.spawn(install_cuda_runtime())
    return JSONResponse({"status": "started"})

@app.get("/api/model/status")
async def get_model_status():
    downloaded = is_model_downloaded()
    return JSONResponse({
        "downloaded": downloaded,
        "state": model_download_state,
    })

@app.post("/api/model/download")
async def trigger_model_download(request: Request):
    if model_download_state["status"] == "downloading":
        return JSONResponse({"status": "busy"})
    # Set the state here, not inside the spawned task: a rapid second POST
    # must see "downloading" instead of racing into a second download.
    model_download_state.update(status="downloading", percent=0, message="Starting download...", error=None)
    async def run_download_and_start():
        await download_model_file()
        await start_llama_server(request.app.state.http_client)
    tasks.spawn(run_download_and_start())
    return JSONResponse({"status": "started"})

@app.get("/api/accounts")
async def list_account_auth_status():
    return JSONResponse({
        "accounts": get_stored_accounts(),
        "authenticated": is_authenticated(),
    })

@app.post("/api/accounts/connect")
async def connect_account_endpoint():
    log.info("Account connect requested (OAuth browser flow)")
    email = await asyncio.to_thread(connect_account)
    if email:
        return JSONResponse({
            "status": "ok",
            "account": email,
            "accounts": get_stored_accounts(),
        })
    return JSONResponse({"status": "error", "message": "OAuth connect failed"}, status_code=400)

@app.post("/sync", response_class=HTMLResponse)
async def manual_sync(
    request: Request,
    tab: str = Form("important"),
    q: str = Form(""),
    unread: int = Form(0),
    account: str = Form(""),
):
    log.info("Manual sync triggered (running in background)")
    tasks.spawn(run_sync_and_classify(request.app.state.http_client, fetch_gmail=True, interactive=True))
    return _feed_template(_feed_context(request, tab, q, unread, account))

@app.get("/api/feed/status")
async def feed_status():
    return JSONResponse(get_feed_status())

@app.post("/rescan", response_class=HTMLResponse)
async def rescan_inbox(
    request: Request,
    tab: str = Form("important"),
    q: str = Form(""),
    unread: int = Form(0),
    account: str = Form(""),
):
    log.info("Manual rescan triggered (newest %d mails, background)", RESCAN_LIMIT)
    reset_rescan_state()
    tasks.spawn(rescan_last_items(request.app.state.http_client, RESCAN_LIMIT))
    return _feed_template(_feed_context(request, tab, q, unread, account))

@app.get("/api/rescan/progress")
async def rescan_progress():
    return JSONResponse(get_rescan_progress())

@app.post("/settings/prompt", response_class=HTMLResponse)
async def update_prompt(
    request: Request,
    triage_prompt: str = Form(...),
    tab: str = Form("important"),
    unread: int = Form(0),
    account: str = Form(""),
):
    prompt = triage_prompt.strip()
    # Reject before persisting: an over-cap prompt would otherwise be silently
    # truncated at classification time, so part of the user's rules never applies.
    if len(prompt) > TRIAGE_PROMPT_MAX_CHARS:
        return JSONResponse(
            {
                "status": "error",
                "message": f"Instructions too long ({len(prompt)} chars). Limit is {TRIAGE_PROMPT_MAX_CHARS} characters.",
            },
            status_code=400,
        )
    set_setting("triage_prompt", prompt)
    log.info("Triage prompt updated; re-scoring newest %d mails", RESCAN_LIMIT)
    reset_rescan_state()
    tasks.spawn(rescan_last_items(request.app.state.http_client, RESCAN_LIMIT))
    return _feed_template(_feed_context(request, tab, "", unread, account))
