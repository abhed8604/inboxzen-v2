import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "InboxZen"
DATA_DIR = Path.home() / ".local" / "share" / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)

def get_bundle_dir() -> Path:
    """Returns the base directory for bundled resources (PyInstaller-compatible)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent

DB_PATH = DATA_DIR / "inboxzen.db"

# Check credentials in app data dir first, then bundle root
if (DATA_DIR / "credentials.json").exists():
    CREDENTIALS_FILE = DATA_DIR / "credentials.json"
else:
    CREDENTIALS_FILE = get_bundle_dir() / "credentials.json"

LLAMA_HOST = "127.0.0.1"
LLAMA_PORT = 8081
LLAMA_URL = f"http://{LLAMA_HOST}:{LLAMA_PORT}"
MODEL_REPO = "ggml-org/vllm-d3-lite-GGUF:Q8_0"
MODEL_FILENAME = "vllm-d3-lite-Q8_0.gguf"
MODEL_URL = f"https://huggingface.co/ggml-org/vllm-d3-lite-GGUF/resolve/main/{MODEL_FILENAME}"

SYNC_INTERVAL_SECONDS = 60

def get_model_path() -> Path | None:
    """Returns the local path to the GGUF model file if it exists."""
    local_path = DATA_DIR / "models" / MODEL_FILENAME
    if local_path.exists() and local_path.stat().st_size > 500_000_000:
        return local_path
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub" / "models--ggml-org--vllm-d3-lite-GGUF"
    if hf_cache.exists():
        for gguf in hf_cache.glob("**/*.gguf"):
            if gguf.stat().st_size > 500_000_000:
                return gguf.resolve()
    dev_path = Path("bin") / MODEL_FILENAME
    if dev_path.exists() and dev_path.stat().st_size > 500_000_000:
        return dev_path
    return None

def is_model_downloaded() -> bool:
    """Checks if the GGUF model exists locally."""
    return get_model_path() is not None

DEFAULT_TRIAGE_PROMPT = """# User Profile
Final-year engineering student & software developer.

## VERY_IMPORTANT (Action Required or Urgent)
- Direct emails from recruiters, hiring managers, HR, professors, or teammates
- Interview invitations, scheduling links, and job offers
- Online coding assessments (HackerRank, Mettl, CodeSignal, OA links)
- Placement cell (TnP) notices and urgent academic deadlines
- OTPs, 2FA security alerts, bank bills, and travel tickets

## IMPORTANT (Worth Reading Today, No Urgent Deadline)
- General college or department announcements
- GitHub PRs, issue mentions, and CI/CD notifications
- Hackathon updates, project threads, and package delivery updates

## LOW_PRIORITY (Automated Bulk Mail & Noise)
- Automated job board digests (LinkedIn Job Alerts, Naukri, Unstop, Wellfound digests)
- Marketing newsletters, course promotions, and discount codes
- Automated payment receipts, social media digests, and cold outreach"""

def get_compute_device() -> str:
    from app.db import get_setting
    return get_setting("compute_device", "cpu")

def has_nvidia_gpu() -> bool:
    return shutil.which("nvidia-smi") is not None

def get_nvidia_gpu_name() -> str:
    if not has_nvidia_gpu():
        return ""
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            stderr=subprocess.DEVNULL,
            timeout=2.0
        ).decode().strip()
        return out.splitlines()[0].strip() if out else "NVIDIA GPU"
    except Exception:
        return "NVIDIA GPU"

def is_cuda_installed() -> bool:
    cuda_dir = DATA_DIR / "cuda"
    if (cuda_dir / "libggml-cuda.so").exists():
        return True
    if getattr(sys, "frozen", False):
        bundled_cuda = get_bundle_dir() / "bin" / "libggml-cuda.so"
        return bundled_cuda.exists()
    return False

def compute_prompt_hash(md_text: str) -> str:
    return hashlib.sha256(md_text.strip().encode("utf-8")).hexdigest()[:16]

def get_llama_cmd(gpu_enabled: bool | None = None) -> tuple[list[str], dict]:
    # Check bundled bin/ first, then local ./bin, then system PATH
    bundle_bin = get_bundle_dir() / "bin" / ("llama-server.exe" if os.name == "nt" else "llama-server")
    local_bin = Path("bin") / ("llama-server.exe" if os.name == "nt" else "llama-server")
    if bundle_bin.exists():
        binary = str(bundle_bin)
    elif local_bin.exists():
        binary = str(local_bin)
    else:
        binary = shutil.which("llama-server") or "llama-server"

    if gpu_enabled is None:
        gpu_enabled = (get_compute_device() == "gpu") and is_cuda_installed()

    ngl = "99" if gpu_enabled else "0"

    env = dict(os.environ)
    cuda_dir = DATA_DIR / "cuda"
    current_ld = env.get("LD_LIBRARY_PATH", "")
    dirs = []
    if cuda_dir.exists():
        dirs.append(str(cuda_dir))
    bundle_bin_dir = str(get_bundle_dir() / "bin")
    if bundle_bin_dir not in dirs:
        dirs.append(bundle_bin_dir)
    if current_ld:
        dirs.append(current_ld)
    env["LD_LIBRARY_PATH"] = ":".join(dirs)

    model_path = get_model_path()
    if model_path:
        model_args = ["-m", str(model_path)]
    else:
        model_args = ["-hf", MODEL_REPO]

    cmd = [
        binary,
        *model_args,
        "--no-mmproj",          # Do not load vision projector into VRAM
        "-ngl", ngl,            # 99 for GPU VRAM, 0 for pure CPU
        "-c", "2048",           # Total context size
        "-b", "2048",           # Batch size (MUST equal -ub for vllm-d3)
        "-ub", "2048",          # Micro-batch size (fits full email + triage prompt)
        "-np", "1",             # Single slot to keep memory flat
        "--cache-ram", "0",     # Disable RAM cache to prevent memory growth
        "--host", LLAMA_HOST,
        "--port", str(LLAMA_PORT),
    ]
    return cmd, env
