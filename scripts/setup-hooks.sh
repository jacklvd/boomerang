#!/bin/sh
# Install the repo's git hooks. Idempotent; run once per clone.
#
# dev-note: husky is the client's tool and it is what runs on `bun install`, so it stays the
# owner of core.hooksPath when node tooling is present. A server-only developer needn't have
# bun at all, hence the fallback — husky v9's hooks are plain shell scripts, so pointing git
# straight at .husky runs exactly the same dispatcher.
set -e

repo_root=$(git rev-parse --show-toplevel)
cd "$repo_root"
chmod +x .husky/pre-commit scripts/pre-commit-server.sh

if [ -d client/node_modules/husky ]; then
	./client/node_modules/.bin/husky .husky
	echo "hooks installed via husky -> $(git config core.hooksPath)"
else
	git config core.hooksPath .husky
	echo "hooks installed -> .husky (husky not present; run 'bun install' in client/ to hand it over)"
fi
