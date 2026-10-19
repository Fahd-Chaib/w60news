#!/usr/bin/env bash
# Keeps the bot's memory between GitHub Actions runs, on a separate `state` branch.
#   pull : restore data/newsbot.sqlite and data/secure/*.enc (encrypted tokens)
#   push : save them back as ONE fresh orphan commit (force-push → the history never grows)
set -euo pipefail

pull() {
  mkdir -p data/secure
  if git ls-remote --exit-code --heads origin state >/dev/null 2>&1; then
    local tmp; tmp="$(mktemp -d)"
    git fetch -q --depth=1 origin state
    git archive FETCH_HEAD | tar -x -C "$tmp"
    if [ -f "$tmp/newsbot.sqlite" ]; then cp "$tmp/newsbot.sqlite" data/; fi
    if [ -d "$tmp/secure" ]; then cp -r "$tmp/secure/." data/secure/; fi
    echo "State restored."
  else
    echo "No state branch yet (first run)."
  fi
}

push() {
  local tmp; tmp="$(mktemp -d)"
  mkdir -p "$tmp/work"
  if [ -f data/newsbot.sqlite ]; then cp data/newsbot.sqlite "$tmp/work/"; fi
  if ls data/secure/*.enc >/dev/null 2>&1; then
    mkdir -p "$tmp/work/secure" && cp data/secure/*.enc "$tmp/work/secure/"
  fi
  printf 'Bot memory for the news channel. Files in secure/ are encrypted with STATE_KEY.\n' \
    > "$tmp/work/README.md"
  export GIT_INDEX_FILE="$tmp/index"
  git --work-tree="$tmp/work" add -A
  local tree commit
  tree="$(git write-tree)"
  commit="$(git -c user.name=newsbot -c user.email=newsbot@users.noreply.github.com \
            commit-tree "$tree" -m "state $(date -u +%Y-%m-%dT%H:%M:%SZ)")"
  unset GIT_INDEX_FILE
  git push -qf origin "$commit:refs/heads/state"
  echo "State saved."
}

"$@"
