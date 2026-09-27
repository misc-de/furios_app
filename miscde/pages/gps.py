# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The GPS page: contributing Wi-Fi observations to beaconDB.

Until 27.9.2026 this page switched a filter that kept geoclue from publishing
the carrier's IP address as a position. geoclue does that itself now, the
filter is retired, and what is left is the other direction - what this phone
hands out, not what it accepts."""

from gi.repository import Adw

from .. import process


class GpsPage:
    def build_gps_page(self):
        gpage = Adw.PreferencesPage()

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
        gpage.add(contribution)

        # The switch above reaches the same state. But a way back that exists
        # on some pages and not on others is one somebody has to go looking
        # for - so it is here too.
        back, self.gps_restore_btn = self.build_restore_group(
            "Switches sending off. Nothing more is collected, and what is "
            "still waiting is not sent.",
            self.on_gps_restore)
        gpage.add(back)

        self.gps_rows = [self.gps_contrib, self.gps_restore_btn]
        return gpage

    def on_gps_contrib(self, row, _param):
        """On or off, and nothing in between - the tool keeps the marker."""
        if self._syncing or self.busy:
            return
        tool = self.live.get("gps")
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
        tool = self.live.get("gps")
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
        if self.busy or not self.live.get("gps"):
            return
        self.set_busy(True)
        process.run_async([self.live["gps"], "off"], self.on_gps_restored)

    def on_gps_restored(self, ok, out):
        self.set_busy(False)
        if ok:
            self.toast("Sending to beaconDB is off")
        else:
            self.toast("Could not switch sending off")
            self.report(out or "No output.")
        self.refresh_gps_contrib()
