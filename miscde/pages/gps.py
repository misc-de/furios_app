# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The GPS page: the filter that refuses geoclue a position derived
from the carrier's IP address."""

from gi.repository import Adw, Gtk

from .. import process, tools
from ..tools import CONTRIB


class GpsPage:
    def build_gps_page(self):
        """Where the phone says it is.

        The same question as the other two pages - as shipped, or repaired -
        but the "off" side is the one that needs explaining here. Off does not
        mean "no location". It means geoclue publishes the position of the
        carrier's exit node as though the phone had been observed there.
        """
        gpage = Adw.PreferencesPage()

        grp = Adw.PreferencesGroup(title="GPS fix")
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

        # Giving back, in its own group: this is the opposite direction of
        # everything above it. The filter decides what this phone accepts;
        # this decides what it hands out, and conflating the two in one group
        # would be the wrong question in the wrong place.
        # No description on the group: one paragraph here lifts the heading
        # above every other tab's, which was measured on the phone. What has
        # to be said sits in the row it is about.
        contribution = Adw.PreferencesGroup(title="Contribute to beaconDB")
        self.gps_contrib = Adw.SwitchRow(
            title="Send my observations",
            subtitle="reading …",
        )
        self.gps_contrib.connect("notify::active", self.on_gps_contrib)
        contribution.add(self.gps_contrib)
        self.gps_contrib_stats = Adw.ActionRow(
            title="Sent so far", subtitle="—",
        )
        contribution.add(self.gps_contrib_stats)

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
        gpage.add(contribution)

        info = Adw.PreferencesGroup(title="Status")
        self.grow_profile = Adw.ActionRow(title="Profile", subtitle="…")
        self.grow_seen = Adw.ActionRow(title="Since this boot", subtitle="…")
        self.grow_health = Adw.ActionRow(title="Checks", subtitle="…")
        for row in (self.grow_profile, self.grow_seen, self.grow_health):
            row.set_subtitle_selectable(True)
            info.add(row)
        gpage.add(info)

        # The switch above reaches the same state, and for a while that was
        # the argument against a button here. But a way back that exists on
        # some pages and not on others is one somebody has to go looking for -
        # so it is here too, worded so that nobody presses it by mistake.
        back, self.gps_restore_btn = self.build_restore_group(
            "Switches the filter off and remembers it. Asked where it is with "
            "no Wi-Fi it recognises, the phone then publishes the position of "
            "the carrier's IP address again - the exit node of their network, "
            "tens of kilometres away.",
            self.on_gps_restore)
        gpage.add(back)

        self.gps_rows = [self.gps_row, self.gps_persist, self.gps_contrib,
                         self.gps_restore_btn]
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
            "On: a position that is really just the carrier's IP address is refused"
            if actual == "fixed"
            else "Off: the carrier's IP address is published as a position"
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
        if not tools.PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        mode = "set" if self.gps_persist.get_active() else "try"
        want = "fixed" if row.get_active() else "shipped"
        self.set_busy(True)
        self.gps_progress.set_text("Switching …")
        self.gps_revealer.set_reveal_child(True)
        self.pulse_start("Switching the location filter …")
        process.run_async([tools.PKEXEC, self.live["gps"], mode, want], self.on_gps_switched,
                  on_line=self.on_progress_line)

    def on_gps_switched(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
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

    def on_gps_contrib(self, row, _param):
        """On or off, and nothing in between - the tool keeps the marker."""
        if self._syncing or self.busy:
            return
        tool = tools._tool_maybe(CONTRIB)
        if not tool:
            return
        self.set_busy(True)
        process.run_async([tool, "on" if row.get_active() else "off"],
                  self.on_gps_contrib_done)

    def on_gps_contrib_done(self, ok, out):
        self.set_busy(False)
        if not ok:
            self.toast("Could not change the contribution setting")
            self.report(out or "No output.")
        self.refresh_gps_contrib()

    def refresh_gps_contrib(self):
        tool = tools._tool_maybe(CONTRIB)
        if not tool:
            # Not installed is not "off": saying "off" would claim we looked.
            self._syncing = True
            self.gps_contrib.set_active(False)
            self._syncing = False
            self.gps_contrib.set_sensitive(False)
            self.gps_contrib.set_subtitle("not installed")
            self.gps_contrib_stats.set_subtitle("—")
            return
        process.run_async([tool, "status"], self.on_gps_contrib_status)

    def on_gps_contrib_status(self, ok, out):
        if not ok:
            self.gps_contrib.set_subtitle("did not answer")
            return
        values = dict(z.split("=", 1) for z in out.splitlines() if "=" in z)
        an = values.get("contributing") == "yes"
        self._syncing = True
        self.gps_contrib.set_active(an)
        self._syncing = False
        self.gps_contrib.set_sensitive(True)
        # Asked for and actually happening are two facts, and the row must not
        # pass the first off as the second: the service exits when the marker
        # is missing, so "on" with nothing running is a state that exists.
        runs = values.get("running") == "yes"
        if an and not runs:
            self.gps_contrib.set_subtitle(
                "Switched on, but the service is not running - "
                "nothing is being collected")
        elif an:
            self.gps_contrib.set_subtitle(
                "Networks in range with the satellite position, over Wi-Fi only")
        else:
            self.gps_contrib.set_subtitle(
                "Off - nothing is collected or sent. On: networks in range, "
                "never hidden or _nomap ones")
        # Both numbers, because they answer different questions: whether it is
        # measuring at all, and whether any of it has reached beaconDB.
        self.gps_contrib_stats.set_subtitle(
            "%s sent, %s waiting" % (values.get("submitted", "0"),
                                     values.get("queued", "0")))

    def on_gps_restore(self, _btn):
        if self.busy:
            return
        if not tools.PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        self.set_busy(True)
        self.gps_progress.set_text("Restoring …")
        self.gps_revealer.set_reveal_child(True)
        self.pulse_start("Back to the shipped state …")
        # "set", not "try", like the other pages: what it restores is what the
        # phone comes back to after the next boot.
        process.run_async([tools.PKEXEC, self.live["gps"], "set", "shipped"], self.on_gps_restored,
                  on_line=self.on_progress_line)

    def on_gps_restored(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
        self.gps_revealer.set_reveal_child(False)
        if ok:
            # Again not a neutral "done" - what was switched off is the part
            # that matters.
            self.toast("Shipped state - the IP position is published again")
        else:
            self.toast("Could not restore the shipped state")
            self.report(out or "No output.")
        self.refresh()
