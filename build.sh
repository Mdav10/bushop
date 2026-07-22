#!/bin/bash
set -e

echo "🚀 Building BuShop..."

# Install dependencies
pip install -r requirements.txt

# Initialize database
echo "🗄️ Initializing database..."
python -c "
from app import init_db
init_db()
"

echo "✅ Build complete!"
