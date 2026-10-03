# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The GPS page: contributing Wi-Fi observations to beaconDB, and letting
Firefox web apps wait long enough for a satellite fix.

Until 27.9.2026 this page switched a filter that kept geoclue from publishing
the carrier's IP address as a position. geoclue does that itself now, the
filter is retired, and what is left is the other direction - what this phone
hands out, not what it accepts."""

import os

from gi.repository import Adw

from .. import faults, process
from ..i18n import _


def firefox_tool(contribute):
    """furios-gps-firefox ships next to furios-gps-contribute, in the same
    package and the same install.sh - so it is looked for there, and only
    there. An older checkout has the one without the other."""
    if not contribute:
        return None
    path = os.path.join(os.path.dirname(contribute), "furios-gps-firefox")
    return path if os.access(path, os.X_OK) else None


class GpsPage:
    def build_gps_page(self):
        gpage = Adw.PreferencesPage()

        # No description on the group: one paragraph here lifts the heading
        # above every other tab's, which was measured on the phone. What has
        # to be said sits in the row it is about.
        contribution = Adw.PreferencesGroup(title=_("Contribute to beaconDB"))
        self.gps_contrib = Adw.SwitchRow(
            title=_("Send my observations"),
            subtitle=_("reading …"),
        )
        self.gps_contrib.connect("notify::active", self.on_gps_contrib)
        contribution.add(self.gps_contrib)
        self.gps_contrib_stats = Adw.ActionRow(
            title=_("Sent so far"), subtitle="—",
        )
        contribution.add(self.gps_contrib_stats)
        gpage.add(contribution)

        browser = Adw.PreferencesGroup(title=_("Firefox and web apps"))
        self.gps_firefox_group = browser
        self.gps_firefox = Adw.SwitchRow(
            title=_("Wait for the satellite fix"),
            subtitle=_("reading …"),
        )
        self.gps_firefox.connect("notify::active", self.on_gps_firefox)
        browser.add(self.gps_firefox)
        gpage.add(browser)

        # The switch above reaches the same state. But a way back that exists
        # on some pages and not on others is one somebody has to go looking
        # for - so it is here too.
        back, self.gps_restore_btn = self.build_restore_group(
            _("Switches sending off - nothing more is collected, and what is "
              "still waiting is not sent - and gives Firefox back its "
              "12-second limit."),
            self.on_gps_restore)
        gpage.add(back)

        self.gps_rows = [self.gps_contrib, self.gps_firefox,
                         self.gps_restore_btn]
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
            self.toast(_("Could not change the contribution setting"))
            self.report(out or _("No output."))
        self.refresh_gps_contrib()

    def on_gps_firefox(self, row, _param):
        if self._syncing or self.busy:
            return
        tool = firefox_tool(self.live.get("gps"))
        if not tool:
            return
        self.set_busy(True)
        process.run_async([tool, "on" if row.get_active() else "off"],
                          self.on_gps_firefox_done)

    def on_gps_firefox_done(self, ok, out):
        self.set_busy(False)
        if not ok:
            self.toast(_("Could not change the Firefox setting"))
            self.report(out or _("No output."))
        self.refresh_gps_contrib()

    def on_gps_firefox_status(self, ok, out):
        if not ok:
            self.gps_firefox.set_subtitle(_("did not answer"))
            return
        values = dict(z.split("=", 1) for z in out.splitlines() if "=" in z)
        on = values.get("firefox_wait") == "yes"
        self._syncing = True
        self.gps_firefox.set_active(on)
        self._syncing = False
        self.gps_firefox.set_sensitive(True)
        profiles = values.get("profiles", "0")
        self.offer("firefox", self.gps_firefox_group,
                   on or values.get("leftover", "0") != "0",
                   faults.firefox_profiles(values))
        if on:
            self.gps_firefox.set_subtitle(
                _("Up to 3 minutes instead of 12 seconds - %s of %s profiles. "
                "An open app needs a restart")
                % (values.get("patched", "0"), profiles))
        elif values.get("leftover", "0") != "0":
            # Off was asked for, but an open profile still has the values.
            self.gps_firefox.set_subtitle(
                _("Off - %s open app(s) keep it until the next login")
                % values["leftover"])
        else:
            self.gps_firefox.set_subtitle(
                _("Off - Firefox gives up after 12 seconds, before a cold fix "
                "arrives"))

    def refresh_gps_contrib(self):
        ff = firefox_tool(self.live.get("gps"))
        if ff:
            process.run_async([ff, "status"], self.on_gps_firefox_status)
        else:
            self._syncing = True
            self.gps_firefox.set_active(False)
            self._syncing = False
            self.gps_firefox.set_sensitive(False)
            self.gps_firefox.set_subtitle(_("not installed"))
            self.offer("firefox", self.gps_firefox_group, False, False)
        tool = self.live.get("gps")
        if not tool:
            # Not installed is not "off": saying "off" would claim we looked.
            self._syncing = True
            self.gps_contrib.set_active(False)
            self._syncing = False
            self.gps_contrib.set_sensitive(False)
            self.gps_contrib.set_subtitle(_("not installed"))
            self.gps_contrib_stats.set_subtitle("—")
            return
        process.run_async([tool, "status"], self.on_gps_contrib_status)

    def on_gps_contrib_status(self, ok, out):
        if not ok:
            self.gps_contrib.set_subtitle(_("did not answer"))
            return
        values = dict(z.split("=", 1) for z in out.splitlines() if "=" in z)
        on = values.get("contributing") == "yes"
        self._syncing = True
        self.gps_contrib.set_active(on)
        self._syncing = False
        self.gps_contrib.set_sensitive(True)
        # Asked for and actually happening are two facts, and the row must not
        # pass the first off as the second: the service exits when the marker
        # is missing, so "on" with nothing running is a state that exists.
        runs = values.get("running") == "yes"
        if on and not runs:
            self.gps_contrib.set_subtitle(
                _("Switched on, but the service is not running - "
                "nothing is being collected"))
        elif on:
            self.gps_contrib.set_subtitle(
                _("Networks in range with the satellite position, over Wi-Fi only"))
        else:
            self.gps_contrib.set_subtitle(
                _("Off - nothing is collected or sent. On: networks in range, "
                "never hidden or _nomap ones"))
        # Both numbers, because they answer different questions: whether it is
        # measuring at all, and whether any of it has reached beaconDB.
        self.gps_contrib_stats.set_subtitle(
            _("%s sent, %s waiting") % (values.get("submitted", "0"),
                                     values.get("queued", "0")))

    def on_gps_restore(self, _btn):
        if self.busy or not self.live.get("gps"):
            return
        self.set_busy(True)
        steps = [[self.live["gps"], "off"]]
        ff = firefox_tool(self.live["gps"])
        if ff:
            steps.append([ff, "off"])
        self.run_chain(steps, self.on_gps_restored)

    def on_gps_restored(self, ok, out):
        self.set_busy(False)
        if ok:
            self.toast(_("Sending to beaconDB is off, Firefox as shipped"))
        else:
            self.toast(_("Could not switch sending off"))
            self.report(out or _("No output."))
        self.refresh_gps_contrib()
