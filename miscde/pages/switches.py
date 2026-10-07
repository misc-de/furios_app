# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Switches page: the three sliders on the case."""

import os
import subprocess

from gi.repository import Adw

from .. import faults, process
from ..i18n import _

# furios_killswitch's furios-switch-mask: Android stops reading the camera
# and network sliders. For sliders with a loose contact - this phone's network
# one flapped 65 times in an afternoon untouched (1.10.2026), and on 30.9.
# that coincided with two modem resets. The microphone slider is a real line
# cut with nothing to read, so it stays out of this. Installed with
# furios_killswitch, never enabled there.
NWK_MASK_UNIT = "furios-switch-mask.service"
NWK_MASK_UNIT_FILE = "/etc/systemd/system/" + NWK_MASK_UNIT


def nwk_mask_installed(path=NWK_MASK_UNIT_FILE):
    return os.path.exists(path)


def nwk_mask_enabled():
    try:
        return subprocess.run(["systemctl", "is-enabled", "--quiet", NWK_MASK_UNIT],
                              timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def nwk_mask_argv(on, secret=None):
    front = (["sudo", "-S", "-p", ""] if secret is not None
             else ["sudo", "-n"])
    return front + ["systemctl", "enable" if on else "disable", "--now",
                    NWK_MASK_UNIT]


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

        # First, because it is the one somebody comes here for when the
        # phone keeps losing its network by itself.
        grp = Adw.PreferencesGroup()
        self.sw_nwk_mask_group = grp
        self.sw_nwk_mask = Adw.SwitchRow(
            title=_("Ignore the camera and network switches"))
        self.sw_nwk_mask.connect("notify::active", self.on_nwk_mask)
        grp.add(self.sw_nwk_mask)
        spage.add(grp)
        self.sync_nwk_mask()

        # No paragraphs on this page. Each group is a switch, each row says
        # what it is, and what needed explaining sits in the row's own
        # subtitle - where it is read next to the thing it is about.
        # The icons are a phosh plugin, and this switch is the shell's own list
        # of them. That is why there is no "remember this" beside it any more:
        # the list IS the memory, and the shell follows it while it runs.
        grp = Adw.PreferencesGroup(title=_("Indicator"))
        self.sw_row = Adw.SwitchRow(
            title=_("Icons for the camera and network switch"),
            subtitle=_("reading …"))
        self.sw_row.connect("notify::active", self.on_indicator_switch)
        grp.add(self.sw_row)
        spage.add(grp)
        self.sw_ind_group = grp

        # The camera and microphone groups are gone (28.9., on request):
        # they only described what the sliders do, and nothing there could be
        # changed. What is left is what this page actually sets.
        net = Adw.PreferencesGroup(title=_("Network switch"))
        self.sw_net_group = net
        # A fact, not a choice: the Android side stops the RIL before any
        # program here learns the slider moved. It was a greyed switch fixed
        # on, which read as a control somebody had locked - so a plain row.
        self.sw_modem = Adw.ActionRow(
            title=_("Mobile network: always switched off by the firmware"),
            subtitle=_("Settings switches mobile data off separately, any time"),
        )
        net.add(self.sw_modem)
        self.sw_wifi = Adw.SwitchRow(
            title=_("Take Wi-Fi down with it as well"),
            subtitle=_("reading …"),
        )
        self.sw_wifi.connect("notify::active", self.on_extra_wifi)
        net.add(self.sw_wifi)
        self.sw_bt = Adw.SwitchRow(
            title=_("Take Bluetooth down with it as well"),
            subtitle=_("reading …"),
        )
        self.sw_bt.connect("notify::active", self.on_extra_bt)
        net.add(self.sw_bt)
        spage.add(net)
        if nwk_mask_installed():
            self.say_mask_effect(self.sw_nwk_mask.get_active())

        # Nothing here can undo what the sliders do - they are hardware, and
        # Android acts on them before this program hears about it. What this
        # page added is the indicator and the two extra radios, and that is
        # exactly what goes away again.
        back, self.sw_restore_btn = self.build_restore_group(
            _("Takes the icons out of the top bar, stops the service behind "
            "them and leaves Wi-Fi and Bluetooth out of the network switch. "
            "The sliders themselves keep doing what they do - that is "
            "hardware, and nothing here reaches it."),
            self.on_switches_restore)
        spage.add(back)

        self.sw_rows = [self.sw_row, self.sw_wifi, self.sw_bt,
                        self.sw_restore_btn]
        return spage

    def sync_nwk_mask(self):
        row = self.sw_nwk_mask
        self._loading = True
        if not nwk_mask_installed():
            row.set_active(False)
            row.set_sensitive(False)
            row.set_subtitle(_("Needs the current furios_killswitch"))
            self.offer("nwk-mask", self.sw_nwk_mask_group, False, False)
        else:
            on = nwk_mask_enabled()
            row.set_active(on)
            row.set_sensitive(True)
            self.say_mask_effect(on)
            # The fault is a slider that moves with nobody touching it -
            # read off the kernel's edge count, see faults.sliders_flap.
            self.offer("nwk-mask", self.sw_nwk_mask_group, on,
                       faults.sliders_flap())
        self._loading = False

    def say_mask_effect(self, on):
        """What ignoring the sliders costs, said where it shows.

        It weakens privacy: the camera slider stops blocking the cameras. The
        row said nothing, and the groups below went on describing what the
        network slider does - which, while it is ignored, it does not.
        """
        self.sw_nwk_mask.set_subtitle(
            _("On: the camera and network sliders do nothing") if on else
            _("For a loose slider that switches by itself"))
        # And greyed out (asked for 7.10.2026): a row that can still be
        # switched reads as one that still does something.
        note = _("Not in effect while the sliders are ignored") if on else ""
        for group in (getattr(self, "sw_ind_group", None),
                      getattr(self, "sw_net_group", None)):
            if group is not None:
                group.set_description(note)
                group.set_sensitive(not on)

    def on_nwk_mask(self, row, _param):
        if getattr(self, "_loading", False):
            return
        if not row.get_active():
            self.apply_nwk_mask(False)
            return
        # Switching protection off asks first, the way every restore does.
        dlg = Adw.AlertDialog(
            heading=_("Ignore the sliders?"),
            body=_("The camera slider will no longer block the cameras, and "
                   "the network slider will no longer cut the network. Meant "
                   "for a slider that switches by itself."))
        dlg.add_response("cancel", _("Cancel"))
        dlg.add_response("go", _("Ignore them"))
        dlg.set_response_appearance("go", Adw.ResponseAppearance.DESTRUCTIVE)
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        dlg.connect("response", self.on_nwk_mask_confirmed)
        dlg.present(self)

    def on_nwk_mask_confirmed(self, _dlg, response):
        if response == "go":
            self.apply_nwk_mask(True)
            return
        self._loading = True
        self.sw_nwk_mask.set_active(False)
        self._loading = False

    def apply_nwk_mask(self, wanted, secret=None, then=None):
        """Switch the mask, asking for a password if sudo wants one.

        `then` is for the way back, which has more to do afterwards: it is
        handed (ok, out) once the mask is settled - switched, failed or
        cancelled - and takes over the reporting of a failure.
        """
        self.sw_nwk_mask.set_sensitive(False)
        process.run_async(
            nwk_mask_argv(wanted, secret),
            lambda ok, out: self.on_nwk_mask_done(ok, out, wanted, then),
            stdin=None if secret is None else (secret + "\n"))

    def on_nwk_mask_done(self, ok, out, wanted, then=None):
        low = (out or "").lower()
        if not ok and ("password is required" in low or "askpass" in low):
            self.ask_nwk_mask_password(wanted, then)
            return
        self.sync_nwk_mask()
        if then is not None:
            then(ok, out)
            return
        if not ok:
            self.report(out or _("No output."))
            return
        self.toast(_("The camera and network switches are ignored now") if wanted
                   else _("The camera and network switches work again"))

    def ask_nwk_mask_password(self, wanted, then=None):
        entry = Adw.PasswordEntryRow(title=_("Your password (for sudo)"))
        group = Adw.PreferencesGroup()
        group.add(entry)
        dlg = Adw.AlertDialog(
            heading=_("Ignore the camera and network switches"),
            body=_("This hangs two files into the Android container, so sudo "
                   "asks for a password. It goes to sudo through a pipe and "
                   "nowhere else."))
        dlg.set_extra_child(group)
        dlg.add_response("go", _("Change it"))
        dlg.add_response("cancel", _("Cancel"))
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        self._nwk_mask_pending = (wanted, entry, then)
        dlg.connect("response", self.on_nwk_mask_password)
        dlg.present(self)

    def on_nwk_mask_password(self, _dlg, response):
        wanted, entry, then = self._nwk_mask_pending
        self._nwk_mask_pending = (None, None, None)
        secret = entry.get_text() if entry is not None else None
        if entry is not None:
            entry.set_text("")
        if response != "go" or wanted is None:
            self.sync_nwk_mask()
            if then is not None:
                then(False, _("Cancelled - nothing was changed"))
            return
        self.apply_nwk_mask(wanted, secret, then)

    def on_switches_status(self, ok, out):
        if not ok:
            self.sw_row.set_subtitle(_("killswitch-indicator did not answer"))
            return
        data = process.json_object(out)
        if data is None:
            self.sw_row.set_subtitle(_("unreadable answer"))
            return

        icons = data.get("icons")
        self._loading = True
        self.sw_row.set_active(bool(icons))
        self._loading = False
        self.sw_row.set_sensitive(icons is not None)
        # A missing key is not phosh's null. The killswitch-indicator this
        # phone runs predates "icons" altogether (and has no "icons" command
        # either), and blaming phosh's plugin list for that sends somebody
        # looking in the one place that is fine.
        self.sw_row.set_subtitle(
            _("in the top bar, at the left end of the indicators") if icons else
            _("not shown") if icons is False else
            _("this killswitch-indicator is too old to switch them - update it")
            if "icons" not in data else
            _("phosh's plugin list is not readable here"))

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
        # The radio's state right now, not the setting - "currently on" next
        # to a switch that was off read as a contradiction.
        words = {"wifi": (_("Wi-Fi is on right now"), _("Wi-Fi is off right now")),
                 "bluetooth": (_("Bluetooth is on right now"),
                               _("Bluetooth is off right now"))}
        for row, key in ((self.sw_wifi, "wifi"), (self.sw_bt, "bluetooth")):
            state = radios.get(key)
            text = (words[key][0] if state else
                    words[key][1] if state is False else _("not reachable"))
            if getattr(self, "_daemon_active", True) is False:
                text += _(" - but the service that would act is not running")
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
            self.toasts.add_toast(Adw.Toast(
                title=_("Could not switch the icons on") if value == "on"
                else _("Could not switch the icons off")))
        elif value == "on":
            # Said once, here, because it is the one thing about this switch
            # that surprises: phosh looks for new plugins only when it starts.
            self.toasts.add_toast(Adw.Toast(
                title=_("On. After a fresh install they appear at the next boot.")))
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
        # The tool's key ("wifi"), not a word for the screen.
        name = _("Wi-Fi") if radio == "wifi" else _("Bluetooth")
        if not ok:
            self.toasts.add_toast(Adw.Toast(title=_('Could not change {0}').format(name)))
            self.refresh()
            return
        if value == "on":
            self.toasts.add_toast(Adw.Toast(
                title=_('{0} will go off with the network switch').format(name)))

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
        rest = [
            [self.live["switches"], "config", "wifi", "off"],
            [self.live["switches"], "config", "bluetooth", "off"],
            [self.live["switches"], "icons", "off"],
            ["systemctl", "--user", "disable", "--now", "killswitch-indicator"],
        ]

        def after_mask(ok, out):
            if not ok:
                self.on_switches_restored(False, out)
                return
            self.run_chain(rest, self.on_switches_restored)

        # The mask first: it is the one change here that reaches Android. It
        # goes the way its own switch goes, password question included - with
        # a bare "sudo -n" here the way back failed at its first step on every
        # phone whose sudo asks, and undid nothing.
        if nwk_mask_installed() and nwk_mask_enabled():
            self.apply_nwk_mask(False, then=after_mask)
        else:
            after_mask(True, "")

    def on_switches_restored(self, ok, out):
        self.set_busy(False)
        if ok:
            self.toast(_("Shipped state - no icons, and the switch takes only "
                       "the modem"))
        else:
            self.toast(_("Could not restore the shipped state"))
            self.report(out or _("No output."))
        self.sync_nwk_mask()
        self.refresh()
