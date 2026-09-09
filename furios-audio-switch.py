#!/usr/bin/env python3
"""Kleine Schaltflaeche fuer den Audiostack des FuriPhone.

Ein Schalter: PipeWire spricht direkt mit dem Android-HAL - oder eben nicht,
dann haelt PulseAudio ihn wie im Auslieferungszustand. Die Arbeit macht
audioctl; diese Oberflaeche ruft es nur auf und zeigt, was wirklich laeuft.

Bewusst schlicht gehalten: auf einem Telefon will man einen Knopf, keine
Schaltzentrale.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

APP_ID = "de.furios.audioswitch"
AUDIOCTL = "/usr/local/bin/audioctl"


def run_async(argv, on_done):
    """audioctl laeuft bis zu 15 Sekunden (es wartet auf einen Sink).
    Deshalb niemals blockierend aufrufen - sonst friert das Fenster ein."""
    try:
        proc = Gio.Subprocess.new(
            argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
        )
    except GLib.Error as err:
        on_done(False, str(err))
        return

    def finished(p, res):
        try:
            ok, out, _ = p.communicate_utf8_finish(res)
            on_done(p.get_successful(), (out or "").strip())
        except GLib.Error as err:
            on_done(False, str(err))

    proc.communicate_utf8_async(None, None, finished)


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Audio-Umschalter")
        self.set_default_size(360, 480)
        self.busy = False
        self._syncing = False

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text("Zustand neu einlesen")
        self.refresh_btn.connect("clicked", lambda *_: self.refresh())
        header.pack_end(self.refresh_btn)

        page = Adw.PreferencesPage()

        # --- Der eigentliche Schalter ---
        grp = Adw.PreferencesGroup(title="Audiostack")
        self.switch_row = Adw.SwitchRow(
            title="PipeWire haelt den HAL",
            subtitle="Aus: PulseAudio wie im Auslieferungszustand",
        )
        self.switch_row.connect("notify::active", self.on_switch)
        grp.add(self.switch_row)

        self.persist_row = Adw.SwitchRow(
            title="Auswahl behalten",
            subtitle="Aus: ein Neustart fuehrt zurueck zum Auslieferungszustand",
        )
        grp.add(self.persist_row)
        page.add(grp)

        # --- Was gerade wirklich laeuft ---
        info = Adw.PreferencesGroup(title="Zustand")
        self.row_profile = Adw.ActionRow(title="Profil", subtitle="wird gelesen …")
        self.row_server = Adw.ActionRow(title="Tonserver", subtitle="…")
        self.row_sinks = Adw.ActionRow(title="Ausgaenge", subtitle="…")
        for row in (self.row_profile, self.row_server, self.row_sinks):
            row.set_subtitle_selectable(True)
            info.add(row)
        page.add(info)

        # --- Notnagel ---
        rescue = Adw.PreferencesGroup(
            title="Wenn nichts zu hoeren ist",
            description="Stellt den Auslieferungszustand her und schaltet den "
            "Ton auf den Lautsprecher, hoerbar laut und nicht stumm.",
        )
        btn = Gtk.Button(label="Ton wiederherstellen")
        btn.add_css_class("pill")
        btn.add_css_class("suggested-action")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(6)
        btn.set_margin_bottom(6)
        btn.connect("clicked", self.on_rescue)
        rescue.add(btn)
        page.add(rescue)

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(page)
        toolbar.set_content(self.toasts)
        self.set_content(toolbar)

        self.refresh()

    # ------------------------------------------------------------ Zustand

    def refresh(self):
        run_async([AUDIOCTL, "status"], self.on_status)

    def on_status(self, ok, out):
        profile, server, sinks = "unbekannt", "-", "-"
        warn = None
        for line in out.splitlines():
            if line.startswith("Profil (aktiv):"):
                profile = line.split(":", 1)[1].strip()
            elif line.startswith("ACHTUNG:"):
                warn = line.split(":", 1)[1].strip()
            elif line.startswith("Pulse-Server:"):
                server = line.split(":", 1)[1].strip()
            elif line.startswith("Sinks:"):
                sinks = line.split(":", 1)[1].strip()

        self.row_profile.set_subtitle(profile if not warn else f"{profile} ({warn})")
        self.row_server.set_subtitle(server)
        self.row_sinks.set_subtitle(sinks.replace(",", ", ") or "keine")

        # Schalter nachfuehren, ohne dabei ein Umschalten auszuloesen.
        self._syncing = True
        self.switch_row.set_active(profile == "pw-hal")
        self._syncing = False
        self.set_busy(False)

    def set_busy(self, busy):
        self.busy = busy
        self.switch_row.set_sensitive(not busy)
        self.persist_row.set_sensitive(not busy)
        self.refresh_btn.set_sensitive(not busy)
        if busy:
            self.switch_row.set_subtitle("Wird umgeschaltet, das dauert einen Moment …")
        elif self.switch_row.get_active():
            self.switch_row.set_subtitle("An: PipeWire spricht direkt mit dem HAL")
        else:
            self.switch_row.set_subtitle("Aus: PulseAudio wie im Auslieferungszustand")

    # ------------------------------------------------------------ Aktionen

    def on_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        want_pw = row.get_active()
        mode = "set" if self.persist_row.get_active() else "try"
        argv = [AUDIOCTL, mode, "pw-hal"] if want_pw else [AUDIOCTL, "set", "standard"]
        self.set_busy(True)
        run_async(argv, self.on_switched)

    def on_switched(self, ok, out):
        if not ok:
            self.toast("Umschalten fehlgeschlagen")
            self.report(out or "Keine Ausgabe.")
        else:
            last = [l for l in out.splitlines() if l.strip()]
            self.toast(last[-1].strip() if last else "Fertig")
        self.refresh()

    def on_rescue(self, _btn):
        if self.busy:
            return
        self.set_busy(True)
        script = (
            "set -e\n"
            f"{AUDIOCTL} set standard\n"
            "pactl set-sink-mute @DEFAULT_SINK@ 0 || true\n"
            "pactl set-sink-volume @DEFAULT_SINK@ 65% || true\n"
            "pactl set-sink-port sink.primary_output output-speaker || true\n"
            "pactl set-source-mute @DEFAULT_SOURCE@ 0 || true\n"
        )
        run_async(["/bin/sh", "-c", script], self.on_rescued)

    def on_rescued(self, ok, out):
        self.toast(
            "Auslieferungszustand, Lautsprecher, 65 %"
            if ok
            else "Wiederherstellen fehlgeschlagen"
        )
        if not ok:
            self.report(out or "Keine Ausgabe.")
        self.refresh()

    # ------------------------------------------------------------ Meldungen

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))

    def report(self, text):
        dlg = Adw.AlertDialog(heading="Das ging schief", body=text)
        dlg.add_response("ok", "Verstanden")
        dlg.present(self)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        win = self.props.active_window or Window(self)
        win.present()


if __name__ == "__main__":
    import sys

    sys.exit(App().run(sys.argv))
