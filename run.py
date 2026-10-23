import uvicorn

from app.config import SESSION_TOKEN

if __name__ == "__main__":
    # No auto-reload: a reload would leave the llama-server child running and
    # the next worker would silently reuse the old engine.
    print(f"Open http://127.0.0.1:8000/?token={SESSION_TOKEN}")
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, access_log=False)
