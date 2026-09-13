#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The switches for a FuriPhone that has been repaired by hand.

Two pages, and each is one switch: the audio stack talks to the Android HAL
through PipeWire or through PulseAudio as shipped, and the modem runs with the
repairs from furios_modem_fixes or exactly as it came. The tools do the work -
audioctl and modemctl - and this front end only calls them and shows what is
actually running.

The modem page exists only when modemctl does. A tab that is always there and
always says "not installed" is worse than no tab: it makes a phone where
nothing is wrong look like a phone where something is.

Deliberately plain: on a phone you want a button, not a control room.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

# This app used to carry a polkit authentication agent, because switching the
# stack meant masking system units and writing into /etc, and phosh registers
# no agent of its own. It does not need one any more: audioctl keeps the
# profile under $HOME, where the session may write anyway, so there is nothing
# left to authenticate and no password for this app to handle.

APP_ID = "de.misc-de.tools"
import os
import shutil

# From the package it lives in /usr/bin, from the source tree in /usr/local/bin.
#
# The installed paths are tried BEFORE $PATH. What is started here goes on to
# ask polkit for root, and this app registers the agent that answers - so the
# one thing not to do is let the search order decide which "audioctl" that is.
# $PATH stays as the last resort for an install somewhere else entirely.
def _tool(name):
    for path in ("/usr/local/bin/" + name, "/usr/bin/" + name):
        if os.access(path, os.X_OK):
            return path
    return shutil.which(name) or "/usr/bin/" + name


# Like _tool, but it admits when the program is not there at all. The modem
# page is built from this: present or absent, never present-and-broken.
def _tool_maybe(name):
    for path in ("/usr/local/bin/" + name, "/usr/bin/" + name):
        if os.access(path, os.X_OK):
            return path
    return shutil.which(name)


AUDIOCTL = _tool("audioctl")
DMNR = _tool("furios-audio-dmnr")
# Ships in a different package (furios_modem_fixes) and may simply not be here.
MODEMCTL = _tool_maybe("modemctl")
# Switching the modem writes /usr/lib and /etc, so it needs root, and unlike
# audioctl there is no version of it that does not. polkit's own helper is how
# that is asked for; the action this phone carries allows it without a prompt
# for the session sitting at the device, which is why no authentication agent
# is needed here any more than on the audio side.
PKEXEC = _tool_maybe("pkexec")


def server_in_words(raw):
    """PipeWire's PulseAudio interface announces itself as
    "PulseAudio (on PipeWire 1.6.6)". Reading that underneath a switch which
    says "PipeWire holds the HAL" rightly looks like a contradiction. So
    translate it."""
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
    """audioctl runs for up to 15 seconds (it waits for a sink), so never
    call it blocking - the window would freeze.

    If on_line is passed, lines arrive one by one while the program is still
    running. That is the difference between "something is happening" and a
    window that looks dead for ten seconds."""
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
        if line is None:                      # end of output
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
        super().__init__(application=app, title="misc-de")
        self.set_default_size(360, 480)
        self.busy = False
        self._syncing = False
        self.modem_rows = []

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

        # Progress: deliberately pulsing instead of a percentage. Nobody
        # knows in advance how long the switch takes - audioctl waits up to 15
        # seconds for a sink. An invented percentage that gets stuck at 90 %
        # would be worse than none at all.
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

        # --- echo during a call ---
        #
        # MediaTek's dual-microphone method against noise and echo is disabled
        # for calls on this device, although the chip could do it. The switch
        # lays a modified tuning file over the vendor's.
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

        # --- die Seiten ---
        #
        # One page is the app that existed before this. The second only comes
        # into being if modemctl is installed, and with a single page the
        # switcher bar stays hidden - so on a phone without the modem package
        # nothing about this window looks different from before.
        self.stack = Adw.ViewStack()
        self.stack.add_titled_with_icon(page, "audio", "Audio", "audio-speakers-symbolic")

        self.modem_rows = []
        if MODEMCTL:
            self.stack.add_titled_with_icon(
                self.build_modem_page(), "modem", "Modem", "network-cellular-symbolic"
            )

        switcher = Adw.ViewSwitcherBar(stack=self.stack)
        switcher.set_reveal(bool(MODEMCTL))
        toolbar.add_bottom_bar(switcher)

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(self.stack)
        toolbar.set_content(self.toasts)
        self.set_content(toolbar)

        self.refresh()

    # ------------------------------------------------------------ Modem

    def build_modem_page(self):
        """The same shape as the audio page, because it is the same question:
        the phone as it shipped, or the phone as somebody repaired it."""
        mpage = Adw.PreferencesPage()

        grp = Adw.PreferencesGroup(
            title="Modem",
            description="Off is FuriOS exactly as it came: no fallback route "
            "when Wi-Fi goes away, no name resolution without it, and a signal "
            "bar that cannot leave zero.",
        )
        self.modem_row = Adw.SwitchRow(
            title="Repairs active",
            subtitle="reading …",
        )
        self.modem_row.connect("notify::active", self.on_modem_switch)
        grp.add(self.modem_row)

        self.modem_persist = Adw.SwitchRow(
            title="Remember this choice",
            subtitle="Off: the next boot returns to what was recorded",
            active=True,
        )
        grp.add(self.modem_persist)

        self.modem_progress = Gtk.ProgressBar(show_text=True, text="")
        for m in ("top", "bottom"):
            getattr(self.modem_progress, "set_margin_" + m)(6)
        for m in ("start", "end"):
            getattr(self.modem_progress, "set_margin_" + m)(12)
        self.modem_revealer = Gtk.Revealer(
            child=self.modem_progress,
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            reveal_child=False,
        )
        grp.add(self.modem_revealer)
        mpage.add(grp)

        info = Adw.PreferencesGroup(title="Status")
        self.mrow_profile = Adw.ActionRow(title="Profile", subtitle="…")
        self.mrow_health = Adw.ActionRow(title="Checks", subtitle="…")
        self.mrow_signal = Adw.ActionRow(title="Signal", subtitle="…")
        for row in (self.mrow_profile, self.mrow_health, self.mrow_signal):
            row.set_subtitle_selectable(True)
            info.add(row)
        mpage.add(info)

        self.modem_rows = [self.modem_row, self.modem_persist]
        return mpage

    # ------------------------------------------------------------ Zustand

    def refresh(self):
        run_async([AUDIOCTL, "status"], self.on_status)
        run_async([DMNR, "status"], self.on_dmnr_status)
        if MODEMCTL:
            # Both read-only, and neither needs root - which is the whole
            # reason the page can show something before anybody touches it.
            run_async([MODEMCTL, "profile"], self.on_modem_profile)
            run_async([MODEMCTL, "status"], self.on_modem_status)

    # "recorded: x" and "actual: y", split on the colon rather than matched
    # against a prefix. modemctl lives in another package, so this is a
    # contract between two repositories - it is checked from the other side
    # too, where the words are printed.
    @staticmethod
    def _keyed(out):
        found = {}
        for line in out.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                found[key.strip()] = value.strip()
        return found

    def on_modem_profile(self, ok, out):
        if not ok:
            self.modem_row.set_sensitive(False)
            self.mrow_profile.set_subtitle("modemctl did not answer")
            return
        found = self._keyed(out)
        recorded, actual = found.get("recorded", "?"), found.get("actual", "?")

        if actual == "fixed":
            words = "the repairs are in place"
        elif actual == "shipped":
            words = "FuriOS as it came"
        else:
            # "mixed" is a real state and saying either of the other two would
            # be wrong in both directions.
            words = "half repaired - use \"Repairs active\" to settle it"
        if recorded != actual and actual in ("fixed", "shipped"):
            words += f" · not remembered, the next boot returns to \"{recorded}\""
        self.mrow_profile.set_subtitle(words)

        self._syncing = True
        self.modem_row.set_active(actual == "fixed")
        self.modem_persist.set_active(recorded == actual)
        self._syncing = False
        self.modem_row.set_subtitle(
            "On: patched, with a route and a resolver that work without Wi-Fi"
            if actual == "fixed"
            else "Off: the state the phone shipped in"
        )

    def on_modem_status(self, ok, out):
        if not ok and not out:
            self.mrow_health.set_subtitle("modemctl did not answer")
            return
        bad = sum(1 for line in out.splitlines() if "FAIL" in line)
        good = sum(1 for line in out.splitlines() if " ok " in line)
        self.mrow_health.set_subtitle(
            f"{good} in place" if bad == 0 else f"{good} in place, {bad} not"
        )
        for line in out.splitlines():
            if "signal quality" in line:
                self.mrow_signal.set_subtitle(line.split("signal quality", 1)[1].strip())
                break
        else:
            self.mrow_signal.set_subtitle("not readable")

    def on_modem_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        if not PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        mode = "set" if self.modem_persist.get_active() else "try"
        want = "fixed" if row.get_active() else "shipped"
        self.set_busy(True)
        self.modem_progress.set_text("Switching …")
        self.modem_revealer.set_reveal_child(True)
        self.pulse_start("Switching the modem …")
        run_async([PKEXEC, MODEMCTL, mode, want], self.on_modem_switched,
                  on_line=self.on_progress_line)

    def on_modem_switched(self, ok, out):
        self.pulse_stop()
        self.modem_revealer.set_reveal_child(False)
        if not ok:
            # A refusal from polkit looks like any other failure from here, and
            # it is the likely one on a phone where this is not authorised.
            self.toast("Switching the modem failed")
            self.report(out or "No output.")
        else:
            last = [l for l in out.splitlines() if l.strip()]
            self.toast(last[-1].strip() if last else "Done")
        self.refresh()

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
        profile, server, sinks = "unknown", "-", "-"
        warn = None
        testmode = False
        for line in out.splitlines():
            if line.startswith("Profile (active):"):
                profile = line.split(":", 1)[1].strip()
            elif line.startswith("WARNING:"):
                warn = line.split(":", 1)[1].strip()
            elif line.startswith("Test mode:"):
                testmode = line.split(":", 1)[1].strip().startswith("yes")
            elif line.startswith("Pulse server:"):
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
        # Empty when there is no modem page, which is the point: nothing here
        # may assume the second page exists.
        for row in self.modem_rows:
            row.set_sensitive(not busy)
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
        """Shows the step audioctl is currently reporting - shortened so it
        fits on one line."""
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
        run_async([DMNR, "on" if row.get_active() else "off"], self.on_dmnr_done,
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
        # The same recovery as on the command line - one truth, not two
        # versions that can drift apart.
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
