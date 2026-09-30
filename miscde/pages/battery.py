# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Battery page: what the battery icon is allowed to say."""

import json

from gi.repository import Adw, GLib, Gtk

from .. import original, process
from ..components import BATTERY_UNIT
from ..i18n import _


class BatteryPage:

    # What each option switches, what its switch says, and the thresholds it
    # owns. (config key, box heading, switch title, switch subtitle,
    # [(slider label, config key, from, to, step, digits, unit)]).
    #
    # The subtitle is None for all but one. The box heading already says
    # which state this is about and the switch says what happens in it, so
    # a line under it would be the same sentence a third time. The
    # exception is the option that takes something away: that cannot be
    # read off a switch, so it is said where it is decided.
    #
    # One box per option, and the sliders in the box with the switch they
    # belong to: in a single box the six of them read as one block of
    # furniture, and which pair belonged to which switch was a thing to work
    # out rather than to see.
    BATTERY_OPTIONS = (
        ("charging", _("While charging"), _("Colour the bolt"), None, (
            (_("Green"), "charge_green_w", 1.0, 12.0, 0.5, 1, "W"),
            (_("Amber"), "charge_amber_w", 0.5, 11.0, 0.5, 1, "W"))),
        ("level", _("Charge level"), _("Colour the filling"), None, (
            (_("Amber"), "level_amber_pct", 20.0, 95.0, 5.0, 0, "%"),
            (_("Red"), "level_red_pct", 5.0, 90.0, 5.0, 0, "%"))),
        ("discharging", _("Drain"), _("Colour the frame"), None, (
            (_("Amber"), "drain_amber_w", 0.5, 8.0, 0.5, 1, "W"),
            (_("Red"), "drain_red_w", 1.0, 12.0, 0.5, 1, "W"))),
        # No sliders on these two: there is nothing to set, only whether it
        # is shown.
        # It is shown by the phosh plugin, left of the battery icon; the
        # strip that stood in the percentage's place is gone. battctl
        # status says when the plugin is missing or not loaded yet.
        ("runtime", _("Time left"), _("Show it in the top bar"),
         _("how long the battery lasts, as 00:00, left of the battery icon"), ()),
        # Its own switch, not part of the one above: "how long does it last"
        # and "how long until it is full" are two questions, and somebody may
        # want one without the other. Off, there is no time while the cable
        # is in.
        ("charge_time", _("Charging time"), _("While the cable is in"),
         _("how long until full, in the same place - off, there is no time "
           "while charging"), ()),
    )

    # Which threshold has to stay below which, and by how much.
    BATTERY_PAIRS = (("charge_amber_w", "charge_green_w", 0.5),
                     ("level_red_pct", "level_amber_pct", 5.0),
                     ("drain_amber_w", "drain_red_w", 0.5))

    @staticmethod
    def threshold_text(value, digits, unit):
        """The number between - and +, with what it is measured in.

        Watts and percent in the same column of controls, and no sentence
        anywhere to say which is which - so each threshold carries its
        unit."""
        return _("%.*f %s") % (digits, value, unit)

    def build_stepper(self, adj, low, high, digits, unit):
        """- value + for one threshold, one step per tap.

        Not a slider: on the phone the page is scrolled with the same finger,
        and a swipe that began on a slider moved it - every threshold on the
        page shifted while somebody only wanted to get past them. A button
        acts on a tap alone; a swipe that starts on it belongs to the
        scrolling and changes nothing.
        """
        box = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        minus = Gtk.Button(icon_name="list-remove-symbolic",
                           tooltip_text=_("Lower"))
        plus = Gtk.Button(icon_name="list-add-symbolic",
                          tooltip_text=_("Higher"))
        value = Gtk.Label(width_chars=7)
        for btn in (minus, plus):
            btn.add_css_class("circular")
            btn.add_css_class("flat")
        minus.connect("clicked", lambda _b: adj.set_value(
            adj.get_value() - adj.get_step_increment()))
        plus.connect("clicked", lambda _b: adj.set_value(
            adj.get_value() + adj.get_step_increment()))

        def show(v):
            value.set_label(self.threshold_text(v, digits, unit))
            minus.set_sensitive(v > low)
            plus.set_sensitive(v < high)
        adj.connect("value-changed", lambda a: show(a.get_value()))
        show(low)
        for w in (minus, value, plus):
            box.append(w)
        return box

    def build_battery_page(self):
        """One box per option, and in it the sliders that decide it.

        No readings on this page. A watt figure belongs where somebody is
        measuring; here the question is only which colour appears when, and
        an answer to that is a slider, not a number to read off.

        The sliders sit under their own option and are revealed with it: a
        page that shows six of them at once asks to be studied, and this is
        a page to glance at.
        """
        bpage = Adw.PreferencesPage()
        self.batt_switches = {}
        self.batt_scales = {}
        self.batt_rows = []
        # What the file held at the last reading, and the thresholds moved
        # since then that are still waiting for their quiet moment.
        self.batt_cfg = None
        self._batt_pending = {}
        self._batt_write = 0

        # A box of its own for each, headed by what it is. Not one box with
        # a heading over the lot: that heading named the page rather than
        # anything a person decides, and the sliders of the third option sat
        # under the same card as the switch of the first.
        for key, heading, title, subtitle, sliders in self.BATTERY_OPTIONS:
            grp = Adw.PreferencesGroup(title=heading)
            # The subtitle goes in at construction, not afterwards: set
            # later it is invisible to the test that checks this page says
            # nothing it does not have to, and that test would go on passing
            # while the page filled up.
            row = (Adw.SwitchRow(title=title, subtitle=subtitle) if subtitle
                   else Adw.SwitchRow(title=title))
            row.connect("notify::active", self.on_battery_option, key)
            grp.add(row)
            self.batt_switches[key] = row
            self.batt_rows.append(row)

            row.slider_rows = []
            for label, ckey, low, high, step, digits, unit in sliders:
                scale = Gtk.Adjustment(value=low, lower=low, upper=high,
                                       step_increment=step)
                srow = Adw.ActionRow(title=label)
                srow.add_suffix(self.build_stepper(scale, low, high, digits, unit))
                scale.connect("value-changed", self.on_battery_slider, ckey)
                srow.set_visible(False)
                # Into the group as a row of its own, not into a revealer:
                # a PreferencesGroup sorts everything that is not a row to
                # the end, and the sliders then sat under the whole card
                # instead of under the switch they belong to. Seen on the
                # phone - it looked like a second, nameless block.
                grp.add(srow)
                row.slider_rows.append(srow)
                self.batt_scales[ckey] = scale
            bpage.add(grp)

        back, self.batt_restore_btn = self.build_restore_group(
            _("Stops the colouring and the time left, takes them out of the "
              "next boot and out of the top bar. What the battery reports is "
              "untouched - that is the kernel's."),
            self.on_battery_restore)
        bpage.add(back)
        self.batt_rows.append(self.batt_restore_btn)
        return bpage

    def on_battery_status(self, ok, out):
        """Follow battctl: which options are on, and where the sliders
        stand. Nothing else - the page shows no readings."""
        if not ok:
            for row in self.batt_switches.values():
                row.set_sensitive(False)
            return
        try:
            data = json.loads(out)
        except ValueError:
            return
        self.batt_cfg = data.get("config", {})
        self.sync_battery_switches()

    def sync_battery_switches(self):
        """Switch on means "this colour is happening" - which is the
        setting AND the service that acts on it.

        An option left on in the file while the daemon is stopped would
        show a switch that is on with nothing behind it, and this app's
        rule is to never claim more than it knows.
        """
        cfg = getattr(self, "batt_cfg", {})
        self._loading = True
        for key, _heading, _title, _subtitle, sliders in self.BATTERY_OPTIONS:
            row = self.batt_switches[key]
            on = bool(cfg.get(key)) and getattr(self, "batt_running", True)
            row.set_sensitive(True)
            row.set_active(on)
            self.show_sliders(row, on)
            for _label, ckey, _lo, _hi, _st, _di, _un in sliders:
                if ckey in cfg:
                    self.batt_scales[ckey].set_value(float(cfg[ckey]))
        self._loading = False

    def on_battery_active(self, ok, out):
        self.batt_running = ok and out.strip() == "active"
        if getattr(self, "batt_cfg", None) is not None:
            self.sync_battery_switches()

    def on_battery_enabled(self, ok, out):
        self.batt_enabled = ok and out.strip() == "enabled"

    def on_battery_option(self, row, _param, key):
        """One option on or off - and with it the service, which is the
        thing that actually does the colouring.

        No separate switch for "remember": an option somebody turns on is
        one they want after the next boot as well, and a page of three
        switches plus a fourth about the other three is exactly the kind of
        furniture this page is meant not to have.
        """
        if getattr(self, "_loading", False):
            return
        wanted = row.get_active()
        self.show_sliders(row, wanted)
        steps = [[self.live["battery"], "config", key,
                  "on" if wanted else "off"]]
        ident = original.unit_ident(BATTERY_UNIT)
        if wanted:
            # How the unit stood before this page first enabled it - known
            # from the last refresh; not known yet, nothing is written down
            # rather than a guess. Enabled while another option is already
            # on is this page's own doing from before records existed (or
            # battctl's, which enables it with an option too), not an
            # original.
            enabled = getattr(self, "batt_enabled", None)
            others = any(r.get_active() for k, r in self.batt_switches.items()
                         if k != key)
            if enabled is not None and not (enabled and others):
                try:
                    original.remember_unit(BATTERY_UNIT, enabled,
                                           getattr(self, "batt_running", False))
                except OSError:
                    pass
            steps.append(["systemctl", "--user", "enable", "--now",
                          BATTERY_UNIT])
        elif not any(r.get_active() for r in self.batt_switches.values()):
            # Nothing left to colour: the unit goes back to how it was
            # before this page first enabled it - disabled and stopped, as
            # battctl's installer leaves it, unless somebody had enabled it
            # themselves; that stays. Without a record, disabled as before.
            record = original.load(ident)
            if record is None or not record.get("enabled"):
                steps.append(["systemctl", "--user", "disable", "--now",
                              BATTERY_UNIT])
            original.forget(ident)
        self.run_chain(steps, lambda ok, out: self.after_battery(
            ok, out, "change"))

    @staticmethod
    def show_sliders(row, visible):
        """The two sliders of one option, shown with it."""
        for srow in getattr(row, "slider_rows", ()):
            srow.set_visible(visible)

    def on_battery_slider(self, scale, key):
        """A threshold moved. Written after a moment's quiet, not on every
        tap of a run of them - and the other threshold of the pair is pushed
        out of the way rather than refused, because battctl will not take a
        pair that crosses."""
        if getattr(self, "_loading", False):
            return
        self.keep_thresholds_apart(key)
        # Collected, not replaced: a tap on one threshold and then on another
        # inside the quiet moment used to cancel the first write outright.
        # Both of the pair, at the value they have NOW: a refresh that lands
        # inside the quiet moment puts the file's values back on screen, and
        # reading the steppers when the timer fires would then write nothing.
        for low, high, _gap in self.BATTERY_PAIRS:
            if key in (low, high):
                for one in (low, high):
                    self._batt_pending[one] = self.batt_scales[one].get_value()
        if self._batt_write:
            GLib.source_remove(self._batt_write)
        self._batt_write = GLib.timeout_add(400, self.write_battery_thresholds)

    def keep_thresholds_apart(self, key):
        """Push the neighbour along instead of refusing the move."""
        for low, high, gap in self.BATTERY_PAIRS:
            if key not in (low, high):
                continue
            lower_scale, upper_scale = self.batt_scales[low], self.batt_scales[high]
            if lower_scale.get_value() + gap > upper_scale.get_value():
                self._loading = True
                if key == low:
                    upper_scale.set_value(lower_scale.get_value() + gap)
                else:
                    lower_scale.set_value(upper_scale.get_value() - gap)
                self._loading = False

    def write_battery_thresholds(self):
        """Both thresholds of every pair that moved, in an order battctl takes.

        The neighbour that keep_thresholds_apart pushed along has to reach the
        file too. Written alone, the moved threshold crosses the neighbour's
        OLD value, and battctl checks every single write against the whole
        file: amber from 6.5 to 7 W with green at 7 W was refused with
        "charge_green_w must be above charge_amber_w" and the page jumped
        back - the push only ever happened on screen.

        The order keeps every state in between valid. If the upper one rises,
        it goes first and makes room; if it falls, the lower one has already
        moved out of its way. A value the file already has is not written.
        """
        self._batt_write = 0
        pending, self._batt_pending = self._batt_pending, {}
        cfg = self.batt_cfg or {}
        steps = []
        for low, high, _gap in self.BATTERY_PAIRS:
            if low not in pending or high not in pending:
                continue
            old_high = cfg.get(high)
            rises = old_high is None or pending[high] >= float(old_high)
            for key in ((high, low) if rises else (low, high)):
                value = pending[key]
                if cfg.get(key) is not None and float(cfg[key]) == value:
                    continue
                steps.append([self.live["battery"], "config", key, "%g" % value])
        if steps:
            self.run_chain(steps, lambda ok, out: self.after_battery(
                ok, out, "change"))
        return False

    def after_battery(self, ok, out, verb):
        if not ok:
            self.toast(_("Could not change the colouring"))
            if out:
                self.report(out)
        self.refresh()

    def on_battery_restore(self, _btn):
        """The service first, then the tool.

        In that order on purpose: battctl restore takes the colour, the
        time and the widget out of the bar, and a daemon still running
        would put them back within the minute.
        """
        if self.busy:
            return
        self.set_busy(True)
        self.run_chain([
            ["systemctl", "--user", "disable", "--now", BATTERY_UNIT],
            [self.live["battery"], "restore"],
        ], self.on_battery_restored)

    def on_battery_restored(self, ok, out):
        self.set_busy(False)
        if ok:
            self.toast(_("Shipped state - no colouring"))
        else:
            self.toast(_("Could not restore the shipped state"))
            self.report(out or _("No output."))
        self.refresh()
