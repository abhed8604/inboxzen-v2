import asyncio
from pathlib import Path
import subprocess
import httpx
from app.config import get_llama_cmd, LLAMA_URL

CONFIDENCE_THRESHOLD = 0.60

_llama_process: subprocess.Popen | None = None

async def is_llama_healthy(client: httpx.AsyncClient) -> bool:
    try:
        r = await client.get(f"{LLAMA_URL}/health", timeout=1.5)
        return r.status_code == 200
    except Exception:
        return False

async def start_llama_server(client: httpx.AsyncClient):
    global _llama_process
    if await is_llama_healthy(client):
        return
    cmd, env = get_llama_cmd()
    try:
        _llama_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )
    except FileNotFoundError:
        return

    # Non-blocking background health waiter
    async def wait_healthy():
        for _ in range(120):
            if await is_llama_healthy(client):
                return
            await asyncio.sleep(0.5)

    asyncio.create_task(wait_healthy())

def stop_llama_server():
    global _llama_process
    if _llama_process and _llama_process.poll() is None:
        _llama_process.terminate()
        try:
            _llama_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _llama_process.kill()
    _llama_process = None

async def restart_llama_server(client: httpx.AsyncClient):
    stop_llama_server()
    await asyncio.sleep(0.5)
    await start_llama_server(client)

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

# CUDA On-Demand Downloader State
cuda_download_state = {
    "status": "idle",     # idle, downloading, ready, error
    "percent": 0,
    "message": "",
}

async def install_cuda_runtime():
    """Installs or copies CUDA runtime libraries to DATA_DIR / 'cuda'."""
    global cuda_download_state
    from app.config import DATA_DIR, is_cuda_installed
    import shutil
    import urllib.request

    if is_cuda_installed():
        cuda_download_state = {"status": "completed", "percent": 100, "message": "CUDA already installed"}
        return

    cuda_dir = DATA_DIR / "cuda"
    cuda_dir.mkdir(parents=True, exist_ok=True)

    cuda_download_state = {"status": "downloading", "percent": 5, "message": "Initializing CUDA runtime install..."}

    local_bin = Path("bin")
    # If files exist in local bin, copy them over
    if (local_bin / "libggml-cuda.so").exists() and (local_bin / "libcublasLt.so.12").exists():
        cuda_download_state["message"] = "Copying local CUDA libraries..."
        files = ["libcublasLt.so.12", "libcublas.so.12", "libggml-cuda.so", "libcudart.so.12"]
        for idx, fname in enumerate(files):
            src = local_bin / fname
            if src.exists():
                shutil.copy2(src, cuda_dir / fname)
            cuda_download_state["percent"] = int(20 + (idx + 1) * 20)
            await asyncio.sleep(0.1)
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
            tar.extractall(path=cuda_dir)
        archive_path.unlink(missing_ok=True)
        cuda_download_state = {"status": "ready", "percent": 100, "message": "CUDA runtime ready!"}
    except Exception as e:
        cuda_download_state = {"status": "error", "percent": 0, "message": f"Download failed: {e}"}

async def classify_email(
    client: httpx.AsyncClient,
    email_row: dict,
    triage_prompt_md: str,
) -> tuple[str, float]:
    state_text = (
        f"Triage Rules (Markdown):\n{triage_prompt_md[:1200]}\n\n"
        f"---\n"
        f"Incoming Email:\n"
        f"From: {email_row['sender_name']} <{email_row['sender_email']}>\n"
        f"Subject: {email_row['subject'][:200]}\n"
        f"Date: {email_row['date_str']}\n"
        f"Body:\n{email_row['model_input'][:1500]}"
    )

    payload = {
        "state": state_text,
        "questions": {
            "triage": {
                "type": "choice",
                "instructions": "Classify this email into one category strictly following the Triage Rules (Markdown).",
                "criteria": {
                    "very_important": (
                        "Action required or time-sensitive from a person or critical system: "
                        "interview invite, online assessment link, job offer, recruiter email, "
                        "placement deadline, professor message, OTP code, bill due, or travel ticket."
                    ),
                    "important": (
                        "Useful update with no immediate deadline: college or department notice, "
                        "GitHub notification, project or hackathon update, package tracking, "
                        "or general conversation."
                    ),
                    "low_priority": (
                        "Bulk or automated mail needing no reply: job alert digest, newsletter, "
                        "promotional discount, marketing campaign, social media notification, "
                        "payment receipt, or cold spam."
                    )
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
        return ("important", prob)
    return (choice, prob)
