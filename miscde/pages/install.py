# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Fetching a tool, and updating one - the app itself included.

The longest single subject in this app, and the one furthest from
any particular page: it builds the stand-in tab for a tool that is
missing, asks before it runs anything, drives the steps and swaps
the real page in when they are through."""

import os
import sys

from gi.repository import Adw, Gtk

from .. import askpass, components, process, tools
from ..components import (CLONE_HOME, COMPONENTS, SELF, behind_count,
                         clone_path, component_steps, installer_said,
                         source_steps)


class InstallPage:
    def build_component_page(self, comp):
        """Build one tab and put it in the stack: the real page if its tool is
        there, otherwise the one that offers to fetch it."""
        tool = tools._tool_maybe(comp["tool"])
        self.live[comp["key"]] = tool
        page = (self.build_page_with_update(comp, self.builders[comp["key"]])
                 if tool else self.build_missing_page(comp))
        self.pages[comp["key"]] = page
        self.stack.add_titled_with_icon(
            page, comp["key"], comp["page"], comp["icon"])
        return page

    def swap_in_page(self, comp):
        """Turn the "not installed" tab into the real one, without a restart.

        This used to be a sentence - "restart the app to get its tab" - and it
        was the whole answer somebody got after watching a clone, a build and
        an install go by. The tool is on the phone at that point; there is
        nothing left to wait for but the window.

        Adw.ViewStack can only append, so keeping Audio · Modem · GPS ·
        Switches in that order means taking the tabs after this one out and
        putting them back. The same widgets go back in, not rebuilt ones: they
        carry the status somebody has been reading, and a page that silently
        loses it is worse than one that never had it.
        """
        if self.live.get(comp["key"]) or not tools._tool_maybe(comp["tool"]):
            return False                       # already real, or still absent
        keys = [c["key"] for c in COMPONENTS]
        after = COMPONENTS[keys.index(comp["key"]):]
        for c in after:
            if self.pages.get(c["key"]) is not None:
                self.stack.remove(self.pages[c["key"]])
        self.build_component_page(comp)
        for c in after[1:]:
            # A tab that was never built has nothing to put back - the
            # Switches one is absent on a phone without the hardware.
            if self.pages.get(c["key"]) is None:
                continue
            self.stack.add_titled_with_icon(
                self.pages[c["key"]], c["key"], c["page"], c["icon"])
        # The tab somebody was standing on went out with the swap, so say
        # where to stand now: on the page they just installed.
        self.stack.set_visible_child_name(comp["key"])
        return True

    def pill_button(self, label):
        """The one button shape this app has: a pill, centred, with a line of
        air above it.

        Install, Update and the way back are built here, because they used to
        be the same four lines written out three times - and the Install
        button sat six pixels under the last row of the page, close enough to
        read as part of it rather than as the thing you press.
        """
        btn = Gtk.Button(label=label)
        btn.add_css_class("pill")
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_margin_top(18)
        btn.set_margin_bottom(6)
        return btn

    def build_missing_page(self, comp):
        """The page of a tool that is not here: what it would do, where it
        comes from, and one button.

        Nothing else. The switches and status rows of the real page would be
        furniture with nothing behind it - and a page full of greyed-out
        controls reads like a broken phone rather than a missing package.
        """
        page = Adw.PreferencesPage()
        grp = Adw.PreferencesGroup(
            title=comp["page"] + " · not installed",
            description="This tab drives " + comp["tool"] + ", and that is not "
            "on this phone. It can be fetched and installed from here; until "
            "then there is nothing to show.",
        )
        rows = {}
        rows["does"] = Adw.ActionRow(title="What it would do",
                                       subtitle=comp["does"])
        rows["from"] = Adw.ActionRow(title="Comes from", subtitle=comp["url"])
        rows["state"] = Adw.ActionRow(
            title="What will happen",
            subtitle=("fetched to " + clone_path(comp) + ", then "
                      + installer_said(comp))
            + (" - that one needs root, so sudo will ask for your password"
               if comp["root"] else " - no root needed"))
        for row in rows.values():
            row.set_subtitle_selectable(True)
            grp.add(row)
        btn = self.pill_button("Install")
        btn.connect("clicked", lambda _b, c=comp: self.ask_component(c, "install"))
        grp.add(btn)
        rows["button"] = btn
        self.comp_rows[comp["tool"]] = rows
        page.add(grp)
        return page

    def build_page_with_update(self, comp, build):
        """The real page, with a way to update what is behind it.

        The group is built hidden and only appears once someone has looked and
        found something: an "Update" that is always there says nothing, and an
        app that keeps offering an update it never checked for is worse than
        one that offers none.
        """
        page = build()
        grp = Adw.PreferencesGroup(title="Update available")
        grp.set_visible(False)
        row = Adw.ActionRow(title="What is new", subtitle="…")
        row.set_subtitle_selectable(True)
        grp.add(row)
        btn = self.pill_button("Update")
        btn.connect("clicked", lambda _b, c=comp: self.ask_component(
            c, self.comp_rows[c["tool"]].get("mode", "update")))
        grp.add(btn)
        self.comp_rows[comp["tool"]] = {"group": grp, "state": row,
                                        "button": btn}
        page.add(grp)
        return page

    def check_updates(self):
        """Ask, once per window, whether any of the installed tools has moved
        on. Bounded like every other call here - a phone in a tunnel must not
        be left with a page that says "checking" for ever."""
        for comp in COMPONENTS:
            if not tools._tool_maybe(comp["tool"]) or comp["tool"] not in self.comp_rows:
                continue
            self.look_for_update(comp)
        self.check_self_update()

    def look_for_update(self, comp, other=None):
        """Where an update for this component would come from, in the order
        that leaves other people's work alone: our own clone first, somebody
        else's only to read, and `other` when neither had anything to say."""
        mine = clone_path(comp) if components.is_clone(clone_path(comp)) else None
        if mine:
            self.check_component(comp, mine, other)
            return
        foreign_path = components.clone_elsewhere(comp["url"])
        if foreign_path:
            self.peek_upstream(comp, foreign_path, other)
        elif other:
            other()

    def check_self_update(self):
        """Is there a newer version of this window?

        Two questions, and on this phone only the second one ever has an
        answer: the clone here IS where the next version is written, so it is
        never behind the server. Asked in that order anyway, because on a
        phone that only ever installs what this app fetched, the first is the
        only one that can be true.
        """
        if not self.live.get("app"):
            return                             # not installed - nothing to replace
        self.look_for_update(SELF, self.check_app_program)

    def check_component(self, comp, mine, other=None):
        """Our own clone: fetch, then count what is waiting.

        `other` is asked when this found nothing - the second question some
        components have, and the place where "nothing new on the server" and
        "nothing to say at all" stop being the same sentence.
        """
        def counted(ok, out):
            behind = behind_count(out) if ok else None
            if behind:
                self.offer_update(comp, "%d new commit(s) in %s"
                                  % (behind, comp["url"]), mine)
            elif other:
                other()

        def fetched(ok, _out):
            if ok:
                process.run_async(["git", "-C", mine, "rev-list", "--count",
                           "HEAD..@{u}"], counted, timeout=30)
            elif other:
                other()

        process.run_async(["git", "-C", mine, "fetch", "--quiet"], fetched, timeout=60)

    def check_app_program(self, comp=SELF):
        """Is the program that is running the one the clone has?

        The git comparison answers a different question, and for this one
        component it is usually the wrong one: the clone on this phone is
        where the next version of the window is WRITTEN. It is never behind
        the server - what it is, regularly, is newer than the program that is
        installed, and until now the only way to close that gap was a
        terminal.

        Answered by comparing what is on disk, not by asking git: whether the
        clone is committed, pushed or dirty is a different matter entirely.

        Until 15.9.2026 that was one file against one file. The app is a
        package now, so it is a fingerprint of every .py in it against the
        same of the clone's - one changed line in any page still shows up,
        and a file added or removed does too, which a comparison of the
        launcher alone would have missed entirely.
        """
        source = (clone_path(comp) if components.is_clone_of(clone_path(comp), comp["url"])
                  else components.clone_elsewhere(comp["url"]))
        if not source or not self.live.get("app"):
            return
        theirs = tools.source_digest(os.path.join(source, "miscde"))
        ours = tools.source_digest(tools.PACKAGE_DIR)
        if theirs is None or ours is None:
            return                             # nothing to compare, nothing said
        if theirs != ours:
            self.offer_update(
                comp, "the misc-de in this clone is not the program that "
                "is running", source, "reinstall")

    def offer_update(self, comp, words, path, state="update"):
        """Show the group at the foot of the page, and say where it would
        pull. The path matters: it may be a clone somebody keeps themselves.

        The kind is remembered with it: "update" pulls and installs,
        "reinstall" only installs what the clone already has.
        """
        if comp["key"] == "app":
            return self.offer_self_update(words, path, state)
        rows = self.comp_rows[comp["tool"]]
        rows["path"] = path
        rows["mode"] = state
        rows["state"].set_subtitle(words + " · " + path)
        rows["group"].set_visible(True)
        rows["button"].set_sensitive(not self.busy)

    def offer_self_update(self, words, path, state="update"):
        """The window has no page of its own, so its offer is the icon in the
        header bar: it appears, and what it found is in its tooltip.

        Where it would pull from is remembered next to it, exactly as a page's
        offer remembers it - it may be a clone somebody keeps themselves.
        """
        self.comp_rows[SELF["tool"]] = {"path": path, "mode": state}
        self.update_btn.set_tooltip_text("Update this app: " + words + " · " + path)
        self.update_btn.set_visible(True)
        self.update_btn.set_sensitive(not self.busy)

    def ask_self_update(self):
        """The icon was pressed. Nothing happens yet: this replaces the
        program somebody is looking at, so it is asked first, in the same
        words and the same dialog every other component gets."""
        rows = self.comp_rows.get(SELF["tool"], {})
        self.ask_component(SELF, rows.get("mode", "update"))

    def peek_upstream(self, comp, foreign_path, other=None):
        """Is there something new for a clone we must not touch?

        Answered by asking the server what its HEAD is and comparing it with
        the clone's - "git ls-remote" writes nothing at all, not even the
        remote refs a fetch would update. Somebody else's working tree is read
        and nothing more; what to do about it is their business, in their
        terminal.
        """
        def compared(ok, out, theirs):
            ours = (out or "").strip().split()
            if not ok or not theirs or not ours or ours[0] == theirs:
                if other:
                    other()
                return                         # nothing to say, so nothing said
            self.offer_update(comp, "something new in " + comp["url"], foreign_path)

        def upstream_read(ok, out):
            head = (out or "").split()
            theirs = head[0] if ok and head else None
            process.run_async(["git", "-C", foreign_path, "rev-parse", "HEAD"],
                      lambda ok2, out2: compared(ok2, out2, theirs), timeout=30)

        process.run_async(["git", "ls-remote", comp["url"], "HEAD"], upstream_read,
                  timeout=60)

    def ask_component(self, comp, state):
        """Ask before fetching anything, and say exactly what will happen.

        Including the part that is easy to gloss over: this runs a script from
        the internet, and for three of the four it runs commands as root.
        """
        if self.busy:
            return
        path = self.comp_rows.get(comp["tool"], {}).get("path") or clone_path(comp)
        steps = [source_steps(comp, state, path)[1],
                    "run %s from that clone" % installer_said(comp)]
        text = "\n".join("%d. %s" % (n, t) for n, t in enumerate(steps, 1))
        body = text + "\n\nThat is code from the internet, running on this "
        if comp["root"]:
            body += ("phone. The installer writes to /usr/local, so sudo will "
                     "ask for your password below - it goes to sudo and "
                     "nowhere else, and the ticket is dropped when this is "
                     "done.")
        else:
            body += "phone. Nothing here needs root."
        if state == "update" and not path.startswith(CLONE_HOME):
            body += ("\n\nThis is your own clone. With anything uncommitted "
                     "in it, nothing is touched at all.")

        dlg = Adw.AlertDialog(heading=comp["tool"] + "?", body=body)
        entry = None
        if comp["root"]:
            entry = Adw.PasswordEntryRow(title="Your password (for sudo)")
            grp = Adw.PreferencesGroup()
            grp.add(entry)
            dlg.set_extra_child(grp)
        dlg.add_response("go", "Fetch and install" if state == "install"
                         else "Update")
        dlg.add_response("cancel", "Cancel")
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        self._comp_pending = (comp, state, entry, path)
        dlg.connect("response", self.on_component_response)
        dlg.present(self)

    def on_component_response(self, _dlg, response):
        comp, state, entry, path = self._comp_pending
        self._comp_pending = (None, None, None, None)
        if response != "go" or comp is None:
            return
        secret = entry.get_text() if entry is not None else None
        if entry is not None:
            entry.set_text("")               # not kept a moment longer
        self.run_component(comp, state, secret, path)

    def run_component(self, comp, state, secret, path=None):
        os.makedirs(CLONE_HOME, exist_ok=True)
        # Only where root is involved, and only for as long as this one chain
        # runs. Set up before the steps are built: the installer's step needs
        # the helper's path in it.
        self.askpass = askpass.Askpass(secret) if comp["root"] else None
        helper = self.askpass.start() if self.askpass else None
        steps = component_steps(comp, state, secret, path, helper)

        # A helper that could not be set up is not fatal - the install falls
        # back on sudo's ticket, which is where it was before this existed.
        # But it is the reason an install can stop at its first sudo line, so
        # it is said out loud rather than left to be guessed at.
        if self.askpass is not None and helper is None and self.askpass.error:
            self.component_says(comp, "no password helper: " + self.askpass.error)
        self.component_says(comp, "working …")
        self.set_busy(True)

        rest = list(steps)

        def step(ok=True, out=""):
            if not ok or not rest:
                self.component_done(comp, ok, out)
                return
            argv, stdin, cwd, env = rest.pop(0)
            self.component_says(comp, argv[0] + " …")
            # The installer gets its own patience. A clone or a pull is over
            # in seconds, but an installer may have to fetch build packages
            # over a phone connection and compile something afterwards - the
            # audio one builds an SPA plugin - and a wait that runs out mid
            # apt-get leaves a half-installed system behind.
            deadline = 1800 if argv[0].endswith("install.sh") else 600

            def said(line, page=comp):
                # This is the longest thing the app ever starts - half an
                # hour for the audio installer, which fetches build packages
                # and compiles an SPA plugin. Until 15.9.2026 the row said
                # "./install.sh …" for all of it and nothing else, while a
                # three-second audio switch reported line by line: the wait
                # with the least to show for it was the one that looked most
                # like a hang. Same shortening as on_progress_line - a row
                # subtitle holds about that much.
                self.component_says(page, line[:60])

            process.run_async(argv, step, timeout=deadline, cwd=cwd, stdin=stdin,
                      env=env, on_line=said)

        step()

    def component_says(self, comp, words):
        """Where a running fetch reports: the row on the tool's page, or - for
        the window itself, which has no page - the tooltip of the icon that
        offered the update. Something has to carry it, and a window that goes
        busy for two minutes without a word reads as one that has hung."""
        row = self.comp_rows.get(comp["tool"], {}).get("state")
        if row is not None:
            row.set_subtitle(words)
        else:
            self.update_btn.set_tooltip_text(words)

    def component_done(self, comp, ok, out):
        # First thing, before anything can return early: socket down, helper
        # deleted, password forgotten. Every way out of an install comes
        # through here, the ones that failed and the one that timed out
        # included.
        if getattr(self, "askpass", None) is not None:
            self.askpass.stop()
            self.askpass = None
        self.set_busy(False)
        if ok and self.live.get(comp["key"]):
            # An update: the page was already the real one, so nothing is
            # swapped - what changes is the offer, which has just been taken
            # and would otherwise go on offering the same commits.
            group = self.comp_rows.get(comp["tool"], {}).get("group")
            if group is not None:
                group.set_visible(False)
            if comp["key"] == "app":
                # The icon goes with the offer it carried; it comes back the
                # next time somebody looks and finds something.
                self.update_btn.set_visible(False)
                # The one update that cannot take effect by itself: the new
                # program is on disk and this window is the old one.
                self.ask_restart()
            else:
                self.toast(comp["tool"] + " is up to date")
        elif ok:
            # The page first, the words after it: if the tab is already the
            # real one by the time the toast is read, the sentence is a
            # description and not a promise.
            if self.swap_in_page(comp):
                self.toast(comp["tool"] + " is in place - this tab is live")
            else:
                # Everything ran and the tool is still not findable. There is
                # no sentence this window can invent that beats what the
                # installer said, so show that.
                self.toast(comp["tool"] + " ran, but is not on the phone")
                self.report(out or "No output.")
        else:
            self.toast("Could not set up " + comp["tool"])
            # A wrong password shows up here as sudo's own words, which say it
            # better than anything this window could invent.
            self.report(out or "No output.")
        self.refresh()

    def restart_self(self):
        """Replace this process with the program that was just installed.

        execv and not "start a copy, then quit": the application id makes a
        second instance hand its activation to the one already running, so the
        copy would present the OLD window and then die with it. Replacing the
        image keeps the pid, releases the bus name with the connection, and
        the new program takes the same place in the shell.
        """
        prog = tools._tool_maybe("misc-de") or os.path.abspath(sys.argv[0])
        try:
            os.execv(prog, [prog])
        except OSError as err:                 # then at least say so
            self.toast("Could not restart: " + str(err))

    def ask_restart(self):
        """An update is on disk; this window is still the old program."""
        dlg = Adw.AlertDialog(
            heading="Updated",
            body="The new version is installed. This window is still running "
                 "the old one - restarting takes a second.")
        dlg.add_response("now", "Restart now")
        dlg.add_response("later", "Later")
        dlg.set_default_response("now")
        dlg.set_close_response("later")
        dlg.connect("response", lambda _d, answer:
                    self.restart_self() if answer == "now" else None)
        dlg.present(self)
