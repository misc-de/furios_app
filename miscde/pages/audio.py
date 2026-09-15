# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Audio page: who owns the Android HAL.

The page itself is built in window.py with the rest of the window -
it is the one tab that exists before any tool is found. What lives
here is everything that happens after somebody touches it."""

from .. import process, tools
from ..tools import DMNR
from ..words import profile_in_words, server_in_words


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
        self.set_busy(False)


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
        # The same reading of the persist switch as the stack switch above:
        # "set" is now and after the next reboot, the bare word is now only.
        wanted = "on" if row.get_active() else "off"
        argv = [tools._tool_maybe(DMNR) or DMNR]
        argv += ["set", wanted] if self.persist_row.get_active() else [wanted]
        process.run_async(argv, self.on_dmnr_done, on_line=self.on_progress_line)

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
        process.run_async([self.live["audio"], "rescue"], self.on_rescued,
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
