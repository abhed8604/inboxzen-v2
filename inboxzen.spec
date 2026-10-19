# -*- mode: python ; coding: utf-8 -*-
import os
from pathlib import Path

block_cipher = None

project_dir = Path.cwd()

datas = [
    (str(project_dir / "app" / "templates"), "app/templates"),
    (str(project_dir / "app" / "static"), "app/static"),
]

if (project_dir / "credentials.json").exists():
    datas.append((str(project_dir / "credentials.json"), "."))
if (project_dir / "credentials.json.example").exists():
    datas.append((str(project_dir / "credentials.json.example"), "."))

# Bundle native llama.cpp binaries and shared libraries from ./bin
cuda_patterns = ("libcublas", "libggml-cuda", "libcudart", "libnvjitlink")
binaries = []
bin_dir = project_dir / "bin"
if bin_dir.exists():
    for f in bin_dir.iterdir():
        # Exclude GGUF models (downloaded on demand)
        if f.suffix.lower() == ".gguf":
            continue
        # Exclude heavy CUDA libraries (downloaded on-demand when user selects GPU)
        if any(pat in f.name.lower() for pat in cuda_patterns):
            continue
        if f.is_file() or f.is_symlink():
            binaries.append((str(f), "bin"))

hidden_imports = [
    "uvicorn",
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.uvloop",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespans",
    "uvicorn.lifespans.on",
    "fastapi",
    "starlette",
    "jinja2",
    "selectolax",
    "selectolax.parser",
    "keyring",
    "keyring.backends",
    "keyring.backends.SecretStorage",
    "webview",
    "webview.platforms.gtk",
    "gi",
    "gi.repository.GLib",
    "gi.repository.GObject",
    "gi.repository.Gio",
    "gi.repository.Gtk",
    "gi.repository.Gdk",
    "gi.repository.WebKit2",
    "googleapiclient",
    "google_auth_oauthlib",
]

a = Analysis(
    ["desktop.py"],
    pathex=[str(project_dir)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "scipy", "numpy", "PIL", "pillow", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Filter out heavy CUDA/NVIDIA libraries discovered by PyInstaller crawler
a.binaries = [
    (dest, src, typ) for (dest, src, typ) in a.binaries
    if not any(pat in os.path.basename(dest).lower() for pat in cuda_patterns)
]

# Filter out unused google discovery cache (keep only gmail.v1) and heavy system icon themes
filtered_datas = []
for dest, src, typ in a.datas:
    dest_lower = dest.lower()
    if "googleapiclient/discovery_cache/documents" in dest_lower:
        if "gmail.v1.json" not in dest_lower:
            continue
    if dest.startswith("share/icons/Yaru") or dest.startswith("share/themes") or dest.startswith("share/icons/Adwaita") or dest.startswith("share/icons/HighContrast"):
        continue
    filtered_datas.append((dest, src, typ))
a.datas = filtered_datas

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="inboxzen",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(project_dir / "app" / "static" / "logo.svg") if (project_dir / "app" / "static" / "logo.svg").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="InboxZen",
)
