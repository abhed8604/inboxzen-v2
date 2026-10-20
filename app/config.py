import hashlib
import logging
import logging.handlers
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_NAME = "InboxZen"
DATA_DIR = Path.home() / ".local" / "share" / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)

LOG_PATH = DATA_DIR / "inboxzen.log"
LLAMA_LOG_PATH = DATA_DIR / "llama-server.log"

_logging_configured = False

def setup_logging(level: int = logging.INFO):
    """Configures app logging to a rotating file in DATA_DIR and stderr."""
    global _logging_configured
    if _logging_configured:
        return
    _logging_configured = True

    formatter = logging.Formatter(
        "%(asctime)s %(name)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    root = logging.getLogger()
    root.setLevel(level)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    root.addHandler(stream_handler)

    file_handler = logging.handlers.RotatingFileHandler(
        LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    # Keep per-request library chatter out of the logs
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

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
MODEL_DISPLAY_NAME = "vllm-d3-lite:Q8_0"
MODEL_URL = f"https://huggingface.co/ggml-org/vllm-d3-lite-GGUF/resolve/main/{MODEL_FILENAME}"

# Classification payload budget (chars). The -c 4096 context covers rules + body
# with headroom: rules and body tokens ~600 + ~875 + wrappers ~150 at worst case.
TRIAGE_PROMPT_MAX_CHARS = 2400
MODEL_INPUT_CHARS = 3500

SYNC_INTERVAL_SECONDS = 300

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
    dev_path = get_bundle_dir() / "bin" / MODEL_FILENAME
    if dev_path.exists() and dev_path.stat().st_size > 500_000_000:
        return dev_path
    return None

def is_model_downloaded() -> bool:
    """Checks if the GGUF model exists locally."""
    return get_model_path() is not None

DEFAULT_TRIAGE_PROMPT = """# User Profile
Final-year engineering student & software developer. Actively job-hunting through on-campus placement and off-campus applications. The inbox is mostly college, placement, and developer-tool traffic — judge each mail against that reality.

## VERY_IMPORTANT (Action Required or Time-Sensitive — act today)
- Direct mails from recruiters, hiring managers, HR, professors, or teammates
- Interview invitations, online assessments (HackerRank, Mettl, CodeSignal, company OA), scheduling links, and job offers
- Placement cell (TnP) notices: drives, shortlists, registration cut-offs, submission deadlines
- OTPs, 2FA and login alerts, security warnings, suspicious-activity notices
- Bills, fees, or dues with a stated deadline; travel tickets and bookings
- Any deadline stated in the mail that lands within the next 48 hours

## IMPORTANT (Worth Reading Today — no urgent clock)
- General college or department announcements, timetable or venue changes, event notices
- GitHub mentions, PR review requests, issue assigns, CI failures on your repositories
- Hackathon announcements, project or collaboration threads, community invitations
- Package delivery updates (especially out-for-delivery or failed delivery)
- Off-campus job postings that genuinely match the profile (not bulk digests)

## LOW_PRIORITY (Automated Bulk Mail & Noise — no reply needed)
- Job-board digests and alert mails: LinkedIn Job Alerts, Naukri, Unstop, Wellfound, Internshala
- Marketing newsletters, discount codes, course promos, webinar and conference reminders
- Social-media digests and notification storms (YouTube, Kaggle, Substack, forums)
- Automated receipts, confirmations, and tickets with no action and no deadline
- Cold outreach that asks for nothing specific; bulk mail from firms never applied to

## Tiebreakers
- A real person's name in From plus a specific question or ask → very_important, never low_priority.
- "Action required" boilerplate inside a bulk marketing footer → still low_priority.
- An automated mail that carries a real deadline (exam form, fee payment, hall ticket) → very_important.
- Torn between important and low_priority → answer important. Torn between very_important and important → answer important unless a deadline, OTP, or interview is explicitly stated."""

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
        "-c", "4096",           # Context: rules + body with headroom; KV cache stays tiny
        "-b", "2048",           # Batch size (MUST equal -ub for vllm-d3)
        "-ub", "2048",          # Micro-batch size (fits full email + triage prompt)
        "-np", "1",             # Single slot to keep memory flat
        "--cache-ram", "0",     # Disable RAM cache to prevent memory growth
        "--host", LLAMA_HOST,
        "--port", str(LLAMA_PORT),
    ]
    return cmd, env
