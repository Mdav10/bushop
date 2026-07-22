#!/bin/bash
set -e

echo "🚀 Building MugiStore..."

export PYTHON_VERSION=3.11.0

echo "📦 Installing Python dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "🗄️ Initializing database..."
python -c "from app import init_db; init_db()"

echo "✅ Build complete!"
