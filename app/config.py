import hashlib
import os
import shutil
from pathlib import Path

APP_NAME = "InboxZen"
DATA_DIR = Path.home() / ".local" / "share" / APP_NAME
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "inboxzen.db"
CREDENTIALS_FILE = Path("credentials.json")

LLAMA_HOST = "127.0.0.1"
LLAMA_PORT = 8081
LLAMA_URL = f"http://{LLAMA_HOST}:{LLAMA_PORT}"
MODEL_REPO = "ggml-org/vllm-d3-lite-GGUF:Q8_0"

SYNC_INTERVAL_SECONDS = 60

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

def compute_prompt_hash(md_text: str) -> str:
    return hashlib.sha256(md_text.strip().encode("utf-8")).hexdigest()[:16]

def get_llama_cmd() -> list[str]:
    # Check local ./bin first (for future desktop packaging), then system PATH
    local_bin = Path("bin") / ("llama-server.exe" if os.name == "nt" else "llama-server")
    binary = str(local_bin) if local_bin.exists() else (shutil.which("llama-server") or "llama-server")

    return [
        binary,
        "-hf", MODEL_REPO,
        "--no-mmproj",          # Do not load vision projector into GTX 1650 VRAM
        "-ngl", "99",           # Offload 100% of layers to GPU VRAM
        "-c", "2048",           # Total context size
        "-b", "2048",           # Batch size (MUST equal -ub for vllm-d3)
        "-ub", "2048",          # Micro-batch size (fits full email + triage prompt)
        "-np", "1",             # Single slot to keep VRAM flat at ~1.1 GB
        "--cache-ram", "0",     # Disable RAM cache to prevent memory growth
        "--host", LLAMA_HOST,
        "--port", str(LLAMA_PORT),
    ]
