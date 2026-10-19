"""
InboxZen — Desktop Application Launcher
Runs FastAPI with Uvicorn in a background thread and opens a native PyWebview window.
"""
import socket
import sys
import threading
import time
import urllib.request
import uvicorn
import webview
from app.main import app

def find_free_port(start_port: int = 8000) -> int:
    """Finds an available local TCP port."""
    for port in range(start_port, start_port + 50):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return start_port

def wait_for_server(url: str, timeout: float = 10.0) -> bool:
    """Polls until the server is responding."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            with urllib.request.urlopen(f"{url}/api/engine/status", timeout=0.5) as response:
                if response.status == 200:
                    return True
        except Exception:
            time.sleep(0.1)
    return False

def main():
    if "--headless-check" in sys.argv:
        port = find_free_port(8000)
        server_url = f"http://127.0.0.1:{port}"
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_level="warning",
            access_log=False,
        )
        server = uvicorn.Server(config)
        server_thread = threading.Thread(target=server.run, daemon=True)
        server_thread.start()

        ready = wait_for_server(server_url, timeout=12.0)
        server.should_exit = True
        server_thread.join(timeout=2.0)
        if ready:
            print("InboxZen headless server check OK")
            sys.exit(0)
        else:
            print("InboxZen headless server check FAILED", file=sys.stderr)
            sys.exit(1)

    port = find_free_port(8000)
    server_url = f"http://127.0.0.1:{port}"

    # Configure uvicorn
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
    )
    server = uvicorn.Server(config)

    # Start uvicorn in background daemon thread
    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for server ready
    if not wait_for_server(server_url, timeout=12.0):
        print("Failed to start internal server.", file=sys.stderr)
        sys.exit(1)

    # Create native desktop window
    window = webview.create_window(
        title="InboxZen",
        url=server_url,
        width=1280,
        height=820,
        min_size=(960, 600),
        background_color="#111b1d",
    )

    # Start PyWebview with GTK/WebKit2
    try:
        webview.start(gui="gtk")
    except Exception:
        webview.start()

    # Clean shutdown on window close
    server.should_exit = True
    server_thread.join(timeout=2.0)

if __name__ == "__main__":
    main()
