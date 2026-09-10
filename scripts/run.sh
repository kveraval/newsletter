#!/usr/bin/env bash
set -euo pipefail
export PATH="$PATH:/root/.tavily-env/bin"
cd /root/.openclaw/workspace/newsletter
python3 scripts/generate.py
