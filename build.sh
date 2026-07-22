#!/bin/bash
set -e

echo "🚀 Building MugiStore..."

pip install -r requirements.txt

echo "🗄️ Initializing database..."
python -c "from app import init_db; init_db()"

echo "✅ Build complete!"
