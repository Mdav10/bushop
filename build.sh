#!/bin/bash
set -e

echo "🚀 Starting build process for BuShop..."

# Install dependencies
echo "📦 Installing Python dependencies..."
pip install -r requirements.txt

# Reset and initialize database
echo "🗄️  Resetting and initializing database..."
python reset_db.py

echo "✅ Build completed successfully!"
