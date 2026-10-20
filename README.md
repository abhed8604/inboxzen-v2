# InboxZen

InboxZen is a local, private email triage client and reader powered by an on-device lightweight language model. It classifies incoming emails into **Important**, **Very Important**, and **Low Priority** categories based on customizable markdown instructions, keeping triage private and noise-free.

---

## Features

- **Local LLM Triage**: Uses `ggml-org/vllm-d3-lite-GGUF` via `llama-server`, running fully on-device (CPU or NVIDIA GPU). The model is downloaded once from the UI and the engine loads lazily only when needed.
- **Custom Classification Rules**: Edit your triage prompt in Markdown and re-score your inbox without restarting the application.
- **Two-way Gmail Mirror**: Latest 400 inbox messages mirrored to a local SQLite store; read/unread states stay in sync both ways.
- **Privacy & Security**: OAuth tokens stored in your system keyring, emails sanitized server-side, and the reader renders HTML in a sandboxed iframe.
- **Multi-Account Filtering**: Connect multiple Gmail accounts and switch or filter emails per account with one click.
- **Light & Dark Themes**: Fully adaptive interface with synchronized color palettes across both HTML and plain-text email views.
- **Fast Desktop UI**: Built with FastAPI, Jinja2, HTMX, and pure modern CSS.

---

## Prerequisites

- **Python**: 3.10 or newer
- **llama-server**: [llama.cpp](https://github.com/ggerganov/llama.cpp) binary on your system `PATH` or in `./bin/` (the packaged desktop build bundles it)
- **Google Cloud Console Project**: Desktop OAuth 2.0 credentials for Gmail API access

---

## Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd zen3
   ```

2. **Set up a virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Configure Google OAuth**:
   - Create a project on the [Google Cloud Console](https://console.cloud.google.com/).
   - Enable the **Gmail API** under *APIs & Services > Library*.
   - Configure the **OAuth Consent Screen** (User Type: *External*, Scope: `https://www.googleapis.com/auth/gmail.readonly`, add your email to *Test Users*).
   - Under *Credentials > Create Credentials > OAuth client ID*, select **Desktop app**.
   - Download the JSON credentials and save it as `credentials.json` in the root of the project:
     ```bash
     cp credentials.json.example credentials.json
     # Replace placeholders with your actual Google Cloud client details
     ```

---

## Running the Application

Start the dev server using:

```bash
python run.py
```

The app will start on `http://127.0.0.1:8000`.

- Connect your Gmail account from **Settings > Accounts** (browser OAuth flow).
- The local LLM is **lazy**: it launches only when new mail arrives, you press Rescan, or you press Scan on an open email. **Engine pane > Start** loads it manually.
- **Sync mails** mirrors your inbox, **Rescan** re-scores the newest 100 emails with a live progress bar, **Scan** re-scores the open email.

---

## Desktop Build & Install

```bash
./build_linux.sh
cd dist/InboxZen && ./install.sh
```

This bundles everything with PyInstaller and installs to `~/.local/lib/inboxzen` with a launcher in your app menu (`inboxzen`).

---

## Project Structure

```text
├── app/                          # FastAPI package
│   ├── auth.py                   # Google OAuth2 flow and keyring token storage
│   ├── classifier.py             # lazy llama-server lifecycle, watchdog, classification
│   ├── config.py                 # App configuration, triage prompts, and model arguments
│   ├── db.py                     # SQLite schema, queries, and count aggregations
│   ├── gmail_sync.py             # two-way Gmail mirror sync + classification pipeline
│   ├── html_sanitize.py          # strips active content from stored email HTML
│   ├── tasks.py                  # background task registry for the event loop
│   ├── main.py                   # FastAPI application routes and lifespan hooks
│   ├── static/                   # CSS, JavaScript controller, and SVG assets
│   └── templates/                # Jinja2 templates and partials for HTMX swaps
├── bin/                          # runtime llama.cpp server + CUDA libs (gitignored)
├── build_linux.sh                # PyInstaller bundle + installer script generator
├── inboxzen.spec                 # PyInstaller spec (desktop entrypoint: desktop.py)
├── desktop.py                    # pywebview desktop shell + headless smoke check
├── credentials.json.example      # Sample OAuth desktop client structure
├── .gitignore                    # Excludes credentials, databases, virtualenvs, binaries
├── requirements.txt              # Python dependencies
└── run.py                        # Development entrypoint
```

---

## License

MIT
