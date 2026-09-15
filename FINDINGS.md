# Was dabei herauskam

Das README sagt, was die App ist und wie man sie benutzt. Diese Datei sagt
*warum* sie so gebaut ist: die Entscheidungen hinter der Oberflaeche, die
Mechanik des Installierens und die Stellen, die Zeit gekostet haben.

Geraet: FuriPhone FLX1 (radon), FuriOS mit phosh.

Die App lag bis zum 14.9.2026 in
[furios_pipewire](https://github.com/misc-de/furios_pipewire) unter `gui/`.
Sie ist mit ihrer Geschichte hierher umgezogen, weil sie inzwischen vier
Werkzeuge aus vier Repos bedient und keines davon ihr Zuhause ist.


## Aus dem README

Das README wurde auf das gekuerzt, was man zum Benutzen braucht. Was hier folgt, stand bis dahin dort: die Begruendungen, die Messwerte und die Abwaegungen hinter den Entscheidungen.

## Die App aktualisiert sich selbst - ohne Reiter

Die App ist eine Komponente wie die vier Werkzeuge (`misc-de`, dieses Repo):
derselbe Klon, derselbe Installer. Was sie nicht ist, ist etwas, das man auf
einer Seite *bedient* - sie IST die Seite. Ein fuenfter Reiter dafuer kostete
auf jeder anderen Seite ein Fuenftel der Reiterleiste, um zu sagen, aus welcher
Datei das Fenster laeuft; und das Einzige, wofuer er da war - die naechste
Fassung nehmen - muss nicht hinter einem Reiter warten, den niemand oeffnet.

Deshalb sitzt es in der Kopfleiste: **links oben ein Icon, das nur erscheint,
wenn es eine neuere Fassung gibt.** Was gefunden wurde und woher es kaeme,
steht in seinem Tooltip. Ein Druck darauf startet noch nichts, sondern fragt
zurueck - dieselbe Rueckfrage, die jede andere Komponente bekommt, mit den
Schritten, die laufen wuerden, und dem Passwortfeld fuer `sudo`. Danach ist das
Icon wieder weg; es war die Antwort auf eine Frage, die beantwortet ist.

(Rechts oben sass frueher ein "Aktualisieren"-Knopf. Der stellte genau den
Zustand her, der ohnehin schon auf dem Schirm stand - das Fenster fragt beim
Oeffnen, nach jedem Umschalten und nach jeder Installation von selbst nach.)

Gefragt wird dabei etwas anderes als bei den vier Werkzeugen: nicht nur, ob auf dem Server
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
und einem **Update**-Knopf - fuer die App selbst das Icon links oben in der
Kopfleiste. Gibt es nichts - oder war die Frage nicht zu
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

## Herkunft

Die App lag bis zum 14.9.2026 in
[furios_pipewire](https://github.com/misc-de/furios_pipewire) unter `gui/`.
Sie ist mit ihrer Geschichte hierher umgezogen, weil sie inzwischen vier
Werkzeuge aus vier Repos bedient und keines davon ihr Zuhause ist.
