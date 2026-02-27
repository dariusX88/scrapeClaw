#!/usr/bin/env bash
set -e

echo ""
echo "  ScrapeClaw Installer"
echo "  ===================="
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "  Python 3 is required but not installed."
    echo "  Install it from https://python.org"
    exit 1
fi

PY_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Python $PY_VERSION detected"

# Clone
if [ ! -d "scrapeClaw" ]; then
    echo "  Cloning repository..."
    git clone https://github.com/dariusX88/scrapeClaw.git
else
    echo "  scrapeClaw/ already exists, updating..."
    git -C scrapeClaw pull
fi

cd scrapeClaw

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "  Creating virtual environment..."
    python3 -m venv .venv
else
    echo "  Virtual environment already exists."
fi

# Activate and install
echo "  Installing dependencies..."
.venv/bin/pip install -e . --quiet

# Setup .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo ""
    echo "  Add your Anthropic API key to .env:"
    echo "  nano scrapeClaw/.env"
fi

echo ""
echo "  Installation complete!"
echo ""
echo "  Usage:"
echo "    cd scrapeClaw"
echo "    .venv/bin/scrapeclaw scrape example --max-pages 3"
echo ""
echo "  Or activate the virtual environment first:"
echo "    source .venv/bin/activate"
echo "    scrapeclaw scrape example --max-pages 3"
echo ""
echo "  Quick single-URL scrape:"
echo "    .venv/bin/scrapeclaw scrape-url https://example.com -f \"title,price\""
echo ""
