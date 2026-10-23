#!/usr/bin/env bash
set -e

echo "=== Building InboxZen Linux Desktop Application ==="

# Directory resolution
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

# Virtual environment python & pyinstaller
PYTHON="./.venv/bin/python3"
PYINSTALLER="./.venv/bin/pyinstaller"

if [ ! -f "$PYINSTALLER" ]; then
    echo "PyInstaller not found in .venv. Installing dependencies..."
    $PYTHON -m pip install pywebview pyinstaller
fi

LLAMA_RELEASE="${LLAMA_RELEASE:-$(sed -n 's/^LLAMA_RELEASE = "\(.*\)"/\1/p' app/config.py)}"
if [ -z "$LLAMA_RELEASE" ]; then
    echo "Could not determine the llama.cpp release."
    exit 1
fi

mkdir -p bin
if [ ! -x bin/llama-server ]; then
    echo "Fetching llama-server ${LLAMA_RELEASE}..."
    LLAMA_ARCHIVE="llama-${LLAMA_RELEASE}-bin-ubuntu-x64.tar.gz"
    LLAMA_URL="https://github.com/ggml-org/llama.cpp/releases/download/${LLAMA_RELEASE}/${LLAMA_ARCHIVE}"
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
    curl -fL --retry 3 --connect-timeout 30 -o "$TMP_DIR/$LLAMA_ARCHIVE" "$LLAMA_URL"
    tar -xzf "$TMP_DIR/$LLAMA_ARCHIVE" -C "$TMP_DIR"
    LLAMA_SOURCE="$(find "$TMP_DIR" -maxdepth 3 -type f -name llama-server -print -quit)"
    if [ -z "$LLAMA_SOURCE" ]; then
        echo "llama-server was not found in the downloaded release."
        exit 1
    fi
    LLAMA_DIR="$(dirname "$LLAMA_SOURCE")"
    cp -a "$LLAMA_DIR/llama-server" bin/
    for lib in "$LLAMA_DIR"/lib*.so*; do
        [ -e "$lib" ] && cp -a "$lib" bin/
    done
    chmod +x bin/llama-server
fi

# Clean previous build artifacts
rm -rf build dist

echo "Running PyInstaller..."
$PYINSTALLER inboxzen.spec --noconfirm

DIST_DIR="$DIR/dist/InboxZen"

# Create application icon
mkdir -p "$DIST_DIR/icons"
cp "$DIR/app/static/logo.svg" "$DIST_DIR/icons/inboxzen.svg"

# Create desktop launcher file
cat << 'EOF' > "$DIST_DIR/InboxZen.desktop"
[Desktop Entry]
Name=InboxZen
GenericName=Email Client
Comment=Autonomous Local LLM Email Triage Client
Exec=inboxzen
Icon=inboxzen
Terminal=false
Type=Application
Categories=Office;Network;Email;
Keywords=email;gmail;inbox;triage;ai;llm;
StartupWMClass=inboxzen
EOF

# Create quick user installer script
cat << 'EOF' > "$DIST_DIR/install.sh"
#!/usr/bin/env bash
set -e

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="$HOME/.local/lib/inboxzen"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"
ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"

echo "Installing InboxZen to $INSTALL_DIR..."
mkdir -p "$BIN_DIR" "$DESKTOP_DIR" "$ICON_DIR"
rm -rf "$INSTALL_DIR"
cp -r "$APP_DIR" "$INSTALL_DIR"

# Create symlink in ~/.local/bin
ln -sf "$INSTALL_DIR/inboxzen" "$BIN_DIR/inboxzen"

# Install icon
cp "$INSTALL_DIR/icons/inboxzen.svg" "$ICON_DIR/inboxzen.svg"

# Install desktop entry with absolute paths
sed -e "s|^Exec=.*|Exec=$BIN_DIR/inboxzen|g" \
    -e "s|^Icon=.*|Icon=$ICON_DIR/inboxzen.svg|g" \
    "$INSTALL_DIR/InboxZen.desktop" > "$DESKTOP_DIR/InboxZen.desktop"

chmod +x "$DESKTOP_DIR/InboxZen.desktop"
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true

echo "✓ InboxZen successfully installed!"
echo "You can launch it from your application menu or by typing 'inboxzen' in the terminal."
EOF

chmod +x "$DIST_DIR/install.sh"
chmod +x "$DIST_DIR/inboxzen"

echo "Creating compressed release package..."
tar -czf "$DIR/dist/InboxZen-linux-x86_64.tar.gz" -C "$DIR/dist" InboxZen

ARCHIVE_SIZE=$(du -h "$DIR/dist/InboxZen-linux-x86_64.tar.gz" | cut -f1)
BUNDLE_SIZE=$(du -sh "$DIST_DIR" | cut -f1)

echo ""
echo "=========================================================="
echo "✓ Build complete!"
echo "Bundle folder size: $BUNDLE_SIZE"
echo "Release archive: $DIR/dist/InboxZen-linux-x86_64.tar.gz ($ARCHIVE_SIZE)"
echo "To install to your desktop menu, run: cd $DIST_DIR && ./install.sh"
echo "=========================================================="
