#!/usr/bin/env bash
# Redrive messages from a DLQ back to the source queue
set -euo pipefail
echo "Usage: bash redrive_dlq.sh <DLQ_URL> <SOURCE_QUEUE_URL>"
