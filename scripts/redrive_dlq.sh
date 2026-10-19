#!/usr/bin/env bash
# Redrive messages from a DLQ back to the source queue using AWS SQS Message Move Task
set -euo pipefail

if [ "$#" -lt 1 ]; then
    echo "Usage: bash redrive_dlq.sh <DLQ_ARN> [DESTINATION_QUEUE_ARN]"
    exit 1
fi

DLQ_ARN="$1"
DEST_ARN="${2:-}"

echo "Initiating redrive task for DLQ: $DLQ_ARN..."
if [ -n "$DEST_ARN" ]; then
    aws sqs start-message-move-task --source-arn "$DLQ_ARN" --destination-arn "$DEST_ARN"
else
    aws sqs start-message-move-task --source-arn "$DLQ_ARN"
fi
echo "Redrive task started successfully."
