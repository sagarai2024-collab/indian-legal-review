#!/usr/bin/env bash
# Run the review-agreement skill headlessly on every eval case, then score it.
# Needs Claude Code installed and logged in. Run from the repository root:
#   bash evals/run_agent.sh
# Each run writes legal-review/<case>/{prescan,report}.json and report.md.
# If your Claude Code version names the plugin flag differently, adjust PLUGIN_FLAG.
set -euo pipefail
PLUGIN_FLAG="--plugin-dir ."
for doc in evals/cases/*; do
  case "$doc" in *.json) continue ;; esac
  stem="$(basename "${doc%.*}")"
  echo "== $stem"
  claude -p "Use the indian-legal-review:review-agreement skill to review ${doc}. \
Write the working files to ./legal-review/${stem}/. Do not ask questions; this is an unattended eval run." \
    $PLUGIN_FLAG --allowedTools "Read,Write,Bash(python3:*)" > "/dev/null" || echo "   run failed: $stem"
done
python3 evals/score.py --layer agent
