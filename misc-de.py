#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The switches for a FuriPhone that has been repaired by hand.

Three pages, and each is one switch: the audio stack talks to the Android HAL
through PipeWire or through PulseAudio as shipped, the modem runs with the
repairs from furios_modem_fixes or exactly as it came, and geoclue either has
the filter that throws away positions derived from the carrier's IP address or
it does not. The tools do the work - audioctl, modemctl and gpsctl - and this
front end only calls them and shows what is actually running.

The modem and GPS pages exist only when their tool does. A tab that is always
there and always says "not installed" is worse than no tab: it makes a phone
where nothing is wrong look like a phone where something is.

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
import json
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
    # ~/.local/bin is searched too, and last: a tool that needs no root at all
    # is installed there, and killswitch-indicator is one of those.
    home_bin = os.path.expanduser("~/.local/bin/" + name)
    for path in ("/usr/local/bin/" + name, "/usr/bin/" + name, home_bin):
        if os.access(path, os.X_OK):
            return path
    return shutil.which(name)


KILLSWITCH = _tool_maybe("killswitch-indicator")
AUDIOCTL = _tool("audioctl")
DMNR = _tool("furios-audio-dmnr")
# Ships in a different package (furios_modem_fixes) and may simply not be here.
MODEMCTL = _tool_maybe("modemctl")
# Same again, from furios_gps.
GPSCTL = _tool_maybe("gpsctl")
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


PROFILE_WORDS = {
    "pw-hal": "PipeWire owns the HAL",
    "standard": "PulseAudio owns the HAL (as shipped)",
    "pw-tunnel": "PulseAudio owns the HAL, PipeWire gets a sink",
}


def profile_in_words(p):
    return PROFILE_WORDS.get(p, p)


# Long enough that nothing honest is ever cut off - audioctl alone may wait 15
# seconds for a sink, and a switch behind pkexec runs several systemctl calls
# after that - and short enough that a phone is not left with a greyed-out
# window and a pulsing bar until somebody kills the app.
CALL_TIMEOUT = 90


def run_async(argv, on_done, on_line=None, timeout=CALL_TIMEOUT):
    """audioctl runs for up to 15 seconds (it waits for a sink), so never
    call it blocking - the window would freeze.

    If on_line is passed, lines arrive one by one while the program is still
    running. That is the difference between "something is happening" and a
    window that looks dead for ten seconds.

    Every call is bounded. systemctl can block on a job that is itself
    waiting, and a helper that never returns used to mean set_busy(True) with
    nothing to ever set it back: the switches stay grey, the progress bar
    keeps pulsing, and the only way out is to kill the window. A bounded wait
    turns that into an error message, which is a state somebody can act on.
    """
    try:
        proc = Gio.Subprocess.new(
            argv, Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
        )
    except GLib.Error as err:
        on_done(False, str(err))
        return

    # on_done exactly once, whichever of the two gets there first. The caller's
    # callback is held under its own name: the readers below look "on_done" up
    # when they run, so rebinding it without this would have settle calling
    # itself for ever.
    finish = on_done
    state = {"done": False, "timer": 0}

    def settle(ok, out):
        if state["done"]:
            return
        state["done"] = True
        if state["timer"]:
            GLib.source_remove(state["timer"])
            state["timer"] = 0
        finish(ok, out)

    def give_up():
        state["timer"] = 0
        if not state["done"]:
            # force_exit, not a polite signal: what is being waited on is a
            # program that has already stopped answering.
            proc.force_exit()
        # Handed to settle either way rather than checked twice here. Whether
        # an answer is too late is one question and it has one place to be
        # asked, which is also the place a reader answering twice runs into.
        settle(False, f"{argv[0]} did not answer within {timeout} seconds")
        return False

    if timeout:
        state["timer"] = GLib.timeout_add_seconds(timeout, give_up)
    on_done = settle

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
        # Whether there is anything behind each control. A switch whose tool
        # did not answer must not look operable - and it must not become
        # operable again the moment something else finishes, which is what
        # happened as long as set_busy was the only hand on the sensitivity.
        self.audio_ok = True
        self.dmnr_ok = True
        self.modem_ok = True
        self.gps_ok = True
        self.gps_rows = []

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

        # Echo during a call, in the same group as the stack switch and
        # without the essay it used to carry: MediaTek's dual-microphone
        # method against noise and echo is disabled for calls on this device
        # although the chip could do it, and this lays a modified tuning file
        # over the vendor's. Experimental - it restarts audio and a reboot
        # undoes it.
        self.dmnr_row = Adw.SwitchRow(
            title="Handsfree echo suppression (DMNR)",
            subtitle="Vendor setting: off",
        )
        self.dmnr_row.connect("notify::active", self.on_dmnr)
        grp.add(self.dmnr_row)

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

        self.gps_rows = []
        if GPSCTL:
            self.stack.add_titled_with_icon(
                self.build_gps_page(), "gps", "GPS", "find-location-symbolic"
            )

        self.sw_rows = []
        if KILLSWITCH:
            self.stack.add_titled_with_icon(
                self.build_switches_page(), "switches", "Switches",
                "changes-prevent-symbolic"
            )

        # Revealed when there is more than one page, rather than when the modem
        # page in particular is there. Naming one page here is how a third one
        # gets added and reaches nobody, because the bar that switches to it
        # stays hidden on a phone without the second.
        switcher = Adw.ViewSwitcherBar(stack=self.stack)
        switcher.set_reveal(bool(MODEMCTL) or bool(GPSCTL) or bool(KILLSWITCH))
        toolbar.add_bottom_bar(switcher)

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(self.stack)
        toolbar.set_content(self.toasts)
        self.set_content(toolbar)

        self.refresh()


    # ------------------------------------------------------------ Switches

    def build_switches_page(self):
        """The three sliders on the housing, and what each of them really does.

        They look alike and work nothing alike. Camera and network are software
        kills: a GPIO tells the Android side, which stops a service with signal
        9. The microphone one cuts the line, which is why it is the only one
        the system cannot see at all - and the only one that is beyond doubt.
        """
        spage = Adw.PreferencesPage()

        grp = Adw.PreferencesGroup(
            title="Indicator",
            description="Shows an icon in the top bar for as long as a switch "
            "is engaged. Nothing else on the phone says so: there is no rfkill "
            "device for these, and the bar keeps showing the bars of whatever "
            "the modem last reported.",
        )
        self.sw_row = Adw.SwitchRow(title="Icons in the top bar", subtitle="reading …")
        self.sw_row.connect("notify::active", self.on_indicator_switch)
        grp.add(self.sw_row)
        self.sw_persist = Adw.SwitchRow(
            title="Remember this choice",
            subtitle="Off: gone again after the next boot",
            active=True,
        )
        self.sw_persist.connect("notify::active", self.on_indicator_persist)
        grp.add(self.sw_persist)
        spage.add(grp)

        cam = Adw.PreferencesGroup(
            title="1 · Camera",
            description="This always covers ALL cameras at once - there is no "
            "picking one. Engaged, the Android side stops camerahalserver, the "
            "one service every camera goes through: signal 9, about two "
            "seconds after the slider moves. No power is cut - the sensors "
            "stay connected, but nothing is left running that could reach "
            "them.",
        )
        self.srow_cam = Adw.ActionRow(title="Position", subtitle="…")
        self.srow_cam_hal = Adw.ActionRow(title="Camera service", subtitle="…")
        self.srow_cams = Adw.ActionRow(title="Cameras affected", subtitle="…")
        for row in (self.srow_cam, self.srow_cam_hal, self.srow_cams):
            row.set_subtitle_selectable(True)
            cam.add(row)
        spage.add(cam)

        net = Adw.PreferencesGroup(
            title="2 · Network",
            description="By itself this switch takes down the modem and "
            "nothing else - Wi-Fi and Bluetooth keep running. The two below "
            "can be added, and are then switched off in software whenever the "
            "slider moves, and back on when it returns. Only radios switched "
            "off here are switched back on: one turned off by hand beforehand "
            "stays off.",
        )
        self.srow_net = Adw.ActionRow(title="Position", subtitle="…")
        self.srow_net.set_subtitle_selectable(True)
        net.add(self.srow_net)
        # Shown as a switch like the other two, but fixed on: the Android side
        # stops the RIL before any program here learns the slider moved. The
        # only way to "deselect" it would be to start the modem back up behind
        # the switch - undermining the very thing somebody flipped it for.
        self.sw_modem = Adw.SwitchRow(
            title="Turn off the mobile network",
            subtitle="always on - the switch itself does this, in firmware, "
            "and it cannot be opted out of",
            active=True,
        )
        self.sw_modem.set_sensitive(False)
        net.add(self.sw_modem)
        self.sw_wifi = Adw.SwitchRow(
            title="Turn off Wi-Fi as well",
            subtitle="reading …",
        )
        self.sw_wifi.connect("notify::active", self.on_extra_wifi)
        net.add(self.sw_wifi)
        self.sw_bt = Adw.SwitchRow(
            title="Turn off Bluetooth as well",
            subtitle="reading …",
        )
        self.sw_bt.connect("notify::active", self.on_extra_bt)
        net.add(self.sw_bt)
        spage.add(net)

        mic = Adw.PreferencesGroup(
            title="3 · Microphone",
            description="Cuts the BUILT-IN microphones - measured: the level "
            "drops by 37.8 dB and what is left is the converter's own noise. "
            "A headset brings its own microphone along a path of its own, over "
            "Bluetooth or the jack, and this switch is not in that path (not "
            "verified here - ask and it can be measured with a headset "
            "connected).\n\n"
            "It cannot be switched from software, and its position cannot be "
            "read either. It is the only one of the three that physically cuts "
            "the line, and that is exactly why the system cannot see it: a "
            "built-in microphone is not a device that announces itself, it is "
            "an analogue line into a codec input. Engaged against free, 2337 "
            "lines of GPIOs, properties, ALSA controls and jack states came "
            "back identical.",
        )
        self.srow_mic = Adw.ActionRow(title="Last measurement", subtitle="…")
        self.srow_mic.set_subtitle_selectable(True)
        mic.add(self.srow_mic)
        self.mic_button = Gtk.Button(label="Listen now")
        self.mic_button.set_margin_top(6)
        self.mic_button.set_margin_bottom(6)
        self.mic_button.set_halign(Gtk.Align.CENTER)
        self.mic_button.connect("clicked", self.on_mic_check)
        mic.add(self.mic_button)
        spage.add(mic)

        self.sw_rows = [self.sw_row, self.sw_persist, self.sw_wifi, self.sw_bt]
        return spage

    def on_switches_status(self, ok, out):
        if not ok:
            for row in (self.srow_cam, self.srow_net):
                row.set_subtitle("killswitch-indicator did not answer")
            return
        try:
            data = json.loads(out)
        except ValueError:
            self.srow_cam.set_subtitle("unreadable answer")
            return

        def stellung(value):
            return {"0": "engaged", "1": "free"}.get(value, "unknown")

        self.srow_cam.set_subtitle(stellung(data.get("switches", {}).get("cam_switch")))
        self.srow_net.set_subtitle(stellung(data.get("switches", {}).get("nwk_switch")))

        hal = data.get("camera_hal")
        self.srow_cam_hal.set_subtitle(
            "running" if hal else "stopped" if hal is False else "unknown")

        cams = data.get("cameras")
        if cams:
            seiten = ", ".join(c.lower() for c in cams)
            self.srow_cams.set_subtitle(f"all {len(cams)} ({seiten}) - never one alone")
        else:
            self.srow_cams.set_subtitle(
                "all of them - list not fetched yet "
                "(sudo killswitch-indicator cameras --refresh)")

        extras = data.get("network_extras", {})
        radios = data.get("radios", {})
        self._loading = True
        self.sw_wifi.set_active(bool(extras.get("wifi")))
        self.sw_bt.set_active(bool(extras.get("bluetooth")))
        self._loading = False
        for row, key in ((self.sw_wifi, "wifi"), (self.sw_bt, "bluetooth")):
            zustand = radios.get(key)
            row.set_subtitle("currently on" if zustand else
                             "currently off" if zustand is False else "not reachable")

        mic = data.get("mic")
        if not mic:
            self.srow_mic.set_subtitle("not measured yet")
        else:
            when = GLib.DateTime.new_from_unix_local(mic.get("when", 0))
            # The tool speaks German, this window does not.
            urteil = {"GESPERRT": "engaged", "frei": "free",
                      "unbrauchbar": "unusable"}.get(mic.get("verdict"),
                                                     mic.get("verdict", "?"))
            self.srow_mic.set_subtitle(
                f"{urteil} - median {mic.get('median')} "
                f"at {when.format('%H:%M')} ({mic.get('reason', '?')})")

    def on_indicator_active(self, ok, out):
        aktiv = ok and out.strip() == "active"
        self._loading = True
        self.sw_row.set_active(aktiv)
        self._loading = False
        self.sw_row.set_subtitle("running" if aktiv else "not running")

    def on_indicator_enabled(self, ok, out):
        self._loading = True
        self.sw_persist.set_active(ok and out.strip() == "enabled")
        self._loading = False

    def on_indicator_switch(self, row, _param):
        if getattr(self, "_loading", False):
            return
        verb = "start" if row.get_active() else "stop"
        run_async(["systemctl", "--user", verb, "killswitch-indicator"],
                  lambda ok, out: self.after_indicator(ok, out, verb))

    def after_indicator(self, ok, out, verb):
        if not ok:
            self.toasts.add_toast(Adw.Toast(title=f"Could not {verb} the indicator"))
        self.refresh()

    def on_indicator_persist(self, row, _param):
        if getattr(self, "_loading", False):
            return
        verb = "enable" if row.get_active() else "disable"
        run_async(["systemctl", "--user", verb, "killswitch-indicator"],
                  lambda ok, out: self.after_indicator(ok, out, verb))

    def on_extra_wifi(self, row, _param):
        self.set_extra("wifi", row)

    def on_extra_bt(self, row, _param):
        self.set_extra("bluetooth", row)

    def set_extra(self, radio, row):
        if getattr(self, "_loading", False):
            return
        wert = "on" if row.get_active() else "off"
        run_async([KILLSWITCH, "config", radio, wert],
                  lambda ok, out: self.after_extra(ok, radio, wert))

    def after_extra(self, ok, radio, wert):
        if not ok:
            self.toasts.add_toast(Adw.Toast(title=f"Could not change {radio}"))
            self.refresh()
            return
        if wert == "on":
            self.toasts.add_toast(Adw.Toast(
                title=f"{radio} will go off with the network switch"))

    def on_mic_check(self, _button):
        self.mic_button.set_sensitive(False)
        self.mic_button.set_label("listening …")
        self.srow_mic.set_subtitle("recording three seconds …")
        run_async([KILLSWITCH, "mic-check"], self.after_mic_check, timeout=30)

    def after_mic_check(self, ok, out):
        self.mic_button.set_sensitive(True)
        self.mic_button.set_label("Listen now")
        if not ok:
            self.srow_mic.set_subtitle("measurement failed")
            return
        zeilen = [z.strip() for z in out.splitlines() if z.strip()]
        urteil = next((z for z in zeilen if z.startswith("Mikrofon:")), "")
        werte = next((z for z in zeilen if z.startswith("Median")), "")
        urteil = urteil.replace("Mikrofon:", "").strip()
        urteil = {"GESPERRT": "engaged", "frei": "free"}.get(urteil, urteil)
        self.srow_mic.set_subtitle(f"{urteil} - {werte}" if werte else urteil)

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

        # The counterpart to "Restore sound" on the audio page, and named for
        # what it does rather than for rescue: taking the repairs out is a way
        # back to the phone as it came, not a way out of trouble. The audio
        # button restores something audible; this one takes function away, so
        # it says so and is styled as the destructive thing it is.
        back = Adw.PreferencesGroup(
            title="Back to how it shipped",
            description="Takes every repair out, restarts the modem stack and "
            "remembers it. With Wi-Fi off there is then no route out and no "
            "name resolution.",
        )
        self.modem_restore_btn = Gtk.Button(label="Restore shipped state")
        self.modem_restore_btn.add_css_class("pill")
        self.modem_restore_btn.add_css_class("destructive-action")
        self.modem_restore_btn.set_halign(Gtk.Align.CENTER)
        self.modem_restore_btn.set_margin_top(6)
        self.modem_restore_btn.set_margin_bottom(6)
        self.modem_restore_btn.connect("clicked", self.on_modem_restore)
        back.add(self.modem_restore_btn)
        mpage.add(back)

        self.modem_rows = [self.modem_row, self.modem_persist,
                           self.modem_restore_btn]
        return mpage

    # ------------------------------------------------------------ GPS

    def build_gps_page(self):
        """Where the phone says it is.

        The same question as the other two pages - as shipped, or repaired -
        but the "off" side is the one that needs explaining here. Off does not
        mean "no location". It means geoclue publishes the position of the
        carrier's exit node as though the phone had been observed there.
        """
        gpage = Adw.PreferencesPage()

        grp = Adw.PreferencesGroup(
            title="Location",
            description="Off is FuriOS as it came: asked where it is with no "
            "Wi-Fi it recognises, the service answers with the position of "
            "this phone's IP address - on mobile data the carrier's exit node, "
            "tens of kilometres away - and geoclue passes it on as a position "
            "like any other.",
        )
        self.gps_row = Adw.SwitchRow(
            title="Filter active",
            subtitle="reading …",
        )
        self.gps_row.connect("notify::active", self.on_gps_switch)
        grp.add(self.gps_row)

        self.gps_persist = Adw.SwitchRow(
            title="Remember this choice",
            subtitle="Off: the next boot returns to what was recorded",
            active=True,
        )
        grp.add(self.gps_persist)

        self.gps_progress = Gtk.ProgressBar(show_text=True, text="")
        for m in ("top", "bottom"):
            getattr(self.gps_progress, "set_margin_" + m)(6)
        for m in ("start", "end"):
            getattr(self.gps_progress, "set_margin_" + m)(12)
        self.gps_revealer = Gtk.Revealer(
            child=self.gps_progress,
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            reveal_child=False,
        )
        grp.add(self.gps_revealer)
        gpage.add(grp)

        info = Adw.PreferencesGroup(title="Status")
        self.grow_profile = Adw.ActionRow(title="Profile", subtitle="…")
        self.grow_seen = Adw.ActionRow(title="Since this boot", subtitle="…")
        self.grow_health = Adw.ActionRow(title="Checks", subtitle="…")
        for row in (self.grow_profile, self.grow_seen, self.grow_health):
            row.set_subtitle_selectable(True)
            info.add(row)
        gpage.add(info)

        # No second button to turn this off with. On the other two pages the
        # way back restores something - sound, a working network - and is worth
        # its own control. Here the way back is the switch above, and a button
        # that did the same thing would only be a second way to arrive at the
        # carrier's IP address.
        self.gps_rows = [self.gps_row, self.gps_persist]
        return gpage

    def on_gps_profile(self, ok, out):
        """gpsctl prints the profile and *then* fails, when the two halves of
        the state disagree - the switch is "mixed" and it exits 1 to say so.

        So the return code is not what decides whether there was an answer.
        Reading it that way would turn the one state a person most needs to see
        into "gpsctl did not answer", on a phone where gpsctl answered
        perfectly well and had something important to report.
        """
        found = self._keyed(out)
        recorded, actual = found.get("recorded"), found.get("actual")
        if not recorded or not actual:
            self.gps_ok = False
            self.gps_row.set_sensitive(False)
            self.grow_profile.set_subtitle("gpsctl did not answer")
            return
        self.gps_ok = True

        if actual == "fixed":
            words = "IP positions are thrown away"
        elif actual == "shipped":
            words = "FuriOS as it came - the IP position is published"
        else:
            words = "half applied - use \"Filter active\" to settle it"
        if recorded != actual and actual in ("fixed", "shipped"):
            words += f" · not remembered, the next boot returns to \"{recorded}\""
        self.grow_profile.set_subtitle(words)

        self._syncing = True
        self.gps_row.set_active(actual == "fixed")
        self.gps_persist.set_active(recorded == actual)
        self._syncing = False
        self.gps_row.set_subtitle(
            "On: a position that is really just this phone's IP address is refused"
            if actual == "fixed"
            else "Off: the carrier's exit node is published as a position"
        )

    def on_gps_status(self, ok, out):
        if not out:
            self.grow_health.set_subtitle("gpsctl did not answer")
            self.grow_seen.set_subtitle("nothing to count")
            return
        bad = sum(1 for line in out.splitlines() if "FAIL" in line)
        good = sum(1 for line in out.splitlines() if " ok " in line)
        self.grow_health.set_subtitle(
            f"{good} in place" if bad == 0 else f"{good} in place, {bad} not"
        )
        # "since boot: 5 asked, 0 located, 5 IP fallbacks rejected" - said back
        # as it was printed. Counting nothing is a normal state and reads as one
        # on a phone that has not asked yet, so it is not dressed up as a fault.
        for line in out.splitlines():
            if line.strip().startswith("since boot:"):
                self.grow_seen.set_subtitle(line.split(":", 1)[1].strip())
                break
        else:
            self.grow_seen.set_subtitle("nothing counted yet")

    def on_gps_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        if not PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        mode = "set" if self.gps_persist.get_active() else "try"
        want = "fixed" if row.get_active() else "shipped"
        self.set_busy(True)
        self.gps_progress.set_text("Switching …")
        self.gps_revealer.set_reveal_child(True)
        self.pulse_start("Switching the location filter …")
        run_async([PKEXEC, GPSCTL, mode, want], self.on_gps_switched,
                  on_line=self.on_progress_line)

    def on_gps_switched(self, ok, out):
        self.pulse_stop()
        self.gps_revealer.set_reveal_child(False)
        if not ok:
            self.toast("Switching the location filter failed")
            self.report(out or "No output.")
        elif not self.gps_row.get_active():
            # Not a neutral "done": the switch has just been turned off, and
            # what that means is the thing somebody should be told.
            self.toast("Filter off - the IP position is published again")
        else:
            self.toast("Filter on - IP positions are refused")
        self.refresh()

    # ------------------------------------------------------------ Zustand

    def refresh(self):
        run_async([AUDIOCTL, "status"], self.on_status)
        run_async([DMNR, "status"], self.on_dmnr_status)
        if MODEMCTL:
            # Both read-only, and neither needs root - which is the whole
            # reason the page can show something before anybody touches it.
            run_async([MODEMCTL, "profile"], self.on_modem_profile)
            run_async([MODEMCTL, "status"], self.on_modem_status)
        if GPSCTL:
            run_async([GPSCTL, "profile"], self.on_gps_profile)
            run_async([GPSCTL, "status"], self.on_gps_status)
        if KILLSWITCH:
            run_async([KILLSWITCH, "status", "--json"], self.on_switches_status)
            run_async(["systemctl", "--user", "is-active",
                       "killswitch-indicator"], self.on_indicator_active)
            run_async(["systemctl", "--user", "is-enabled",
                       "killswitch-indicator"], self.on_indicator_enabled)

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
            self.modem_ok = False
            self.modem_row.set_sensitive(False)
            self.mrow_profile.set_subtitle("modemctl did not answer")
            return
        self.modem_ok = True
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

    def on_modem_restore(self, _btn):
        if self.busy:
            return
        if not PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        self.set_busy(True)
        self.modem_progress.set_text("Restoring …")
        self.modem_revealer.set_reveal_child(True)
        self.pulse_start("Back to the shipped state …")
        # "set", not "try": the same promise the audio button makes - what it
        # restores is what the phone comes back to. And the same command a
        # person would type, so there is one truth about what this does.
        run_async([PKEXEC, MODEMCTL, "set", "shipped"], self.on_modem_restored,
                  on_line=self.on_progress_line)

    def on_modem_restored(self, ok, out):
        self.pulse_stop()
        self.modem_revealer.set_reveal_child(False)
        if ok:
            self.toast("Shipped state - no network without Wi-Fi")
        else:
            self.toast("Could not restore the shipped state")
            self.report(out or "No output.")
        self.refresh()

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
            self.dmnr_ok = False
            self.dmnr_row.set_sensitive(False)
            self.dmnr_row.set_subtitle("not available on this device")
            return
        self.dmnr_ok = True
        on = "state=on" in out
        self._syncing = True
        self.dmnr_row.set_active(on)
        self._syncing = False
        self.dmnr_row.set_subtitle(
            "On - modified tuning file in place" if on else "Vendor setting: off"
        )

    def on_status(self, ok, out):
        profile, persistent, server, sinks = "unknown", "unknown", "-", "-"
        warn = None
        testmode = False
        for line in out.splitlines():
            if line.startswith("Profile (active):"):
                profile = line.split(":", 1)[1].strip()
            elif line.startswith("Profile (persistent):"):
                persistent = line.split(":", 1)[1].strip()
            elif line.startswith("WARNING:"):
                warn = line.split(":", 1)[1].strip()
            elif line.startswith("Test mode:"):
                testmode = line.split(":", 1)[1].strip().startswith("yes")
            elif line.startswith("Pulse server:"):
                server = line.split(":", 1)[1].strip()
            elif line.startswith("Sinks:"):
                sinks = line.split(":", 1)[1].strip()

        # What survives a reboot is not what is running: audioctl keeps both,
        # and "try" changes only the first of them. Showing one and calling it
        # the state is how this window claimed the shipped stack was set while
        # the phone had been on pw-hal permanently for two days.
        sticks = profile != "unknown" and persistent == profile and not testmode

        # Nothing came back that names a profile: say that, and leave both
        # switches where they are. Showing them off would be a statement about
        # a phone this window knows nothing about - and "off" happens to be
        # the shipped state, so it would be a plausible, wrong one.
        self.audio_ok = profile != "unknown"
        if not self.audio_ok:
            self.row_profile.set_subtitle("audioctl did not answer")
            self.row_server.set_subtitle(server_in_words(server))
            self.row_sinks.set_subtitle(sinks.replace(",", ", ") or "none")
            self.persist_row.set_subtitle("audioctl did not answer")
            self.set_busy(False)
            return

        text = profile_in_words(profile)
        if persistent == "unknown":
            pass
        elif sticks:
            text += " - permanent"
        else:
            text += f" - until the next reboot, then {profile_in_words(persistent)}"
        if warn:
            text += f" | {warn}"
        self.row_profile.set_subtitle(text)
        self.row_server.set_subtitle(server_in_words(server))
        self.row_sinks.set_subtitle(sinks.replace(",", ", ") or "none")

        # Schalter nachfuehren, ohne dabei ein Umschalten auszuloesen.
        self._syncing = True
        self.switch_row.set_active(profile == "pw-hal")
        # This one is both a report and a choice: it says whether what is
        # running now is what the phone comes back to, and it decides between
        # "set" and "try" for the next switch.
        self.persist_row.set_active(sticks)
        self._syncing = False
        if persistent == "unknown":
            self.persist_row.set_subtitle("Off: a reboot returns to the shipped state")
        elif sticks:
            self.persist_row.set_subtitle("On: this is what the phone comes back to")
        else:
            self.persist_row.set_subtitle(
                f"Off: a reboot returns to {profile_in_words(persistent)}"
            )
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
        self.switch_row.set_sensitive(not busy and self.audio_ok)
        self.persist_row.set_sensitive(not busy and self.audio_ok)
        self.dmnr_row.set_sensitive(not busy and self.dmnr_ok)
        self.refresh_btn.set_sensitive(not busy)
        # Empty when there is no modem page, which is the point: nothing here
        # may assume the second page exists.
        for row in self.modem_rows:
            row.set_sensitive(not busy and self.modem_ok)
        for row in self.gps_rows:
            row.set_sensitive(not busy and self.gps_ok)
        if busy:
            self.switch_row.set_subtitle("Switching, this takes a moment …")
        elif not self.audio_ok:
            self.switch_row.set_subtitle("audioctl did not answer")
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
