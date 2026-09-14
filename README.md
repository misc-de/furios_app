# misc-de

Eine GTK4/libadwaita-App fuer das FuriPhone FLX1, die zeigt und umschaltet,
was an diesem Telefon von Hand repariert wurde: Audio, Modem, Standort und die
drei Hardware-Schalter am Gehaeuse.

Sie repariert nichts selbst. Sie bedient die Werkzeuge, die es tun, liest
deren Zustand und sagt, was eine Entscheidung kostet:

| Reiter | Werkzeug | Repo |
|---|---|---|
| Audio | `audioctl` | [furios_pipewire](https://github.com/misc-de/furios_pipewire) |
| Modem | `modemctl` | [furios_modem_fixes](https://github.com/misc-de/furios_modem_fixes) |
| GPS | `gpsctl` | [furios_gps](https://github.com/misc-de/furios_gps) |
| Switches | `killswitch-indicator` | [furios_killswitch](https://github.com/misc-de/furios_killswitch) |

Nur `audioctl` muss da sein. Fehlt eines der anderen, fehlt sein Reiter - und
weil die Reiterleiste sich erst ab der zweiten Seite zeigt, sieht ein Telefon
ohne diese Pakete aus wie eine App, die nur Audio kann. Ein Reiter, der
dauernd "nicht installiert" sagt, laesst ein gesundes Telefon kaputt aussehen.

## Installation

```bash
./install.sh        # braucht sudo fuer /usr/local, sonst nichts
```

Legt `misc-de` nach `/usr/local/bin`, dazu Symbol und Starter. Danach steht
die App im App-Raster; direkt starten geht mit `misc-de`.

Voraussetzungen: `python3-gi`, `gir1.2-adw-1` und `audioctl`.

## Components: was fehlt, woher es kommt, was es tut

Der Knopf oben links oeffnet eine Seite, die alle vier Werkzeuge auflistet -
auch die, die nicht installiert sind und deshalb keinen Reiter haben. Pro
Werkzeug drei Zeilen: was es tut, aus welchem Repo es kommt, und wie es auf
diesem Telefon steht.

Dazu ein Knopf, und der heisst je nach Lage anders:

| Lage | Knopf | was passiert |
|---|---|---|
| nicht installiert | **Install** | `git clone` nach `~/.local/share/misc-de/<repo>`, dann `./install.sh` daraus |
| unser Klon, Repo ist weiter | **Update (N new)** | `git pull --ff-only`, dann `./install.sh` |
| unser Klon, gleichstand | Up to date | nichts, der Knopf ist aus |
| installiert, kein Klon | **Fetch the source** | nur klonen, damit Updates ueberhaupt sichtbar werden |
| **eigener Klon** anderswo | Kept by you | **nichts** - siehe unten |

**Ein Klon, den du selbst haeltst, wird nie angefasst.** Gefunden wird er an
seiner origin-URL, nicht am Verzeichnisnamen (dasselbe Repo heisst hier
`furios_gps_fix` und oben `furios_gps`), und dann bleibt es beim Hinsehen:
`git ls-remote` fragt den Server nach seinem HEAD, `git rev-parse` liest den
des Klons, und die Zeile sagt "up to date" oder "there is something new
upstream". Kein `fetch`, kein `pull` - in einem fremden Arbeitsbaum kann
unfertige Arbeit liegen, und was damit geschieht, entscheidet ihr Besitzer im
Terminal.

**Vor jedem Holen wird gefragt**, und die Frage sagt die Befehle an, die
laufen werden. Drei der vier Installer schreiben nach `/usr/local` und
brauchen root - dieses Telefon hat keinen polkit-Agenten (`pkexec` antwortet
"No authentication agent found"), also wird es gemacht wie im Terminal: `sudo`
fragt einmal nach dem Passwort, das Installationsskript laeuft als du, und nur
seine eigenen sudo-Zeilen werden root. Danach wird das Ticket mit `sudo -k`
wieder weggeworfen.

Das Passwort geht durch die Pipe an `sudo` und nirgendwo sonst: nicht in
`argv` (wo jedes `ps` es mitlesen wuerde), nicht in eine Datei, nicht in die
Umgebung, nicht in eine Logzeile. Aus dem Eingabefeld wird es geloescht, sobald
die Frage beantwortet ist. Ein falsches Passwort meldet `sudo` mit seinen
eigenen Worten, und die Kette bricht dort ab, statt einen Installer zu
starten, der nicht fertig werden kann.

Ein frisch geholtes Werkzeug bekommt seinen Reiter erst beim naechsten Start -
die Reiter werden gebaut, wenn das Fenster aufgeht, und die Meldung sagt das.

## Was jede Seite tut

**Audio** - wem der Android-HAL gehoert (PipeWire direkt oder PulseAudio wie
ausgeliefert), ob das einen Neustart ueberlebt, und MediaTeks Doppelmikrofon-
Echounterdrueckung fuer Gespraeche. Darunter steht, was tatsaechlich laeuft.

**Modem** - die Reparaturen an ofono2mm/ModemManager an oder aus, gemerkt oder
nur bis zum naechsten Boot, was die Pruefungen sagen und wie gut das Signal
ist.

**GPS** - der Filter, der geoclue eine aus der IP-Adresse abgeleitete Position
verweigert. "Aus" heisst hier nicht "keine Position", sondern: die Position
des Netzanbieter-Ausgangs wird veroeffentlicht, als waere das Telefon dort
gesehen worden. Deshalb sagt jede Zeile dieser Seite, was "aus" bedeutet.

**Switches** - die drei Schieber am Gehaeuse. Kamera und Netz sind
Software-Abschaltungen (Android stoppt den Dienst), der Mikrofon-Schalter
trennt wirklich die Leitung - und ist genau deshalb softwareseitig unsichtbar.
Die Seite misst ihm nicht hinterher: das hiesse, das Mikrofon zu oeffnen, und
die Antwort gaelte nur fuer die Sekunden der Messung. Sie schreibt das an.

## Regeln, nach denen die Oberflaeche gebaut ist

- **Zeilen statt Absaetze.** Was gesagt werden muss, steht im Untertitel der
  Zeile, um die es geht. Auf einem Telefon liest niemand den Aufsatz ueber dem
  Schalter.
- **Ein Weg zurueck, ueberall gleich.** Jede Seite hat dieselbe Gruppe "Back
  to how it shipped" mit demselben schmucklosen Knopf. Keine Farben: blau
  hiesse "mach das", rot hiesse "Vorsicht", und was zutrifft, haengt von der
  Seite ab - das steht im Text daneben.
- **Vorher fragen.** Kein Weg zurueck handelt auf den blossen Tipper. Die
  Rueckfrage wiederholt genau den Text, der neben dem Knopf steht; Abbrechen
  ist die Vorgabe und auch die Bedeutung des Wegtippens.
- **Nie mehr behaupten als bekannt ist.** Ein Werkzeug, das nicht antwortet,
  macht seine Schalter grau und sagt es. Ein Funk, der `null` meldet, ist
  "nicht erreichbar" und nicht "aus".
- **Jeder Helferaufruf ist gedeckelt** (90 s). systemctl kann auf einen Job
  warten, der selbst wartet, und pkexec erbt das; ohne Deckel blieb das
  Fenster grau mit pulsendem Balken stehen.

## Tests

```bash
tests/run-tests.sh      # ohne Bildschirm, ohne root, ohne Telefon in der Hand
tests/coverage.sh       # Zeilenabdeckung, mit der Standardbibliothek gemessen
```

Stand: **182 Tests, 100 % der 1075 Zeilen** von `misc-de.py`.

`tests/gi_stub.py` tritt an die Stelle von PyGObject: das Fenster wird im
Testprozess gebaut, gefuellt und geklickt, ohne dass ein Wayland-Server
laeuft. Was so nicht geprueft werden kann, ist, was ein Mensch sieht - ob der
Text auf 360 logische Pixel passt, ob ein Tipper dort landet, wo er aussieht.
Das wird am Geraet abgelesen, nicht behauptet.

Die Naht zu den Werkzeugen wird gegen die **installierten** geprueft: die App
wartet auf Zeilen, die `audioctl` druckt, und sendet Worte, auf die
`furios-audio-dmnr` verzweigt. Wird drueben eine Bezeichnung umbenannt, faellt
das hier auf - und wo ein Werkzeug fehlt, wird der Test uebersprungen und sagt
warum, statt gegen eine leere Datei zu vergleichen.

## Herkunft

Die App lag bis zum 14.9.2026 in
[furios_pipewire](https://github.com/misc-de/furios_pipewire) unter `gui/`.
Sie ist mit ihrer Geschichte hierher umgezogen, weil sie inzwischen vier
Werkzeuge aus vier Repos bedient und keines davon ihr Zuhause ist.

## Lizenz

MIT, siehe [LICENSE](LICENSE).
