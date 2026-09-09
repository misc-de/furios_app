#!/bin/bash
# Installiert den Audio-Umschalter (GTK4/libadwaita) samt Symbol und
# Startereintrag. Aendert nichts am aktiven Audioprofil.
set -e
cd "$(dirname "$0")"

command -v audioctl >/dev/null || { echo "audioctl fehlt - erst ../install.sh ausfuehren"; exit 1; }
python3 -c "import gi; gi.require_version('Adw','1')" 2>/dev/null \
  || { echo "libadwaita-Bindings fehlen: apt install python3-gi gir1.2-adw-1"; exit 1; }

echo "1) Programm"
sudo install -m755 furios-audio-switch.py /usr/local/bin/furios-audio-switch

echo "2) Symbol"
sudo install -Dm644 de.furios.audioswitch.svg \
    /usr/local/share/icons/hicolor/scalable/apps/de.furios.audioswitch.svg

echo "3) Startereintrag"
sudo install -Dm644 de.furios.audioswitch.desktop \
    /usr/local/share/applications/de.furios.audioswitch.desktop

# Damit Phosh Symbol und Eintrag sofort findet.
sudo gtk-update-icon-cache -qtf /usr/local/share/icons/hicolor 2>/dev/null || true
sudo update-desktop-database -q /usr/local/share/applications 2>/dev/null || true

echo
echo "Fertig. Der Umschalter steht im Anwendungsraster als \"Audio-Umschalter\"."
echo "Direkt starten: furios-audio-switch"
