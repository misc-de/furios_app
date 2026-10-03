# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Security page: locks for a kernel that gets no more fixes, and one
for the lock screen."""


from gi.repository import Adw, Gtk

from .. import faults, process, tools
from ..i18n import _


class SecurityPage:
    # The three parts, in the order secctl applies them, with the words this
    # page says about each. Kept here rather than built inline because the
    # subtitle of a switch has to change with the reading while its title
    # must not, and the two are easy to tangle when they are written apart.
    PARTS = (
        ("sysctl", _("Kernel settings"),
         _("unprivileged BPF, dmesg, kernel pointers, ptrace")),
        ("modules", _("Block unused modules"),
         _("protocol families and filesystems nothing here uses")),
        ("lockout", _("Lock screen lockout"),
         _("3 wrong PINs lock it: 5 min, then 10, 15, 30, 60 and longer")),
    )

    def build_security_page(self):
        """What is switched on, and what is exposed.

        No kernel line: the switches are worth having on any phone,
        whatever kernel it boots.
        """
        page = Adw.PreferencesPage()

        # One group, not two, and no paragraph under the heading: a group
        # with a description draws its title higher than one without, and a
        # single explanatory line here would put this tab's heading twelve
        # pixels above every other tab's. What needs saying sits in the row
        # it is about.
        grp = Adw.PreferencesGroup(title=_("Hardening"))
        self.sec_group = grp
        # No firewall here any more (removed 28.9. on request), and with it
        # the home network it needed. secctl still has both for the command
        # line; "revert all" below still takes a firewall out if one is on.
        self.sec_switches = {}
        for key, title, subtitle in self.PARTS:
            row = Adw.SwitchRow(title=title, subtitle=subtitle)
            row.connect("notify::active", self.on_security_switch, key)
            grp.add(row)
            self.sec_switches[key] = row
        page.add(grp)

        back, self.sec_restore_btn = self.build_restore_group(
            _("Takes everything back out: the sysctl file, the module blocks "
            "and the lock-screen lockout. One "
            "value stays until the next boot - the kernel will not let "
            "unprivileged BPF be re-enabled while it runs, which is by "
            "design and not a fault here."),
            self.on_security_restore)
        page.add(back)

        self.sec_rows = [self.sec_restore_btn]
        self.sec_rows += list(self.sec_switches.values())
        return page

    # ---------------------------------------------------------------- reading

    def on_security_status(self, ok, out):
        if not ok:
            self.say_security_unread(_("secctl did not answer"))
            return
        data = process.json_object(out)
        if data is None:
            self.say_security_unread(_("unreadable answer"))
            return

        # No "Listening" list any more (removed 28.9. on request): the
        # exposure part of the answer is still there for "secctl status".
        self.say_security_parts(data.get("parts", {}))

    def say_security_unread(self, why):
        """A reading that did not happen, said on the rows that are readings.

        Silence would be the dangerous answer here: three switches sitting
        at off look exactly like a phone with nothing switched on, and this
        page is where somebody checks that. So every row that means "this is
        what secctl reported" says instead that secctl reported nothing.
        """
        for row in self.sec_switches.values():
            row.set_subtitle(why)

    @staticmethod
    def lockout_subtitle(part, subtitle):
        """The lock screen tells nobody why a right PIN is refused - phosh
        does not show PAM's messages - so this row is where it is said."""
        if not part.get("module", True):
            return _("not installed - run the security install again")
        user = part.get("user") or {}
        left = user.get("locked_for") or 0
        if part.get("state") == "on" and left:
            return _("Locked right now, %d:%02d left") % divmod(left, 60)
        return subtitle

    def say_security_parts(self, parts):
        # _loading, the way every other page here does it: set_active fires
        # notify::active, and without the guard reading the state would
        # switch the thing being read.
        self._loading = True
        shown = 0
        for key, _title, subtitle in self.PARTS:
            part = parts.get(key, {})
            row = self.sec_switches[key]
            state = part.get("state")
            row.set_active(state == "on")
            self.offer("security-" + key, row,
                       state in ("on", "partial"), self.hardening_missing(key, part))
            shown += ("security-" + key) in self.offered()
            if key == "sysctl" and state == "partial":
                row.set_subtitle(_("some values did not take - press twice to "
                                 "write them again"))
            elif key == "modules":
                blocked = sum(1 for v in (part.get("modules") or {}).values()
                              if v)
                row.set_subtitle(_("%d of %d blocked") % (blocked,
                                                       part.get("count", 0))
                                 if state == "on" else subtitle)
            elif key == "lockout":
                row.set_subtitle(self.lockout_subtitle(part, subtitle))
            else:
                row.set_subtitle(subtitle)
        self._loading = False
        # A heading over nothing would be a group that offers nothing.
        self.sec_group.set_visible(shown > 0)

    @staticmethod
    def hardening_missing(key, part):
        """Whether the part's fault is there, for offer()."""
        if not part:
            return False
        if key == "sysctl":
            return faults.sysctl_open(part)
        if key == "modules":
            return faults.modules_loadable(part)
        if key == "lockout":
            return faults.pin_tries_unlimited()
        return False

    # ---------------------------------------------------------------- acting

    def no_pkexec(self):
        """The modem and GPS pages ask this too. Without it argv[0] is None,
        Gio refuses it with a TypeError rather than a GLib.Error, run_async
        does not catch that - and set_busy(True) has already happened, so
        the whole window stayed grey for good."""
        if tools.PKEXEC:
            return False
        self.toast(_("pkexec is missing - cannot ask for the rights to switch"))
        # The switch has already moved under the finger; put it back to
        # what secctl says rather than leave it claiming a change.
        self.refresh()
        return True

    def on_security_switch(self, row, _param, key):
        if getattr(self, "_loading", False) or self.busy:
            return
        if self.no_pkexec():
            return
        value = "on" if row.get_active() else "off"
        self.set_busy(True)
        process.run_async(
            [tools.PKEXEC, self.live["security"], "set", key, value],
            lambda ok, out: self.after_security(ok, out, key, value))

    def after_security(self, ok, out, key, value):
        self.set_busy(False)
        if not ok:
            self.toast(_("Could not switch {part} {state}").format(
                part=key, state=_("on") if value == "on" else _("off")))
            # secctl's refusals are sentences, not error codes.
            if out and out.strip():
                self.report(out.strip())
        self.refresh()

    def on_security_restore(self, _btn):
        if self.busy or self.no_pkexec():
            return
        self.set_busy(True)
        process.run_async(
            [tools.PKEXEC, self.live["security"], "revert", "all"],
            self.on_security_restored)

    def on_security_restored(self, ok, out):
        self.set_busy(False)
        if ok:
            self.toast(_("Shipped state - nothing of ours is left in /etc"))
        else:
            self.toast(_("Could not take it back out"))
            self.report(out or _("No output."))
        self.refresh()
