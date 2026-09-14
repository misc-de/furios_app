#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# Line coverage for the app, using the standard library's own tracer.
#
# No third-party coverage package: this has to run on the phone, and trace is
# already there.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
OUT=$(mktemp -d)
trap 'rm -rf "$OUT"' EXIT

( cd "$ROOT" && python3 -m trace --count --coverdir="$OUT" --missing \
    "$HERE/test-app.py" >/dev/null 2>&1 )

python3 - "$ROOT" "$OUT" <<'PY'
import os, re, sys

root, out = sys.argv[1], sys.argv[2]
wanted = ["misc-de.py"]

covers = {}
for name in os.listdir(out):
    if name.endswith(".cover"):
        covers[name] = os.path.join(out, name)

for want in wanted:
    stem = want[:-3].replace("-", "_")
    match = None
    for name, path in covers.items():
        if stem in name.replace("-", "_"):
            match = path
            break
    if match is None:
        print("  %-40s not measured - never imported" % want)
        continue
    # The "if __name__" block at the bottom is the entry point, and a module
    # that is imported never runs it. Counting it would leave every file short
    # by the same two lines, for a reason that has nothing to do with testing.
    path = None
    for where in ("",):
        candidate = os.path.join(root, where, want)
        if os.path.exists(candidate):
            path = candidate
            break
    source = open(path, errors="replace").read() if path else ""
    entry_line = None
    for n, line in enumerate(source.splitlines(), 1):
        if line.startswith("if __name__"):
            entry_line = n
            break

    total = hit = 0
    missing = []
    for n, line in enumerate(open(match, errors="replace"), 1):
        if entry_line is not None and n >= entry_line:
            continue
        if line.startswith(">>>>>>"):
            total += 1
            missing.append(n)
        elif re.match(r"\s*\d+:", line):
            total += 1
            hit += 1
    print("  %-40s %6.2f%% of %d" % (want, hit / total * 100 if total else 100, total))
    if os.environ.get("SHOW_MISSING") and missing:
        print("      not reached:", " ".join(str(n) for n in missing[:40]))
PY
