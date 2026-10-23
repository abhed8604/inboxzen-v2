import asyncio
import logging
import os
import re
import signal
import shutil
import tarfile
import time
import subprocess
from contextlib import asynccontextmanager
import httpx
from app.config import (
    get_llama_cmd,
    LLAMA_URL,
    LLAMA_LOG_PATH,
    LLAMA_PORT,
    TRIAGE_PROMPT_MAX_CHARS,
    MODEL_INPUT_CHARS,
    MODEL_MIN_BYTES,
)
from app import tasks

log = logging.getLogger(__name__)

CONFIDENCE_THRESHOLD = 0.60
HARD_RULE_CONFIDENCE = 0.60
RULE_CONFIDENCE = 0.90

_HARD_RULE_URGENT_RE = re.compile(
    r"\b("
    r"security alert|otp|one[ -]?time (password|code)|verification code|"
    r"verify your (device|identity|email)|new sign[ -]?in|sign[ -]?in|"
    r"account recovery|2-step verification|two-factor|"
    r"password (changed|reset)|assessment (link|invite)|deadline|last date|"
    r"due (today|tomorrow)|expires? (today|tomorrow)|"
    r"(less than )?\d+\s*(hours?|minutes?)\s+left"
    r")\b",
    re.IGNORECASE,
)


_INTERVIEW_ACTION_RE = re.compile(
    r"\b("
    r"interview (invitation|invite|scheduled|call|round|today|tomorrow)|"
    r"assessment (link|invite)|offer letter|shortlist"
    r")\b",
    re.IGNORECASE,
)


def _hard_rule_urgent(email_row: dict) -> bool:
    text = f"{email_row.get('subject', '')}\n{email_row.get('model_input', '')}"
    return bool(
        _HARD_RULE_URGENT_RE.search(text)
        or _INTERVIEW_ACTION_RE.search(text)
    )


_MASS_SENDER_RE = re.compile(
    r"^(?:.*[-_.])?(no[-_.]?reply|updates?|notifications?|newsletters?|"
    r"marketing|promotions?|events?|digests?)(?:[-_.][^@]*)?@",
    re.IGNORECASE,
)
_MARKETING_SUBJECT_RE = re.compile(
    r"("
    r"\bwin\b|\bprize\b|prize pool|\bgrab\b|\bppi\b|\bstipend\b|giveaway|"
    r"contest|coupon|discount|% off|cashback|limited time|last chance|"
    r"few hours|expires? (soon|today|tomorrow)|register now|don'?t miss|"
    r"up for grabs"
    r")",
    re.IGNORECASE,
)


def _bulk_marketing(email_row: dict) -> bool:
    return (
        _MASS_SENDER_RE.search(email_row.get("sender_email", "")) is not None
        and _MARKETING_SUBJECT_RE.search(email_row.get("subject", "")) is not None
    )


_SECURITY_VI_SUBJECT_RE = re.compile(
    r"("
    r"security alert|new sign[ -]?in|new login|account recovery|"
    r"account (was )?recovered|verify your (device|email|identity)|"
    r"verification code|one[ -]?time (password|code)|\botp\b|"
    r"2-step verification|two-factor|password (changed|reset)|"
    r"security code|suspicious (activity|login)"
    r")",
    re.IGNORECASE,
)
_SECURITY_STATUS_SUBJECT_RE = re.compile(
    r"(verification (successfully )?completed|customer verification)",
    re.IGNORECASE,
)
_ACTION_VI_SUBJECT_RE = re.compile(
    r"("
    r"online assessment|assessment (link|invite)|attempt:?\s+round|"
    r"goes live in less than|"
    r"interview (invitation|invite|scheduled|call|today|tomorrow)|"
    r"offer letter|shortlisted"
    r")",
    re.IGNORECASE,
)
_EVENT_IMPORTANT_SUBJECT_RE = re.compile(
    r"(made it to round|registration (complete|initiated)|confirmation pending)",
    re.IGNORECASE,
)


def _deterministic_override(email_row: dict) -> tuple[str, str] | None:
    subject = email_row.get("subject", "")
    if _SECURITY_VI_SUBJECT_RE.search(subject):
        return "very_important", "security"
    if _ACTION_VI_SUBJECT_RE.search(subject):
        return "very_important", "action"
    if _EVENT_IMPORTANT_SUBJECT_RE.search(subject):
        return "important", "event-status"
    if _SECURITY_STATUS_SUBJECT_RE.search(subject):
        return "important", "security-status"
    return None


def _apply_deterministic_override(
    email_row: dict, choice: str, prob: float,
) -> tuple[str, float, str | None]:
    override = _deterministic_override(email_row)
    if not override:
        return choice, prob, None
    new_choice, reason = override
    promote = (
        (new_choice == "very_important" and choice != "very_important")
        or (new_choice == "important" and choice == "low_priority")
    )
    if promote:
        return new_choice, RULE_CONFIDENCE, reason
    return choice, prob, None


_llama_process: subprocess.Popen | None = None
_llama_last_error: str | None = None
_last_restart_ts = 0.0
_engine_session = False  # True once this session deliberately launched the engine

_engine_lock = asyncio.Lock()
_model_download_lock = asyncio.Lock()
_cuda_download_lock = asyncio.Lock()

WATCHDOG_RESTART_COOLDOWN = 120  # don't fight a manual restart that just happened
WATCHDOG_MAX_FAILS = 3           # failed restart cycles before auto-restart stops (manual start clears)
_watchdog_fails = 0

IDLE_UNLOAD_SECONDS = 30.0
IDLE_CHECK_INTERVAL = 1.0
_last_activity = 0.0
_active_uses = 0
_engine_starting = False
_use_lock = asyncio.Lock()

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


def mark_engine_activity() -> None:
    global _last_activity
    _last_activity = time.monotonic()


@asynccontextmanager
async def engine_use():
    """Keeps the idle unloader away for the whole classification job."""
    global _active_uses, _last_activity
    async with _use_lock:
        _active_uses += 1
        _last_activity = time.monotonic()
    try:
        yield
    finally:
        async with _use_lock:
            _active_uses -= 1
            _last_activity = time.monotonic()


async def maybe_unload_idle_engine() -> bool:
    """Stops llama-server once it has been idle long enough."""
    global _engine_starting, _engine_session
    async with _use_lock:
        if not _engine_session or _active_uses or _engine_starting:
            return False
        if time.monotonic() - _last_activity < IDLE_UNLOAD_SECONDS:
            return False
        async with _engine_lock:
            if not _engine_session or _active_uses or _engine_starting:
                return False
            if time.monotonic() - _last_activity < IDLE_UNLOAD_SECONDS:
                return False
            if _llama_process is not None:
                stop_llama_server()
            else:
                _kill_port_listener(LLAMA_PORT)
                _engine_session = False
            log.info("Engine idle for %.0fs; unloaded", IDLE_UNLOAD_SECONDS)
            return True


async def idle_unload_loop():
    while True:
        await asyncio.sleep(IDLE_CHECK_INTERVAL)
        try:
            await maybe_unload_idle_engine()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Idle engine unload failed")


async def _start_llama_locked(client: httpx.AsyncClient):
    global _llama_process, _llama_last_error, _engine_session, _engine_starting
    if await is_llama_healthy(client):
        _llama_last_error = None
        _engine_session = True
        mark_engine_activity()
        return
    if _llama_process and _llama_process.poll() is None:
        return
    cmd, env = get_llama_cmd()
    try:
        with open(LLAMA_LOG_PATH, "wb") as llama_log:
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
    _engine_starting = True

    async def wait_healthy():
        global _engine_starting
        try:
            for _ in range(120):
                if await is_llama_healthy(client):
                    log.info("llama-server healthy")
                    _set_llama_error(None)
                    mark_engine_activity()
                    return
                await asyncio.sleep(0.5)
            if await is_llama_healthy(client):
                mark_engine_activity()
                return
            _set_llama_error("Engine did not become healthy after 60s (see llama-server.log)")
        finally:
            _engine_starting = False

    tasks.spawn(wait_healthy())


async def start_llama_server(client: httpx.AsyncClient):
    async with _engine_lock:
        await _start_llama_locked(client)

def stop_llama_server():
    global _llama_process, _engine_session, _engine_starting
    _engine_session = False
    _engine_starting = False
    if _llama_process and _llama_process.poll() is None:
        _llama_process.terminate()
        try:
            _llama_process.wait(timeout=5)
            log.info("llama-server stopped")
        except subprocess.TimeoutExpired:
            _llama_process.kill()
            log.warning("llama-server force-killed after terminate timeout")
    _llama_process = None


def _kill_port_listener(port: int) -> bool:
    """Best-effort kill of a stray llama-server on `port` (Linux/macOS)."""
    try:
        out = subprocess.run(
            ["ss", "-lptnH", f"sport = :{port}"],
            capture_output=True, text=True, timeout=3.0,
        ).stdout
    except Exception:
        return False
    procs = re.findall(r'users:\(\("([^"]+)",pid=(\d+)', out)
    killed = False
    for name, pid in procs:
        if "llama" not in name.lower():
            continue
        try:
            os.kill(int(pid), signal.SIGTERM)
            killed = True
            log.info("Stopped stray llama-server on port %s (pid %s)", port, pid)
        except Exception:
            pass
    return killed


async def _restart_llama_locked(client: httpx.AsyncClient, reset_watchdog: bool):
    global _last_restart_ts, _watchdog_fails
    _last_restart_ts = time.time()
    if reset_watchdog:
        _watchdog_fails = 0
    stop_llama_server()
    await asyncio.sleep(0.5)
    # An engine we do not own (left over from an earlier session) still holds
    # the port and would keep the old device settings: take the port back.
    if await is_llama_healthy(client):
        _kill_port_listener(LLAMA_PORT)
        await asyncio.sleep(0.5)
    await _start_llama_locked(client)


async def restart_llama_server(client: httpx.AsyncClient, reset_watchdog: bool = True):
    async with _engine_lock:
        await _restart_llama_locked(client, reset_watchdog)


async def ensure_engine_started(client: httpx.AsyncClient) -> bool:
    """Lazy launch: returns True once the local LLM is reachable, starting it
    on first use. Callers pass False only for "go without classification"."""
    global _engine_session, _watchdog_fails
    if await is_llama_healthy(client):
        _engine_session = True
        _watchdog_fails = 0
        mark_engine_activity()
        return True
    from app.config import is_model_downloaded
    if not is_model_downloaded():
        _set_llama_error("Engine not downloaded yet — start it from the Engine pane")
        return False
    async with _engine_lock:
        if await is_llama_healthy(client):
            _engine_session = True
            _watchdog_fails = 0
            mark_engine_activity()
            return True
        pre_existing_error = _llama_last_error
        await _start_llama_locked(client)
        if _llama_process is None and not await is_llama_healthy(client):
            return False
        for _ in range(120):
            if _llama_last_error and _llama_last_error != pre_existing_error:
                return False
            if await is_llama_healthy(client):
                _engine_session = True
                _watchdog_fails = 0
                mark_engine_activity()
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
        return True
    if _watchdog_fails >= WATCHDOG_MAX_FAILS:
        return False
    if time.time() - _last_restart_ts < WATCHDOG_RESTART_COOLDOWN:
        return False
    log.info("Engine watchdog: llama-server not responding; restarting")
    _watchdog_fails += 1
    if _watchdog_fails >= WATCHDOG_MAX_FAILS:
        _set_llama_error("Engine keeps dying (check llama-server.log); start it from the Engine pane")
    await restart_llama_server(client, reset_watchdog=False)
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

async def _download_to_file(url: str, dest, on_progress) -> int:
    """Streams `url` into `dest` and reports (downloaded, total) as it goes.
    A read timeout stops a stalled connection instead of hanging forever."""
    timeout = httpx.Timeout(connect=30.0, read=60.0, write=60.0, pool=30.0)
    downloaded = 0
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("content-length") or 0)
            encoded = bool(resp.headers.get("content-encoding"))
            with open(dest, "wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=256 * 1024):
                    f.write(chunk)
                    downloaded += len(chunk)
                    on_progress(downloaded, total)
    if total and not encoded and downloaded != total:
        raise RuntimeError(f"Download ended early ({downloaded} of {total} bytes)")
    return downloaded


async def download_model_file():
    async with _model_download_lock:
        await _download_model_file_locked()


async def _download_model_file_locked():
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
        def progress(downloaded, total_size):
            if total_size > 0:
                percent = min(99, int(downloaded * 100 / total_size))
                dl_mb = round(downloaded / (1024 * 1024), 1)
                tot_mb = round(total_size / (1024 * 1024), 1)
                model_download_state["percent"] = percent
                model_download_state["downloaded_mb"] = dl_mb
                model_download_state["total_mb"] = tot_mb
                model_download_state["message"] = f"Downloading: {dl_mb} MB / {tot_mb} MB ({percent}%)"

        await _download_to_file(MODEL_URL, temp_file, progress)
        if temp_file.stat().st_size < MODEL_MIN_BYTES:
            raise RuntimeError("Model download is incomplete")
        with open(temp_file, "rb") as f:
            if f.read(4) != b"GGUF":
                raise RuntimeError("Downloaded file is not a GGUF model")
        temp_file.replace(target_file)
        get_model_path.cache_clear()
        model_download_state = {
            "status": "ready",
            "percent": 100,
            "downloaded_mb": model_download_state.get("total_mb", 1032),
            "total_mb": model_download_state.get("total_mb", 1032),
            "message": "Model downloaded and ready!",
            "error": None,
        }
    except Exception as e:
        temp_file.unlink(missing_ok=True)
        model_download_state = {
            "status": "error",
            "percent": 0,
            "downloaded_mb": 0,
            "total_mb": 1032,
            "message": f"Download failed: {e}",
            "error": str(e),
        }
        log.error("Model download failed: %s", e)

# CUDA On-Demand Installer State
cuda_download_state = {
    "status": "idle",     # idle, downloading, extracting, ready, error
    "percent": 0,
    "message": "",
}


def cuda_install_in_progress() -> bool:
    return _cuda_download_lock.locked()


def _find_file(root, name: str):
    if not root.exists():
        return None
    for path in root.rglob(name):
        if path.is_file():
            return path
    return None


def _link_or_copy(source, target) -> None:
    try:
        os.link(source, target)
    except OSError:
        shutil.copy2(source, target)


def repair_cuda_layout() -> None:
    """Flattens an older install whose runtime was extracted into a
    subdirectory, and seeds the GPU backend from the bundle when present."""
    from app.config import DATA_DIR, CUDA_REQUIRED_FILES, get_bundle_dir

    cuda_dir = DATA_DIR / "cuda"
    cuda_dir.mkdir(parents=True, exist_ok=True)
    for name in CUDA_REQUIRED_FILES:
        target = cuda_dir / name
        if target.is_file():
            continue
        nested = _find_file(cuda_dir, name)
        if nested is not None and nested != target:
            shutil.move(str(nested), str(target))
            continue
        bundled = _find_file(get_bundle_dir() / "bin", name)
        if bundled is not None:
            try:
                _link_or_copy(bundled, target)
            except OSError:
                log.warning("Could not seed %s from the bundle", name)


def _seed_cuda_files(tmp_dir) -> None:
    """Reuses already-downloaded or bundled libraries before touching the
    network, so a missing 170 MB backend does not re-download 600 MB."""
    from app.config import DATA_DIR, CUDA_REQUIRED_FILES, get_bundle_dir

    roots = (DATA_DIR / "cuda", get_bundle_dir() / "bin")
    for name in CUDA_REQUIRED_FILES:
        target = tmp_dir / name
        if target.is_file():
            continue
        for root in roots:
            source = _find_file(root, name)
            if source is not None and source != target:
                _link_or_copy(source, target)
                break


def _extract_cuda_files(archive, names, dest) -> None:
    wanted = set(names)
    with tarfile.open(archive, "r:gz") as tar:
        for member in tar:
            if not member.isfile():
                continue
            base = os.path.basename(member.name)
            if base not in wanted:
                continue
            extracted = tar.extractfile(member)
            if extracted is None:
                continue
            with open(dest / base, "wb") as out:
                shutil.copyfileobj(extracted, out, 1024 * 1024)
            wanted.discard(base)
    if wanted:
        raise RuntimeError(f"archive is missing {', '.join(sorted(wanted))}")


async def install_cuda_runtime():
    async with _cuda_download_lock:
        await _install_cuda_runtime_locked()


async def _install_cuda_runtime_locked():
    """Installs the CUDA GPU backend and its runtime into DATA_DIR/cuda.

    Both llama.cpp release archives are used: the llama-…-cuda build carries
    libggml-cuda.so, while the cudart archive carries cublas/cudart. Files that
    already exist on disk are reused, so only the missing archive is fetched.
    """
    global cuda_download_state
    from app.config import (
        DATA_DIR,
        CUDA_BACKEND_FILES,
        CUDA_BACKEND_URL,
        CUDA_REQUIRED_FILES,
        CUDA_RUNTIME_FILES,
        CUDA_RUNTIME_URL,
        is_cuda_installed,
    )

    repair_cuda_layout()

    if is_cuda_installed():
        cuda_download_state = {
            "status": "ready", "percent": 100,
            "message": "CUDA backend already installed",
        }
        return

    cuda_dir = DATA_DIR / "cuda"
    tmp_dir = DATA_DIR / "cuda.tmp"
    shutil.rmtree(tmp_dir, ignore_errors=True)
    tmp_dir.mkdir(parents=True, exist_ok=True)
    cuda_download_state = {
        "status": "downloading", "percent": 2,
        "message": "Preparing CUDA install…",
    }

    try:
        _seed_cuda_files(tmp_dir)
        need_backend = any(not (tmp_dir / n).is_file() for n in CUDA_BACKEND_FILES)
        need_runtime = any(not (tmp_dir / n).is_file() for n in CUDA_RUNTIME_FILES)

        steps = []
        if need_backend:
            steps.append(("CUDA GPU backend", CUDA_BACKEND_URL, CUDA_BACKEND_FILES, 172))
        if need_runtime:
            steps.append(("CUDA runtime", CUDA_RUNTIME_URL, CUDA_RUNTIME_FILES, 594))
        total_weight = sum(step[3] for step in steps) or 1
        done_weight = 0

        for label, url, files, weight in steps:
            cuda_download_state.update(
                status="downloading",
                message=f"Downloading {label.lower()}…",
            )

            def progress(downloaded, total_size, label=label, weight=weight, base=done_weight):
                total_size = total_size or weight * 1024 * 1024
                fraction = min(1.0, downloaded / total_size) if total_size else 0.0
                percent = 5 + int(88 * (base + fraction * weight) / total_weight)
                cuda_download_state.update(
                    status="downloading",
                    percent=percent,
                    message=(
                        f"Downloading {label.lower()} — "
                        f"{downloaded // (1024 * 1024)} / "
                        f"{max(1, total_size // (1024 * 1024))} MB"
                    ),
                )

            archive = tmp_dir / f"{label.lower().replace(' ', '_')}.tar.gz"
            await _download_to_file(url, archive, progress)
            cuda_download_state.update(
                status="extracting",
                message=f"Extracting {label.lower()}…",
            )
            _extract_cuda_files(archive, files, tmp_dir)
            archive.unlink(missing_ok=True)
            done_weight += weight
            cuda_download_state["percent"] = 5 + int(88 * done_weight / total_weight)

        missing = [
            name for name in CUDA_REQUIRED_FILES
            if not (tmp_dir / name).is_file()
            or (tmp_dir / name).stat().st_size < 1024
        ]
        if missing:
            raise RuntimeError(f"missing after install: {', '.join(missing)}")

        shutil.rmtree(cuda_dir, ignore_errors=True)
        tmp_dir.replace(cuda_dir)
        cuda_download_state = {
            "status": "ready", "percent": 100,
            "message": "CUDA backend installed — GPU ready",
        }
        log.info("CUDA backend installed to %s", cuda_dir)
    except Exception as e:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        cuda_download_state = {
            "status": "error", "percent": 0,
            "message": f"Install failed: {e}",
        }
        log.error("CUDA install failed: %s", e)

async def classify_email(
    client: httpx.AsyncClient,
    email_row: dict,
    triage_prompt_md: str,
) -> tuple[str, float]:
    mark_engine_activity()
    state_text = (
        f"Triage Rules (Markdown):\n{triage_prompt_md[:TRIAGE_PROMPT_MAX_CHARS]}\n\n"
        f"---\n"
        f"Incoming Email:\n"
        f"From: {email_row['sender_name']} <{email_row['sender_email']}>\n"
        f"Subject: {email_row['subject'][:200]}\n"
        f"Date: {email_row['date_str']}\n"
        f"Body:\n{email_row['model_input'][:MODEL_INPUT_CHARS]}"
    )

    questions = {
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
    hard_rule_enabled = (
        re.search(r"never\s+low", triage_prompt_md, re.IGNORECASE) is not None
    )
    if hard_rule_enabled:
        questions["hard_rule"] = {
            "type": "choice",
            "instructions": (
                "Apply the hard rule independently of the Triage Rules. Answer yes "
                "if this email is a booking, ticket, reservation, bank/payment/loan, "
                "security alert, OTP, interview/assessment/offer, or has a concrete "
                "deadline. Answer no for bulk marketing, job-board digests, "
                "newsletters, promotions, and phishing."
            ),
            "criteria": {
                "yes": "Must never be low_priority.",
                "no": "May be low_priority.",
            },
        }
    payload = {"state": state_text, "questions": questions}

    resp = await client.post(f"{LLAMA_URL}/v1/systemone", json=payload, timeout=15.0)
    resp.raise_for_status()
    answers = resp.json()["answers"]
    triage_ans = answers["triage"]
    choice = triage_ans["choice"]
    prob = float(triage_ans.get("probabilities", {}).get(choice, 0.0))

    if choice not in ("very_important", "important", "low_priority"):
        log.info(
            "Invalid model choice for %s: choice=%s prob=%.2f; using important",
            email_row.get("id"), choice, prob,
        )
        return ("important", prob)

    if hard_rule_enabled:
        hard_ans = answers.get("hard_rule") or {}
        hard_choice = hard_ans.get("choice")
        hard_probs = hard_ans.get("probabilities") or {}
        hard_yes = float(hard_probs.get("yes", 0.0))
        if (
            hard_choice == "yes"
            and hard_yes >= HARD_RULE_CONFIDENCE
            and choice == "low_priority"
        ):
            new_choice = "very_important" if _hard_rule_urgent(email_row) else "important"
            log.info(
                "Hard-rule promotion for %s: %s %.2f -> %s %.2f",
                email_row.get("id"), choice, prob, new_choice, hard_yes,
            )
            choice, prob = new_choice, hard_yes
        elif (
            hard_choice == "no"
            and choice == "very_important"
            and prob < CONFIDENCE_THRESHOLD
        ):
            important_prob = float(
                triage_ans.get("probabilities", {}).get("important", 0.0)
            )
            log.info(
                "Hard-rule demotion for %s: very_important %.2f -> important %.2f",
                email_row.get("id"), prob, important_prob,
            )
            choice, prob = "important", important_prob

    if choice != "low_priority" and _bulk_marketing(email_row):
        low_prob = float(
            triage_ans.get("probabilities", {}).get("low_priority", 0.0)
        )
        log.info(
            "Bulk-marketing ceiling for %s: %s %.2f -> low_priority %.2f",
            email_row.get("id"), choice, prob, low_prob,
        )
        choice, prob = "low_priority", low_prob

    before_choice, before_prob = choice, prob
    choice, prob, reason = _apply_deterministic_override(email_row, choice, prob)
    if reason:
        log.info(
            "Deterministic %s promotion for %s: %s %.2f -> %s %.2f",
            reason, email_row.get("id"), before_choice, before_prob,
            choice, prob,
        )

    if prob < CONFIDENCE_THRESHOLD:
        # Confidence is informational: the model's top label is still the best
        # answer we have. Never hide urgent mail by downgrading it.
        log.info(
            "Low-confidence label kept for %s: choice=%s prob=%.2f",
            email_row.get("id"), choice, prob,
        )
    return (choice, prob)
