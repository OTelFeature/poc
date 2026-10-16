#!/bin/sh
# Replace a flag file so flagd is guaranteed to reload it.
#
#   apply-preset.sh <preset.json> <flagd.json>
#
# Two traps this avoids:
# - flagd's polling watcher (and the Python provider's file watcher) reload
#   only when the mtime *increases*. Two rewrites within one timestamp tick
#   keep the same mtime and the second is silently ignored. So the new file
#   gets an mtime strictly greater than the old one.
# - A plain `cp` truncates and then writes, so a watcher can read an empty
#   or half-written file. Writing a temp file next to the target and renaming
#   it over the target is atomic; flagd's fsnotify watcher handles the
#   rename (it re-adds the watch and reloads).
set -eu

src=$1
dst=$2
tmp="$(dirname "$dst")/.$(basename "$dst").tmp.$$"

mtime() {
  stat -c %Y "$1" 2>/dev/null || stat -f %m "$1" 2>/dev/null || echo 0
}

before=$(mtime "$dst")
now=$(date +%s)
next=$(( (before >= now ? before : now) + 1 ))

cp "$src" "$tmp"
# GNU touch, then BSD/macOS touch.
touch -d "@$next" "$tmp" 2>/dev/null || touch -t "$(date -r "$next" +%Y%m%d%H%M.%S)" "$tmp"
mv -f "$tmp" "$dst"
