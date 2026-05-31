#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 <storage-account-name> [resource-group]" >&2
  exit 1
fi

STORAGE_ACCOUNT="$1"
RESOURCE_GROUP="${2:-}"

python3 website/src/build_website.py

az storage blob upload-batch \
  --account-name "$STORAGE_ACCOUNT" \
  --auth-mode login \
  --destination '$web' \
  --source website/dist \
  --overwrite

if [[ -n "$RESOURCE_GROUP" ]]; then
  az storage account show \
    --name "$STORAGE_ACCOUNT" \
    --resource-group "$RESOURCE_GROUP" \
    --query "primaryEndpoints.web" \
    --output tsv
fi
