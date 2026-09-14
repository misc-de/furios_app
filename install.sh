#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# Installs the app (GTK4/libadwaita) with its icon and launcher entry.
# Changes nothing about the active audio profile, nothing about the modem,
# nothing about where the phone says it is and nothing about the kill
# switches - the pages for those only appear where their tool is installed.
set -e
cd "$(dirname "$0")"

# audioctl is what the first tab drives; without it the app would open and
# have nothing to say. It lives in its own repository:
# https://github.com/misc-de/furios_pipewire
command -v audioctl >/dev/null || {
    echo "audioctl missing - install furios_pipewire first"; exit 1; }
python3 -c "import gi; gi.require_version('Adw','1')" 2>/dev/null \
  || { echo "libadwaita bindings missing: apt install python3-gi gir1.2-adw-1"; exit 1; }

echo "1) program"
sudo install -m755 misc-de.py /usr/local/bin/misc-de

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
command -v modemctl >/dev/null || echo "(no modemctl here, so no modem page - that is not a fault)"
command -v gpsctl >/dev/null || echo "(no gpsctl here, so no GPS page - that is not a fault)"
