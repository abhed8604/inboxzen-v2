import asyncio
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from app.config import (
    SYNC_INTERVAL_SECONDS,
    CREDENTIALS_FILE,
    DEFAULT_TRIAGE_PROMPT,
    get_bundle_dir,
    is_model_downloaded,
    get_compute_device,
    has_nvidia_gpu,
    get_nvidia_gpu_name,
    is_cuda_installed,
)
from app.db import (
    init_db,
    get_setting,
    set_setting,
    fetch_emails,
    get_email_by_id,
    mark_email_read,
    get_accounts,
)
from app.classifier import (
    start_llama_server,
    is_llama_healthy,
    stop_llama_server,
    restart_llama_server,
    install_cuda_runtime,
    cuda_download_state,
    model_download_state,
    download_model_file,
)
from app.auth import is_authenticated
from app.gmail_sync import run_sync_and_classify

templates = Jinja2Templates(directory=str(get_bundle_dir() / "app" / "templates"))

async def auto_sync_loop(app: FastAPI):
    while True:
        try:
            if is_authenticated():
                await run_sync_and_classify(app.state.http_client, fetch_gmail=True)
        except Exception:
            pass
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    app.state.http_client = httpx.AsyncClient(limits=httpx.Limits(max_connections=5))
    if is_model_downloaded():
        asyncio.create_task(start_llama_server(app.state.http_client))
    sync_task = asyncio.create_task(auto_sync_loop(app))
    yield
    sync_task.cancel()
    await app.state.http_client.aclose()
    stop_llama_server()

app = FastAPI(title="InboxZen", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(get_bundle_dir() / "app" / "static")), name="static")

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
    email_data = get_email_by_id(email_id)
    return templates.TemplateResponse(request, "partials/email_view.html", {
        "email": email_data,
    })

@app.get("/api/engine/status")
async def engine_status(request: Request):
    http_client = getattr(request.app.state, "http_client", None)
    healthy = await is_llama_healthy(http_client) if http_client else False
    cached = is_model_downloaded()
    compute_dev = get_compute_device()
    gpu_name = get_nvidia_gpu_name()
    device_label = (gpu_name or "NVIDIA GPU") if compute_dev == "gpu" else "CPU"

    if healthy:
        status = "ready"
        message = f"Online ({device_label})"
    elif not cached:
        status = "downloading"
        message = "Downloading model (first launch)..."
    else:
        status = "offline"
        message = "Engine Paused"

    return JSONResponse({
        "healthy": healthy,
        "status": status,
        "message": message,
        "model": "vllm-d3-lite:Q8_0",
        "compute_device": compute_dev,
        "device": device_label,
    })

@app.post("/api/settings/compute")
async def update_compute_setting(request: Request, device: str = Form(...)):
    target = "gpu" if device == "gpu" else "cpu"
    set_setting("compute_device", target)
    http_client = getattr(request.app.state, "http_client", None)
    if http_client:
        asyncio.create_task(restart_llama_server(http_client))
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
    http_client = getattr(request.app.state, "http_client", None)
    if http_client and target == "gpu" and is_cuda_installed():
        asyncio.create_task(restart_llama_server(http_client))
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
    asyncio.create_task(install_cuda_runtime())
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
    async def run_download_and_start():
        await download_model_file()
        http_client = getattr(request.app.state, "http_client", None)
        if http_client:
            await start_llama_server(http_client)
    asyncio.create_task(run_download_and_start())
    return JSONResponse({"status": "started"})

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
    set_setting("triage_prompt", triage_prompt.strip())
    asyncio.create_task(run_sync_and_classify(request.app.state.http_client, fetch_gmail=False))
    emails, counts = fetch_emails(tab=tab, unread_only=bool(unread), account=account)
    return templates.TemplateResponse(request, "partials/email_feed.html", {
        "emails": emails,
        "counts": counts,
        "current_tab": tab,
        "unread_only": bool(unread),
        "selected_account": account,
    })
