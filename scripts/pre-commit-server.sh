#!/bin/sh
# Server quality gate. Mirrors `make -C server check`, with formatting applied and re-staged
# rather than merely checked. Run standalone to reproduce what the commit hook saw.
set -e

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"

if ! command -v uv >/dev/null 2>&1; then
	echo "pre-commit: uv is not on PATH — install it (https://astral.sh/uv) or commit with --no-verify." >&2
	exit 1
fi

staged_py=$(git diff --cached --name-only --diff-filter=ACMR -- 'server/*.py' | sed 's|^server/||')

# 1. Format and auto-fix, then re-stage.
if [ -n "$staged_py" ]; then
	# dev-note: a file that is *partially* staged must not be blind `git add`-ed — that would
	# sweep unrelated working-tree edits into the commit. Those are reported instead, and the
	# developer runs `make -C server fmt` and stages deliberately.
	dirty=$(git diff --name-only -- 'server/*.py' | sed 's|^server/||')
	conflicted=""
	for f in $staged_py; do
		for d in $dirty; do
			[ "$f" = "$d" ] && conflicted="$conflicted $f"
		done
	done

	(cd server && printf '%s\n' $staged_py | xargs uv run ruff check --fix --quiet -- ) || true
	(cd server && printf '%s\n' $staged_py | xargs uv run ruff format --quiet -- )

	if [ -n "$conflicted" ]; then
		echo "pre-commit: these files have both staged and unstaged changes, so formatting was" >&2
		echo "            applied but NOT re-staged:$conflicted" >&2
		echo "            Review the working tree and stage what you mean to commit." >&2
		exit 1
	fi
	# Re-staged from the repo root: these paths are repo-relative, not server-relative.
	printf '%s\n' $staged_py | sed 's|^|server/|' | xargs git add --
fi

# 2. Lint, 3. static analysis, 4. tests + coverage floor — any of these blocks the commit.
cd server
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run pytest --cov -q

# 5. Dependency audit — advisory. A fresh CVE in a transitive dependency is not the committer's
# fault and blocking every commit in the repo on it is how hooks get bypassed wholesale.
if ! make audit >/dev/null 2>&1; then
	echo "pre-commit: WARNING — dependency audit reported findings. Run 'make -C server audit'." >&2
fi
