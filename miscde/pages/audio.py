# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Audio page: who owns the Android HAL.

The page itself is built in window.py with the rest of the window -
it is the one tab that exists before any tool is found. What lives
here is everything that happens after somebody touches it."""

from gi.repository import Adw

from .. import askpass, components, process, tools
from ..tools import DMNR
from ..words import profile_in_words, server_in_words


# batman, the battery manager that ships with the phone, keeps its settings
# here as plain KEY=value lines. BTSAVE is the one that decides whether the
# Bluetooth adapter is switched off along with the screen.
BATMAN_CONFIG = "/var/lib/batman/config"
BATMAN_UNIT = "batman.service"

# Everything it works on comes in as an argument: the file as $1, the unit as
# $2, the value as $3. Not for quoting's sake - all three are ours - but so
# the script can be run against a scratch file in a test. A script that names
# /var/lib/batman/config in its own text can only ever be read, not checked.
# `sed` over the existing line, append when the key is missing; batman reads
# this file at startup only, hence the restart.
BTSAVE_SCRIPT = (
    'set -e\n'
    'if grep -q "^BTSAVE=" "$1"; then\n'
    '  sed -i "s/^BTSAVE=.*/BTSAVE=$3/" "$1"\n'
    'else\n'
    '  printf "BTSAVE=%s\\n" "$3" >> "$1"\n'
    'fi\n'
    'systemctl restart "$2"\n'
)


def btsave_in_config(text):
    """Whether batman is set to power the adapter down.

    None when the key is not in the file at all, which is a different thing
    from "off" and is shown as such: an unknown setting must not be drawn as
    a switch that is merely not on."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("BTSAVE="):
            return line.split("=", 1)[1].strip().lower() == "true"
    return None


def btsave_argv(wanted, secret=None):
    """The one command that changes it, with or without a password.

    Without a secret this is `sudo -n`: on a phone whose sudoers asks for
    nothing, the switch just works and nobody is shown a password box for a
    single config line. When sudo does want one, the caller asks and comes
    back through here with it - `-S` reads it from the pipe, `-p ""` keeps
    sudo's prompt out of the window's own output."""
    value = "true" if wanted else "false"
    front = (["sudo", "-S", "-p", ""] if secret is not None
             else ["sudo", "-n"])
    return front + ["sh", "-c", BTSAVE_SCRIPT, "sh",
                    BATMAN_CONFIG, BATMAN_UNIT, value]


def needs_a_password(out):
    """sudo -n turning the job down, told apart from the job failing.

    sudo says "a password is required" (or, in older versions, "no tty
    present and no askpass program specified"). Either way the answer is to
    ask, not to report a broken switch."""
    low = (out or "").lower()
    return "password is required" in low or "askpass" in low


class AudioPage:
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
        # The tool reports both, because one cannot be read off the other:
        # switched on now and not remembered looks identical until the reboot.
        remembered = "persistent=yes" in out
        if on:
            self.dmnr_row.set_subtitle(
                "On, remembered" if remembered else "On until the next reboot")
        else:
            self.dmnr_row.set_subtitle(
                "Off, and stays off" if not remembered else
                "Off now - but comes back at the next reboot")

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
            self.set_busy(self.busy)
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

        # Follow the switch without triggering a toggle while doing it.
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
        # Re-applied, not released. This answer arrives from every refresh,
        # and refreshes run while other things are in flight - a battery
        # change, the first one at start-up - so releasing here handed the
        # controls back in the middle of a modem switch or an install, and a
        # second tap started a second pkexec beside the first. And on a phone
        # without audioctl it never arrived at all, so every other page's
        # switch left the window grey for good. Whoever set busy releases it.
        self.set_busy(self.busy)


    def on_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        want_pw = row.get_active()
        mode = "set" if self.persist_row.get_active() else "try"
        audioctl = self.live["audio"]
        argv = ([audioctl, mode, "pw-hal"] if want_pw
                else [audioctl, "set", "standard"])
        self.set_busy(True)
        self.pulse_start("Switching …")
        process.run_async(argv, self.on_switched, on_line=self.on_progress_line)

    def on_switched(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
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
        # The same reading of the persist switch as the stack switch above:
        # "set" is now and after the next reboot, the bare word is now only.
        wanted = "on" if row.get_active() else "off"
        self._dmnr_args = (["set", wanted] if self.persist_row.get_active()
                           else [wanted])
        self.apply_dmnr()

    def apply_dmnr(self, secret=None):
        """Run the helper, and with a password when sudo wants one.

        The helper is a script with its own sudo lines - bind mounts, the
        modem's tuning memory - and it runs as this user, not under sudo: it
        restarts the user's audio stack at the end, which root cannot reach.
        So there is no "sudo -S" in front of it to pipe a password into. On
        a phone whose sudoers asks for nothing that never mattered; with a
        password its first sudo had no terminal to ask at, and the switch
        failed. Same answer as the installers: the password goes to sudo
        through the askpass socket, never through argv or a file."""
        argv = [tools._tool_maybe(DMNR) or DMNR] + list(self._dmnr_args)
        env = None
        if secret is not None:
            self._dmnr_askpass = askpass.Askpass(secret)
            helper = self._dmnr_askpass.start()
            if helper is None:
                self.toast("no password helper: " +
                           str(self._dmnr_askpass.error))
                self._dmnr_askpass = None
                self.refresh()
                return
            env = components.installer_env(helper)
        self.set_busy(True)
        self.pulse_start("Switching echo suppression …")
        process.run_async(argv,
                          lambda ok, out: self.on_dmnr_done(
                              ok, out, asked=secret is not None),
                          on_line=self.on_progress_line, env=env)

    def on_dmnr_done(self, ok, out, asked=False):
        self.pulse_stop()
        self.set_busy(False)
        if getattr(self, "_dmnr_askpass", None) is not None:
            self._dmnr_askpass.stop()
            self._dmnr_askpass = None
        # The helper checks first whether sudo can be asked at all and stops
        # before changing anything, so this is a question, not a half-done
        # switch. Asked once: a wrong password is a failure to report.
        if not ok and not asked and needs_a_password(out):
            self.ask_dmnr_password()
            return
        if not ok:
            self.toast("Could not switch echo suppression")
            self.report(out or "No output.")
        else:
            self.toast("Echo suppression changed - try a call")
        self.refresh()

    def ask_dmnr_password(self):
        entry = Adw.PasswordEntryRow(title="Your password (for sudo)")
        group = Adw.PreferencesGroup()
        group.add(entry)
        dlg = Adw.AlertDialog(
            heading="Echo suppression",
            body="This lays tuning files over the vendor's and opens the "
                 "modem's tuning memory to the audio group, so sudo asks for "
                 "a password. It goes to sudo and nowhere else.")
        dlg.set_extra_child(group)
        dlg.add_response("go", "Switch")
        dlg.add_response("cancel", "Cancel")
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        self._dmnr_pending = entry
        dlg.connect("response", self.on_dmnr_password)
        dlg.present(self)

    def on_dmnr_password(self, _dlg, response):
        entry, self._dmnr_pending = self._dmnr_pending, None
        secret = entry.get_text() if entry is not None else None
        if entry is not None:
            entry.set_text("")               # not kept a moment longer
        if response != "go" or secret is None:
            # Cancelled: the row goes back to what the helper reports.
            self.refresh()
            return
        self.apply_dmnr(secret)

    def on_rescue(self, _btn):
        if self.busy:
            return
        self.set_busy(True)
        self.pulse_start("Restoring …")
        # The same recovery as on the command line - one truth, not two
        # versions that can drift apart.
        process.run_async([self.live["audio"], "rescue"], self.on_rescued,
                  on_line=self.on_progress_line)

    def on_rescued(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
        self.toast(
            "Shipped state, speaker, 65 %"
            if ok
            else "Restore failed"
        )
        if not ok:
            self.report(out or "No output.")
        self.refresh()

    # --- Bluetooth powersave ---
    #
    # Not part of the audio stack and not ours: batman, the battery manager
    # the phone ships with, powers the Bluetooth adapter DOWN when the screen
    # goes off and nothing is connected. It is on this page because that is
    # where somebody looking for "why is my headset silent" arrives - and
    # because the symptom is entirely an audio one: take the earbuds out of
    # their case with the screen dark and they page a controller that is not
    # there. Nothing happens until the phone is woken, and then the headset
    # is back in under a second. Measured on 16.9.2026 with btmon.

    @staticmethod
    def btsave_words(state):
        """What the switch says about itself, including "no idea"."""
        if state is None:
            return "batman is not installed - nothing powers the adapter down"
        if state:
            return ("On: the adapter goes off with the screen - a headset "
                    "cannot get back until the phone is woken")
        return "Off: the adapter stays on, a headset reconnects by itself"

    def sync_btsave(self):
        """Follow the config file, which is the only thing that decides this.

        Read here rather than through a helper: the file is world-readable
        and this is one line of it. It is also read again after every change,
        because a switch that reports what somebody just clicked, rather than
        what is in the file, is how this window once claimed a setting it had
        failed to write."""
        try:
            with open(BATMAN_CONFIG) as handle:
                state = btsave_in_config(handle.read())
        except OSError:
            state = None
        self.btsave_ok = state is not None
        self._syncing = True
        self.btsave_row.set_active(bool(state))
        self._syncing = False
        self.btsave_row.set_subtitle(self.btsave_words(state))
        self.btsave_row.set_sensitive(not self.busy and self.btsave_ok)

    def on_btsave(self, row, _param):
        if self._syncing or self.busy:
            return
        self.apply_btsave(row.get_active())

    def apply_btsave(self, wanted, secret=None):
        self.set_busy(True)
        self.pulse_start("Changing Bluetooth powersave …")
        process.run_async(
            btsave_argv(wanted, secret),
            lambda ok, out: self.on_btsave_done(ok, out, wanted),
            stdin=None if secret is None else (secret + "\n"))

    def on_btsave_done(self, ok, out, wanted):
        self.pulse_stop()
        self.set_busy(False)
        # A password being wanted is not a failure - it is the one answer
        # this switch can do something about, so it asks instead of reporting.
        if not ok and needs_a_password(out):
            self.ask_btsave_password(wanted)
            return
        if not ok:
            self.toast("Could not change Bluetooth powersave")
            self.report(out or "No output.")
        else:
            self.toast("Bluetooth powersave " + ("on" if wanted else "off"))
        self.sync_btsave()

    def ask_btsave_password(self, wanted):
        entry = Adw.PasswordEntryRow(title="Your password (for sudo)")
        group = Adw.PreferencesGroup()
        group.add(entry)
        dlg = Adw.AlertDialog(
            heading="Bluetooth powersave",
            body="This changes one line in batman's config and restarts it, "
                 "so sudo asks for a password. It goes to sudo through a "
                 "pipe and nowhere else.")
        dlg.set_extra_child(group)
        dlg.add_response("go", "Change it")
        dlg.add_response("cancel", "Cancel")
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        self._btsave_pending = (wanted, entry)
        dlg.connect("response", self.on_btsave_password)
        dlg.present(self)

    def on_btsave_password(self, _dlg, response):
        wanted, entry = self._btsave_pending
        self._btsave_pending = (None, None)
        secret = entry.get_text() if entry is not None else None
        if entry is not None:
            entry.set_text("")               # not kept a moment longer
        if response != "go" or wanted is None:
            # Cancelled: the switch goes back to what the file says, not to
            # what the finger left it at.
            self.sync_btsave()
            return
        self.apply_btsave(wanted, secret)

    def run_chain(self, commands, done):
        """Run several commands one after another, stopping at the first that
        fails. The last output seen is what `done` is handed, because that is
        the one worth showing."""
        rest = list(commands)

        def step(ok=True, out=""):
            if not ok or not rest:
                done(ok, out)
                return
            process.run_async(rest.pop(0), step)

        step()
