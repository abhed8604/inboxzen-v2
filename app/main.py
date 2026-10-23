import asyncio
import json
import logging
import os
import secrets
from contextlib import asynccontextmanager
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request, Response, Form, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.config import (
    SYNC_INTERVAL_SECONDS,
    DATA_DIR,
    get_credentials_file,
    DEFAULT_TRIAGE_PROMPT,
    MODEL_DISPLAY_NAME,
    TRIAGE_PROMPT_MAX_CHARS,
    SESSION_COOKIE,
    SESSION_TOKEN,
    get_bundle_dir,
    is_model_downloaded,
    get_compute_device,
    get_effective_device,
    has_nvidia_gpu,
    get_nvidia_gpu_name,
    is_cuda_installed,
    compute_prompt_hash,
    setup_logging,
)
from app import tasks
from app import classifier as classifier_mod
from app.db import (
    init_db,
    get_setting,
    set_setting,
    fetch_emails,
    get_email_by_id,
    mark_email_read,
    get_accounts,
    get_counts,
    get_feed_status,
    get_db,
    get_sync_state,
)
from app.classifier import (
    is_llama_healthy,
    stop_llama_server,
    restart_llama_server,
    ensure_engine_started,
    ensure_engine_alive,
    engine_use,
    idle_unload_loop,
    classify_email,
    install_cuda_runtime,
    start_llama_server,
    download_model_file,
    get_llama_last_error,
)
from app.auth import (is_authenticated, connect_account, get_stored_accounts,
                      migrate_legacy_token, remove_account)
from app.gmail_sync import (
    run_sync_and_classify,
    rescan_last_items,
    drain_classification,
    get_rescan_progress,
    reset_rescan_state,
    rescan_in_progress,
    get_sync_progress,
    reset_sync_state,
    sync_in_progress,
    sync_lock,
    request_sync_cancel,
    request_rescan_cancel,
    RESCAN_LIMIT,
    FIRST_SYNC_CAP,
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
    app.state.onboard_device = get_compute_device()
    app.state.onboard_phase = None      # None | cuda | model | error | done
    app.state.onboard_done = {}
    app.state.onboard_error = ""
    await asyncio.to_thread(migrate_legacy_token)
    await asyncio.to_thread(classifier_mod.repair_cuda_layout)
    if get_compute_device() == "gpu" and not is_cuda_installed():
        log.info("GPU selected but CUDA is incomplete; installing it automatically")
        tasks.spawn(_install_cuda_then_restart(app.state.http_client))
    tasks.spawn(engine_watchdog_loop(app.state.http_client))
    tasks.spawn(idle_unload_loop())
    sync_task = asyncio.create_task(auto_sync_loop(app))
    yield
    sync_task.cancel()
    await tasks.cancel_all()
    await app.state.http_client.aclose()
    stop_llama_server()
    log.info("InboxZen stopped")

async def _install_cuda_then_restart(client):
    """Installs the missing CUDA pieces and only then relaunches the engine, so
    it comes up with -ngl 99 instead of starting on the CPU first."""
    await install_cuda_runtime()
    if (classifier_mod.cuda_download_state.get("status") == "ready"
            and get_compute_device() == "gpu" and is_model_downloaded()):
        await restart_llama_server(client)


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

def session_token_ok(request: Request) -> bool:
    token = request.query_params.get("token") or request.cookies.get(SESSION_COOKIE, "")
    return bool(token) and secrets.compare_digest(token, SESSION_TOKEN)

@app.middleware("http")
async def loopback_guard(request: Request, call_next):
    decision = loopback_guard_decision(request)
    if decision:
        return decision
    if not request.url.path.startswith("/static/") and not session_token_ok(request):
        return JSONResponse({"status": "forbidden", "reason": "bad token"}, status_code=403)
    response = await call_next(request)
    if request.query_params.get("token"):
        response.set_cookie(SESSION_COOKIE, SESSION_TOKEN, httponly=True,
                            samesite="lax", max_age=31536000)
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response

# ---------------------------------------------------------------------------
# Fragment helpers
# ---------------------------------------------------------------------------

def _render(request: Request, name: str, **ctx):
    return templates.TemplateResponse(request, name, ctx)

async def _filter_params(request: Request) -> tuple:
    """Merges query params and form fields (htmx puts included inputs there)."""
    form: dict = {}
    if request.method == "POST":
        form = dict(await request.form())
    def pick(key, default):
        v = request.query_params.get(key, None)
        if v is None:
            v = form.get(key, default)
        return v
    tab = pick("tab", "important") or "important"
    q = pick("q", "") or ""
    rq = pick("unread", 0)
    try:
        unread = int(bool(int(rq)))
    except (TypeError, ValueError):
        unread = 0
    account = pick("account", "") or ""
    try:
        page = max(1, int(pick("page", 1) or 1))
    except (TypeError, ValueError):
        page = 1
    return tab, q, unread, account, page

async def _reader_id(request) -> str | None:
    """The mail the reader currently shows (query param or posted form)."""
    value = request.query_params.get("reader_id")
    if value:
        return value
    if request.method == "POST":
        form = await request.form()
        value = form.get("reader_id")
        if value:
            return value
    return None


async def _reader_state(request) -> str:
    """Label+confidence the reader currently shows, so the server can tell
    that a background re-score changed the open mail."""
    value = request.query_params.get("reader_state")
    if not value and request.method == "POST":
        form = await request.form()
        value = form.get("reader_state")
    return value or ""


def _accounts_with_tokens() -> list[dict]:
    """DB counts plus connected accounts still waiting for their first sync."""
    return get_accounts(get_stored_accounts())

def _feed_signature() -> str:
    return json.dumps(get_feed_status(), sort_keys=True)

def _feed_ctx(request: Request, tab: str, q: str, unread: int, account: str,
              page: int = 1, reader_id: str | None = None, reader_state: str = ""):
    """Feed context; replicas the old JS afterSwap selection logic: the email
    the user is reading stays open while alive in the filtered list, else the
    first email becomes the open one, and the reader re-renders only then.
    While searching, an open mail outside the results stays in the reader."""
    unread_only = bool(unread)
    searching = bool(q.strip())
    emails, counts, pager = fetch_emails(
        tab=tab, query=q, unread_only=unread_only, account=account, page=page
    )
    active = None
    if reader_id:
        active = next((e for e in emails if e["id"] == reader_id), None)
        if active is None and searching:
            active = get_email_by_id(reader_id)
    if active is None:
        active = emails[0] if emails else None
    # Feed rows deliberately exclude body_html (list perf); the reader pane
    # needs the full row so the initial auto-open renders the HTML view too.
    if active is not None and "body_html" not in active:
        active = get_email_by_id(active["id"]) or active
    render_reader = reader_id is None or active is None or active["id"] != reader_id
    # The open mail was re-scored in the background: refresh the reader too.
    if not render_reader and reader_state:
        label = active.get("label") or ""
        confidence = active.get("confidence")
        current = f"{label}|{'' if confidence is None else confidence}"
        if current != reader_state:
            render_reader = True
    return {
        "emails": emails,
        "counts": counts,
        "pager": pager,
        "current_tab": tab,
        "unread_only": unread_only,
        "search_query": q,
        "selected_account": account,
        "selected_email": active,
        "open_email": active,
        "render_reader": render_reader,
        "reader_id": reader_id,
        "feed_sig": _feed_signature(),
        "accounts": _accounts_with_tokens(),
    }

def _cuda_view(state: dict) -> dict:
    """Turns the downloader state into what the UI shows (one place, so the
    Engine pane and the CUDA box can never disagree)."""
    status = state.get("status", "idle")
    if status == "completed":
        status = "ready"
    percent = state.get("percent", 0)
    line = state.get("message") or ""
    if status == "downloading":
        line = line or f"Downloading CUDA libraries ({percent}%)…"
    elif status == "extracting":
        line = line or "Extracting CUDA libraries…"
    elif status == "ready":
        line = "CUDA backend installed — GPU ready!"
    error = ""
    if status == "error":
        error = state.get("message") or "Download failed"
    return {
        "cuda_state": status,
        "cuda_percent": percent,
        "cuda_status": line,
        "cuda_error": error,
    }


async def _engine_snapshot(client) -> dict:
    """Replicates the exact state machine of the old JS poller: the footer
    indicator and the settings modal stat block, including strings."""
    healthy = await is_llama_healthy(client)
    cached = is_model_downloaded()
    md = classifier_mod.model_download_state
    last_error = get_llama_last_error()
    # Report the device the engine really uses, not the stored preference:
    # "gpu" without the CUDA runtime still runs on the CPU.
    device_label = "NVIDIA GPU" if get_effective_device() == "gpu" else "CPU"

    if healthy:
        status, message = "ready", f"Online ({device_label})"
    elif not cached:
        if md.get("status") == "downloading":
            status = "downloading"
            message = md.get("message") or "Downloading model (first launch)..."
        elif md.get("status") == "error":
            status = "error"
            message = f"Model download failed: {md.get('error') or 'unknown error'}"
        else:
            status, message = "offline", "Model not on disk — download it from the Engine pane"
    elif last_error:
        status, message = "error", f"Engine Error: {last_error}"
    else:
        status, message = "offline", "Offline — engine loads when needed"

    if healthy:
        footer = {"engine_dot": "var(--ok)", "engine_pulse": False,
                  "engine_label": "vllm-d3-lite", "engine_title": "Engine status: Online in VRAM"}
        modal = {"engine_text": "Classifying locally", "engine_sub": f"vllm-d3-lite · {device_label}"}
    elif status == "downloading":
        footer = {"engine_dot": "var(--warn, #e5a93c)", "engine_pulse": True,
                  "engine_label": "Downloading model…", "engine_title": "Engine status: Downloading model (first launch)"}
        modal = {"engine_text": "Downloading model…", "engine_sub": f"vllm-d3-lite · {device_label}"}
    elif status == "error":
        footer = {"engine_dot": "var(--vi, #b5532f)", "engine_pulse": False,
                  "engine_label": "Engine error", "engine_title": f"Engine status: {message or 'Error'}"}
        modal = {"engine_text": message or "Engine error", "engine_sub": f"vllm-d3-lite · {device_label}"}
    else:
        footer = {"engine_dot": "var(--ink3)", "engine_pulse": False,
                  "engine_label": "vllm-d3-lite", "engine_title": "Engine status: Engine Paused"}
        modal = {"engine_text": "Offline — starts when needed", "engine_sub": f"vllm-d3-lite · {device_label}"}

    return {
        "healthy": healthy,
        "status": status,
        "message": message,
        "device_label": device_label,
        "model_downloaded": cached,
        **footer,
        **modal,
    }

async def _settings_ctx(request: Request) -> dict:
    """Everything the settings modal panes (and their fragments) render."""
    eng = await _engine_snapshot(request.app.state.http_client)
    return {
        "accounts": _accounts_with_tokens(),
        "has_credentials": get_credentials_file().exists(),
        "triage_prompt": get_setting("triage_prompt", DEFAULT_TRIAGE_PROMPT),
        "current_theme": request.cookies.get("iz-theme", "dark"),
        "compute_device": get_compute_device(),
        "effective_device": get_effective_device(),
        "has_nvidia": has_nvidia_gpu(),
        "gpu_name": get_nvidia_gpu_name(),
        "cuda_installed": is_cuda_installed(),
        "model_downloaded": is_model_downloaded(),
        **_cuda_view(classifier_mod.cuda_download_state),
        **eng,
    }

def _onboarding_base_ctx(request: Request) -> dict:
    return {
        "onboard_device": request.app.state.onboard_device,
        "cuda_installed": is_cuda_installed(),
        "has_nvidia": has_nvidia_gpu(),
        "gpu_name": get_nvidia_gpu_name(),
        "model_downloaded": is_model_downloaded(),
        "has_credentials": get_credentials_file().exists(),
    }

def _onboarding_dl_ctx(request: Request) -> dict:
    """Renders the current state of the onboarding download card (pure read)."""
    ctx = {
        "dl_visible": False, "dl_poll": None, "dl_advance": None,
        "dl_title": "Downloading classification model",
        "dl_sub": "ggml-org/vllm-d3-lite-GGUF (Q8_0)",
        "dl_percent": 0, "dl_bar": 0, "dl_stats": "",
        "dl_status": "Connecting to repository…",
    }
    phase = request.app.state.onboard_phase
    if phase == "error":
        ctx.update(
            dl_visible=True,
            dl_title="Setup failed",
            dl_sub="Use Retry Download to try again",
            dl_percent=0, dl_bar=0,
            dl_stats="",
            dl_status=request.app.state.onboard_error or "Download failed",
        )
        return ctx
    if phase == "cuda":
        cst = classifier_mod.cuda_download_state
        if cst.get("status") in ("downloading", "extracting"):
            ctx.update(dl_visible=True, dl_poll="0.8s",
                       dl_title="Installing CUDA acceleration",
                       dl_sub="GPU backend + runtime (one-time, ~760 MB)",
                       dl_percent=cst.get("percent", 0), dl_bar=cst.get("percent", 0),
                       dl_stats="", dl_status=cst.get("message") or "In progress")
        elif is_model_downloaded():
            ctx.update(dl_visible=True,
                       dl_title="Classification model ready",
                       dl_sub="ggml-org/vllm-d3-lite-GGUF:Q8_0",
                       dl_percent=100, dl_bar=100,
                       dl_stats="Verified on disk ✓", dl_status="Ready")
        else:
            ctx.update(dl_visible=True, dl_poll="0.5s",
                       dl_title="Downloading classification model",
                       dl_sub="ggml-org/vllm-d3-lite-GGUF (Q8_0, 1.08 GB)")
    elif phase == "model":
        mst = classifier_mod.model_download_state
        ctx["dl_sub"] = "ggml-org/vllm-d3-lite-GGUF (Q8_0, 1.08 GB)"
        if mst.get("status") == "downloading":
            p = mst.get("percent", 0)
            ctx.update(dl_visible=True, dl_poll="0.5s",
                       dl_title="Downloading classification model",
                       dl_sub="ggml-org/vllm-d3-lite-GGUF (Q8_0, 1.08 GB)",
                       dl_percent=p, dl_bar=p,
                       dl_stats=f"{mst.get('downloaded_mb') or 0} MB / {mst.get('total_mb') or 1082} MB",
                       dl_status="Downloading…")
        elif mst.get("status") == "error":
            ctx.update(dl_visible=True,
                       dl_status=f"Error: {mst.get('error') or 'Download failed'}")
        else:
            tot = int(mst.get("total_mb") or 1082)
            ctx.update(dl_visible=True,
                       dl_title="Model downloaded & loaded ✓",
                       dl_sub="ggml-org/vllm-d3-lite-GGUF (Q8_0, 1.08 GB)",
                       dl_percent=100, dl_bar=100,
                       dl_stats=f"{tot} MB / {tot} MB",
                       dl_status="Complete")
    elif phase == "done":
        ctx.update(request.app.state.onboard_done)
    return ctx

def _onboarding_btn_ctx(request: Request) -> dict:
    phase = request.app.state.onboard_phase
    if phase in ("cuda", "model"):
        return {"onboard_busy": True, "next_label": "Setting up..."}
    if phase == "error":
        return {"onboard_busy": False, "next_label": "Retry Download"}
    if phase == "done":
        return {"onboard_busy": False, "next_label": "Continue →"}
    return {"onboard_busy": False,
            "next_label": ('Continue →' if is_model_downloaded() else 'Download Model & Continue →')}

def _download_and_start(client):
    async def _run():
        await download_model_file()
        if not is_model_downloaded():
            log.warning("Model not on disk after download; engine start skipped")
            return
        await start_llama_server(client)
        # The model is on disk now: classify whatever piled up while the
        # engine was off, otherwise that mail stays "Queued" forever.
        await drain_classification(client, wake_engine=True)
    return _run()

# ---------------------------------------------------------------------------
# Main page + feed
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    tab: str = "important",
    q: str = "",
    unread: int = 0,
    account: str = "",
    page: int = 1,
):
    eng = await _engine_snapshot(request.app.state.http_client)
    ctx = _feed_ctx(request, tab, q, unread, account, page)
    onboarding_done = get_setting("onboarding_completed", "0") == "1"
    tpl_ctx = {
        **ctx,
        "triage_prompt": get_setting("triage_prompt", DEFAULT_TRIAGE_PROMPT),
        "current_theme": request.cookies.get("iz-theme", "dark"),
        "show_onboarding": not onboarding_done,
        "sync_active": sync_in_progress(),
        **eng,
        **_onboarding_base_ctx(request),
        **_onboarding_dl_ctx(request),
        **_onboarding_btn_ctx(request),
    }
    return _render(request, "index.html", **tpl_ctx)

@app.get("/emails", response_class=HTMLResponse)
async def list_emails_partial(request: Request):
    tab, q, unread, account, page = await _filter_params(request)
    ctx = _feed_ctx(request, tab, q, unread, account, page,
                    await _reader_id(request), await _reader_state(request))
    return _render(request, "partials/feed_oob.html", **ctx)

@app.get("/feed/poll", response_class=HTMLResponse)
async def feed_poll(request: Request):
    sig = _feed_signature()
    if request.query_params.get("sig") == sig:
        return Response(status_code=204)
    tab, q, unread, account, page = await _filter_params(request)
    ctx = _feed_ctx(request, tab, q, unread, account, page,
                    await _reader_id(request), await _reader_state(request))
    return _render(request, "partials/feed_oob.html", **ctx)

@app.post("/emails/{email_id}/open", response_class=HTMLResponse)
async def open_email_in_app(request: Request, email_id: str):
    """Opens a mail: marks it read and re-renders the reader. A POST, so a
    plain link from another site cannot flip the read state."""
    mark_email_read(email_id)
    _, _, _, account, _ = await _filter_params(request)
    reader_id = await _reader_id(request)
    row = get_email_by_id(email_id)
    prev_row = get_email_by_id(reader_id) if reader_id and reader_id != email_id else None
    return _render(request, "partials/response_email_open.html", email=row, prev_email=prev_row,
                   item_row=row, counts=get_counts(account))

@app.post("/sync", response_class=HTMLResponse)
async def manual_sync(request: Request, only_account: str = ""):
    tab, q, unread, account, page = await _filter_params(request)
    reader_id = await _reader_id(request)
    reader_state = await _reader_state(request)
    if rescan_in_progress():
        return _render(request, "partials/response_toast.html",
                       msg="Rescan in progress — cancel it first")
    already = sync_in_progress()
    if already and only_account:
        # The running job skipped this account on purpose (first sync pending),
        # so queue a scoped run instead of attaching to the wrong sync.
        log.info("Queueing first sync for %s behind the running sync", only_account)
        tasks.spawn(run_sync_and_classify(
            request.app.state.http_client, fetch_gmail=True,
            interactive=True, queue=True, only_account=only_account,
        ))
        sync_label = "First sync queued…"
        msg = "First sync will start after the current sync"
    elif already:
        log.info("Manual sync requested while one is running; attaching to it")
        sync_label = "Syncing inbox…"
        msg = "Sync already running"
    else:
        log.info("Manual sync triggered (running in background)")
        reset_sync_state()
        tasks.spawn(run_sync_and_classify(
            request.app.state.http_client, fetch_gmail=True,
            interactive=True, queue=True, only_account=only_account,
        ))
        sync_label = "Starting sync…"
        msg = "Syncing in background — progress below"
    ctx = dict(
        sync_live=True,
        sync_label=sync_label,
        sync_count="", sync_fill=0, sync_cancel=True, feed_refresh=False,
        close_first_sync=bool(only_account), msg=msg,
        **_feed_ctx(request, tab, q, unread, account, page,
                    reader_id, reader_state),
    )
    return _render(request, "partials/response_sync_hud.html", **ctx)

@app.get("/fragments/sync-progress", response_class=HTMLResponse)
async def sync_progress_fragment(request: Request):
    s = get_sync_progress()
    phase = s.get("phase") or ""
    processed = s.get("processed") or 0
    total = s.get("total") or 0
    pct = round((processed / total) * 100) if total else 0

    if phase in ("starting", "listing", "syncing", "classifying", "cancelling"):
        labels = {
            "starting": "Starting sync…",
            "listing": "Checking Gmail…",
            "syncing": "Mirroring inbox…",
            "classifying": "Classifying mail…",
            "cancelling": "Cancelling sync…",
        }
        count = f"{processed}/{total}" if phase in ("syncing", "classifying") and total else ""
        return _render(request, "partials/response_sync_hud.html",
                       sync_live=True, sync_label=labels[phase],
                       sync_count=count, sync_fill=pct,
                       sync_cancel=phase != "cancelling",
                       feed_refresh=False, msg=None)

    fetched = s.get("fetched") or 0
    failed = s.get("failed") or 0
    refreshed = fetched > 0 or processed > 0
    if phase == "cancelled":
        msg = f"Sync cancelled — {fetched} new, {processed} classified"
    elif phase == "error":
        msg = f"Sync failed — {s.get('error') or 'check the log for details'}"
    elif phase == "done":
        msg = f"Sync complete — {fetched} new, {processed} classified"
        if failed:
            msg += f", {failed} failed"
    else:
        msg = None

    ctx: dict = {
        "sync_live": False, "sync_label": "", "sync_count": "", "sync_fill": 0,
        "sync_cancel": False, "feed_refresh": refreshed, "msg": msg,
    }
    if refreshed:
        tab, q, unread, account, page = await _filter_params(request)
        ctx.update(_feed_ctx(request, tab, q, unread, account, page,
                             await _reader_id(request), await _reader_state(request)))
    return _render(request, "partials/response_sync_hud.html", **ctx)

@app.post("/sync/cancel", response_class=HTMLResponse)
async def cancel_sync(request: Request):
    if not sync_in_progress():
        return _render(request, "partials/response_sync_hud.html",
                       sync_live=False, sync_label="", sync_count="", sync_fill=0,
                       sync_cancel=False, feed_refresh=False,
                       msg="No sync is running")
    log.info("Sync cancel requested")
    request_sync_cancel()
    s = get_sync_progress()
    processed = s.get("processed") or 0
    total = s.get("total") or 0
    pct = round((processed / total) * 100) if total else 0
    return _render(request, "partials/response_sync_hud.html",
                   sync_live=True, sync_label="Cancelling sync…",
                   sync_count=f"{processed}/{total}" if total else "",
                   sync_fill=pct, sync_cancel=False,
                   feed_refresh=False, msg=None)

@app.post("/rescan", response_class=HTMLResponse)
async def rescan_inbox(request: Request, limit: int = RESCAN_LIMIT):
    tab, q, unread, account, page = await _filter_params(request)
    reader_id = await _reader_id(request)
    reader_state = await _reader_state(request)
    if sync_in_progress():
        return _render(request, "partials/response_hud.html",
                       hud_hidden=True, hud_label="", hud_count="", hud_fill=0,
                       feed_refresh=False,
                       msg="Sync in progress — cancel it first")
    if rescan_in_progress():
        return _render(request, "partials/response_hud.html",
                       hud_hidden=False, hud_label="Rescanning inbox…",
                       hud_count="", hud_fill=0, feed_refresh=False,
                       msg="A rescan is already running")
    scope = "all stored" if limit < 0 else f"the newest {limit}"
    log.info("Manual rescan triggered (%s mails, background)", scope)
    reset_rescan_state()
    tasks.spawn(rescan_last_items(request.app.state.http_client, limit))
    ctx = dict(
        hud_hidden=False, hud_label="Waking engine…", hud_count="", hud_fill=0,
        hud_cancel=True, feed_refresh=True, msg=f"Re-scoring {scope} mails…",
        **_feed_ctx(request, tab, q, unread, account, page, reader_id, reader_state),
    )
    return _render(request, "partials/response_hud.html", **ctx)

@app.get("/fragments/rescan-progress", response_class=HTMLResponse)
async def rescan_progress_fragment(request: Request):
    s = get_rescan_progress()
    phase = s.get("phase") or ""
    if phase in ("scanning", "cancelling"):
        total = s.get("total") or 0
        processed = s.get("processed") or 0
        pct = round((processed / total) * 100) if total else 0
        return _render(request, "partials/response_hud.html",
                       hud_hidden=False,
                       hud_label="Cancelling rescan…" if phase == "cancelling" else "Rescanning inbox…",
                       hud_count=f"{processed}/{total}", hud_fill=pct,
                       hud_cancel=phase == "scanning",
                       feed_refresh=False, msg=None)
    if phase == "starting-engine":
        return _render(request, "partials/response_hud.html",
                       hud_hidden=False, hud_label="Waking engine…",
                       hud_count="", hud_fill=0, hud_cancel=True,
                       feed_refresh=False, msg=None)
    if s.get("error"):
        return _render(request, "partials/response_hud.html",
                       hud_hidden=True, hud_label="", hud_count="", hud_fill=0,
                       hud_cancel=False, feed_refresh=False,
                       msg=f"Rescan failed: {s['error']}")
    processed = s.get("processed") or 0
    failed = s.get("failed") or 0
    refreshed = processed > 0
    if phase == "cancelled":
        msg = f"Rescan cancelled — {processed} mails re-scored"
    else:
        msg = f"Rescan complete — {processed} mails re-scored" if refreshed else "Nothing to rescan"
        if refreshed and failed:
            msg += f", {failed} failed"
    ctx: dict = {
        "hud_hidden": True, "hud_label": "", "hud_count": "", "hud_fill": 0,
        "hud_cancel": False, "feed_refresh": refreshed, "msg": msg,
    }
    if refreshed:
        tab, q, unread, account, page = await _filter_params(request)
        ctx.update(_feed_ctx(request, tab, q, unread, account, page,
                             await _reader_id(request), await _reader_state(request)))
    return _render(request, "partials/response_hud.html", **ctx)

@app.post("/rescan/cancel", response_class=HTMLResponse)
async def cancel_rescan(request: Request):
    if not rescan_in_progress():
        return _render(request, "partials/response_hud.html",
                       hud_hidden=True, hud_label="", hud_count="", hud_fill=0,
                       hud_cancel=False, feed_refresh=False,
                       msg="No rescan is running")
    log.info("Rescan cancel requested")
    request_rescan_cancel()
    s = get_rescan_progress()
    processed = s.get("processed") or 0
    total = s.get("total") or 0
    pct = round((processed / total) * 100) if total else 0
    return _render(request, "partials/response_hud.html",
                   hud_hidden=False, hud_label="Cancelling rescan…",
                   hud_count=f"{processed}/{total}" if total else "",
                   hud_fill=pct, hud_cancel=False,
                   feed_refresh=False, msg=None)

# ---------------------------------------------------------------------------
# Settings + compute + CUDA + engine status
# ---------------------------------------------------------------------------

@app.get("/api/engine/status")
async def engine_status(request: Request):
    snap = await _engine_snapshot(request.app.state.http_client)
    return JSONResponse({
        "healthy": snap["healthy"],
        "status": snap["status"],
        "message": snap["message"],
        "model": MODEL_DISPLAY_NAME,
        "compute_device": get_compute_device(),
        "device": snap["device_label"],
    })

@app.get("/fragments/engine-status", response_class=HTMLResponse)
async def engine_status_fragment(request: Request, scope: str = "footer"):
    snap = await _engine_snapshot(request.app.state.http_client)
    if scope == "modal":
        return _render(request, "partials/engine_block.html", **snap)
    return _render(request, "partials/engine_footer.html", **snap)

@app.get("/fragments/settings", response_class=HTMLResponse)
async def open_settings(request: Request, pane: str = "rules"):
    if pane not in ("rules", "accounts", "look", "model"):
        pane = "rules"
    ctx = await _settings_ctx(request)
    return _render(request, "partials/settings_modal.html",
                   settings_open=True, active_pane=pane, autofocus_close=True, **ctx)

@app.get("/fragments/settings/pane/{pane}", response_class=HTMLResponse)
async def settings_pane_fragment(request: Request, pane: str, view: str | None = None):
    if pane not in ("rules", "accounts", "look", "model"):
        pane = "rules"
    ctx = await _settings_ctx(request)
    return _render(request, "partials/settings_pane_response.html",
                   active_pane=pane, accounts_view=view, **ctx)

@app.post("/fragments/compute", response_class=HTMLResponse)
async def set_compute_fragment(request: Request, device: str = "cpu"):
    target = "gpu" if device == "gpu" else "cpu"
    changed = get_compute_device() != target
    if changed:
        set_setting("compute_device", target)
        log.info("Compute device switched to %s", target)

    installing = target == "gpu" and not is_cuda_installed()
    if installing:
        if not classifier_mod.cuda_install_in_progress():
            classifier_mod.cuda_download_state.update(
                status="downloading", percent=1,
                message="Starting CUDA install…",
            )
            log.info("CUDA missing; downloading and installing it automatically")
            tasks.spawn(_install_cuda_then_restart(request.app.state.http_client))
        msg = "NVIDIA GPU selected — downloading and installing CUDA automatically…"
    elif changed:
        tasks.spawn(restart_llama_server(request.app.state.http_client))
        msg = ("Compute device set to NVIDIA GPU" if target == "gpu"
               else "Compute device set to CPU")
    else:
        msg = "Compute device already set to NVIDIA GPU" if target == "gpu" else "Compute device set to CPU"

    ctx = await _settings_ctx(request)
    return _render(request, "partials/response_pane_toast.html",
                   pane_template="partials/settings_pane_model.html", msg=msg, **ctx)

@app.post("/fragments/cuda/install", response_class=HTMLResponse)
async def cuda_install_fragment(request: Request):
    if not classifier_mod.cuda_install_in_progress() and not is_cuda_installed():
        classifier_mod.cuda_download_state.update(
            status="downloading", percent=1,
            message="Starting CUDA install…",
        )
        tasks.spawn(_install_cuda_then_restart(request.app.state.http_client))
    ctx = await _settings_ctx(request)
    return _render(request, "partials/response_pane_toast.html",
                   pane_template="partials/cuda_box.html",
                   msg="Installing CUDA automatically…", **ctx)

@app.get("/fragments/cuda/progress", response_class=HTMLResponse)
async def cuda_progress_fragment(request: Request):
    view = _cuda_view(classifier_mod.cuda_download_state)
    ctx = {
        **view,
        "compute_device": get_compute_device(),
        "effective_device": get_effective_device(),
        "cuda_installed": is_cuda_installed(),
    }
    if view["cuda_state"] == "ready":
        return _render(request, "partials/response_pane_toast.html",
                       pane_template="partials/cuda_box.html",
                       msg="CUDA runtime installed and active!", **ctx)
    return _render(request, "partials/response_pane_toast.html",
                   pane_template="partials/cuda_box.html", msg=None, **ctx)

@app.post("/fragments/model/download", response_class=HTMLResponse)
async def model_download_fragment(request: Request):
    if not is_model_downloaded():
        md = classifier_mod.model_download_state
        if md.get("status") != "downloading":
            md.update(status="downloading", percent=0,
                      message="Starting download...", error=None)
            tasks.spawn(_download_and_start(request.app.state.http_client))
    ctx = await _settings_ctx(request)
    return _render(request, "partials/response_pane_toast.html",
                   pane_template="partials/settings_pane_model.html",
                   msg="Model download started", **ctx)

# ---------------------------------------------------------------------------
# Accounts + prompt
# ---------------------------------------------------------------------------

@app.post("/fragments/accounts/connect", response_class=HTMLResponse)
async def accounts_connect_fragment(request: Request):
    log.info("Account connect requested (OAuth browser flow)")
    email = await asyncio.to_thread(connect_account)
    if email:
        state = get_sync_state(email)
        pending = not state or not state.get("initial_sync_done")
        return _render(request, "partials/response_account_connected.html",
                       pane_template="partials/settings_pane_accounts.html",
                       accounts=_accounts_with_tokens(), selected_account=None,
                       has_credentials=True, msg="Account connected",
                       first_sync_account=email if pending else "",
                       first_sync_cap=FIRST_SYNC_CAP)
    return _render(request, "partials/response_toast.html",
                   msg="Google sign-in failed or was cancelled")

@app.post("/fragments/accounts/credentials", response_class=HTMLResponse)
async def accounts_credentials_fragment(
    request: Request,
    credentials: UploadFile = File(...),
):
    raw = await credentials.read(1_000_001)
    if len(raw) > 1_000_000:
        return _render(request, "partials/response_toast.html",
                       msg="Credentials file is too large")
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return _render(request, "partials/response_toast.html",
                       msg="That file is not valid JSON")
    installed = data.get("installed") if isinstance(data, dict) else None
    if not isinstance(installed, dict) or not installed.get("client_id") or not installed.get("client_secret"):
        return _render(request, "partials/response_toast.html",
                       msg="Expected a Google Desktop OAuth credentials file")
    target = DATA_DIR / "credentials.json"
    temp = DATA_DIR / ".credentials.json.tmp"
    temp.write_bytes(raw)
    os.chmod(temp, 0o600)
    temp.replace(target)
    ctx = await _settings_ctx(request)
    return _render(request, "partials/response_pane_toast.html",
                   pane_template="partials/settings_pane_accounts.html",
                   msg="Credentials installed", **ctx)

@app.post("/fragments/accounts/remove", response_class=HTMLResponse)
async def accounts_remove_fragment(request: Request, account: str = ""):
    """Forgets an account: drops its token, its mirrored mail and its row in
    the account list."""
    account = (account or "").strip()
    if not account:
        return _render(request, "partials/response_toast.html", msg="No account given")
    if sync_in_progress() or rescan_in_progress():
        return _render(request, "partials/response_toast.html",
                       msg="Sync or rescan in progress — finish it before removing an account")
    async with sync_lock:
        remove_account(account)
        with get_db() as conn:
            conn.execute("DELETE FROM emails WHERE account = ?", (account,))
            conn.execute("DELETE FROM sync_state WHERE account = ?", (account,))
            conn.execute("DELETE FROM local_reads WHERE email_id NOT IN (SELECT id FROM emails)")
    log.info("Account removed: %s", account)
    return _render(request, "partials/response_pane_toast.html",
                   pane_template="partials/settings_pane_accounts.html",
                   accounts=_accounts_with_tokens(), selected_account=None,
                   has_credentials=get_credentials_file().exists(),
                   msg=f"Removed {account}")

@app.post("/settings/prompt", response_class=HTMLResponse)
async def update_prompt(request: Request, triage_prompt: str = Form(...)):
    prompt = triage_prompt.strip()
    # Reject before persisting: an over-cap prompt would otherwise be silently
    # truncated at classification time, so part of the user's rules never applies.
    if len(prompt) > TRIAGE_PROMPT_MAX_CHARS:
        return _render(request, "partials/response_toast.html",
                       msg=f"Instructions too long ({len(prompt)} chars). Limit is {TRIAGE_PROMPT_MAX_CHARS} characters.")
    busy = sync_in_progress() or rescan_in_progress()
    set_setting("triage_prompt", prompt)
    log.info("Triage prompt updated; re-scoring all stored mails")
    reset_rescan_state()
    tasks.spawn(rescan_last_items(
        request.app.state.http_client, RESCAN_LIMIT, queue=True,
    ))
    saved_msg = ("Instructions saved — re-scoring queued behind the current job"
                 if busy else "Classification instructions saved")
    tab, q, unread, account, page = await _filter_params(request)
    ctx = _feed_ctx(request, tab, q, unread, account, page,
                    await _reader_id(request), await _reader_state(request))
    return _render(request, "partials/response_prompt_saved.html",
                   saved_msg=saved_msg, **ctx)

@app.get("/fragments/prompt/finish", response_class=HTMLResponse)
async def prompt_finish(request: Request):
    return _render(request, "partials/response_empty_oob.html")

# ---------------------------------------------------------------------------
# Toast fragments
# ---------------------------------------------------------------------------

@app.get("/fragments/toast", response_class=HTMLResponse)
async def fragment_toast(request: Request, msg: str = ""):
    return _render(request, "partials/response_toast.html", msg=msg)

@app.get("/fragments/toast-off", response_class=HTMLResponse)
async def fragment_toast_off(request: Request):
    return _render(request, "partials/toast.html")

# ---------------------------------------------------------------------------
# Email scan (in-app reader re-classify)
# ---------------------------------------------------------------------------

@app.post("/emails/{email_id}/scan", response_class=HTMLResponse)
async def scan_email_endpoint(request: Request, email_id: str):
    """Re-classifies the currently open email and re-renders the reader panel."""
    email_data = get_email_by_id(email_id)
    if not email_data or not email_data.get("model_input"):
        return _render(request, "partials/email_view.html", email=email_data)
    client = request.app.state.http_client
    async with engine_use():
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
    return _render(request, "partials/email_view.html", email=email_data)

# ---------------------------------------------------------------------------
# Onboarding flow (server-driven; mirrors the old JS state machine)
# ---------------------------------------------------------------------------

def _ready_card(title: str, sub: str, stats: str, status: str = "Ready") -> dict:
    return {
        "dl_title": title, "dl_sub": sub,
        "dl_percent": 100, "dl_bar": 100,
        "dl_stats": stats, "dl_status": status,
    }

def _render_onboarding_step(request: Request, step: str = "compute", side_step: str | None = None):
    ctx = _onboarding_base_ctx(request)
    if step == "mail":
        return _render(request, "partials/onboarding_step_response.html",
                       render_step="mail", side_step=side_step, **ctx)
    ctx.update(_onboarding_dl_ctx(request))
    ctx.update(_onboarding_btn_ctx(request))
    return _render(request, "partials/onboarding_step_response.html",
                   render_step="compute", side_step=side_step, **ctx)

@app.get("/fragments/onboarding/select", response_class=HTMLResponse)
async def onboarding_select_fragment(request: Request, device: str = "cpu"):
    request.app.state.onboard_device = device
    return _render_onboarding_step(request, side_step=None)

@app.post("/fragments/onboarding/setup", response_class=HTMLResponse)
async def onboarding_setup_fragment(request: Request):
    client = request.app.state.http_client
    state = request.app.state
    state.onboard_error = ""
    device = state.onboard_device or "cpu"
    target = "gpu" if device == "gpu" else "cpu"
    if get_compute_device() != target:
        set_setting("compute_device", target)
        log.info("Compute device switched to %s; restarting engine", target)
        tasks.spawn(restart_llama_server(client))

    if target == "gpu" and not is_cuda_installed():
        tasks.spawn(install_cuda_runtime())
        state.onboard_phase = "cuda"
        return _render_onboarding_step(request, side_step=None)

    if is_model_downloaded():
        # Model already on disk: CUDA (if any) done, go to mail step after 500ms.
        state.onboard_phase = "done"
        state.onboard_done = _ready_card(
            "Classification model ready",
            "ggml-org/vllm-d3-lite-GGUF:Q8_0",
            "Verified on disk ✓",
        )
        ctx = _onboarding_base_ctx(request)
        ctx.update(_onboarding_btn_ctx(request))
        card = dict(state.onboard_done)
        card.update({"dl_visible": True, "dl_poll": None, "dl_advance": "0.5s"})
        return _render(request, "partials/onboarding_step_response.html",
                       render_step="compute", side_step=None, **card, **ctx)

    model_download_state = classifier_mod.model_download_state
    if model_download_state.get("status") != "downloading":
        model_download_state.update(status="downloading", percent=0,
                                    message="Starting download...", error=None)
        tasks.spawn(_download_and_start(client))
    state.onboard_phase = "model"
    return _render_onboarding_step(request, side_step=None)

@app.get("/fragments/onboarding/progress", response_class=HTMLResponse)
async def onboarding_progress_fragment(request: Request):
    state = request.app.state
    client = request.app.state.http_client
    phase = state.onboard_phase

    if phase == "cuda":
        cst = classifier_mod.cuda_download_state
        if cst.get("status") in ("downloading", "extracting"):
            card = _onboarding_dl_ctx(request)
            return _render(request, "partials/onboarding_progress_response.html", oob_next_label=None, **card)
        if cst.get("status") == "error":
            state.onboard_phase = "error"
            state.onboard_error = f"CUDA runtime download failed: {cst.get('message') or 'unknown error'}"
            card = _onboarding_dl_ctx(request)
            return _render(request, "partials/onboarding_progress_response.html",
                           oob_next_label="Retry Download", oob_next_busy=False, **card)
        # Terminal cuda state (ready/completed): move to the model check,
        # exactly like the old JS did once its poll loop resolved.
        if is_model_downloaded():
            state.onboard_phase = "done"
            state.onboard_done = _ready_card(
                "Classification model ready",
                "ggml-org/vllm-d3-lite-GGUF:Q8_0",
                "Verified on disk ✓",
            )
            card = dict(state.onboard_done)
            card["dl_poll"] = None
            card["dl_advance"] = "0.5s"
            return _render(request, "partials/onboarding_progress_response.html",
                           oob_next_label="Continue →", oob_next_busy=False, **card)
        md = classifier_mod.model_download_state
        if md.get("status") != "downloading":
            md.update(status="downloading", percent=0, message="Starting download...", error=None)
            tasks.spawn(_download_and_start(client))
        state.onboard_phase = "model"
        card = _onboarding_dl_ctx(request)
        card["dl_stats"] = ""
        return _render(request, "partials/onboarding_progress_response.html", oob_next_label=None, **card)

    if phase == "model":
        md = classifier_mod.model_download_state
        card = _onboarding_dl_ctx(request)
        if md.get("status") == "downloading":
            return _render(request, "partials/onboarding_progress_response.html", oob_next_label=None, **card)
        if md.get("status") == "error":
            state.onboard_phase = "error"
            state.onboard_error = f"Model download failed: {md.get('error') or 'unknown error'}"
            card = _onboarding_dl_ctx(request)
            return _render(request, "partials/onboarding_progress_response.html",
                           oob_next_label="Retry Download", oob_next_busy=False, **card)
        finished = classifier_mod.model_download_state
        tot = int(finished.get("total_mb") or 1082)
        state.onboard_phase = "done"
        state.onboard_done = _ready_card(
            "Model downloaded & loaded ✓",
            "ggml-org/vllm-d3-lite-GGUF (Q8_0, 1.08 GB)",
            f"{tot} MB / {tot} MB",
            status="Complete",
        )
        card = dict(state.onboard_done)
        card["dl_poll"] = None
        card["dl_advance"] = "0.8s"
        return _render(request, "partials/onboarding_progress_response.html",
                       oob_next_label="Continue →", oob_next_busy=False, **card)

    return Response(status_code=204)

@app.get("/fragments/onboarding/step/{step}", response_class=HTMLResponse)
async def onboarding_step_fragment(request: Request, step: str):
    if step == "mail":
        return _render_onboarding_step(request, step="mail", side_step="mail")
    return _render_onboarding_step(request, step="compute", side_step="compute")

@app.post("/fragments/onboarding/finish", response_class=HTMLResponse)
async def onboarding_finish_fragment(request: Request, open_accounts: bool = False):
    state = request.app.state
    device = state.onboard_device or "cpu"
    set_setting("compute_device", "gpu" if device == "gpu" else "cpu")
    set_setting("onboarding_completed", "1")
    if device == "gpu" and is_cuda_installed():
        tasks.spawn(restart_llama_server(request.app.state.http_client))
    state.onboard_phase = None
    state.onboard_done = {}

    ctx = await _settings_ctx(request)
    ctx.update(await _engine_snapshot(request.app.state.http_client))
    return _render(request, "partials/onboarding_finish_response.html",
                   open_accounts=str(open_accounts).lower() == "true",
                   msg=f"Setup completed ({('GPU' if device == 'gpu' else 'CPU')} mode active)",
                   settings_open=True, active_pane="accounts", accounts_view="guide",
                   autofocus_close=True, **ctx)
