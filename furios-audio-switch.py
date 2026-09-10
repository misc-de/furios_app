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
import shutil

# Aus dem Paket liegt es in /usr/bin, aus dem Quellbaum in /usr/local/bin.
AUDIOCTL = shutil.which("audioctl") or "/usr/bin/audioctl"
DMNR = shutil.which("furios-audio-dmnr") or "/usr/bin/furios-audio-dmnr"


def server_in_words(raw):
    """PipeWires PulseAudio-Schnittstelle meldet sich als
    "PulseAudio (on PipeWire 1.6.6)". Wer das unter einem Schalter liest, der
    "PipeWire haelt den HAL" sagt, haelt es zu Recht fuer einen Widerspruch.
    Also uebersetzen."""
    if not raw or raw == "-":
        return "not reachable"
    if "PipeWire" in raw:
        ver = ""
        for token in raw.replace(")", " ").split():
            if token[:1].isdigit():
                ver = " " + token
                break
        return f"PipeWire{ver} - also speaks PulseAudio for older apps"
    if raw.lower().startswith("pulseaudio"):
        return "PulseAudio - the shipped setup"
    return raw


def run_async(argv, on_done, on_line=None):
    """audioctl laeuft bis zu 15 Sekunden (es wartet auf einen Sink).
    Deshalb niemals blockierend aufrufen - sonst friert das Fenster ein.

    Wird on_line uebergeben, kommen die Zeilen einzeln herein, waehrend das
    Programm noch laeuft. Das ist der Unterschied zwischen "es tut sich was"
    und einem Fenster, das zehn Sekunden lang tot wirkt."""
    try:
        proc = Gio.Subprocess.new(
            argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
        )
    except GLib.Error as err:
        on_done(False, str(err))
        return

    if on_line is None:
        def finished(p, res):
            try:
                _ok, out, _ = p.communicate_utf8_finish(res)
                on_done(p.get_successful(), (out or "").strip())
            except GLib.Error as err:
                on_done(False, str(err))

        proc.communicate_utf8_async(None, None, finished)
        return

    stream = Gio.DataInputStream.new(proc.get_stdout_pipe())
    collected = []

    def read_next():
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, got_line)

    def got_line(src, res):
        try:
            line, _length = src.read_line_finish_utf8(res)
        except GLib.Error as err:
            on_done(False, str(err))
            return
        if line is None:                      # Ende der Ausgabe
            proc.wait_async(None, waited)
            return
        line = line.strip()
        if line:
            collected.append(line)
            on_line(line)
        read_next()

    def waited(p, res):
        try:
            p.wait_finish(res)
            on_done(p.get_successful(), "\n".join(collected))
        except GLib.Error as err:
            on_done(False, str(err))

    read_next()


class Window(Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Audio Switch")
        self.set_default_size(360, 480)
        self.busy = False
        self._syncing = False

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        self.refresh_btn = Gtk.Button(icon_name="view-refresh-symbolic")
        self.refresh_btn.set_tooltip_text("Reload status")
        self.refresh_btn.connect("clicked", lambda *_: self.refresh())
        header.pack_end(self.refresh_btn)

        page = Adw.PreferencesPage()

        # --- Der eigentliche Schalter ---
        grp = Adw.PreferencesGroup(title="Audio stack")
        self.switch_row = Adw.SwitchRow(
            title="PipeWire owns the HAL",
            subtitle="Off: PulseAudio, exactly as shipped",
        )
        self.switch_row.connect("notify::active", self.on_switch)
        grp.add(self.switch_row)

        self.persist_row = Adw.SwitchRow(
            title="Remember this choice",
            subtitle="Off: a reboot returns to the shipped state",
        )
        grp.add(self.persist_row)

        # Fortschritt: bewusst pulsierend statt mit Prozentzahl. Wie lange das
        # Umschalten dauert, weiss niemand vorher - audioctl wartet bis zu 15
        # Sekunden auf einen Sink. Eine erfundene Prozentzahl, die bei 90 %
        # haengen bleibt, waere schlechter als gar keine.
        self.progress = Gtk.ProgressBar(show_text=True, text="")
        self.progress.set_margin_top(6)
        self.progress.set_margin_bottom(6)
        self.progress.set_margin_start(12)
        self.progress.set_margin_end(12)
        self.progress_revealer = Gtk.Revealer(
            child=self.progress,
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            reveal_child=False,
        )
        grp.add(self.progress_revealer)
        page.add(grp)
        self._pulse_id = 0

        # --- Was gerade wirklich laeuft ---
        info = Adw.PreferencesGroup(title="Status")
        self.row_profile = Adw.ActionRow(title="Owns the Android HAL", subtitle="reading …")
        self.row_server = Adw.ActionRow(title="Sound server", subtitle="…")
        self.row_sinks = Adw.ActionRow(title="Outputs", subtitle="…")
        for row in (self.row_profile, self.row_server, self.row_sinks):
            row.set_subtitle_selectable(True)
            info.add(row)
        page.add(info)

        # --- Echo im Gespraech ---
        #
        # MediaTeks Zweimikrofonverfahren gegen Stoergeraeusche und Echo ist
        # auf diesem Geraet fuer den Anruf abgeschaltet, obwohl der Chip es
        # koennte. Der Schalter legt eine geaenderte Abstimmungsdatei darueber.
        echo_grp = Adw.PreferencesGroup(
            title="Call echo",
            description="The vendor disabled MediaTek's dual-mic echo "
            "suppression (DMNR) for calls, although this phone has two "
            "microphones and the chip supports it. Turning it on may stop the "
            "other side from hearing themselves - especially on speakerphone. "
            "Experimental: it restarts audio and is undone by a reboot.",
        )
        self.dmnr_row = Adw.SwitchRow(
            title="Handsfree echo suppression (DMNR)",
            subtitle="Vendor setting: off",
        )
        self.dmnr_row.connect("notify::active", self.on_dmnr)
        echo_grp.add(self.dmnr_row)
        page.add(echo_grp)

        # --- Notnagel ---
        rescue = Adw.PreferencesGroup(
            title="If you hear nothing",
            description="Returns to the shipped state and sends sound to the "
            "speaker - audible volume, unmuted.",
        )
        btn = Gtk.Button(label="Restore sound")
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
        run_async([DMNR, "status"], self.on_dmnr_status)

    def on_dmnr_status(self, ok, out):
        if not ok:
            self.dmnr_row.set_sensitive(False)
            self.dmnr_row.set_subtitle("not available on this device")
            return
        on = "state=on" in out
        self._syncing = True
        self.dmnr_row.set_active(on)
        self._syncing = False
        self.dmnr_row.set_subtitle(
            "On - modified tuning file in place" if on else "Vendor setting: off"
        )

    def on_status(self, ok, out):
        profile, server, sinks = "unbekannt", "-", "-"
        warn = None
        testmode = False
        for line in out.splitlines():
            if line.startswith("Profil (aktiv):"):
                profile = line.split(":", 1)[1].strip()
            elif line.startswith("ACHTUNG:"):
                warn = line.split(":", 1)[1].strip()
            elif line.startswith("Testmodus:"):
                testmode = line.split(":", 1)[1].strip().startswith("ja")
            elif line.startswith("Pulse-Server:"):
                server = line.split(":", 1)[1].strip()
            elif line.startswith("Sinks:"):
                sinks = line.split(":", 1)[1].strip()

        if profile == "pw-hal":
            text = "PipeWire owns the HAL"
        elif profile == "standard":
            text = "PulseAudio owns the HAL (as shipped)"
        elif profile == "pw-tunnel":
            text = "PulseAudio owns the HAL, PipeWire gets a sink"
        else:
            text = profile
        if testmode:
            text += " - until reboot"
        if warn:
            text += f" | {warn}"
        self.row_profile.set_subtitle(text)
        self.row_server.set_subtitle(server_in_words(server))
        self.row_sinks.set_subtitle(sinks.replace(",", ", ") or "none")

        # Schalter nachfuehren, ohne dabei ein Umschalten auszuloesen.
        self._syncing = True
        self.switch_row.set_active(profile == "pw-hal")
        self._syncing = False
        self.set_busy(False)

    def pulse_start(self, text):
        self.progress.set_text(text)
        self.progress.set_fraction(0.0)
        self.progress.pulse()
        self.progress_revealer.set_reveal_child(True)
        if self._pulse_id == 0:
            self._pulse_id = GLib.timeout_add(120, self._pulse_tick)

    def _pulse_tick(self):
        self.progress.pulse()
        return GLib.SOURCE_CONTINUE

    def pulse_stop(self):
        if self._pulse_id:
            GLib.source_remove(self._pulse_id)
            self._pulse_id = 0
        self.progress_revealer.set_reveal_child(False)

    def set_busy(self, busy):
        self.busy = busy
        self.switch_row.set_sensitive(not busy)
        self.persist_row.set_sensitive(not busy)
        self.dmnr_row.set_sensitive(not busy)
        self.refresh_btn.set_sensitive(not busy)
        if busy:
            self.switch_row.set_subtitle("Switching, this takes a moment …")
        elif self.switch_row.get_active():
            self.switch_row.set_subtitle("On: PipeWire talks to the HAL directly")
        else:
            self.switch_row.set_subtitle("Off: PulseAudio, exactly as shipped")

    # ------------------------------------------------------------ Aktionen

    def on_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        want_pw = row.get_active()
        mode = "set" if self.persist_row.get_active() else "try"
        argv = [AUDIOCTL, mode, "pw-hal"] if want_pw else [AUDIOCTL, "set", "standard"]
        self.set_busy(True)
        self.pulse_start("Switching …")
        run_async(argv, self.on_switched, on_line=self.on_progress_line)

    def on_progress_line(self, line):
        """Zeigt den Schritt, den audioctl gerade meldet - gekuerzt, damit er
        in eine Zeile passt."""
        self.progress.set_text(line[:60])

    def on_switched(self, ok, out):
        self.pulse_stop()
        if not ok:
            self.toast("Switching failed")
            self.report(out or "No output.")
        else:
            last = [l for l in out.splitlines() if l.strip()]
            self.toast(last[-1].strip() if last else "Done")
        self.refresh()

    def on_dmnr(self, row, _param):
        if self._syncing or self.busy:
            return
        self.set_busy(True)
        self.pulse_start("Switching echo suppression …")
        run_async([DMNR, "an" if row.get_active() else "aus"], self.on_dmnr_done,
                  on_line=self.on_progress_line)

    def on_dmnr_done(self, ok, out):
        self.pulse_stop()
        if not ok:
            self.toast("Could not switch echo suppression")
            self.report(out or "No output.")
        else:
            self.toast("Echo suppression changed - try a call")
        self.refresh()

    def on_rescue(self, _btn):
        if self.busy:
            return
        self.set_busy(True)
        self.pulse_start("Restoring …")
        # Dieselbe Wiederherstellung wie auf der Kommandozeile - eine Wahrheit,
        # nicht zwei Fassungen, die auseinanderlaufen koennen.
        run_async([AUDIOCTL, "rescue"], self.on_rescued,
                  on_line=self.on_progress_line)

    def on_rescued(self, ok, out):
        self.pulse_stop()
        self.toast(
            "Shipped state, speaker, 65 %"
            if ok
            else "Restore failed"
        )
        if not ok:
            self.report(out or "No output.")
        self.refresh()

    # ------------------------------------------------------------ Meldungen

    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))

    def report(self, text):
        dlg = Adw.AlertDialog(heading="Something went wrong", body=text)
        dlg.add_response("ok", "Got it")
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
