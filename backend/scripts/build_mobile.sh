#!/bin/bash
# Build Python backend for mobile platforms using serious_python.
#
# Usage:
#   ./build_mobile.sh Android
#   ./build_mobile.sh iOS

set -e

PLATFORM=${1:-Android}

echo "Building ChatBox Backend for $PLATFORM..."

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
BACKEND_DIR="$SCRIPT_DIR/.."

cd "$PROJECT_ROOT"

if [ ! -f "pubspec.yaml" ]; then
    echo "Error: Run from Flutter project root or ensure project structure is correct"
    exit 1
fi

mkdir -p assets/backend

dart run serious_python:main package "$BACKEND_DIR" \
    -p "$PLATFORM" \
    --asset assets/backend/app.zip \
    --requirements fastapi,uvicorn,pydantic,pydantic-settings,httpx,sse-starlette

echo "Build complete: assets/backend/app.zip"
echo "Run 'flutter build apk' or 'flutter build ios' to build app"
