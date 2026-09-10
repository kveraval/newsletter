#!/usr/bin/env bash
set -euo pipefail
export PATH="$PATH:/root/.tavily-env/bin"
cd /root/.openclaw/workspace/newsletter

# Generate today's edition
python3 scripts/generate.py

# Commit and publish to GitHub Pages
git add -A
git commit -m "Daily newsletter update - $(date +%Y-%m-%d)" || true
git push origin main || true
