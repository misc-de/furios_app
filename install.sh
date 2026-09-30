#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# Installs the app (GTK4/libadwaita) with its icon and launcher entry.
# Changes nothing about the active audio profile, nothing about the modem,
# nothing about where the phone says it is and nothing about the kill
# switches - the pages for those only appear where their tool is installed.
set -e
cd "$(dirname "$0")"

# How a tool is looked for here. Not "command -v": this script runs under
# sudo, where $PATH and $HOME are root's, while two of the five tools need no
# root at all and are installed in the user's own ~/.local/bin - so the plain
# lookup reported them missing and offered to install what was already there.
# The app's own order (miscde/tools.py, _tool_maybe): the two system
# directories, then the bin of whoever called this script, $PATH last.
# --- tool lookup (the tests extract everything down to the end marker) ---
user_home=$(getent passwd "${SUDO_USER:-$(id -un)}" | cut -d: -f6) || true
have_tool() {
    local dir
    for dir in /usr/local/bin /usr/bin "${user_home:-$HOME}/.local/bin"; do
        [ -x "$dir/$1" ] && return 0
    done
    command -v "$1" >/dev/null
}
# --- end tool lookup ---

# audioctl used to be a hard requirement here. It is not one any more: a tab
# whose tool is missing now says so and offers to fetch it, so the app has
# something to say on a phone where nothing else is installed yet - and
# refusing to install would leave somebody with no way to get there at all.
have_tool audioctl || cat <<'HINT'
Note: audioctl is not installed yet. The Audio tab will offer to fetch it
      (github.com/misc-de/furios_audio), like the other three tabs do.
HINT
python3 -c "import gi; gi.require_version('Adw','1')" 2>/dev/null \
  || { echo "libadwaita bindings missing: apt install python3-gi gir1.2-adw-1"; exit 1; }

# DESTDIR, as in make: a staged root instead of /, for the tests.
PREFIX="${DESTDIR:-}/usr/local"

# What was there before the first install, written down before anything is
# changed (the owner's rule, 30.9.2026): the directories and caches under
# /usr/local that this installer shares with others, each present or absent.
# uninstall.sh reads it and takes away exactly what was not there, instead
# of assuming that FuriOS ships none of it. Written once: a reinstall or an
# update finds the file and leaves it, because the first original is the one
# that counts. Where the app is already installed without one, an older
# version put it there and what was before is not known - then nothing is
# written rather than today's state as a guess, and uninstall.sh says it
# falls back. Kept in lib/misc-de beside the package, which is replaced on
# every install while this file is not.
STATE="$PREFIX/lib/misc-de/original-state"
if [ ! -e "$STATE" ]; then
    if [ -e "$PREFIX/bin/misc-de" ] || [ -e "$PREFIX/lib/misc-de/miscde" ]; then
        echo "(misc-de was installed by an older version that wrote down nothing" \
            "about /usr/local before it - uninstall.sh will say it falls back)"
    else
        record=""
        for p in lib/misc-de share/icons share/icons/hicolor \
                share/icons/hicolor/scalable share/icons/hicolor/scalable/apps \
                share/icons/hicolor/icon-theme.cache share/applications \
                share/applications/mimeinfo.cache; do
            if [ -e "$PREFIX/$p" ]; then
                record+="present $p"$'\n'
            else
                record+="absent $p"$'\n'
            fi
        done
        sudo install -d -m755 "$PREFIX/lib/misc-de"
        printf '%s' "$record" | sudo tee "$STATE" >/dev/null
        sudo chmod 644 "$STATE"
    fi
fi

echo "1) program"
# Two parts since 15.9.2026, where there used to be one file: the launcher in
# bin, and the package it starts beside it. rsync --delete rather than a plain
# copy, because a page that was deleted upstream has to disappear here too -
# left behind it would still be imported, and the fingerprint the app compares
# itself against would never match the clone again.
sudo install -m755 misc-de.py "$PREFIX/bin/misc-de"
sudo rm -rf "$PREFIX/lib/misc-de/miscde"
sudo install -d -m755 "$PREFIX/lib/misc-de"
sudo cp -r miscde "$PREFIX/lib/misc-de/miscde"
sudo find "$PREFIX/lib/misc-de/miscde" -name __pycache__ -prune -exec rm -rf {} +
sudo chmod -R a+rX "$PREFIX/lib/misc-de"

echo "2) icon"
sudo install -Dm644 de.misc-de.tools.svg \
    "$PREFIX/share/icons/hicolor/scalable/apps/de.misc-de.tools.svg"

echo "3) launcher entry"
sudo install -Dm644 de.misc-de.tools.desktop \
    "$PREFIX/share/applications/de.misc-de.tools.desktop"

# So Phosh picks up icon and entry right away.
sudo gtk-update-icon-cache -qtf "$PREFIX/share/icons/hicolor" 2>/dev/null || true
sudo update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true

echo
echo "Done. It appears in the app grid as \"misc-de\"."
echo "Start it directly: misc-de"
# Every tab exists whether its tool does or not, and the ones without offer to
# fetch it - so a missing tool is a line about where to get it, not a warning.
for tool in audioctl modemctl furios-gps-contribute killswitch-indicator battctl; do
    have_tool "$tool" \
        || echo "(no $tool yet - its tab offers to install it)"
done
