# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Modem page: the repairs to ofono2mm and ModemManager."""

from gi.repository import Adw, Gtk

from .. import process, tools


class ModemPage:
    def build_modem_page(self):
        """The same shape as the audio page, because it is the same question:
        the phone as it shipped, or the phone as somebody repaired it."""
        mpage = Adw.PreferencesPage()

        # No paragraph under the heading. It was the last one left, and it
        # showed: a group with a description puts its title higher than a
        # group without one, so this page's heading sat twelve pixels above
        # the heading of every other tab. What it said is in the row below
        # ("Off: the state the phone shipped in") and, in full, at the foot of
        # the page under "Back to how it shipped".
        grp = Adw.PreferencesGroup(title="Modem")
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

        # What it costs here is the opposite of the audio page: that one
        # brings something back, this one takes function away. Same button,
        # and the description carries the difference.
        back, self.modem_restore_btn = self.build_restore_group(
            "Takes every repair out, restarts the modem stack and remembers "
            "it. With Wi-Fi off there is then no route out and no name "
            "resolution.",
            self.on_modem_restore)
        mpage.add(back)

        self.modem_rows = [self.modem_row, self.modem_persist,
                           self.modem_restore_btn]
        return mpage


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
            else "Off: as it shipped - no route and no resolver without Wi-Fi"
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
        if not tools.PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        mode = "set" if self.modem_persist.get_active() else "try"
        want = "fixed" if row.get_active() else "shipped"
        self.set_busy(True)
        self.modem_progress.set_text("Switching …")
        self.modem_revealer.set_reveal_child(True)
        self.pulse_start("Switching the modem …")
        process.run_async([tools.PKEXEC, self.live["modem"], mode, want], self.on_modem_switched,
                  on_line=self.on_progress_line)

    def on_modem_restore(self, _btn):
        if self.busy:
            return
        if not tools.PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        self.set_busy(True)
        self.modem_progress.set_text("Restoring …")
        self.modem_revealer.set_reveal_child(True)
        self.pulse_start("Back to the shipped state …")
        # "set", not "try": the same promise the audio button makes - what it
        # restores is what the phone comes back to. And the same command a
        # person would type, so there is one truth about what this does.
        process.run_async([tools.PKEXEC, self.live["modem"], "set", "shipped"], self.on_modem_restored,
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
