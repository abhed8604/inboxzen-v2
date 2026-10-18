import asyncio
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
    cmd = get_llama_cmd()
    try:
        _llama_process = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        return

    for _ in range(120):
        if await is_llama_healthy(client):
            return
        await asyncio.sleep(0.5)

def stop_llama_server():
    global _llama_process
    if _llama_process and _llama_process.poll() is None:
        _llama_process.terminate()
        try:
            _llama_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            _llama_process.kill()

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
