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

        # Which SIM. Shown on every phone with two slots, also with one card
        # in: the option should be findable before anybody needs it. It can
        # only be used when there is somewhere to go - two cards, or a way
        # back from a slot whose card came out. A list rather than a switch,
        # because the slots have numbers, not an on and an off. Always
        # remembered - a SIM that went back at the next boot would be a
        # surprise, not a try.
        self.sim_group = Adw.PreferencesGroup(title="SIM")
        self.sim_row = Adw.ComboRow(
            title="Active SIM",
            subtitle="reading …",
            model=Gtk.StringList.new(["SIM 1", "SIM 2"]),
        )
        self.sim_ok = False
        self.sim_row.set_sensitive(False)
        self.sim_row.connect("notify::selected", self.on_sim_select)
        self._sim_labels = ["SIM 1", "SIM 2"]
        self._sim_present = []
        self._sim_active = 1
        self.sim_group.add(self.sim_row)
        self.sim_group.set_visible(False)
        mpage.add(self.sim_group)

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

        self.modem_rows = [self.modem_row, self.modem_restore_btn]
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
        """modemctl prints both lines and THEN exits 1 when the repairs are
        half in place ("mixed") - the same contract gpsctl had, and the
        same answer: whether there was a reading is decided by the reading.
        Going by the exit code turned the one state this row has words for
        ("use Repairs active to settle it") into "modemctl did not answer",
        with the switch that settles it locked."""
        found = self._keyed(out)
        recorded, actual = found.get("recorded"), found.get("actual")
        if not recorded or not actual:
            self.modem_ok = False
            self.modem_row.set_sensitive(False)
            self.mrow_profile.set_subtitle("modemctl did not answer")
            return
        self.modem_ok = True

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
        # Always "set": the repairs are what makes mobile data work, and a
        # switch that quietly fell back at the next boot was one more thing
        # to remember. There is no "remember" row any more (28.9.); a try is
        # still there for the command line.
        mode = "set"
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
        self.set_busy(False)
        self.modem_revealer.set_reveal_child(False)
        if ok:
            self.toast("Shipped state - no network without Wi-Fi")
        else:
            self.toast("Could not restore the shipped state")
            self.report(out or "No output.")
        self.refresh()

    def on_modem_switched(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
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

    # --- which SIM ---------------------------------------------------------

    @staticmethod
    def sim_labels(present, names):
        """"SIM 1 · Willkommen", "SIM 2 · no card". The name is what the card
        calls itself, or what modemctl remembered or looked up for it - there
        is none for a locked card never used here, and then the slot number
        has to do."""
        labels = []
        for n in (1, 2):
            if n not in present:
                labels.append(f"SIM {n} · no card")
            elif names.get(n):
                labels.append(f"SIM {n} · {names[n]}")
            else:
                labels.append(f"SIM {n}")
        return labels

    def on_sim_status(self, ok, out):
        """modemctl sim prints slots, active, recorded, present and a name per
        card. An older modemctl has no such command and answers with its
        usage - then there is no row, rather than a row that cannot do
        anything. Neither is there one on a phone with a single slot."""
        found = self._keyed(out or "")
        try:
            slots = int(found.get("slots", ""))
            active = int(found.get("active", ""))
        except ValueError:
            slots = active = 0
        if slots < 2 or active not in (1, 2):
            self.sim_ok = False
            self.sim_group.set_visible(False)
            return
        present = [int(p) for p in found.get("present", "").split()
                   if p.isdigit()]
        names = {n: found.get(f"name{n}", "") for n in (1, 2)}
        labels = self.sim_labels(present, names)

        # Usable with two cards, or when the active slot is empty and the
        # other one - with a card in it - is the way back. One card where it
        # belongs, or no card at all: shown, greyed.
        self._sim_present = present
        self._sim_active = active
        self.sim_ok = len(present) >= 2 or (active not in present and bool(present))
        self.sim_group.set_visible(True)
        self._syncing = True
        if labels != self._sim_labels:
            self.sim_row.set_model(Gtk.StringList.new(labels))
            self._sim_labels = labels
        self.sim_row.set_selected(active - 1)
        self._syncing = False
        if len(present) >= 2:
            words = "One at a time - both slots share one radio"
        elif not present:
            words = "No card detected - is the tray pushed all the way in?"
        elif active not in present:
            words = f"No card in slot {active} - pick the other one to get the network back"
        else:
            words = "Insert a second card to choose between them"
        self.sim_row.set_subtitle(words)
        self.sim_row.set_sensitive(self.sim_ok and not self.busy)

    def on_sim_select(self, row, _param):
        if self._syncing or self.busy or not self.sim_ok:
            return
        if not tools.PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        slot = row.get_selected() + 1
        # Nothing to do for the slot already in use, and never a switch to a
        # slot without a card - that is a phone without mobile network.
        # modemctl refuses that too; this keeps the list from even asking.
        if slot == self._sim_active:
            return
        if slot not in self._sim_present:
            self.toast(f"No card in slot {slot}")
            self._syncing = True
            row.set_selected(self._sim_active - 1)
            self._syncing = False
            return
        self.set_busy(True)
        self.modem_progress.set_text("Switching SIM …")
        self.modem_revealer.set_reveal_child(True)
        # About half a minute: oFono comes back on the other slot, then
        # ModemManager and NetworkManager are put in order behind it.
        self.pulse_start(f"Switching to SIM {slot} - mobile network away for about 30 s …")
        process.run_async([tools.PKEXEC, self.live["modem"], "sim", str(slot)],
                          self.on_sim_switched, on_line=self.on_progress_line)

    def on_sim_switched(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
        self.modem_revealer.set_reveal_child(False)
        if not ok:
            # "a call is in progress" is the likely refusal, and it is in out.
            self.toast("Switching the SIM failed")
            self.report(out or "No output.")
        else:
            self.toast("SIM switched")
        self.refresh()
