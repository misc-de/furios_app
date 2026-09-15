#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# Everything that can be checked without a phone in your hand.
#
# The window is built, filled and clicked in this process against a stand-in
# for PyGObject (tests/gi_stub.py), so this runs over ssh and in a terminal
# with no display. What it cannot check is what a person sees - that the text
# fits on 360 logical pixels, that a tap lands where it looks. Those are read
# off the phone, not asserted here.
set -u
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(dirname "$HERE")
FAILED=0

run() {
    printf '\n\033[1m== %s\033[0m\n' "$1"
    shift
    if "$@"; then :; else FAILED=$((FAILED + 1)); fi
}

run "the app, and its seams towards the tools" python3 "$HERE/test-app.py"

# Separate process on purpose: this one needs the REAL GLib, and test-app.py
# has replaced PyGObject in its own. Add --with-sudo to also ask the real
# sudo; that writes failed authentication attempts to the journal, so it is
# not part of the ordinary run.
run "the askpass socket, against the real GLib" python3 "$HERE/askpass-live.py"

printf '\n\033[1m== shell\033[0m\n'
if command -v shellcheck >/dev/null; then
    for f in "$ROOT"/*.sh "$HERE"/*.sh; do
        if shellcheck -x "$f"; then
            printf '  \033[32mok\033[0m   %s\n' "${f#"$ROOT"/}"
        else
            FAILED=$((FAILED + 1))
        fi
    done
else
    printf '  \033[33mskipped\033[0m - no shellcheck (apt install shellcheck)\n'
fi

printf '\n\033[1m== python syntax\033[0m\n'
# The package too, and not just the launcher and the tests - since the
# window was split up, almost every line of this app lives under miscde/.
for f in "$ROOT"/*.py "$HERE"/*.py "$ROOT"/miscde/*.py "$ROOT"/miscde/pages/*.py; do
    if python3 -m py_compile "$f"; then
        printf '  \033[32mok\033[0m   %s\n' "${f#"$ROOT"/}"
    else
        FAILED=$((FAILED + 1))
    fi
done

printf '\n\033[1m== launcher entry\033[0m\n'
if command -v desktop-file-validate >/dev/null; then
    if desktop-file-validate "$ROOT"/de.misc-de.tools.desktop; then
        printf '  \033[32mok\033[0m   de.misc-de.tools.desktop\n'
    else
        FAILED=$((FAILED + 1))
    fi
else
    printf '  \033[33mskipped\033[0m - no desktop-file-validate\n'
fi

echo
if [ "$FAILED" -eq 0 ]; then
    printf '\033[32mall suites passed\033[0m\n'
else
    printf '\033[31m%d suite(s) failed\033[0m\n' "$FAILED"
fi
exit $((FAILED > 0))
