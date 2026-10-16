#!/bin/sh
# Apply a preset and wait until flagd serves it: `make flag` without make.
#
#   docker compose run --rm flag <preset>
#
# Runs in the `flag` compose service (busybox, profile `tools`), with this
# folder mounted at /flagd. The write goes through apply-preset.sh (temp file,
# rename, strictly newer mtime), like `make flag`. Then it polls flagd's OFREP
# endpoint until the answer's metadata carries `"preset":"<preset>"`: every
# preset names itself in its flag-set metadata, and flagd merges that into
# the metadata of each evaluated flag. Exits non-zero if that doesn't happen
# within FLAG_CONFIRM_TIMEOUT seconds (default 10).
set -eu

dir=/flagd
presets="$dir/presets"

list() {
  for f in "$presets"/*.json; do
    n=${f##*/}
    echo "  ${n%.json}"
  done
}

if [ $# -ne 1 ]; then
  echo "usage: docker compose run --rm flag <preset>, one of:"
  list
  exit 2
fi
preset=$1
if [ ! -f "$presets/$preset.json" ]; then
  echo "unknown preset '$preset', one of:"
  list
  exit 2
fi

sh "$dir/apply-preset.sh" "$presets/$preset.json" "$dir/flagd.json"
# The container runs as root; on a native Docker engine the file would stay
# root-owned in the checkout. Give it the folder's owner back.
chown "$(stat -c %u:%g "$dir")" "$dir/flagd.json" 2>/dev/null || true
echo "flagd.json is now $preset, waiting for flagd to serve it"

url="${FLAGD_OFREP_URL:-http://flagd:8016}/ofrep/v1/evaluate/flags"
timeout=${FLAG_CONFIRM_TIMEOUT:-10}
end=$(( $(date +%s) + timeout ))
while :; do
  # Whitespace dropped, so the match doesn't depend on flagd's JSON layout.
  body=$(wget -q -T 2 -O - --header 'Content-Type: application/json' \
    --post-data '{"context":{}}' "$url" 2>/dev/null | tr -d ' \t\r\n') || body=
  case $body in
    *"\"preset\":\"$preset\""*)
      echo "flagd serves $preset"
      exit 0
      ;;
  esac
  if [ "$(date +%s)" -ge "$end" ]; then
    if [ -z "$body" ]; then
      echo "flagd did not answer on $url within ${timeout}s. Is the stack up (docker compose up -d)?" >&2
    else
      echo "flagd does not serve $preset after ${timeout}s; see docker compose logs flagd" >&2
    fi
    exit 1
  fi
  sleep 0.2
done
