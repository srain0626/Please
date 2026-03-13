#!/usr/bin/env bash
set -euo pipefail

# Resolve common PR conflict files by preferring the current branch (ours),
# then run basic validation so the merge commit is safe.

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Not inside a git repository" >&2
  exit 1
fi

conflicted_files=(
  "README.md"
  "agent/__init__.py"
  "agent/runtime.py"
  "main.py"
  "tests/test_team_runtime.py"
)

# Ensure merge is in progress.
if [[ ! -f .git/MERGE_HEAD ]]; then
  echo "No merge in progress."
  echo "Usage:"
  echo "  git fetch origin"
  echo "  git checkout <your-branch>"
  echo "  git merge origin/<base-branch>"
  echo "  ./scripts/resolve_pr_conflicts.sh"
  exit 1
fi

for file in "${conflicted_files[@]}"; do
  if git ls-files -u -- "$file" | grep -q .; then
    echo "Resolving $file using current branch version (ours)"
    git checkout --ours -- "$file"
    git add "$file"
  fi
done

remaining=$(git diff --name-only --diff-filter=U)
if [[ -n "$remaining" ]]; then
  echo "Unresolved conflicts remain:"
  echo "$remaining"
  echo "Resolve them manually, then continue."
  exit 2
fi

echo "Running validation checks..."
python -m py_compile main.py agent/*.py tests/*.py
python -m unittest discover -s tests -v

echo "All conflicts resolved and checks passed."
echo "Now run: git commit"
