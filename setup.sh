#!/bin/bash
# RasoSpeak v2 — Setup Script
# Installs all dependencies and configures the environment
# No GPU required - works on 4GB RAM

set -e

echo "╔══════════════════════════════════════════════════════╗"
echo "║   RasoSpeak v2 — No GPU Setup                          ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""

# Check Python version
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "📌 Python version: $python_version"

# Create virtual environment if not exists
if [ ! -d ".venv" ]; then
    echo "🔧 Creating virtual environment..."
    python3 -m venv .venv
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

# Create .env from example if not exists
if [ ! -f ".env" ]; then
    echo "📝 Creating .env from example..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env and add your API keys!"
    echo "   Get free API keys:"
    echo "   - Google: https://aistudio.google.com/app/apikey"
    echo "   - NVIDIA: https://build.nvidia.com/"
    echo ""
else
    echo "✅ .env file already exists"
fi

# Create directories
echo "📁 Creating directories..."
mkdir -p memory/documents recordings

echo ""
echo "╔══════════════════════════════════════════════════════╗"
echo "║   ✅ Setup Complete!                                  ║"
echo "╚══════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your API keys"
echo "2. Run: uvicorn main:app --reload --port 7860"
echo "3. Open: http://localhost:7860"
echo ""
echo "Default provider: Google Gemini"
echo "To switch: Change DEFAULT_PROVIDER in .env"
echo ""