#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Removes the app - the program, its icon and its launcher entry.
#
# What it deliberately does NOT remove: the five tools behind the tabs. Each
# has its own uninstaller, each was a separate decision to install, and audio
# and modem hold the phone's sound and its data connection - taking those out
# because somebody removed a front end would be the app deciding something it
# was never asked about. The clones stay too, for the same reason: they are
# where the next version comes from, and they may be somebody's own.
set -uo pipefail

if [ "$(id -u)" = 0 ]; then
    echo "Please run WITHOUT sudo - it asks where it needs to." >&2
    exit 1
fi

PREFIX=/usr/local
CLONES="$HOME/.local/share/misc-de"

echo "1) program"
sudo rm -f "$PREFIX/bin/misc-de"

echo "2) icon"
sudo rm -f "$PREFIX/share/icons/hicolor/scalable/apps/de.misc-de.tools.svg"

echo "3) launcher entry"
sudo rm -f "$PREFIX/share/applications/de.misc-de.tools.desktop"

# So the app grid drops the entry right away instead of at the next login.
sudo gtk-update-icon-cache -qtf "$PREFIX/share/icons/hicolor" 2>/dev/null || true
sudo update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true

echo
echo "Removed."
# Said rather than done: somebody who wants these gone should see where they
# are, and each tool's own uninstaller knows what it changed.
for tool in audioctl modemctl gpsctl killswitch-indicator battctl; do
    command -v "$tool" >/dev/null \
        && echo "(still installed: $tool - its own repository has uninstall.sh)"
done
[ -d "$CLONES" ] && echo "(clones kept in $CLONES - delete them yourself if you want them gone)"
exit 0
