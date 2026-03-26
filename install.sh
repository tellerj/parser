#!/usr/bin/env bash
set -e

# ---------------------------------------------------------------------------
# link16-parser install script
# Installs the package and ensures the command is on PATH.
# ---------------------------------------------------------------------------

MIN_PYTHON_MINOR=10  # requires 3.10+

# --- Check Python version ---------------------------------------------------

PYTHON=$(command -v python3 || command -v python || true)
if [ -z "$PYTHON" ]; then
    echo "ERROR: python3 not found. Install Python 3.10 or later and re-run."
    exit 1
fi

PYTHON_VERSION=$($PYTHON -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MINOR=$($PYTHON -c "import sys; print(sys.version_info.minor)")
PYTHON_MAJOR=$($PYTHON -c "import sys; print(sys.version_info.major)")

if [ "$PYTHON_MAJOR" -lt 3 ] || { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt "$MIN_PYTHON_MINOR" ]; }; then
    echo "ERROR: Python 3.${MIN_PYTHON_MINOR}+ required. Found Python ${PYTHON_VERSION}."
    exit 1
fi

echo "Python ${PYTHON_VERSION} — OK"

# --- Install package --------------------------------------------------------

echo "Installing link16-parser..."
$PYTHON -m pip install -e . --quiet
echo "Package installed."

# --- Ensure ~/.local/bin is on PATH -----------------------------------------

LOCAL_BIN="$HOME/.local/bin"

if ! echo "$PATH" | grep -q "$LOCAL_BIN"; then
    SHELL_RC=""
    if [ -n "$BASH_VERSION" ] && [ -f "$HOME/.bashrc" ]; then
        SHELL_RC="$HOME/.bashrc"
    elif [ -n "$ZSH_VERSION" ] && [ -f "$HOME/.zshrc" ]; then
        SHELL_RC="$HOME/.zshrc"
    elif [ -f "$HOME/.profile" ]; then
        SHELL_RC="$HOME/.profile"
    fi

    if [ -n "$SHELL_RC" ]; then
        echo "" >> "$SHELL_RC"
        echo '# Added by link16-parser install.sh' >> "$SHELL_RC"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$SHELL_RC"
        echo "Added ~/.local/bin to PATH in ${SHELL_RC}."
        echo "Run 'source ${SHELL_RC}' or open a new terminal for the change to take effect."
    else
        echo "WARNING: Could not detect shell config file."
        echo "Add the following line to your shell config manually:"
        echo '  export PATH="$HOME/.local/bin:$PATH"'
    fi
else
    echo "~/.local/bin already on PATH — OK"
fi

# --- Verify -----------------------------------------------------------------

if command -v link16-parser > /dev/null 2>&1; then
    echo ""
    echo "link16-parser is ready. Try:"
    echo "  link16-parser --file capture.pcap"
    echo "  sudo tcpdump -i eth0 -w - | link16-parser --pipe"
else
    echo ""
    echo "Install complete. Command will be available after running:"
    echo "  source ${SHELL_RC:-~/.bashrc}"
    echo ""
    echo "In the meantime you can use:"
    echo "  python3 -m link16_parser --file capture.pcap"
fi
