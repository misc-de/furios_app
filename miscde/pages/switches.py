# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Switches page: the three sliders on the case."""

import json

from gi.repository import Adw

from .. import process


class SwitchesPage:
    def build_switches_page(self):
        """The three sliders on the housing, and what each of them really does.

        They look alike and work nothing alike. Camera and network are software
        kills: a GPIO tells the Android side, which stops a service with signal
        9. The microphone one cuts the line, which is why it is the only one
        the system cannot see at all - and the only one that is beyond doubt.

        No slider position is shown. A page cannot switch what the hand on the
        case already decided, so repeating the position back was a reading
        without a use - and next to the microphone, where there is nothing to
        read, it made the absence look like a fault. What is left is what this
        page can actually answer: what the switch took down with it.
        """
        spage = Adw.PreferencesPage()

        # No paragraphs on this page. Each group is a switch, each row says
        # what it is, and what needed explaining sits in the row's own
        # subtitle - where it is read next to the thing it is about.
        # The icons are a phosh plugin, and this switch is the shell's own list
        # of them. That is why there is no "remember this" beside it any more:
        # the list IS the memory, and the shell follows it while it runs.
        grp = Adw.PreferencesGroup(title="Indicator")
        self.sw_row = Adw.SwitchRow(
            title="Icons for the camera and network switch",
            subtitle="reading …")
        self.sw_row.connect("notify::active", self.on_indicator_switch)
        grp.add(self.sw_row)
        spage.add(grp)

        cam = Adw.PreferencesGroup(title="1 · Camera")
        self.srow_cam_hal = Adw.ActionRow(title="Camera service", subtitle="…")
        self.srow_cams = Adw.ActionRow(title="Cameras affected", subtitle="…")
        for row in (self.srow_cam_hal, self.srow_cams):
            row.set_subtitle_selectable(True)
            cam.add(row)
        spage.add(cam)

        net = Adw.PreferencesGroup(title="2 · Network")
        # Shown as a switch like the other two, but fixed on: the Android side
        # stops the RIL before any program here learns the slider moved. The
        # only way to "deselect" it would be to start the modem back up behind
        # the switch - undermining the very thing somebody flipped it for.
        self.sw_modem = Adw.SwitchRow(
            title="The mobile network goes with the switch",
            subtitle="always, and not ours to change - firmware does it. "
            "(Settings switches mobile data off separately, any time.)",
            active=True,
        )
        self.sw_modem.set_sensitive(False)
        net.add(self.sw_modem)
        self.sw_wifi = Adw.SwitchRow(
            title="Take Wi-Fi down with it as well",
            subtitle="reading …",
        )
        self.sw_wifi.connect("notify::active", self.on_extra_wifi)
        net.add(self.sw_wifi)
        self.sw_bt = Adw.SwitchRow(
            title="Take Bluetooth down with it as well",
            subtitle="reading …",
        )
        self.sw_bt.connect("notify::active", self.on_extra_bt)
        net.add(self.sw_bt)
        spage.add(net)

        mic = Adw.PreferencesGroup(title="3 · Microphone")
        # The one line that cannot go: without it the row reads like a defect.
        # It cuts the built-in microphones for real, and reading the position
        # would mean opening them - which is what the switch is flipped
        # against. The long version lives in the project's FINDINGS.md.
        #
        # Said as what it is rather than as a missing reading: "Position:
        # not readable" puts the word Position on screen and then takes it
        # back, which reads as a gap where the other two have an answer.
        self.srow_mic = Adw.ActionRow(
            title="Not controlled by software",
            subtitle="the slider cuts the line itself - nothing here switches "
            "it, and reading it would mean opening the microphone, which is "
            "what it is against")
        self.srow_mic.set_subtitle_selectable(True)
        mic.add(self.srow_mic)
        # For anyone who does want a number: one measurement, asked for by
        # hand, on the terminal. Deliberately not a button here - a button is
        # an invitation, and this one should be a decision.
        hint = Adw.ActionRow(
            title="Measure once by hand",
            subtitle="killswitch-indicator mic-check")
        hint.set_subtitle_selectable(True)
        mic.add(hint)
        spage.add(mic)

        # Nothing here can undo what the sliders do - they are hardware, and
        # Android acts on them before this program hears about it. What this
        # page added is the indicator and the two extra radios, and that is
        # exactly what goes away again.
        back, self.sw_restore_btn = self.build_restore_group(
            "Takes the icons out of the top bar, stops the service behind "
            "them and leaves Wi-Fi and Bluetooth out of the network switch. "
            "The sliders themselves keep doing what they do - that is "
            "hardware, and nothing here reaches it.",
            self.on_switches_restore)
        spage.add(back)

        self.sw_rows = [self.sw_row, self.sw_wifi, self.sw_bt,
                        self.sw_restore_btn]
        return spage

    def on_switches_status(self, ok, out):
        if not ok:
            for row in (self.srow_cam_hal, self.srow_cams):
                row.set_subtitle("killswitch-indicator did not answer")
            return
        try:
            data = json.loads(out)
        except ValueError:
            self.srow_cam_hal.set_subtitle("unreadable answer")
            return

        hal = data.get("camera_hal")
        self.srow_cam_hal.set_subtitle(
            "running" if hal else "stopped" if hal is False else "unknown")

        cams = data.get("cameras")
        if cams:
            sides = ", ".join(c.lower() for c in cams)
            self.srow_cams.set_subtitle(f"all {len(cams)} ({sides}) - never one alone")
        else:
            self.srow_cams.set_subtitle(
                "all of them - list not fetched yet "
                "(sudo killswitch-indicator cameras --refresh)")

        icons = data.get("icons")
        self._loading = True
        self.sw_row.set_active(bool(icons))
        self._loading = False
        self.sw_row.set_sensitive(icons is not None)
        self.sw_row.set_subtitle(
            "in the top bar, at the left end of the indicators" if icons else
            "not shown" if icons is False else
            "phosh's plugin list is not readable here")

        extras = data.get("network_extras", {})
        self._radios = data.get("radios", {})
        self._loading = True
        self.sw_wifi.set_active(bool(extras.get("wifi")))
        self.sw_bt.set_active(bool(extras.get("bluetooth")))
        self._loading = False
        self.say_extra_states()

    def say_extra_states(self):
        """What the two radios are doing, and whether anything is listening.

        The daemon is what acts on the switch here. A row that offers to take
        Wi-Fi down while nothing is running to do it would be a promise the
        phone does not keep.
        """
        radios = getattr(self, "_radios", {})
        for row, key in ((self.sw_wifi, "wifi"), (self.sw_bt, "bluetooth")):
            state = radios.get(key)
            text = ("currently on" if state else
                    "currently off" if state is False else "not reachable")
            if getattr(self, "_daemon_active", True) is False:
                text += " - but the service that would act is not running"
            row.set_subtitle(text)

    def on_indicator_active(self, ok, out):
        """Whether the daemon runs. It draws nothing - it is what takes the
        extra radios down with the network switch - so it is said where that
        is set, and not as a switch of its own."""
        self._daemon_active = ok and out.strip() == "active"
        self.say_extra_states()

    def on_indicator_switch(self, row, _param):
        if getattr(self, "_loading", False):
            return
        value = "on" if row.get_active() else "off"
        process.run_async([self.live["switches"], "icons", value],
                  lambda ok, out: self.after_indicator(ok, out, value))

    def after_indicator(self, ok, out, value):
        if not ok:
            self.toasts.add_toast(
                Adw.Toast(title=f"Could not switch the icons {value}"))
        elif value == "on":
            # Said once, here, because it is the one thing about this switch
            # that surprises: phosh looks for new plugins only when it starts.
            self.toasts.add_toast(Adw.Toast(
                title="On. After a fresh install they appear at the next boot."))
        self.refresh()

    def on_extra_wifi(self, row, _param):
        self.set_extra("wifi", row)

    def on_extra_bt(self, row, _param):
        self.set_extra("bluetooth", row)

    def set_extra(self, radio, row):
        if getattr(self, "_loading", False):
            return
        value = "on" if row.get_active() else "off"
        process.run_async([self.live["switches"], "config", radio, value],
                  lambda ok, out: self.after_extra(ok, radio, value))

    def after_extra(self, ok, radio, value):
        if not ok:
            self.toasts.add_toast(Adw.Toast(title=f"Could not change {radio}"))
            self.refresh()
            return
        if value == "on":
            self.toasts.add_toast(Adw.Toast(
                title=f"{radio} will go off with the network switch"))

    def on_switches_restore(self, _btn):
        """Everything this page added, taken back out - in one go.

        Four commands, not one: the tool owns the two extra radios and the
        shell's plugin list, and systemd owns the unit. They run one after the other and stop at the
        first failure, so a half-done state is reported rather than passed off
        as success.
        """
        if self.busy:
            return
        self.set_busy(True)
        self.run_chain([
            [self.live["switches"], "config", "wifi", "off"],
            [self.live["switches"], "config", "bluetooth", "off"],
            [self.live["switches"], "icons", "off"],
            ["systemctl", "--user", "disable", "--now", "killswitch-indicator"],
        ], self.on_switches_restored)

    def on_switches_restored(self, ok, out):
        if ok:
            self.toast("Shipped state - no icons, and the switch takes only "
                       "the modem")
        else:
            self.toast("Could not restore the shipped state")
            self.report(out or "No output.")
        self.refresh()
