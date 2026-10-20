import asyncio
import logging
import time
import subprocess
import httpx
from app.config import get_llama_cmd, LLAMA_URL, LLAMA_LOG_PATH, TRIAGE_PROMPT_MAX_CHARS, MODEL_INPUT_CHARS
from app import tasks

log = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.60

_llama_process: subprocess.Popen | None = None
_llama_last_error: str | None = None
_last_restart_ts = 0.0
_engine_session = False  # True once this session deliberately launched the engine

WATCHDOG_RESTART_COOLDOWN = 120  # don't fight a manual restart that just happened
WATCHDOG_MAX_FAILS = 3           # failed restart cycles before auto-restart stops (manual start clears)
_watchdog_fails = 0

def get_llama_last_error() -> str | None:
    return _llama_last_error

def _set_llama_error(message: str | None):
    global _llama_last_error
    _llama_last_error = message
    if message:
        log.error("llama-server: %s", message)

async def is_llama_healthy(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(f"{LLAMA_URL}/health", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False

async def start_llama_server(client: httpx.AsyncClient):
    global _llama_process, _llama_last_error, _engine_session
    if await is_llama_healthy(client):
        _llama_last_error = None
        _engine_session = True
        return
    cmd, env = get_llama_cmd()
    try:
        llama_log = open(LLAMA_LOG_PATH, "wb")
        _llama_process = subprocess.Popen(
            cmd,
            stdout=llama_log,
            stderr=subprocess.STDOUT,
            env=env,
        )
    except FileNotFoundError:
        _set_llama_error("llama-server binary not found (install llama.cpp or place it in ./bin)")
        return
    except OSError as e:
        _set_llama_error(f"Failed to launch llama-server: {e}")
        return
    log.info("llama-server launched (pid %s)", _llama_process.pid)
    _llama_last_error = None
    _engine_session = True

    async def wait_healthy():
        global _llama_last_error
        for _ in range(120):
            if await is_llama_healthy(client):
                log.info("llama-server healthy")
                _llama_last_error = None
                return
            await asyncio.sleep(0.5)
        if await is_llama_healthy(client):
            return
        _set_llama_error("Engine did not become healthy after 60s (see llama-server.log)")

    tasks.spawn(wait_healthy())

def stop_llama_server():
    global _llama_process, _engine_session
    _engine_session = False
    if _llama_process and _llama_process.poll() is None:
        _llama_process.terminate()
        try:
            _llama_process.wait(timeout=5)
            log.info("llama-server stopped")
        except subprocess.TimeoutExpired:
            _llama_process.kill()
            log.warning("llama-server force-killed after terminate timeout")
    _llama_process = None

async def restart_llama_server(client: httpx.AsyncClient):
    global _last_restart_ts, _watchdog_fails
    _last_restart_ts = time.time()
    _watchdog_fails = 0  # human-initiated restart always gets a fresh strike count
    stop_llama_server()
    await asyncio.sleep(0.5)
    await start_llama_server(client)

async def ensure_engine_started(client: httpx.AsyncClient) -> bool:
    """Lazy launch: returns True once the local LLM is reachable, starting it
    on first use. Callers pass False only for "go without classification"."""
    global _engine_session, _watchdog_fails
    if await is_llama_healthy(client):
        _engine_session = True
        _watchdog_fails = 0
        return True
    from app.config import is_model_downloaded
    if not is_model_downloaded():
        _set_llama_error("Engine not downloaded yet — start it from the Engine pane")
        return False
    await start_llama_server(client)
    pre_existing_error = _llama_last_error
    for _ in range(120):
        if _llama_last_error and _llama_last_error != pre_existing_error:
            return False
        if await is_llama_healthy(client):
            _engine_session = True
            _watchdog_fails = 0
            return True
        await asyncio.sleep(0.5)
    return False

async def ensure_engine_alive(client: httpx.AsyncClient) -> bool:
    """One watchdog step: relaunch llama-server if the model is on disk and the
    engine isn't answering. Only manages engines this session launched."""
    global _watchdog_fails
    from app.config import is_model_downloaded
    if not _engine_session:
        return False
    if not is_model_downloaded():
        return False
    if await is_llama_healthy(client):
        _watchdog_fails = 0
        return True
    if _watchdog_fails >= WATCHDOG_MAX_FAILS:
        return False
    if time.time() - _last_restart_ts < WATCHDOG_RESTART_COOLDOWN:
        return False
    log.info("Engine watchdog: llama-server not responding; restarting")
    _watchdog_fails += 1
    if _watchdog_fails >= WATCHDOG_MAX_FAILS:
        _set_llama_error("Engine keeps dying (check llama-server.log); start it from the Engine pane")
    await restart_llama_server(client)
    return await is_llama_healthy(client)

# Model Download State & Manager
model_download_state = {
    "status": "idle",       # idle, downloading, ready, error
    "percent": 0,
    "downloaded_mb": 0,
    "total_mb": 1032,
    "message": "",
    "error": None,
}

async def download_model_file():
    """Downloads the GGUF model from Hugging Face with progress tracking."""
    global model_download_state
    from app.config import DATA_DIR, MODEL_FILENAME, MODEL_URL, is_model_downloaded, get_model_path

    if is_model_downloaded():
        model_download_state = {
            "status": "ready",
            "percent": 100,
            "downloaded_mb": 1032,
            "total_mb": 1032,
            "message": "Model ready!",
            "error": None,
        }
        return

    models_dir = DATA_DIR / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    target_file = models_dir / MODEL_FILENAME
    temp_file = models_dir / f"{MODEL_FILENAME}.tmp"

    model_download_state = {
        "status": "downloading",
        "percent": 0,
        "downloaded_mb": 0,
        "total_mb": 1032,
        "message": "Starting download...",
        "error": None,
    }

    try:
        def reporthook(count, block_size, total_size):
            if total_size > 0:
                downloaded = count * block_size
                percent = min(99, int(downloaded * 100 / total_size))
                dl_mb = round(downloaded / (1024 * 1024), 1)
                tot_mb = round(total_size / (1024 * 1024), 1)
                model_download_state["percent"] = percent
                model_download_state["downloaded_mb"] = dl_mb
                model_download_state["total_mb"] = tot_mb
                model_download_state["message"] = f"Downloading: {dl_mb} MB / {tot_mb} MB ({percent}%)"

        import urllib.request
        await asyncio.to_thread(urllib.request.urlretrieve, MODEL_URL, str(temp_file), reporthook)
        temp_file.replace(target_file)
        model_download_state = {
            "status": "ready",
            "percent": 100,
            "downloaded_mb": model_download_state.get("total_mb", 1032),
            "total_mb": model_download_state.get("total_mb", 1032),
            "message": "Model downloaded and ready!",
            "error": None,
        }
    except Exception as e:
        model_download_state = {
            "status": "error",
            "percent": 0,
            "downloaded_mb": 0,
            "total_mb": 1032,
            "message": f"Download failed: {e}",
            "error": str(e),
        }
        log.error("Model download failed: %s", e)

# CUDA On-Demand Downloader State
cuda_download_state = {
    "status": "idle",     # idle, downloading, ready, error
    "percent": 0,
    "message": "",
}

async def install_cuda_runtime():
    """Installs or copies CUDA runtime libraries to DATA_DIR / 'cuda'."""
    global cuda_download_state
    from app.config import DATA_DIR, get_bundle_dir, is_cuda_installed
    import shutil
    import urllib.request

    if is_cuda_installed():
        cuda_download_state = {"status": "completed", "percent": 100, "message": "CUDA already installed"}
        return

    cuda_dir = DATA_DIR / "cuda"
    cuda_dir.mkdir(parents=True, exist_ok=True)

    cuda_download_state = {"status": "downloading", "percent": 5, "message": "Initializing CUDA runtime install..."}

    local_bin = get_bundle_dir() / "bin"
    # If files exist in local bin, copy them over
    if (local_bin / "libggml-cuda.so").exists() and (local_bin / "libcublasLt.so.12").exists():
        cuda_download_state["message"] = "Copying local CUDA libraries..."
        for fname in ("libcublasLt.so.12", "libcublas.so.12", "libggml-cuda.so", "libcudart.so.12"):
            src = local_bin / fname
            if src.exists():
                shutil.copy2(src, cuda_dir / fname)
        cuda_download_state = {"status": "ready", "percent": 100, "message": "CUDA runtime ready!"}
        return

    # Fallback remote download from official llama.cpp release mirror
    cuda_download_state["message"] = "Downloading CUDA acceleration libraries (~850 MB)..."
    try:
        remote_url = "https://github.com/ggml-org/llama.cpp/releases/download/b11669/cudart-llama-b11669-bin-ubuntu-cuda-12.8-x64.tar.gz"
        archive_path = cuda_dir / "cuda_runtime.tar.gz"
        
        def reporthook(count, block_size, total_size):
            if total_size > 0:
                p = min(92, int(count * block_size * 90 / total_size))
                mb = (count * block_size) // (1024 * 1024)
                cuda_download_state["percent"] = p
                cuda_download_state["message"] = f"Downloaded {mb} MB..."

        await asyncio.to_thread(urllib.request.urlretrieve, remote_url, str(archive_path), reporthook)
        cuda_download_state["status"] = "extracting"
        cuda_download_state["percent"] = 95
        cuda_download_state["message"] = "Extracting runtime libraries..."
        import tarfile
        with tarfile.open(archive_path, "r:gz") as tar:
            safe_members = [m for m in tar.getmembers() if m.isreg()]
            tar.extractall(path=cuda_dir, members=safe_members, filter="data")
        archive_path.unlink(missing_ok=True)
        cuda_download_state = {"status": "ready", "percent": 100, "message": "CUDA runtime ready!"}
        log.info("CUDA runtime installed to %s", cuda_dir)
    except Exception as e:
        cuda_download_state = {"status": "error", "percent": 0, "message": f"Download failed: {e}"}
        log.error("CUDA runtime install failed: %s", e)

async def classify_email(
    client: httpx.AsyncClient,
    email_row: dict,
    triage_prompt_md: str,
) -> tuple[str, float]:
    state_text = (
        f"Triage Rules (Markdown):\n{triage_prompt_md[:TRIAGE_PROMPT_MAX_CHARS]}\n\n"
        f"---\n"
        f"Incoming Email:\n"
        f"From: {email_row['sender_name']} <{email_row['sender_email']}>\n"
        f"Subject: {email_row['subject'][:200]}\n"
        f"Date: {email_row['date_str']}\n"
        f"Body:\n{email_row['model_input'][:MODEL_INPUT_CHARS]}"
    )

    payload = {
        "state": state_text,
        "questions": {
            "triage": {
                "type": "choice",
                "instructions": (
                    "Classify this email into one category strictly following "
                    "the Triage Rules (Markdown) above."
                ),
                "criteria": {
                    "very_important": (
                        "Requires immediate action or response, or is time-sensitive, "
                        "as defined in the VERY_IMPORTANT section of the Triage Rules."
                    ),
                    "important": (
                        "Worth reading or following up without an urgent deadline, "
                        "as defined in the IMPORTANT section of the Triage Rules."
                    ),
                    "low_priority": (
                        "Bulk, automated, or promotional mail needing no reply, "
                        "as defined in the LOW_PRIORITY section of the Triage Rules."
                    ),
                }
            }
        }
    }

    resp = await client.post(f"{LLAMA_URL}/v1/systemone", json=payload, timeout=15.0)
    resp.raise_for_status()
    triage_ans = resp.json()["answers"]["triage"]
    choice = triage_ans["choice"]
    prob = float(triage_ans.get("probabilities", {}).get(choice, 0.0))

    if choice not in ("very_important", "important", "low_priority") or prob < CONFIDENCE_THRESHOLD:
        log.info(
            "Low-confidence fallback for %s: choice=%s prob=%.2f",
            email_row.get("id"), choice, prob,
        )
        return ("important", prob)
    return (choice, prob)
