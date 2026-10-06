# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Modem page: the repairs to ofono2mm and ModemManager."""

from gi.repository import Adw, Gtk

from .. import combo, faults, process, tools
from ..i18n import _


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
        grp = Adw.PreferencesGroup(title=_("Modem"))
        self.modem_group = grp
        self._modem_actual = None
        self._modem_fault = None
        self.modem_row = Adw.SwitchRow(
            title=_("Repairs active"),
            subtitle=_("reading …"),
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
        self.sim_group = Adw.PreferencesGroup(title=_("SIM"))
        self.sim_row = Adw.ComboRow(
            title=_("Active SIM"),
            subtitle=_("reading …"),
            model=Gtk.StringList.new(["SIM 1", "SIM 2"]),
        )
        self.sim_ok = False
        self.sim_row.set_sensitive(False)
        self.sim_row.connect("notify::selected", self.on_sim_select)
        self._sim_labels = ["SIM 1", "SIM 2"]
        self._sim_present = []
        self._sim_active = 1
        self.sim_group.add(self.sim_row)
        combo.keep_value_visible(self.sim_row)
        self.sim_group.set_visible(False)
        mpage.add(self.sim_group)

        # 5G. A switch of its own, not part of "Repairs active": it changes
        # what the radio does rather than repairing something broken, and it
        # costs the data call a few seconds each time it is turned on.
        # Hidden until modemctl answers "nr" - an older one does not know it.
        self.nr_group = Adw.PreferencesGroup(title="5G")
        self.nr_row = Adw.SwitchRow(title=_("Allow 5G"), subtitle=_("reading …"))
        self.nr_ok = False
        self.nr_row.set_sensitive(False)
        self.nr_row.connect("notify::active", self.on_nr_switch)
        self.nr_group.add(self.nr_row)
        self.nr_group.set_visible(False)
        mpage.add(self.nr_group)

        info = Adw.PreferencesGroup(title=_("Status"))
        self.mrow_profile = Adw.ActionRow(title=_("Profile"), subtitle="…")
        self.mrow_health = Adw.ActionRow(title=_("Checks"), subtitle="…")
        self.mrow_signal = Adw.ActionRow(title=_("Signal"), subtitle="…")
        for row in (self.mrow_profile, self.mrow_health, self.mrow_signal):
            row.set_subtitle_selectable(True)
            info.add(row)
        mpage.add(info)

        # What it costs here is the opposite of the audio page: that one
        # brings something back, this one takes function away. Same button,
        # and the description carries the difference.
        back, self.modem_restore_btn = self.build_restore_group(
            _("Takes every repair out, restarts the modem stack and remembers "
              "it. With Wi-Fi off there is then no route out and no name "
              "resolution."),
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
            self.mrow_profile.set_subtitle(_("modemctl did not answer"))
            return
        self.modem_ok = True
        self._modem_actual = actual
        self.offer_modem()

        if actual == "fixed":
            words = _("the repairs are in place")
        elif actual == "shipped":
            words = _("FuriOS as it came")
        else:
            # "mixed" is a real state and saying either of the other two would
            # be wrong in both directions.
            words = _("half repaired - use \"Repairs active\" to settle it")
        if recorded != actual and actual in ("fixed", "shipped"):
            words += _(" · not remembered, the next boot returns to \"{recorded}\"").format(
                recorded=recorded)
        self.mrow_profile.set_subtitle(words)

        self._syncing = True
        self.modem_row.set_active(actual == "fixed")
        self._syncing = False
        self.modem_row.set_subtitle(
            _("On: mobile data works without Wi-Fi")
            if actual == "fixed"
            else _("Off: as shipped - without Wi-Fi there is no mobile data")
        )

    def on_modem_status(self, ok, out):
        if not ok and not out:
            self.mrow_health.set_subtitle(_("modemctl did not answer"))
            return
        self._modem_fault = faults.modem_checks_fail(out)
        self.offer_modem()
        bad = sum(1 for line in out.splitlines() if "FAIL" in line)
        good = sum(1 for line in out.splitlines() if " ok " in line)
        self.mrow_health.set_subtitle(
            _('{0} in place').format(good) if bad == 0 else _('{0} in place, {1} not').format(good, bad)
        )
        for line in out.splitlines():
            if "signal quality" in line:
                self.mrow_signal.set_subtitle(line.split("signal quality", 1)[1].strip())
                break
        else:
            self.mrow_signal.set_subtitle(_("not readable"))

    def offer_modem(self):
        """Two answers decide it, and they arrive apart: the profile says
        whether ours is in, the checks whether anything is broken."""
        self.offer("modem", self.modem_group,
                   self._modem_actual not in (None, "shipped"),
                   self._modem_fault)

    def on_modem_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        if not tools.PKEXEC:
            self.toast(_("pkexec is missing - cannot ask for the rights to switch"))
            return
        # Always "set": the repairs are what makes mobile data work, and a
        # switch that quietly fell back at the next boot was one more thing
        # to remember. There is no "remember" row any more (28.9.); a try is
        # still there for the command line.
        if not row.get_active():
            # Off takes mobile data away without Wi-Fi - the cost the restore
            # button asks about first. The switch did it on one tap.
            dlg = Adw.AlertDialog(
                heading=_("Switch the repairs off?"),
                body=_("With Wi-Fi off there is then no mobile data: no route "
                       "out and no name resolution."))
            dlg.add_response("cancel", _("Cancel"))
            dlg.add_response("go", _("Switch off"))
            dlg.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE)
            dlg.set_default_response("cancel")
            dlg.set_close_response("cancel")
            dlg.connect("response", self.on_modem_off_confirmed)
            dlg.present(self)
            return
        self.switch_modem("fixed")

    def on_modem_off_confirmed(self, _dlg, response):
        if response == "go":
            self.switch_modem("shipped")
            return
        self._syncing = True
        self.modem_row.set_active(True)
        self._syncing = False

    def switch_modem(self, want):
        mode = "set"
        self.set_busy(True)
        self.modem_revealer.set_reveal_child(True)
        self.pulse_start(_("Switching the modem …"),
                         self.modem_progress, self.modem_revealer)
        process.run_async([tools.PKEXEC, self.live["modem"], mode, want], self.on_modem_switched,
                  on_line=self.on_progress_line)

    def on_modem_restore(self, _btn):
        if self.busy:
            return
        if not tools.PKEXEC:
            self.toast(_("pkexec is missing - cannot ask for the rights to switch"))
            return
        self.set_busy(True)
        self.modem_revealer.set_reveal_child(True)
        self.pulse_start(_("Back to the shipped state …"),
                         self.modem_progress, self.modem_revealer)
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
            self.toast(_("Shipped state - no network without Wi-Fi"))
        else:
            self.toast(_("Could not restore the shipped state"))
            self.report(out or _("No output."))
        self.refresh()

    def on_modem_switched(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
        self.modem_revealer.set_reveal_child(False)
        if not ok:
            # A refusal from polkit looks like any other failure from here, and
            # it is the likely one on a phone where this is not authorised.
            self.toast(_("Switching the modem failed"))
            self.report(out or _("No output."))
        else:
            last = [l for l in out.splitlines() if l.strip()]
            self.toast(last[-1].strip() if last else _("Done"))
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
                labels.append(_("SIM {n} · no card").format(n=n))
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
            words = _("One at a time - both slots share one radio")
        elif not present:
            words = _("No card detected - is the tray pushed all the way in?")
        elif active not in present:
            words = _("No card in slot {n} - pick the other one to get the "
                      "network back").format(n=active)
        else:
            words = _("Insert a second card to choose between them")
        self.sim_row.set_subtitle(words)
        self.sim_row.set_sensitive(self.sim_ok and not self.busy)

    def on_sim_select(self, row, _param):
        if self._syncing or self.busy or not self.sim_ok:
            return
        if not tools.PKEXEC:
            self.toast(_("pkexec is missing - cannot ask for the rights to switch"))
            return
        slot = row.get_selected() + 1
        # Nothing to do for the slot already in use, and never a switch to a
        # slot without a card - that is a phone without mobile network.
        # modemctl refuses that too; this keeps the list from even asking.
        if slot == self._sim_active:
            return
        if slot not in self._sim_present:
            self.toast(_('No card in slot {0}').format(slot))
            self._syncing = True
            row.set_selected(self._sim_active - 1)
            self._syncing = False
            return
        self.set_busy(True)
        self.modem_revealer.set_reveal_child(True)
        # About half a minute: oFono comes back on the other slot, then
        # ModemManager and NetworkManager are put in order behind it.
        self.pulse_start(_('Switching to SIM {0} - mobile network away for about 30 s …').format(slot),
                         self.modem_progress, self.modem_revealer)
        process.run_async([tools.PKEXEC, self.live["modem"], "sim", str(slot)],
                          self.on_sim_switched, on_line=self.on_progress_line)

    def on_sim_switched(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
        self.modem_revealer.set_reveal_child(False)
        if not ok:
            # "a call is in progress" is the likely refusal, and it is in out.
            self.toast(_("Switching the SIM failed"))
            self.report(out or _("No output."))
        else:
            self.toast(_("SIM switched"))
        self.refresh()

    # --- 5G ----------------------------------------------------------------
    #
    # "modemctl nr" is the contract: recorded (on/off) and allowed (yes, no,
    # unknown). Its other half is tests/test-nr.sh in furios_modem_fixes.

    def on_nr_status(self, ok, out):
        found = self._keyed(out or "")
        recorded, allowed = found.get("recorded"), found.get("allowed")
        if recorded not in ("on", "off"):
            self.nr_ok = False
            self.nr_group.set_visible(False)
            return
        self.nr_ok = True
        self.nr_group.set_visible(True)
        self._syncing = True
        self.nr_row.set_active(recorded == "on")
        self._syncing = False
        if recorded == "on" and allowed == "no":
            words = _("Switched on, but the modem does not allow it right now")
        elif recorded == "on":
            words = _("On - used where the network offers it")
        else:
            words = _("Off: LTE, as FuriOS ships it")
        self.nr_row.set_subtitle(words)
        self.nr_row.set_sensitive(not self.busy)

    def on_nr_switch(self, row, _param):
        if self._syncing or self.busy or not self.nr_ok:
            return
        if not tools.PKEXEC:
            self.toast(_("pkexec is missing - cannot ask for the rights to switch"))
            return
        want = "on" if row.get_active() else "off"
        self.set_busy(True)
        self.modem_revealer.set_reveal_child(True)
        # The radio registers afresh so the network hears about it: mobile
        # data is away for a moment.
        self.pulse_start(_("Switching 5G - mobile data away for a few seconds …"),
                         self.modem_progress, self.modem_revealer)
        process.run_async([tools.PKEXEC, self.live["modem"], "nr", want],
                          self.on_nr_switched, on_line=self.on_progress_line)

    def on_nr_switched(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
        self.modem_revealer.set_reveal_child(False)
        if not ok:
            # "a call is in progress" is not a failure (modemctl waits for
            # the next registration then), so this is a refusal or a HAL
            # that did not answer - both are in out.
            self.toast(_("Switching 5G failed"))
            self.report(out or _("No output."))
        else:
            self.toast(_("5G switched on") if self.nr_row.get_active()
                       else _("5G switched off"))
        self.refresh()
