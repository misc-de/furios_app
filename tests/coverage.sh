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
# Every file of the app, each on its own line. When this was one file the
# list was that file; a package measured as one number would hide a page
# nobody exercises behind four that are covered well.
wanted = ["misc-de.py"]
for sub, _dirs, files in os.walk(os.path.join(root, "miscde")):
    if "__pycache__" in sub:
        continue
    for name in sorted(files):
        if name.endswith(".py"):
            wanted.append(os.path.relpath(os.path.join(sub, name), root))

covers = {}
for name in os.listdir(out):
    if name.endswith(".cover"):
        covers[name] = os.path.join(out, name)

for want in wanted:
    # trace names its output after the MODULE, not the file: miscde/window.py
    # is written as miscde.window.cover. Matching on the file name worked as
    # long as the app was one file at the top; with a package it matched
    # nothing and reported every file as never imported - which looks like a
    # test suite that stopped running, and is not.
    stem = want[:-3].replace("-", "_").replace(os.sep, ".")
    match = covers.get(stem + ".cover")
    if match is None:
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
