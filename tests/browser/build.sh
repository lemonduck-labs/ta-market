#!/bin/sh
# Build a local copy of the planner page (app/dist) with the mock capabilities (mock.js), for the
# browser flow in this folder. Run python3 scripts/build_app.py first so app/dist is current.
set -e
H=$(cd "$(dirname "$0")" && pwd)
DIST="$H/../../app/dist"
[ -f "$DIST/index.html" ] || { echo "app/dist is missing: run python3 scripts/build_app.py first" >&2; exit 1; }
rm -rf "$H/dev" && mkdir -p "$H/dev"
python3 "$H/wrap.py" "$DIST/index.html" "$H/dev"
cp "$H/mock.js" "$H/dev/mock.js"
cp -r "$DIST/data" "$H/dev/data"
cp -r "$DIST/spec" "$H/dev/spec"
