#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# Installs the app (GTK4/libadwaita) with its icon and launcher entry.
# Changes nothing about the active audio profile, nothing about the modem,
# nothing about where the phone says it is and nothing about the kill
# switches - the pages for those only appear where their tool is installed.
set -e
cd "$(dirname "$0")"

# audioctl used to be a hard requirement here. It is not one any more: a tab
# whose tool is missing now says so and offers to fetch it, so the app has
# something to say on a phone where nothing else is installed yet - and
# refusing to install would leave somebody with no way to get there at all.
command -v audioctl >/dev/null || cat <<'HINT'
Note: audioctl is not installed yet. The Audio tab will offer to fetch it
      (github.com/misc-de/furios_pipewire), like the other three tabs do.
HINT
python3 -c "import gi; gi.require_version('Adw','1')" 2>/dev/null \
  || { echo "libadwaita bindings missing: apt install python3-gi gir1.2-adw-1"; exit 1; }

echo "1) program"
# Two parts since 15.9.2026, where there used to be one file: the launcher in
# bin, and the package it starts beside it. rsync --delete rather than a plain
# copy, because a page that was deleted upstream has to disappear here too -
# left behind it would still be imported, and the fingerprint the app compares
# itself against would never match the clone again.
sudo install -m755 misc-de.py /usr/local/bin/misc-de
sudo rm -rf /usr/local/lib/misc-de/miscde
sudo install -d -m755 /usr/local/lib/misc-de
sudo cp -r miscde /usr/local/lib/misc-de/miscde
sudo find /usr/local/lib/misc-de/miscde -name __pycache__ -prune -exec rm -rf {} +
sudo chmod -R a+rX /usr/local/lib/misc-de

echo "2) icon"
sudo install -Dm644 de.misc-de.tools.svg \
    /usr/local/share/icons/hicolor/scalable/apps/de.misc-de.tools.svg

echo "3) launcher entry"
sudo install -Dm644 de.misc-de.tools.desktop \
    /usr/local/share/applications/de.misc-de.tools.desktop

# So Phosh picks up icon and entry right away.
sudo gtk-update-icon-cache -qtf /usr/local/share/icons/hicolor 2>/dev/null || true
sudo update-desktop-database -q /usr/local/share/applications 2>/dev/null || true

echo
echo "Done. It appears in the app grid as \"misc-de\"."
echo "Start it directly: misc-de"
# Every tab exists whether its tool does or not, and the ones without offer to
# fetch it - so a missing tool is a line about where to get it, not a warning.
for tool in audioctl modemctl gpsctl killswitch-indicator battctl; do
    command -v "$tool" >/dev/null \
        || echo "(no $tool yet - its tab offers to install it)"
done
