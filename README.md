# InboxZen

InboxZen is a local, private email triage client and reader powered by an on-device lightweight language model. It classifies incoming emails into **Important**, **Very Important**, and **Low Priority** categories based on customizable markdown instructions, keeping triage private and noise-free.

---

## Features

- **Local LLM Triage**: Uses `ggml-org/vllm-d3-lite-GGUF` via `llama-server` running fully offline in GPU VRAM (~1.1 GB memory footprint).
- **Custom Classification Rules**: Edit your triage prompt in Markdown directly from the UI without restarting the application.
- **Privacy & Security**: Zero external tracking, in-app sandboxed iframe reader, and OAuth tokens stored safely in your system keyring.
- **Multi-Account Filtering**: Connect multiple Gmail accounts and switch or filter emails per account with one click.
- **Light & Dark Themes**: Fully adaptive interface with synchronized color palettes across both HTML and plain-text email views.
- **Fast Desktop UI**: Built with FastAPI, Jinja2, HTMX, and pure modern CSS.

---

## Prerequisites

- **Python**: 3.10 or newer
- **llama-server**: [llama.cpp](https://github.com/ggerganov/llama.cpp) binary installed on your system `PATH` (or placed in `./bin/`)
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

5. **(Optional) Configure environment variables**:
   ```bash
   cp .env.example .env
   ```

---

## Running the Application

Start the server using:

```bash
python run.py
```

The app will start on `http://127.0.0.1:8000`.

- On startup, `llama-server` automatically spins up on port `8081` with GPU layer offloading.
- Initial seed emails are loaded automatically for instant local exploration if no Gmail accounts are synced yet.
- Click **Sync mails** in the sidebar to authenticate and fetch real emails via Gmail OAuth.

---

## Project Structure

```text
├── app/
│   ├── auth.py          # Google OAuth2 flow and keyring token storage
│   ├── classifier.py    # llama-server management and classification logic
│   ├── config.py        # App configuration, triage prompts, and model arguments
│   ├── db.py            # SQLite schema, queries, and count aggregations
│   ├── gmail_sync.py    # Gmail API message fetcher and classifier pipeline
│   ├── main.py          # FastAPI application routes and lifespan hooks
│   ├── seed.py          # Demo inbox emails for testing and development
│   ├── static/          # CSS, JavaScript controller, and SVG assets
│   └── templates/       # Jinja2 templates and partials for HTMX swaps
├── credentials.json.example  # Sample OAuth desktop client structure
├── .env.example              # Sample environment configuration
├── .gitignore                # Excludes credentials, databases, virtualenvs, binaries
├── requirements.txt          # Python dependencies
└── run.py                    # Application entrypoint
```

---

## License

MIT
