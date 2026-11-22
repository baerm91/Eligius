#!/usr/bin/env bash
set -euo pipefail

# Blocks pushes when clearly local/development-only files are tracked.
# Intended as a last safety net in addition to .gitignore.

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "$ROOT_DIR"

forbidden_regex='(^|/)(\.venv/|venv/|\.envrc$|\.env$|\.env\..+|dev-local/|secrets/|db\.sqlite3$|.*\.sqlite3$|.*\.sql$|.*\.sql\.gz$|.*\.ppk$|.*\.pem$|.*\.key$|.*\.cnf$|.*\.tgz$|.*\.tar\.gz$|.*\.patch$|_archiv/|Claude outputs/)'
# Bewusst getrackte Vorlagen (siehe .gitignore: !.env.example, !dev-local/*.example)
allowed_regex='(^|/)(\.env\.example$|dev-local/[^/]+\.example$|dev-local/README\.md$)'

tracked_forbidden="$(git ls-files | grep -E "$forbidden_regex" | grep -Ev "$allowed_regex" || true)"

if [[ -n "$tracked_forbidden" ]]; then
  echo ""
  echo "❌ Push blocked: tracked local/dev files detected"
  echo ""
  echo "$tracked_forbidden"
  echo ""
  echo "Fix suggestions:"
  echo "  git rm --cached <file>"
  echo "  git commit -m 'remove local files from tracking'"
  echo ""
  exit 1
fi

echo "✅ prepush_guard: no forbidden tracked local/dev files found"
