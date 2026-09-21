# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Security page: three locks for a kernel that gets no more fixes."""

import json

from gi.repository import Adw, Gtk

from .. import process, tools


class SecurityPage:
    # The three parts, in the order secctl applies them, with the words this
    # page says about each. Kept here rather than built inline because the
    # subtitle of a switch has to change with the reading while its title
    # must not, and the two are easy to tangle when they are written apart.
    PARTS = (
        ("sysctl", "Kernel settings",
         "unprivileged BPF, dmesg, kernel pointers, ptrace"),
        ("modules", "Block unused modules",
         "protocol families and filesystems nothing here uses"),
        ("firewall", "Firewall",
         "one input chain, default drop"),
    )

    def build_security_page(self):
        """What is switched on, and what is exposed.

        No kernel line. The version and its end of life were at the top as
        the premise for the three switches, and they took a paragraph to
        say something nobody can act on from here - the switches are worth
        having on any phone, whatever kernel it boots. It is still in
        `secctl status` for anyone who wants the reasoning.
        """
        page = Adw.PreferencesPage()

        # One group, not two, and no paragraph under the heading: a group
        # with a description draws its title higher than one without, and a
        # single explanatory line here would put this tab's heading twelve
        # pixels above every other tab's. What needs saying sits in the row
        # it is about.
        grp = Adw.PreferencesGroup(title="Hardening")
        self.sec_switches = {}
        for key, title, subtitle in self.PARTS:
            row = Adw.SwitchRow(title=title, subtitle=subtitle)
            row.connect("notify::active", self.on_security_switch, key)
            grp.add(row)
            self.sec_switches[key] = row

        # Directly under the firewall switch, because it is the firewall's
        # one setting and the only value on this page that belongs to this
        # phone alone. An entry rather than anything automatic: a wrong
        # answer here is what locks somebody out of their own phone, so it
        # is typed, looked at and confirmed.
        self.sec_lan = Adw.EntryRow(title="Home network, e.g. 192.168.0.0/24")
        self.sec_lan.set_show_apply_button(True)
        self.sec_lan.connect("apply", self.on_security_lan)
        grp.add(self.sec_lan)
        page.add(grp)

        # What the chain is actually for. A firewall with nothing listening
        # behind it is theatre, and this is the row that says which it is.
        self.sec_open = Adw.PreferencesGroup(title="Listening")
        self.sec_open_rows = []
        self.sec_open_empty = Adw.ActionRow(title="reading …")
        self.sec_open.add(self.sec_open_empty)
        page.add(self.sec_open)

        back, self.sec_restore_btn = self.build_restore_group(
            "Takes all three back out: the sysctl file, the module blocks and "
            "the firewall, with the original /etc/nftables.conf put back. One "
            "value stays until the next boot - the kernel will not let "
            "unprivileged BPF be re-enabled on a running 4.19, which is by "
            "design and not a fault here.",
            self.on_security_restore)
        page.add(back)

        self.sec_rows = [self.sec_lan, self.sec_restore_btn]
        self.sec_rows += list(self.sec_switches.values())
        return page

    # ---------------------------------------------------------------- reading

    def on_security_status(self, ok, out):
        if not ok:
            self.say_security_unread("secctl did not answer")
            return
        try:
            data = json.loads(out)
        except ValueError:
            self.say_security_unread("unreadable answer")
            return

        self.say_security_parts(data.get("parts", {}))
        self.say_security_open(data.get("exposure", {}),
                               data.get("parts", {}).get("firewall", {}))

    def say_security_unread(self, why):
        """A reading that did not happen, said on the rows that are readings.

        Silence would be the dangerous answer here: three switches sitting
        at off look exactly like a phone with nothing switched on, and this
        page is where somebody checks that. So every row that means "this is
        what secctl reported" says instead that secctl reported nothing.
        """
        for row in self.sec_switches.values():
            row.set_subtitle(why)
        for row in self.sec_open_rows:
            self.sec_open.remove(row)
        self.sec_open_rows = []
        self.sec_open_empty.set_title(why)
        self.sec_open_empty.set_visible(True)

    def say_security_parts(self, parts):
        # _loading, the way every other page here does it: set_active fires
        # notify::active, and without the guard reading the state would
        # switch the thing being read.
        self._loading = True
        for key, _title, subtitle in self.PARTS:
            part = parts.get(key, {})
            row = self.sec_switches[key]
            state = part.get("state")
            row.set_active(state == "on")
            if key == "sysctl" and state == "partial":
                row.set_subtitle("some values did not take - press twice to "
                                 "write them again")
            elif key == "modules":
                blocked = sum(1 for v in (part.get("modules") or {}).values()
                              if v)
                row.set_subtitle("%d of %d blocked" % (blocked,
                                                       part.get("count", 0))
                                 if state == "on" else subtitle)
            elif key == "firewall":
                row.set_subtitle(self.firewall_subtitle(part, subtitle))
            else:
                row.set_subtitle(subtitle)
        self._loading = False

        lan = (parts.get("firewall") or {}).get("lan") or ""
        # Only when it is not being typed in: writing into the entry under
        # somebody's fingers during a refresh is how a half-typed network
        # gets thrown away.
        if not self.sec_lan.has_focus():
            self.sec_lan.set_text(lan)

    def firewall_subtitle(self, part, fallback):
        if not part.get("lan"):
            return "needs the home network below before it can come up"
        if part.get("state") == "on":
            live = part.get("live")
            return ("rules load at boot" if live is None else
                    "loaded, and back after a reboot" if live else
                    "set to load at boot, but not loaded right now")
        return fallback

    def say_security_open(self, exposure, firewall):
        """What listens outside loopback, and whether the chain covers it."""
        for row in self.sec_open_rows:
            self.sec_open.remove(row)
        self.sec_open_rows = []

        if not exposure.get("readable"):
            self.sec_open_empty.set_title("could not be read")
            self.sec_open_empty.set_visible(True)
            return
        open_ports = exposure.get("open") or []
        if not open_ports:
            self.sec_open_empty.set_title("nothing listens outside loopback")
            self.sec_open_empty.set_visible(True)
            return

        self.sec_open_empty.set_visible(False)
        on = firewall.get("state") == "on"
        # Four at most. This is a phone screen, and the list is here to make
        # a point, not to be an inventory - "ss -tulnp" is where somebody
        # goes who wants all of them.
        for entry in open_ports[:4]:
            row = Adw.ActionRow(
                title="%s %s:%s" % (entry.get("proto", ""),
                                    entry.get("addr", ""),
                                    entry.get("port", "")),
                subtitle=("reachable only from the home network"
                          if on else "reachable from every network this "
                          "phone joins, mobile included"))
            self.sec_open.add(row)
            self.sec_open_rows.append(row)
        if len(open_ports) > 4:
            row = Adw.ActionRow(title="and %d more" % (len(open_ports) - 4),
                                subtitle="ss -tulnp")
            row.set_subtitle_selectable(True)
            self.sec_open.add(row)
            self.sec_open_rows.append(row)

    # ---------------------------------------------------------------- acting

    def on_security_switch(self, row, _param, key):
        if getattr(self, "_loading", False) or self.busy:
            return
        value = "on" if row.get_active() else "off"
        self.set_busy(True)
        process.run_async(
            [tools.PKEXEC, self.live["security"], "set", key, value],
            lambda ok, out: self.after_security(ok, out, key, value))

    def after_security(self, ok, out, key, value):
        self.set_busy(False)
        if not ok:
            self.toast("Could not switch %s %s" % (key, value))
            # The reason matters here more than anywhere else on this page:
            # the firewall refuses to come up without a home network, and
            # that refusal is a sentence, not an error code.
            if out and out.strip():
                self.report(out.strip())
        self.refresh()

    def on_security_lan(self, entry):
        """The network, written and - if the chain is already up - applied.

        secctl validates it as CIDR and refuses anything else, so a typo
        cannot become a rule. What it does not do is switch the firewall on:
        naming your network is not asking for the chain.
        """
        if self.busy:
            return
        text = entry.get_text().strip()
        if not text:
            return
        self.set_busy(True)
        process.run_async(
            [tools.PKEXEC, self.live["security"], "lan", text],
            self.after_security_lan)

    def after_security_lan(self, ok, out):
        self.set_busy(False)
        if not ok:
            self.toast("Not a network in CIDR form")
            if out and out.strip():
                self.report(out.strip())
        self.refresh()

    def on_security_restore(self, _btn):
        if self.busy:
            return
        self.set_busy(True)
        process.run_async(
            [tools.PKEXEC, self.live["security"], "revert", "all"],
            self.on_security_restored)

    def on_security_restored(self, ok, out):
        self.set_busy(False)
        if ok:
            self.toast("Shipped state - nothing of ours is left in /etc")
        else:
            self.toast("Could not take it back out")
            self.report(out or "No output.")
        self.refresh()
