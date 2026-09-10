#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
# Installs the audio switcher (GTK4/libadwaita) with its icon and launcher
# entry. Changes nothing about the active audio profile.
set -e
cd "$(dirname "$0")"

command -v audioctl >/dev/null || { echo "audioctl missing - run ../install.sh first"; exit 1; }
python3 -c "import gi; gi.require_version('Adw','1')" 2>/dev/null \
  || { echo "libadwaita bindings missing: apt install python3-gi gir1.2-adw-1"; exit 1; }

echo "1) program"
sudo install -m755 furios-audio-switch.py /usr/local/bin/furios-audio-switch

echo "2) icon"
sudo install -Dm644 de.furios.audioswitch.svg \
    /usr/local/share/icons/hicolor/scalable/apps/de.furios.audioswitch.svg

echo "3) launcher entry"
sudo install -Dm644 de.furios.audioswitch.desktop \
    /usr/local/share/applications/de.furios.audioswitch.desktop

# So Phosh picks up icon and entry right away.
sudo gtk-update-icon-cache -qtf /usr/local/share/icons/hicolor 2>/dev/null || true
sudo update-desktop-database -q /usr/local/share/applications 2>/dev/null || true

echo
echo "Done. The switcher appears in the app grid as \"Audio Switcher\"."
echo "Start it directly: furios-audio-switch"
