#!/usr/bin/env bash
set -euo pipefail

# Local dev quality gate: fast checks for contract + tests.
: "${DJANGO_SETTINGS_MODULE:=tests_settings}"
export DJANGO_SETTINGS_MODULE

python -m django makemigrations --check --dry-run
python -m django webhooks_validate_contracts
python -m pytest tests.py -q

echo "dev_check: OK"
