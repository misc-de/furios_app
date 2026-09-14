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
| App | `misc-de` | dieses Repo |

Keines davon muss da sein. Fehlt eines, ist sein Reiter trotzdem da und bietet
an, es zu holen - siehe unten. Der fuenfte Reiter ist die App selbst: sie war
das Letzte, was nur im Terminal zu aktualisieren war.

## Der Reiter "App"

Drei Zeilen - woher das Fenster laeuft, aus welchem Repo es kommt, aus welchem
Klon ein Update kaeme - und ein Knopf, wenn es etwas zu tun gibt. Gefragt wird
dabei etwas anderes als bei den vier Werkzeugen: nicht nur, ob auf dem Server
neue Commits liegen, sondern ob das **laufende Programm dasselbe ist wie die
`misc-de.py` im Klon**. Auf diesem Telefon wird die naechste Fassung in genau
diesem Klon geschrieben; er ist also nie hinter dem Server, wohl aber
regelmaessig vor dem, was installiert ist. Dann heisst das Angebot
"reinstall": es wird nichts geholt, nur `./install.sh` in diesem Klon
ausgefuehrt - ein `git pull` waere die falsche Frage, und seine Wache wuerde
bei uncommitteten Aenderungen die Installation gleich mit verweigern.

Danach laeuft in diesem Fenster noch die alte Fassung, also fragt es, ob es
sich neu starten soll. Neu starten heisst `execv`: derselbe Prozess wird durch
das neue Programm ersetzt. Eine zweite Instanz waere keine - die Application-ID
laesst sie ihre Aktivierung an die laufende abgeben, und die praesentiert dann
das ALTE Fenster.

## Installation

```bash
./install.sh        # braucht sudo fuer /usr/local, sonst nichts
```

Legt `misc-de` nach `/usr/local/bin`, dazu Symbol und Starter. Danach steht
die App im App-Raster; direkt starten geht mit `misc-de`.

Voraussetzungen: `python3-gi` und `gir1.2-adw-1`. Sonst nichts - die
Werkzeuge hinter den Reitern holt die App sich selbst.

## Wenn ein Werkzeug fehlt

Jeder Reiter ist da, auch wenn sein Werkzeug es nicht ist. Dann zeigt er genau
drei Dinge - was er tun wuerde, aus welchem Repo das kommt, und was beim
Installieren passieren wird - und einen **Install**-Knopf. Sonst nichts:
Schalter und Statuszeilen ohne etwas dahinter waeren Attrappen, und eine Seite
voller ausgegrauter Bedienelemente sieht aus wie ein kaputtes Telefon statt
nach einem fehlenden Paket.

Geholt wird nach `~/.local/share/misc-de/<repo>`, installiert wird daraus.
Drei der vier Installer schreiben nach `/usr/local` und brauchen root; dieses
Telefon hat keinen polkit-Agenten (`pkexec` antwortet "No authentication agent
found"), also wird es gemacht wie im Terminal: `sudo` fragt einmal nach dem
Passwort, das Skript laeuft als du, und nur seine eigenen sudo-Zeilen werden
root. Danach wirft `sudo -k` das Ticket weg.

Auf das Ticket allein ist kein Verlass, und das ist keine Theorie: am
14.9.2026 fiel auf diesem Telefon eine sudoers-Regel weg, und der
GPS-Install blieb bei seiner ersten sudo-Zeile stehen - geklont, nichts
installiert, `sudo: a terminal is required to read the password`. Ohne
Terminal haengt sudo den Zeitstempel naemlich nicht an ein TTY, sondern an
den Elternprozess, und die bash des Installers ist nicht der Elternprozess,
den `sudo -v` hatte. Also bekommt der Installer zusaetzlich `SUDO_ASKPASS`:
einen fuenfzeiligen Helfer ohne Geheimnis darin, der sich das Passwort ueber
einen Socket in `$XDG_RUNTIME_DIR` holt - Verzeichnis 0700, und die
Gegenstelle prueft die uid des Fragenden. So darf jede sudo-Zeile jedes
Installers fragen, so oft sie will. (Dazu `DISPLAY`, falls es fehlt: sudo
greift nur dann zu `SUDO_ASKPASS`, wenn es glaubt, dass jemand eine
grafische Frage sehen koennte - geoeffnet wird es nie.)

Das Passwort geht durch die Pipe an `sudo` und durch diesen Socket, sonst
nirgendwohin - nicht in `argv`, wo jedes `ps` es mitliest, nicht in eine
Datei, nicht in die Umgebung, nicht in eine Logzeile -, und aus dem
Eingabefeld ist es weg, sobald die Frage beantwortet ist. Ein falsches Passwort meldet `sudo` mit seinen eigenen
Worten; die Kette bricht dort ab, statt einen Installer zu starten, der nicht
fertig werden kann. Laeuft alles durch, wird aus dem Angebot sofort die
richtige Seite - an derselben Stelle in der Reiterleiste, und die App steht
danach darauf. Kein Neustart: das Werkzeug ist in dem Moment auf dem Telefon,
zu warten ist auf nichts mehr.

## Wenn es im Repo etwas Neues gibt

Beim Start sieht die App einmal nach, ob die installierten Werkzeuge noch dem
Stand ihres Repos entsprechen. Gibt es Neues, erscheint am **Fuss der
betreffenden Seite** eine Gruppe "Update available" mit dem, was dort wartet,
und einem **Update**-Knopf. Gibt es nichts - oder war die Frage nicht zu
beantworten, weil das Telefon gerade kein Netz hat -, erscheint gar nichts.
Ein Angebot, das immer da ist, sagt nichts.

Wie nachgesehen wird, haengt davon ab, wem der Klon gehoert:

- **Unser eigener** (in `~/.local/share/misc-de`): `git fetch`, dann zaehlen,
  wie viele Commits warten.
- **Deiner** (gefunden an der origin-URL, nicht am Verzeichnisnamen - dasselbe
  Repo heisst hier `furios_gps_fix` und oben `furios_gps`): `git ls-remote`
  fragt den Server nach seinem HEAD, `git rev-parse` liest den des Klons.
  **Kein fetch, kein pull** - das schriebe in ein fremdes `.git`.

Ein Update in einem Klon, der dir gehoert, sagt das in der Rueckfrage, und es
beginnt mit einer Wache: liegt dort irgendetwas Uncommittetes, wird **nichts**
angefasst und der Grund steht als Satz da. Gezogen wird `--ff-only` - ein
Merge ist keine Entscheidung, die eine App fuer einen fremden Arbeitsbaum
trifft.

Ist das Update durch, verschwindet das Angebot: es war die Antwort auf
Commits, die jetzt hier liegen.

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

Stand: **204 Tests.** Die Zeilenabdeckung haengt daran, welche Werkzeuge auf
dem Telefon liegen - gemessen wird nur, was gebaut wird: mit allen vier waren
es zuletzt 100 %, mit nur `modemctl` sind es 79 % von 1147 Zeilen.

`tests/askpass-live.py` laeuft in einem eigenen Prozess, weil es das echte
GLib braucht: es prueft den Socket, an dem `sudo` nach dem Passwort fragt -
dass ein fremder Prozess es wirklich bekommt, dass in der Helferdatei keines
steht und dass hinterher nichts uebrig bleibt. Mit `--with-sudo` wird
zusaetzlich das echte `sudo` gefragt (mit absichtlich falschem Passwort, also
mit Fehlversuchen im Journal - deshalb nicht im normalen Lauf).

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
