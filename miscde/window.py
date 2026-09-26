# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The window itself: the frame, the tabs, and what is the same on every page.

Window is assembled from the pages and the installer rather than
holding them. They are mixins and not widgets of their own because
they share one thing that cannot be split: `self`. A page reads
`self.live` to know whether its tool is there, calls `self.set_busy`
to lock the whole window while a helper runs, and puts its own way
back together with `self.build_restore_group`. Handing each page its
own object would mean handing it a reference to this one anyway, and
the tests reach for `win.on_gps_status` exactly as the GTK signal
does.

What decides where a method goes is the page it speaks for. What is
left here is what every page uses: the busy state, the progress bar,
the toast, the way back, and refresh(), which asks every tool at once
and is the only method that knows about all of them."""

from gi.repository import Adw, GLib, Gtk

from . import process, tools
from .components import BATTERY_UNIT, COMPONENTS, SELF
from .tools import APP_ID, DMNR
from .pages.audio import AudioPage
from .pages.battery import BatteryPage
from .pages.gps import GpsPage
from .pages.install import InstallPage
from .pages.modem import ModemPage
from .pages.other import TAB as OTHER_TAB, OtherPage
from .pages.security import SecurityPage
from .pages.switches import SwitchesPage


class Window(AudioPage, ModemPage, GpsPage, SwitchesPage, BatteryPage,
             SecurityPage, OtherPage, InstallPage,
             Adw.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="misc-de")
        self.set_default_size(360, 480)
        self.busy = False
        self._syncing = False
        # Which way back is waiting for an answer, set while the question is
        # on screen. A pair, never a bare handler: the button belongs with it.
        self._restore_pending = (None, None)
        # Same idea on the components page: which fetch is waiting for an
        # answer, and the entry its password would come from.
        self._comp_pending = (None, None, None, None)
        # The password entry of the update dialog, while it is open.
        self._updates_pending = None
        # The socket sudo asks at while an install runs, and nothing outside
        # of one.
        self.askpass = None
        self.comp_rows = {}
        # What is waiting, keyed by tool: one dict for the whole window, so
        # the count in the header and the list behind it cannot disagree.
        self.updates = {}
        self.modem_rows = []
        # Whether there is anything behind each control. A switch whose tool
        # did not answer must not look operable - and it must not become
        # operable again the moment something else finishes, which is what
        # happened as long as set_busy was the only hand on the sensitivity.
        self.audio_ok = True
        self.dmnr_ok = True
        # Whether batman's config could be read at all. Without it the row is
        # closed rather than shown as "off" - nothing is powering the adapter
        # down in that case, but saying so from a file that is not there
        # would be a guess.
        self.btsave_ok = False
        # Which Bluetooth powersave change is waiting for a password, with the
        # entry it would come from.
        self._btsave_pending = (None, None)
        self._dmnr_pending = None
        self._dmnr_askpass = None
        self._dmnr_args = []
        self.modem_ok = True
        self.gps_ok = True
        self.gps_rows = []
        self.batt_rows = []
        self.sec_rows = []

        toolbar = Adw.ToolbarView()
        header = Adw.HeaderBar()
        toolbar.add_top_bar(header)

        # Left of the title, and hidden until there is something to say.
        #
        # There used to be a "reload" button on the right instead. It asked
        # every tool the same question the window already asks itself - on
        # opening, after every switch, after every install - so it was a
        # button whose whole job was to produce the state that was already on
        # screen. What belongs up here is the one thing the window cannot do
        # by itself: take the next version, of itself and of everything it
        # drives. It appears when there is one and is gone the rest of the
        # time, which makes its presence the message.
        # One place for all of them, not one offer per tab. Five
        # repositories each with their own "Update available" group meant
        # five places to look for the same answer, five passwords for one
        # evening's updates, and no way to see at a glance whether anything
        # was waiting at all. A count says that in one word.
        self.update_btn = Gtk.Button()
        zeile = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        zeile.append(Gtk.Image.new_from_icon_name("dialog-warning-symbolic"))
        self.update_label = Gtk.Label(label="")
        zeile.append(self.update_label)
        self.update_btn.set_child(zeile)
        self.update_btn.set_visible(False)
        self.update_btn.connect("clicked", lambda *_: self.ask_updates())
        header.pack_start(self.update_btn)


        page = Adw.PreferencesPage()

        # --- the switch itself ---
        grp = Adw.PreferencesGroup(title="Audio stack")
        self.switch_row = Adw.SwitchRow(
            title="PipeWire owns the HAL",
            subtitle="Off: PulseAudio, exactly as shipped",
        )
        self.switch_row.connect("notify::active", self.on_switch)
        grp.add(self.switch_row)

        # Echo during a call, above the switch that decides how long a
        # choice lasts - because that switch applies to this one too, and a
        # control has to sit above what qualifies it, not below.
        # MediaTek's dual-microphone method against noise and echo is
        # disabled for calls on this device although the chip could do it,
        # and this lays a modified tuning file over the vendor's.
        self.dmnr_row = Adw.SwitchRow(
            title="Handsfree echo suppression (DMNR)",
            subtitle="Vendor setting: off",
        )
        self.dmnr_row.connect("notify::active", self.on_dmnr)
        grp.add(self.dmnr_row)

        # One switch for both rows above it. Audio profile and echo
        # suppression are undone by a reboot in the same way and for the same
        # kind of reason - one is a set of masks, the other a bind mount - so
        # asking twice whether to keep them would be two questions about one
        # thing.
        self.persist_row = Adw.SwitchRow(
            title="Remember these choices",
            subtitle="Off: a reboot returns to the shipped state",
        )
        grp.add(self.persist_row)

        # Progress: deliberately pulsing instead of a percentage. Nobody
        # knows in advance how long the switch takes - audioctl waits up to 15
        # seconds for a sink. An invented percentage that gets stuck at 90 %
        # would be worse than none at all.
        self.progress = Gtk.ProgressBar(show_text=True, text="")
        self.progress.set_margin_top(6)
        self.progress.set_margin_bottom(6)
        self.progress.set_margin_start(12)
        self.progress.set_margin_end(12)
        self.progress_revealer = Gtk.Revealer(
            child=self.progress,
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            reveal_child=False,
        )
        grp.add(self.progress_revealer)
        page.add(grp)
        self._pulse_id = 0

        # --- what is actually running right now ---
        info = Adw.PreferencesGroup(title="Status")
        self.row_profile = Adw.ActionRow(title="Owns the Android HAL", subtitle="reading …")
        self.row_server = Adw.ActionRow(title="Sound server", subtitle="…")
        self.row_sinks = Adw.ActionRow(title="Outputs", subtitle="…")
        for row in (self.row_profile, self.row_server, self.row_sinks):
            row.set_subtitle_selectable(True)
            info.add(row)
        page.add(info)

        # --- what switches Bluetooth off behind everybody's back ---
        #
        # A group of its own, and deliberately not inside "Audio stack": the
        # switch above it that says how long a choice lasts does not apply
        # here. This one is a line in another program's config file and is
        # permanent the moment it is written.
        bt = Adw.PreferencesGroup(title="Bluetooth")
        self.btsave_row = Adw.SwitchRow(
            title="Bluetooth powersave",
            subtitle="reading …",
        )
        self.btsave_row.connect("notify::active", self.on_btsave)
        bt.add(self.btsave_row)
        page.add(bt)

        # --- last resort ---
        rescue, self.rescue_btn = self.build_restore_group(
            "Returns to the shipped state and sends sound to the speaker - "
            "audible volume, unmuted. This is also the one to press when you "
            "hear nothing at all.",
            self.on_rescue)
        page.add(rescue)

        # --- the pages ---
        #
        # One page is the app that existed before this. The second only comes
        # into being if modemctl is installed, and with a single page the
        # switcher bar stays hidden - so on a phone without the modem package
        # nothing about this window looks different from before.
        # Every tab exists, whether its tool does or not. A phone with only
        # audioctl used to show a single page and look like an app that can do
        # nothing else - the other three were missing without ever saying so.
        # Now the tab is there and says what it would need, where that comes
        # from and what it does, and offers to fetch it. What it does NOT show
        # is the rest of the page: switches and status rows for a tool that is
        # not there would be furniture with nothing behind it.
        self.stack = Adw.ViewStack()
        self.modem_rows = []
        self.gps_rows = []
        self.sw_rows = []
        self.batt_rows = []
        self.sec_rows = []
        self.comp_rows = {}
        # Kept, not local: a tool fetched from the components page gets its
        # real page built right there, and that needs the same builder.
        self.builders = {"audio": lambda: page,
                      "modem": self.build_modem_page,
                      "gps": self.build_gps_page,
                      "switches": self.build_switches_page,
                      "battery": self.build_battery_page,
                      "security": self.build_security_page}
        # One source of truth for "is this tool here", written down while the
        # pages are built and read by refresh() and by every handler
        # afterwards. Asked twice - once here, once from a module constant -
        # a page could end up unbuilt while something still asks its tool for
        # a status, and the answer would arrive at rows that were never
        # created.
        self.live = {}
        # The window itself is not among the tabs, so nothing below writes it
        # down - and an update of it has to know whether it is installed at
        # all before it offers to replace it.
        self.live["app"] = tools._tool_maybe(SELF["tool"])
        # The page widget of each tab, so one of them can be replaced later
        # without the others being rebuilt underneath somebody.
        self.pages = {}
        for comp in COMPONENTS:
            if not comp.get("needs", lambda: True)():
                continue
            self.build_component_page(comp)
        # Last, and not one of COMPONENTS: nothing to install, so it never
        # shows an offer and always has its real page.
        self.pages[OTHER_TAB[0]] = self.build_other_page()
        self.stack.add_titled_with_icon(self.pages[OTHER_TAB[0]], *OTHER_TAB)

        # Directly under the header, not at the foot of the window: the tabs
        # belong with the title of what they switch, and down there they sat
        # where a page's last control is - one thumb's width from "Restore
        # shipped state".
        self.switcher_bar = Adw.ViewSwitcherBar(stack=self.stack)
        self.switcher_bar.set_reveal(True)
        toolbar.add_top_bar(self.switcher_bar)

        self.toasts = Adw.ToastOverlay()
        self.toasts.set_child(self.stack)
        toolbar.set_content(self.toasts)
        self.set_content(toolbar)

        self.refresh()
        # Once per window, not on every refresh: this one goes to the network,
        # and a button people press to re-read their phone should not start
        # four connections every time.
        self.check_updates()

    RESTORE_TITLE = "Back to how it shipped"
    RESTORE_LABEL = "Restore shipped state"

    def build_restore_group(self, description, handler):
        """The group and the button; the caller adds the group to its page.

        The button asks before it acts. None of these four is a keystroke to
        take back: the audio one restarts the sound stack, the modem one takes
        the repairs out and leaves the phone without a network, the location
        one starts publishing an IP-derived position again, and the switches
        one takes the icons away. The question is the same everywhere, and it
        repeats the same words the group carries - nothing new to read at the
        moment of deciding.
        """
        grp = Adw.PreferencesGroup(title=self.RESTORE_TITLE,
                                   description=description)
        btn = self.pill_button(self.RESTORE_LABEL)
        btn.connect("clicked", lambda button:
                    self.confirm_restore(description, handler, button))
        grp.add(btn)
        return grp, btn

    def confirm_restore(self, body, handler, btn):
        """Ask first, act on "Restore" only.

        Cancel is the default and also what closing the dialog means, so a
        stray tap anywhere outside it does nothing at all.
        """
        self._restore_pending = (handler, btn)
        dlg = Adw.AlertDialog(heading=self.RESTORE_TITLE + "?", body=body)
        # Restore first, Cancel second - libadwaita stacks them the other way
        # round on a narrow screen, so this is what puts Cancel on top, under
        # the thumb, and the acting answer below it. Checked on the phone.
        dlg.add_response("restore", self.RESTORE_LABEL)
        dlg.add_response("cancel", "Cancel")
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        dlg.connect("response", self.on_restore_response)
        dlg.present(self)

    def on_restore_response(self, _dlg, response):
        handler, btn = self._restore_pending
        self._restore_pending = (None, None)
        if response == "restore" and handler is not None:
            handler(btn)


    def refresh(self):
        """Ask every tool whose page was actually built.

        self.live, not the module constants: a page that was not built has no
        rows for an answer to arrive at, and an answer that arrives anyway
        takes the callback down with an AttributeError nobody sees.
        """
        if self.live.get("audio"):
            process.run_async([self.live["audio"], "status"], self.on_status)
            dmnr = tools._tool_maybe(DMNR)
            if dmnr:
                process.run_async([dmnr, "status"], self.on_dmnr_status)
            else:
                # Same installer, so this only happens in the seconds after
                # one that stopped half way. The row says so and closes.
                self.on_dmnr_status(False, "")
        # No tool of its own and nothing to wait for: a file read, so the row
        # is right from the first frame instead of after the first answer.
        self.sync_btsave()
        if self.live.get("modem"):
            # Both read-only, and neither needs root - which is the whole
            # reason the page can show something before anybody touches it.
            process.run_async([self.live["modem"], "profile"], self.on_modem_profile)
            process.run_async([self.live["modem"], "status"], self.on_modem_status)
        if self.live.get("gps"):
            process.run_async([self.live["gps"], "profile"], self.on_gps_profile)
            process.run_async([self.live["gps"], "status"], self.on_gps_status)
            # Same installer as gpsctl, so this is normally there - and when
            # it is not, the row says so rather than showing a false "off".
            self.refresh_gps_contrib()
        if self.live.get("switches"):
            process.run_async([self.live["switches"], "status", "--json"],
                      self.on_switches_status)
            # Not a switch of its own any more: the icons are phosh's plugin
            # now, and this daemon is only what acts on the network switch.
            # The Network rows say it when it is not running.
            process.run_async(["systemctl", "--user", "is-active",
                       "killswitch-indicator"], self.on_indicator_active)
        if self.live.get("battery"):
            process.run_async([self.live["battery"], "status", "--json"],
                      self.on_battery_status)
            process.run_async(["systemctl", "--user", "is-active", BATTERY_UNIT],
                      self.on_battery_active)
            process.run_async(["systemctl", "--user", "is-enabled", BATTERY_UNIT],
                      self.on_battery_enabled)
        if self.live.get("security"):
            # One call for the whole page, and it needs no root: what is
            # configured, what the kernel says its values are, and what
            # listens. The one thing it cannot see unprivileged is whether
            # the table is loaded THIS second, and the page says so in those
            # words rather than guessing.
            process.run_async([self.live["security"], "status", "--json"],
                      self.on_security_status)

    def pulse_start(self, text):
        self.progress.set_text(text)
        self.progress.set_fraction(0.0)
        self.progress.pulse()
        self.progress_revealer.set_reveal_child(True)
        if self._pulse_id == 0:
            self._pulse_id = GLib.timeout_add(120, self._pulse_tick)

    def _pulse_tick(self):
        self.progress.pulse()
        return GLib.SOURCE_CONTINUE

    def pulse_stop(self):
        if self._pulse_id:
            GLib.source_remove(self._pulse_id)
            self._pulse_id = 0
        self.progress_revealer.set_reveal_child(False)

    def set_busy(self, busy):
        self.busy = busy
        self.switch_row.set_sensitive(not busy and self.audio_ok)
        self.persist_row.set_sensitive(not busy and self.audio_ok)
        self.dmnr_row.set_sensitive(not busy and self.dmnr_ok)
        self.btsave_row.set_sensitive(not busy and self.btsave_ok)
        # Sensitive only while there is something behind it. show_update_count
        # owns whether it is there at all; this owns whether it can be
        # pressed, and a batch that is running must not be started twice.
        self.update_btn.set_sensitive(not busy and bool(self.updates))
        self.rescue_btn.set_sensitive(not busy)
        # Empty when there is no modem page, which is the point: nothing here
        # may assume the second page exists.
        for row in self.modem_rows:
            row.set_sensitive(not busy and self.modem_ok)
        for row in self.gps_rows:
            row.set_sensitive(not busy and self.gps_ok)
        # The switches page has no tool state to be unsure about - the rows
        # are there or the page is not - so busy is the only thing that closes
        # them.
        for row in self.sw_rows:
            row.set_sensitive(not busy)
        # Same for the battery page: its rows exist only when battctl does.
        for row in self.batt_rows:
            row.set_sensitive(not busy)
        for row in self.sec_rows:
            row.set_sensitive(not busy)
        # Install and Update belong here for the same reason everything else
        # does: ONE hand on the sensitivity. run_component used to switch them
        # off itself and nothing switched them on again, so a single install -
        # the one that failed included - left every button on every tab dead
        # until the app was restarted. Reported from the phone on 14.9.2026.
        for rows in self.comp_rows.values():
            if rows.get("button") is not None:
                rows["button"].set_sensitive(not busy)
        if busy:
            self.switch_row.set_subtitle("Switching, this takes a moment …")
        elif not self.audio_ok:
            self.switch_row.set_subtitle("audioctl did not answer")
        elif self.switch_row.get_active():
            self.switch_row.set_subtitle("On: PipeWire talks to the HAL directly")
        else:
            self.switch_row.set_subtitle("Off: PulseAudio, exactly as shipped")

    def on_progress_line(self, line):
        """Shows the step audioctl is currently reporting - shortened so it
        fits on one line."""
        self.progress.set_text(line[:60])


    def toast(self, text):
        self.toasts.add_toast(Adw.Toast(title=text, timeout=4))

    def report(self, text):
        dlg = Adw.AlertDialog(heading="Something went wrong", body=text)
        dlg.add_response("ok", "Got it")
        dlg.present(self)


class App(Adw.Application):
    def __init__(self):
        super().__init__(application_id=APP_ID)

    def do_activate(self):
        win = self.props.active_window or Window(self)
        win.present()
