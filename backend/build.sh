#!/usr/bin/env bash
# Build Lambda deployment packages
# Usage: bash build.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/build/lambda"
SHARED_DIR="$(dirname "$SCRIPT_DIR")/shared"

rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"

FUNCTIONS=(api dataset_profiler job_launcher status_updater dlq_reaper watchdog pre_signup)

for func in "${FUNCTIONS[@]}"; do
    echo "📦 Building $func..."
    FUNC_DIR="$BUILD_DIR/$func"
    mkdir -p "$FUNC_DIR"

    # Copy function code
    cp -r "$SCRIPT_DIR/$func/" "$FUNC_DIR/$func/"
    # Copy common module
    cp -r "$SCRIPT_DIR/common/" "$FUNC_DIR/common/"
    # Copy shared schemas/registry
    mkdir -p "$FUNC_DIR/shared"
    cp "$SHARED_DIR"/*.json "$FUNC_DIR/shared/" 2>/dev/null || true

    # Install dependencies
    pip install \
        --platform manylinux2014_x86_64 \
        --python-version 3.12 \
        --only-binary=:all: \
        --target "$FUNC_DIR" \
        aws-lambda-powertools jsonschema 2>/dev/null || \
    pip install --target "$FUNC_DIR" aws-lambda-powertools jsonschema

    # Create zip
    cd "$FUNC_DIR"
    zip -r "$BUILD_DIR/${func}.zip" . -x "__pycache__/*" "*.pyc"
    cd "$SCRIPT_DIR"

    echo "  ✅ $func.zip created"
done

echo ""
echo "✅ All Lambda packages built in $BUILD_DIR"
ls -lh "$BUILD_DIR"/*.zip
