#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""A small switch for the FuriPhone's audio stack.

One switch: PipeWire talks directly to the Android HAL - or it does not, and
then PulseAudio holds it the way the device shipped. audioctl does the work;
this front end only calls it and shows what is actually running.

Deliberately plain: on a phone you want a button, not a control room.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

# The password dialog is ours, because nothing else on this phone shows one.
#
# Switching the stack masks system units and writes a systemd drop-in, so it
# needs root. audioctl asks for that through pkexec, and pkexec asks polkit,
# and polkit asks whatever authentication agent the session has registered -
# and phosh registers none. Without an agent every polkit action on this device
# fails with "No authentication agent found", ours included.
#
# So the app brings one, for as long as it is open. Missing bindings, no
# session, an older polkit: all of that has to come out as "no agent" rather
# than as a traceback, because an app that will not start is worse than one
# that tells you to use the terminal.
try:
    gi.require_version("Polkit", "1.0")
    gi.require_version("PolkitAgent", "1.0")
    from gi.repository import Polkit, PolkitAgent  # noqa: E402

    HAVE_POLKIT = True
except (ValueError, ImportError):  # pragma: no cover - depends on the system
    HAVE_POLKIT = False

APP_ID = "de.furios.audioswitch"
AGENT_PATH = "/de/furios/audioswitch/AuthenticationAgent"
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


AUDIOCTL = _tool("audioctl")
DMNR = _tool("furios-audio-dmnr")


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

    def note_no_agent(self):
        """Said once, when nobody can show a password prompt.

        Without an agent pkexec refuses outright, so a switch would fail with
        nothing on screen to explain it. In a terminal pkexec brings its own
        prompt, which is why that still works.
        """
        self.toast("No password prompt available - switch from a terminal")

    def report(self, text):
        dlg = Adw.AlertDialog(heading="Something went wrong", body=text)
        dlg.add_response("ok", "Got it")
        dlg.present(self)


# --------------------------------------------------------- the password dialog

class PasswordAgent(PolkitAgent.Listener if HAVE_POLKIT else object):
    """A polkit authentication agent, for as long as this app is open.

    polkit does not want a password - it wants a PAM conversation carried out
    on behalf of one of the identities it will accept. PolkitAgent.Session does
    the talking; what is left here is to show the prompt it asks for, hand back
    what was typed, and make sure every path ends with the session finished and
    the dialog gone.
    """

    def __init__(self, window):
        super().__init__()
        self.window = window
        self.handle = None
        self.session = None
        self.dialog = None
        self.task = None

    # --- registration -------------------------------------------------------

    def register(self):
        """Take over authentication for this session. False if that is not on."""
        if not HAVE_POLKIT:
            return False
        try:
            subject = Polkit.UnixSession.new_for_process_sync(os.getpid(), None)
            self.handle = PolkitAgent.register_listener(
                self, subject, AGENT_PATH, None)
        except Exception:
            self.handle = None
        return self.handle is not None

    def unregister(self):
        if self.handle is None:
            return
        try:
            PolkitAgent.unregister_listener(self.handle)
        except Exception:
            pass
        self.handle = None

    # --- the identity polkit will accept ------------------------------------

    @staticmethod
    def pick_identity(identities):
        """Prefer the user who is sitting here; otherwise take what is offered.

        polkit hands over everyone it would accept - for auth_admin that is
        every administrator on the system. Asking the owner of the phone for
        somebody else's password would be absurd, so our own uid wins when it
        is in the list.
        """
        if not identities:
            return None
        try:
            me = os.getuid()
            for identity in identities:
                if identity.get_uid() == me:
                    return identity
        except Exception:
            pass
        return identities[0]

    # --- the conversation ---------------------------------------------------

    def do_initiate_authentication(self, action_id, message, icon_name, details,
                                   cookie, identities, cancellable,
                                   callback, user_data=None):
        self.task = Gio.Task.new(self, cancellable, callback, user_data)

        identity = self.pick_identity(identities)
        if identity is None:
            self.finish()
            return

        self.session = PolkitAgent.Session.new(identity, cookie)
        self.session.connect("request", self.on_request)
        self.session.connect("completed", self.on_completed)
        self.session.connect("show-error", self.on_show_message)
        self.session.connect("show-info", self.on_show_message)
        self.show_dialog(message)
        self.session.initiate()

    def do_initiate_authentication_finish(self, result):
        return True

    def finish(self):
        """End the request, whichever way it went. Safe to call twice."""
        self.close_dialog()
        self.session = None
        task, self.task = self.task, None
        if task is not None:
            task.return_boolean(True)

    # --- what the user sees -------------------------------------------------

    def show_dialog(self, message):
        self.entry = Gtk.PasswordEntry(show_peek_icon=True)
        self.entry.set_property("activates-default", True)
        self.dialog = Adw.MessageDialog(
            transient_for=self.window,
            heading="Authentication required",
            body=message or "Authentication is required",
            extra_child=self.entry,
        )
        self.dialog.add_response("cancel", "Cancel")
        self.dialog.add_response("ok", "Authenticate")
        self.dialog.set_default_response("ok")
        self.dialog.set_close_response("cancel")
        self.dialog.connect("response", self.on_response)
        self.dialog.present()

    def close_dialog(self):
        dialog, self.dialog = self.dialog, None
        if dialog is not None:
            dialog.close()

    def on_response(self, dialog, response):
        self.dialog = None
        if response == "ok" and self.session is not None:
            self.session.response(self.entry.get_text())
            return
        # Cancelled: polkit has to hear that, or the request stays open.
        if self.session is not None:
            self.session.cancel()
        else:
            self.finish()

    # --- signals from the session -------------------------------------------

    def on_request(self, session, prompt, echo_on):
        """PAM wants something. Usually the password, sometimes a second one."""
        if self.dialog is None:
            self.show_dialog(prompt)

    def on_completed(self, session, gained_authorization):
        self.finish()

    def on_show_message(self, session, text):
        if self.dialog is not None:
            self.dialog.set_body(text)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)
        self.agent = None

    def do_activate(self):
        win = self.props.active_window or Window(self)
        win.present()
        if self.agent is None:
            self.agent = PasswordAgent(win)
            if not self.agent.register():
                # No prompt is possible, so say so once rather than let a
                # switch fail with nothing on screen.
                win.note_no_agent()

    def do_shutdown(self):
        if self.agent is not None:
            self.agent.unregister()
            self.agent = None
        Adw.Application.do_shutdown(self)


if __name__ == "__main__":
    import sys

    sys.exit(App().run(sys.argv))
