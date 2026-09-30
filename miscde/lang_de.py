# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""German for every text the window shows, keyed by its English original.

tests/test-app.py checks that every _() in the code has an entry here, and
that the placeholders ({name}, %s, %d) match - a German text that drops one
would fail when it is filled in."""

TRANSLATIONS = {
    # --- the window --------------------------------------------------------
    "Language": "Sprache",
    "Could not save the language": "Die Sprache konnte nicht gespeichert werden",
    "Saved - takes effect when the window is opened again":
        "Gespeichert - gilt, sobald das Fenster neu geöffnet wird",
    "Back to how it shipped": "Zurück zum Auslieferungszustand",
    "Restore shipped state": "Auslieferungszustand herstellen",
    "Got it": "Verstanden",
    "Something went wrong": "Etwas ist schiefgegangen",
    "{program} did not answer within {seconds} seconds":
        "{program} hat nicht innerhalb von {seconds} Sekunden geantwortet",
    "reading …": "wird gelesen …",
    "No output.": "Keine Ausgabe.",
    "Done": "Erledigt",
    "none": "keine",
    "on": "an",
    "off": "aus",
    "pkexec is missing - cannot ask for the rights to switch":
        "pkexec fehlt - die Rechte zum Umschalten können nicht angefragt werden",

    # --- tabs and what they are for ----------------------------------------
    "Audio": "Audio",
    "Modem": "Modem",
    "GPS": "GPS",
    "Switches": "Schalter",
    "Not installed": "Nicht installiert",
    "Security": "Sicherheit",
    "Battery": "Akku",
    "PipeWire talks to the Android HAL directly instead of PulseAudio: "
    "playback, recording, calls and Bluetooth audio":
        "PipeWire spricht direkt mit der Android-HAL statt PulseAudio: "
        "Wiedergabe, Aufnahme, Anrufe und Bluetooth-Audio",
    "the modem repairs: mobile data without Wi-Fi, signal bars that move, "
    "26 cell broadcast channels instead of 8":
        "die Modem-Reparaturen: mobile Daten ohne WLAN, Signalbalken, die sich "
        "bewegen, 26 Warnkanäle statt 8",
    "sends the Wi-Fi networks around you with a satellite position to "
    "beaconDB, so Wi-Fi location works where it does not yet - off until you "
    "switch it on":
        "schickt die WLANs in deiner Umgebung mit einer Satellitenposition an "
        "beaconDB, damit Ortung per WLAN auch dort klappt, wo sie es noch nicht "
        "tut - aus, bis du es einschaltest",
    "an icon in the top bar while the camera or the network switch is "
    "engaged - nothing else on the phone says so":
        "ein Symbol in der Leiste oben, solange der Kamera- oder Netzschalter "
        "umgelegt ist - sonst zeigt das nichts auf dem Telefon",
    "fewer routes into the kernel: unprivileged BPF, modules that load "
    "themselves - and a lock screen that locks after wrong PINs":
        "weniger Wege in den Kernel: unprivilegiertes BPF, Module, die sich "
        "selbst laden - und eine Sperre nach falschen PINs",
    "the battery icon goes green, amber or red with the charging power - a "
    "tired cable and a good one look the same otherwise":
        "das Akkusymbol wird je nach Ladeleistung grün, gelb oder rot - sonst "
        "sehen ein müdes und ein gutes Kabel gleich aus",
    "this window - the tabs and the switches on them":
        "dieses Fenster - die Reiter und die Schalter darauf",

    # --- Audio -------------------------------------------------------------
    "Audio stack": "Audio-Stack",
    "Sound server": "Soundserver",
    "Choose the main service for your audio input and output":
        "Wähle den primären Dienst für deine Audio-Ein- und -Ausgabe aus",
    "Switching, this takes a moment …": "Wird umgeschaltet, das dauert einen Moment …",
    "audioctl did not answer": "audioctl hat nicht geantwortet",
    "Bluetooth helpers": "Bluetooth-Helfer",
    "Enables the helper that makes sure audio and microphone are set correctly":
        "Aktiviert den Helfer, der dafür sorgt, dass Audio und Mikrofon richtig "
        "gesetzt werden",
    "Could not change the Bluetooth helpers":
        "Die Bluetooth-Helfer konnten nicht geändert werden",
    "Handsfree echo suppression (DMNR)": "Echounterdrückung beim Freisprechen (DMNR)",
    "Suppresses the echo in speakerphone calls":
        "Unterdrückt das Echo bei Lautsprechertelefonie",
    " · until the next reboot": " · bis zum nächsten Neustart",
    " · on again after the next reboot": " · nach dem nächsten Neustart wieder an",
    "not available on this device": "auf diesem Gerät nicht verfügbar",
    "Remember these choices": "Diese Auswahl merken",
    "Saves the options above": "Die obigen Optionen werden gespeichert",
    " · a reboot returns to {profile}": " · ein Neustart kehrt zurück zu {profile}",
    "Status": "Status",
    "Owns the Android HAL": "Hält die Android-HAL",
    "Outputs": "Ausgänge",
    " - permanent": " - dauerhaft",
    " - until the next reboot, then {profile}":
        " - bis zum nächsten Neustart, dann {profile}",
    " | fell back by itself on {when}: {profile} gave no sound at boot":
        " | am {when} von selbst zurückgefallen: {profile} gab beim Start keinen Ton",
    "PipeWire owns the HAL": "PipeWire hält die HAL",
    "PulseAudio owns the HAL (as shipped)": "PulseAudio hält die HAL (wie ausgeliefert)",
    "PulseAudio owns the HAL, PipeWire gets a sink":
        "PulseAudio hält die HAL, PipeWire bekommt eine Senke",
    "PulseAudio - the shipped setup": "PulseAudio - wie ausgeliefert",
    "PipeWire{0} - also speaks PulseAudio for older apps":
        "PipeWire{0} - spricht für ältere Apps auch PulseAudio",
    "not reachable": "nicht erreichbar",
    "Switching …": "Wird umgeschaltet …",
    "Switching failed": "Umschalten fehlgeschlagen",
    "Switching echo suppression …": "Echounterdrückung wird umgeschaltet …",
    "Could not switch echo suppression":
        "Die Echounterdrückung konnte nicht umgeschaltet werden",
    "Echo suppression changed - try a call":
        "Echounterdrückung geändert - probier es mit einem Anruf",
    "Your password (for sudo)": "Dein Passwort (für sudo)",
    "Echo suppression": "Echounterdrückung",
    "This lays tuning files over the vendor's and opens the modem's tuning "
    "memory to the audio group, so sudo asks for a password. It goes to sudo "
    "and nowhere else.":
        "Das legt Abstimmungsdateien über die des Herstellers und öffnet der "
        "Gruppe audio den Abstimmungsspeicher des Modems, deshalb fragt sudo "
        "nach einem Passwort. Es geht an sudo und nirgendwo sonst hin.",
    "Switch": "Umschalten",
    "Cancel": "Abbrechen",
    "Restoring …": "Wird wiederhergestellt …",
    "Shipped state, speaker, 65 %": "Auslieferungszustand, Lautsprecher, 65 %",
    "Restore failed": "Wiederherstellen fehlgeschlagen",
    "Returns to the shipped state and sends sound to the speaker - audible "
    "volume, unmuted. This is also the one to press when you hear nothing at "
    "all.":
        "Kehrt zum Auslieferungszustand zurück und schickt den Ton an den "
        "Lautsprecher - hörbare Lautstärke, nicht stumm. Das ist auch der "
        "Knopf, wenn du gar nichts hörst.",
    "Bluetooth": "Bluetooth",
    "Bluetooth powersave": "Bluetooth-Energiesparen",
    "Bluetooth powersave on": "Bluetooth-Energiesparen an",
    "Bluetooth powersave off": "Bluetooth-Energiesparen aus",
    "Turns Bluetooth off when possible to save energy":
        "Deaktiviert Bluetooth, wenn möglich, um Energie zu sparen",
    " · a headset reconnects only once the phone is woken":
        " · ein Headset verbindet sich erst wieder, wenn das Telefon aufgeweckt wird",
    " · batman is not installed, so nothing does":
        " · batman ist nicht installiert, also tut das nichts",
    "Changing Bluetooth powersave …": "Bluetooth-Energiesparen wird geändert …",
    "Change it": "Ändern",
    "This changes one line in batman's config and restarts it, so sudo asks "
    "for a password. It goes to sudo through a pipe and nowhere else.":
        "Das ändert eine Zeile in batmans Konfiguration und startet es neu, "
        "deshalb fragt sudo nach einem Passwort. Es geht über eine Pipe an sudo "
        "und nirgendwo sonst hin.",
    "Could not change Bluetooth powersave":
        "Bluetooth-Energiesparen konnte nicht geändert werden",
    "no password helper: {error}": "kein Passwort-Helfer: {error}",
    "Applies to": "Gilt für",
    "All": "Alle",
    "{name} · connected": "{name} · verbunden",
    "Music codec": "Musik-Codec",
    "Automatic": "Automatisch",
    "the best one both ends know": "der beste, den beide Seiten kennen",
    "Same as for all": "Wie für alle",
    "Playing %s": "Spielt %s",
    "Playing %s · %s": "Spielt %s · %s",
    "%s - no device connected": "%s - kein Gerät verbunden",
    "no device connected": "kein Gerät verbunden",
    "This device does not offer %s - it plays %s":
        "Dieses Gerät bietet %s nicht an - es spielt %s",
    "The device is on hands-free right now":
        "Das Gerät ist gerade im Freisprechmodus",
    "Not connected - applies when it connects":
        "Nicht verbunden - gilt, sobald es sich verbindet",
    " · all: %s": " · alle: %s",
    "Could not change the Bluetooth codec":
        "Der Bluetooth-Codec konnte nicht geändert werden",

    # --- Modem -------------------------------------------------------------
    "Modem": "Modem",
    "Repairs active": "Reparaturen aktiv",
    "On: patched, with a route and a resolver that work without Wi-Fi":
        "An: gepatcht, mit Route und Namensauflösung, die ohne WLAN funktionieren",
    "Off: as it shipped - no route and no resolver without Wi-Fi":
        "Aus: wie ausgeliefert - ohne WLAN keine Route und keine Namensauflösung",
    "Profile": "Profil",
    "Checks": "Prüfungen",
    "Signal": "Signal",
    "modemctl did not answer": "modemctl hat nicht geantwortet",
    "the repairs are in place": "die Reparaturen sind eingespielt",
    "FuriOS as it came": "FuriOS wie ausgeliefert",
    "half repaired - use \"Repairs active\" to settle it":
        "halb repariert - mit „Reparaturen aktiv“ bereinigen",
    " · not remembered, the next boot returns to \"{recorded}\"":
        " · nicht gemerkt, der nächste Start kehrt zu „{recorded}“ zurück",
    "{0} in place": "{0} eingespielt",
    "{0} in place, {1} not": "{0} eingespielt, {1} nicht",
    "not readable": "nicht lesbar",
    "Switching the modem …": "Modem wird umgeschaltet …",
    "Switching the modem failed": "Umschalten des Modems fehlgeschlagen",
    "Back to the shipped state …": "Zurück zum Auslieferungszustand …",
    "Shipped state - no network without Wi-Fi":
        "Auslieferungszustand - ohne WLAN kein Netz",
    "Takes every repair out, restarts the modem stack and remembers it. With "
    "Wi-Fi off there is then no route out and no name resolution.":
        "Nimmt jede Reparatur heraus, startet den Modem-Stack neu und merkt sich "
        "das. Ohne WLAN gibt es danach keine Route nach draußen und keine "
        "Namensauflösung.",
    "SIM": "SIM",
    "Active SIM": "Aktive SIM",
    "SIM {n} · no card": "SIM {n} · keine Karte",
    "One at a time - both slots share one radio":
        "Immer nur eine - beide Steckplätze teilen sich ein Funkteil",
    "No card detected - is the tray pushed all the way in?":
        "Keine Karte erkannt - ist der Schlitten ganz eingeschoben?",
    "No card in slot {n} - pick the other one to get the network back":
        "Keine Karte in Steckplatz {n} - wähle den anderen, um wieder Netz zu haben",
    "Insert a second card to choose between them":
        "Lege eine zweite Karte ein, um zwischen ihnen zu wählen",
    "No card in slot {0}": "Keine Karte in Steckplatz {0}",
    "Switching SIM …": "SIM wird umgeschaltet …",
    "Switching to SIM {0} - mobile network away for about 30 s …":
        "Wechsel auf SIM {0} - Mobilfunk etwa 30 s weg …",
    "Switching the SIM failed": "Umschalten der SIM fehlgeschlagen",
    "SIM switched": "SIM umgeschaltet",
    "Allow 5G": "5G erlauben",
    "Switched on, but the modem does not allow it right now": "Eingeschaltet, aber das Modem erlaubt es gerade nicht",
    "On - used where the network offers it": "An - genutzt, wo das Netz es anbietet",
    "Off: LTE, as FuriOS ships it": "Aus: LTE, wie FuriOS es ausliefert",
    "Switching 5G …": "5G wird umgeschaltet …",
    "Switching 5G - mobile data away for a few seconds …": "5G wird umgeschaltet - mobile Daten für einige Sekunden weg …",
    "Switching 5G failed": "Umschalten von 5G fehlgeschlagen",
    "5G switched on": "5G eingeschaltet",
    "5G switched off": "5G ausgeschaltet",

    # --- GPS ---------------------------------------------------------------
    "Contribute to beaconDB": "Zu beaconDB beitragen",
    "Send my observations": "Meine Beobachtungen senden",
    "Sent so far": "Bisher gesendet",
    "Firefox and web apps": "Firefox und Web-Apps",
    "Wait for the satellite fix": "Auf die Satellitenposition warten",
    "Could not change the contribution setting":
        "Die Einstellung zum Beitragen konnte nicht geändert werden",
    "Could not change the Firefox setting":
        "Die Firefox-Einstellung konnte nicht geändert werden",
    "did not answer": "hat nicht geantwortet",
    "not installed": "nicht installiert",
    "Switched on, but the service is not running - nothing is being collected":
        "Eingeschaltet, aber der Dienst läuft nicht - es wird nichts gesammelt",
    "%s sent, %s waiting": "%s gesendet, %s wartend",
    "Sending to beaconDB is off, Firefox as shipped":
        "Senden an beaconDB ist aus, Firefox wie ausgeliefert",
    "Could not switch sending off": "Das Senden konnte nicht abgeschaltet werden",
    "Up to 3 minutes instead of 12 seconds - %s of %s profiles. An open app "
    "needs a restart":
        "Bis zu 3 Minuten statt 12 Sekunden - %s von %s Profilen. Eine offene App "
        "braucht einen Neustart",
    "Off - Firefox gives up after 12 seconds, before a cold fix arrives":
        "Aus - Firefox gibt nach 12 Sekunden auf, bevor eine kalte Position kommt",
    "Networks in range with the satellite position, over Wi-Fi only":
        "Netze in Reichweite mit der Satellitenposition, nur über WLAN",
    "Off - nothing is collected or sent. On: networks in range, never hidden "
    "or _nomap ones":
        "Aus - es wird nichts gesammelt oder gesendet. An: Netze in Reichweite, "
        "nie versteckte oder _nomap-Netze",
    "Off - %s open app(s) keep it until the next login":
        "Aus - %s offene App(s) behalten es bis zur nächsten Anmeldung",
    "Switches sending off - nothing more is collected, and what is still "
    "waiting is not sent - and gives Firefox back its 12-second limit.":
        "Schaltet das Senden ab - es wird nichts mehr gesammelt, und was noch "
        "wartet, wird nicht gesendet - und gibt Firefox seine 12-Sekunden-Grenze "
        "zurück.",

    # --- Switches ----------------------------------------------------------
    "Indicator": "Anzeige",
    "Icons for the camera and network switch":
        "Symbole für den Kamera- und Netzschalter",
    "Network switch": "Netzschalter",
    "The mobile network goes with the switch": "Der Mobilfunk geht mit dem Schalter",
    "always, and not ours to change - firmware does it. (Settings switches "
    "mobile data off separately, any time.)":
        "immer, und nicht von uns änderbar - das macht die Firmware. (In den "
        "Einstellungen lassen sich mobile Daten jederzeit getrennt abschalten.)",
    "Take Wi-Fi down with it as well": "WLAN auch abschalten",
    "Take Bluetooth down with it as well": "Bluetooth auch abschalten",
    "killswitch-indicator did not answer": "killswitch-indicator hat nicht geantwortet",
    "in the top bar, at the left end of the indicators":
        "in der Leiste oben, am linken Ende der Anzeigen",
    "not shown": "nicht angezeigt",
    "this killswitch-indicator is too old to switch them - update it":
        "dieser killswitch-indicator ist zu alt, um sie umzuschalten - bitte aktualisieren",
    "phosh's plugin list is not readable here":
        "die Plugin-Liste von phosh ist hier nicht lesbar",
    "currently on": "gerade an",
    "currently off": "gerade aus",
    " - but the service that would act is not running":
        " - aber der Dienst, der handeln würde, läuft nicht",
    "Shipped state - no icons, and the switch takes only the modem":
        "Auslieferungszustand - keine Symbole, und der Schalter nimmt nur das Modem mit",
    "On. After a fresh install they appear at the next boot.":
        "An. Nach einer Neuinstallation erscheinen sie beim nächsten Start.",
    "Could not switch the icons {0}": "Die Symbole konnten nicht umgeschaltet werden ({0})",
    "Could not change {0}": "{0} konnte nicht geändert werden",
    "{0} will go off with the network switch": "{0} geht mit dem Netzschalter aus",
    "Takes the icons out of the top bar, stops the service behind them and "
    "leaves Wi-Fi and Bluetooth out of the network switch. The sliders "
    "themselves keep doing what they do - that is hardware, and nothing here "
    "reaches it.":
        "Nimmt die Symbole aus der Leiste oben, stoppt den Dienst dahinter und "
        "lässt WLAN und Bluetooth aus dem Netzschalter heraus. Die Schieber "
        "selbst tun weiter, was sie tun - das ist Hardware, und nichts hier "
        "reicht da heran.",

    # --- Battery -----------------------------------------------------------
    "While charging": "Beim Laden",
    "Colour the bolt": "Den Blitz einfärben",
    "Charge level": "Ladestand",
    "Colour the filling": "Die Füllung einfärben",
    "Drain": "Verbrauch",
    "Colour the frame": "Den Rahmen einfärben",
    "Time left": "Restlaufzeit",
    "Show it in the top bar": "In der Leiste oben anzeigen",
    "how long the battery lasts, as 00:00, left of the battery icon":
        "wie lange der Akku reicht, als 00:00, links vom Akkusymbol",
    "Charging time": "Ladezeit",
    "While the cable is in": "Solange das Kabel steckt",
    "how long until full, in the same place - off, there is no time while "
    "charging":
        "wie lange bis voll, an derselben Stelle - aus, dann steht beim Laden "
        "keine Zeit da",
    "Green": "Grün",
    "Amber": "Gelb",
    "Red": "Rot",
    "Lower": "Weniger",
    "Higher": "Mehr",
    "%.*f %s": "%.*f %s",
    "Could not change the colouring": "Die Einfärbung konnte nicht geändert werden",
    "Shipped state - no colouring": "Auslieferungszustand - keine Einfärbung",
    "Could not restore the shipped state":
        "Der Auslieferungszustand konnte nicht hergestellt werden",
    "Stops the colouring and the time left, takes them out of the next boot "
    "and out of the top bar. What the battery reports is untouched - that is "
    "the kernel's.":
        "Beendet die Einfärbung und die Restlaufzeit, nimmt sie aus dem nächsten "
        "Start und aus der Leiste oben. Was der Akku meldet, bleibt unberührt - "
        "das gehört dem Kernel.",

    # --- Security ----------------------------------------------------------
    "Hardening": "Härtung",
    "Kernel settings": "Kernel-Einstellungen",
    "unprivileged BPF, dmesg, kernel pointers, ptrace":
        "unprivilegiertes BPF, dmesg, Kernel-Zeiger, ptrace",
    "Block unused modules": "Ungenutzte Module sperren",
    "protocol families and filesystems nothing here uses":
        "Protokollfamilien und Dateisysteme, die hier nichts nutzt",
    "Lock screen lockout": "Sperre nach falschen PINs",
    "3 wrong PINs lock it: 5 min, then 10, 15, 30, 60 and longer":
        "3 falsche PINs sperren: 5 min, dann 10, 15, 30, 60 und länger",
    "not installed - run the security install again":
        "nicht installiert - die Security-Installation erneut ausführen",
    "Locked right now, %d:%02d left": "Gerade gesperrt, noch %d:%02d",
    "secctl did not answer": "secctl hat nicht geantwortet",
    "unreadable answer": "unlesbare Antwort",
    "some values did not take - press twice to write them again":
        "einige Werte haben nicht gegriffen - zweimal drücken, um sie neu zu schreiben",
    "%d of %d blocked": "%d von %d gesperrt",
    "Could not switch {part} {state}": "{part} konnte nicht auf {state} geschaltet werden",
    "Shipped state - nothing of ours is left in /etc":
        "Auslieferungszustand - nichts von uns ist mehr in /etc",
    "Could not take it back out": "Es konnte nicht wieder herausgenommen werden",
    "Takes everything back out: the sysctl file, the module blocks and the "
    "lock-screen lockout. One value stays until the next boot - the kernel "
    "will not let unprivileged BPF be re-enabled while it runs, which is by "
    "design and not a fault here.":
        "Nimmt alles wieder heraus: die sysctl-Datei, die Modulsperren und die "
        "Sperre nach falschen PINs. Ein Wert bleibt bis zum nächsten Start - der "
        "Kernel lässt unprivilegiertes BPF im laufenden Betrieb nicht wieder zu, "
        "das ist so gewollt und kein Fehler hier.",

    # --- the Phosh tab -----------------------------------------------------
    "Takes effect after the next login": "Gilt nach der nächsten Anmeldung",
    "Home screen": "Startbildschirm",
    "Hide the search field": "Suchfeld ausblenden",
    "In the app overview · after the next login":
        "In der App-Übersicht · nach der nächsten Anmeldung",
    "Folders at the bottom": "Ordner unten",
    "Needs the folder-dock plugin from furios_phosh":
        "Braucht das folder-dock-Plugin aus furios_phosh",
    "Held in a bar at the bottom edge of the app overview":
        "In einer Leiste am unteren Rand der App-Übersicht",
    "Folders in one row": "Ordner in einer Reihe",
    "Scrolls sideways instead of growing upwards":
        "Scrollt seitwärts, statt nach oben zu wachsen",
    "Hide app names": "App-Namen ausblenden",
    "Icons only, like the favorites · folders keep theirs":
        "Nur Symbole, wie bei den Favoriten · Ordner behalten ihre",
    "Unlock": "Entsperren",
    "Keyring prompt in phosh style": "Schlüsselbund-Abfrage im phosh-Stil",
    "Instead of the light window after a restart":
        "Statt des hellen Fensters nach einem Neustart",
    "Could not write %s:\n%s": "%s konnte nicht geschrieben werden:\n%s",

    # --- installing and updating -------------------------------------------
    "{page} · not installed": "{page} · nicht installiert",
    "This tab drives {tool}, and that is not on this phone. It can be fetched "
    "and installed from here; until then there is nothing to show.":
        "Dieser Reiter steuert {tool}, und das ist nicht auf diesem Telefon. Es "
        "lässt sich von hier holen und installieren; bis dahin gibt es nichts zu "
        "zeigen.",
    "What it would do": "Was es tun würde",
    "Comes from": "Kommt von",
    "What will happen": "Was passiert",
    "fetched to {path}, then {installer} - that one needs root, so sudo will "
    "ask for your password":
        "nach {path} geholt, dann {installer} - das braucht root, also fragt sudo "
        "nach deinem Passwort",
    "fetched to {path}, then {installer} - no root needed":
        "nach {path} geholt, dann {installer} - kein root nötig",
    "Fetch and install": "Holen und installieren",
    "Update": "Aktualisieren",
    "%d Update": "%d Update",
    "%d Updates": "%d Updates",
    "1 update": "1 Update",
    "%d updates": "%d Updates",
    "%d new commit(s)": "%d neue(r) Commit(s)",
    "the misc-de in this clone is not the program that is running":
        "das misc-de in diesem Klon ist nicht das laufende Programm",
    "something new on the server": "etwas Neues auf dem Server",
    "The app restarts when they are in.": "Die App startet neu, wenn sie drin sind.",
    "Update and restart": "Aktualisieren und neu starten",
    "Could not install the updates": "Die Updates konnten nicht installiert werden",
    "working …": "arbeitet …",
    "run %s from that clone": "%s aus diesem Klon ausführen",
    "That is code from the internet, running on this phone. The installer "
    "writes to /usr/local, so sudo will ask for your password below - it goes "
    "to sudo and nowhere else, and the ticket is dropped when this is done.":
        "Das ist Code aus dem Internet, der auf diesem Telefon läuft. Der "
        "Installer schreibt nach /usr/local, also fragt sudo unten nach deinem "
        "Passwort - es geht an sudo und nirgendwo sonst hin, und das Ticket wird "
        "am Ende verworfen.",
    "That is code from the internet, running on this phone. Nothing here needs "
    "root.":
        "Das ist Code aus dem Internet, der auf diesem Telefon läuft. Hier "
        "braucht nichts root.",
    "This is your own clone. With anything uncommitted in it, nothing is "
    "touched at all.":
        "Das ist dein eigener Klon. Ist darin etwas nicht committet, wird gar "
        "nichts angefasst.",
    "{tool} is up to date": "{tool} ist aktuell",
    "{tool} is in place - this tab is live": "{tool} ist da - dieser Reiter ist aktiv",
    "{tool} ran, but is not on the phone": "{tool} lief, ist aber nicht auf dem Telefon",
    "Could not set up {tool}": "{tool} konnte nicht eingerichtet werden",
    "Could not restart: {error}": "Neustart nicht möglich: {error}",
    "git clone {url} to {path}": "git clone {url} nach {path}",
    "nothing is fetched - the clone in {path} is used exactly as it is":
        "es wird nichts geholt - der Klon in {path} wird genau so verwendet",
    "git pull --ff-only in {path}": "git pull --ff-only in {path}",
    "the clone in {path} is already here - update it if possible, install from "
    "it either way":
        "der Klon in {path} ist schon da - wenn möglich aktualisieren, in jedem "
        "Fall daraus installieren",
    "{path} is in the way - it is not a clone of {url}":
        "{path} ist im Weg - es ist kein Klon von {url}",
}
