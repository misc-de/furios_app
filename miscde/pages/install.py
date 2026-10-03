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
from .other import TAB as OTHER_TAB
from ..components import (CLONE_HOME, COMPONENTS, PHOSH, SELF, behind_count,
                         clone_path, component_steps, find_component,
                         installer_said, source_steps)
from ..i18n import _


class InstallPage:
    def build_component_page(self, comp):
        """Build one tab and put it in the stack: the real page if its tool is
        there, otherwise the one that offers to fetch it."""
        tool = tools._tool_maybe(comp["tool"])
        self.live[comp["key"]] = tool
        page = (self.builders[comp["key"]]() if tool
                else self.build_missing_page(comp))
        self.pages[comp["key"]] = page
        self.stack.add_titled_with_icon(
            page, comp["key"], _(comp["page"]), comp["icon"])
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
        # The Other tab sits behind all of them and has to go back last.
        tail = [(c["key"], _(c["page"]), c["icon"]) for c in after[1:]]
        tail.append(OTHER_TAB)
        for key in [c["key"] for c in after] + [OTHER_TAB[0]]:
            if self.pages.get(key) is not None:
                self.stack.remove(self.pages[key])
        self.build_component_page(comp)
        for key, title, icon in tail:
            # A tab that was never built has nothing to put back - the
            # Switches one is absent on a phone without the hardware.
            if self.pages.get(key) is None:
                continue
            self.stack.add_titled_with_icon(self.pages[key], key, title, icon)
        # The tab somebody was standing on went out with the swap, so say
        # where to stand now: on the page they just installed.
        self.stack.set_visible_child_name(comp["key"])
        self.mark_installed(comp["key"])
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
            title=_("{page} · not installed").format(page=_(comp["page"])),
            description=_("This tab drives {tool}, and that is not on this "
                          "phone. It can be fetched and installed from here; "
                          "until then there is nothing to show.").format(
                              tool=comp["tool"]),
        )
        rows = {}
        rows["does"] = Adw.ActionRow(title=_("What it would do"),
                                       subtitle=_(comp["does"]))
        rows["from"] = Adw.ActionRow(title=_("Comes from"), subtitle=comp["url"])
        rows["state"] = Adw.ActionRow(
            title=_("What will happen"),
            subtitle=(_("fetched to {path}, then {installer} - that one needs "
                        "root, so sudo will ask for your password")
                      if comp["root"] else
                      _("fetched to {path}, then {installer} - no root needed")
                      ).format(path=clone_path(comp),
                               installer=installer_said(comp)))
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

    def check_updates(self):
        """Ask, once per window, whether anything has moved on - every tool
        and this app.

        One pass, one answer. Each check reports into self.updates as it
        comes back, so the count in the header grows while the checks are
        still running rather than appearing all at once at the end.

        Bounded like every other call here: a phone in a tunnel must not be
        left with a window that says "checking" for ever.
        """
        self.updates = {}
        self.show_update_count()
        for comp in COMPONENTS + [PHOSH]:
            if not find_component(comp):
                continue
            self.look_for_update(comp)
        self.check_self_update()

    def show_update_count(self):
        """The one thing the header says: how many, or nothing at all.

        Nothing at all when there are none - a button that is always there,
        reading "0 Updates", would be furniture. Its presence is the message.
        """
        count = len(self.updates)
        self.update_label.set_text(
            _("%d Update") % count if count == 1 else _("%d Updates") % count)
        self.update_btn.set_visible(count > 0)
        self.update_btn.set_sensitive(count > 0 and not self.busy)

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
                self.offer_update(comp, _("%d new commit(s)") % behind, mine)
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
                comp, _("the misc-de in this clone is not the program that "
                        "is running"), source, "reinstall")

    def offer_update(self, comp, words, path, state="update"):
        """Write down that this one has something waiting, and count it.

        The path matters and is kept: it may be a clone somebody keeps
        themselves. So is the kind - "update" pulls and installs, "reinstall"
        only installs what the clone already has, which is the usual answer
        for this app on this phone.
        """
        self.updates[comp["tool"]] = {"comp": comp, "words": words,
                                      "path": path, "mode": state}
        self.show_update_count()

    def peek_upstream(self, comp, foreign_path, other=None):
        """Is there something new for a clone we must not touch?

        Answered by asking the server what its HEAD is and whether the clone
        already contains it - "git ls-remote" writes nothing at all, not even
        the remote refs a fetch would update. Somebody else's working tree is
        read and nothing more; what to do about it is their business, in their
        terminal.

        Contained, not equal. The clones in ~/Projekte are where the next
        commits are written, and they are regularly ahead of the server with
        work not pushed yet. A hash comparison called that "something new on
        the server" - furios_misc three commits ahead of origin put a battctl
        update in the header that pulled nothing. `merge-base --is-ancestor`
        fails for a commit the clone does not have, which is exactly the case
        that is news.
        """
        def compared(ok, _out):
            if ok:
                if other:
                    other()
                return                         # nothing to say, so nothing said
            self.offer_update(comp, _("something new on the server"), foreign_path)

        def upstream_read(ok, out):
            head = (out or "").split()
            theirs = head[0] if ok and head else None
            if not theirs:
                if other:
                    other()
                return
            process.run_async(["git", "-C", foreign_path, "merge-base",
                               "--is-ancestor", theirs, "HEAD"],
                              compared, timeout=30)

        process.run_async(["git", "ls-remote", comp["url"], "HEAD"], upstream_read,
                  timeout=60)

    def ask_updates(self):
        """The count was pressed: say which, and ask once.

        Once is the point. Before this, four tools with updates meant four
        dialogs and four passwords for what is one decision - "take what is
        waiting". The password is asked here and reaches sudo through the
        same pipe and the same socket a single install uses; it is dropped
        when the last one is done.
        """
        if self.busy or not self.updates:
            return
        waiting = list(self.updates.values())
        missing = []
        for u in waiting:
            missing += [p for p in components.missing_packages(u["comp"])
                        if p not in missing]
        if missing:
            self.say_missing_packages(missing)
            return
        # Just the names: how many commits, or why the app counts, is detail
        # nobody decides on - the answer is the same "take what is waiting".
        lines = ["• %s" % u["comp"]["tool"] for u in waiting]
        root = any(u["comp"]["root"] for u in waiting)
        body = "\n".join(lines)        # the button says it restarts

        dlg = Adw.AlertDialog(
            heading=(_("1 update") if len(waiting) == 1
                     else _("%d updates") % len(waiting)),
            body=body)
        entry = None
        if root:
            entry = Adw.PasswordEntryRow(title=_("Your password (for sudo)"))
            grp = Adw.PreferencesGroup()
            grp.add(entry)
            dlg.set_extra_child(grp)
        dlg.add_response("go", _("Update and restart"))
        dlg.add_response("cancel", _("Cancel"))
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        self._updates_pending = entry
        dlg.connect("response", self.on_updates_response)
        dlg.present(self)

    def on_updates_response(self, _dlg, response):
        entry = self._updates_pending
        self._updates_pending = None
        if response != "go":
            return
        secret = entry.get_text() if entry is not None else None
        if entry is not None:
            entry.set_text("")               # not kept a moment longer
        self.run_updates(secret)

    def run_updates(self, secret):
        """Every waiting update, one after the other, under one password.

        One Askpass for the lot rather than one each: it is the socket sudo
        asks at, and setting it up per tool would mean the password being
        handed over four times for one decision. Each tool still drops its
        own ticket at the end of its own steps, and forget_password drops it
        when a failure stopped the chain before that step.
        """
        if self.busy or not self.updates:
            return
        waiting = list(self.updates.values())
        missing = []
        for u in waiting:
            missing += [p for p in components.missing_packages(u["comp"])
                        if p not in missing]
        if missing:
            self.say_missing_packages(missing)
            return
        os.makedirs(CLONE_HOME, exist_ok=True)
        root = any(u["comp"]["root"] for u in waiting)
        self.askpass = askpass.Askpass(secret) if root else None
        helper = self.askpass.start() if self.askpass else None
        if self.askpass is not None and helper is None and self.askpass.error:
            self.toast(_("no password helper: {error}").format(
                error=self.askpass.error))

        rest = []
        for u in waiting:
            for step in component_steps(u["comp"], u["mode"], secret,
                                           u["path"], helper):
                rest.append((u["comp"], step))
        self.set_busy(True)
        self.update_progress(_("working …"))

        def step(ok=True, out=""):
            if not ok or not rest:
                self.updates_done(ok, out)
                return
            comp, (argv, stdin, cwd, env) = rest.pop(0)
            self.update_progress(comp["tool"] + ": " + argv[0])
            # The installer gets its own patience. A clone or a pull is over
            # in seconds, but an installer may have to fetch build packages
            # over a phone connection and compile something afterwards - the
            # audio one builds an SPA plugin - and a wait that runs out mid
            # apt-get leaves a half-installed system behind.
            deadline = 1800 if argv[0].endswith("install.sh") else 600
            process.run_async(argv, step, timeout=deadline, cwd=cwd,
                              stdin=stdin, env=env,
                              on_line=lambda line, c=comp: self.update_progress(
                                  c["tool"] + ": " + line[:40]))

        step()

    def update_progress(self, words):
        """Where a running batch reports.

        The header button, because that is where the offer was and there is
        nowhere else left: the pages have no update groups any more. A window
        that goes busy for half an hour without a word reads as one that has
        hung.
        """
        self.update_label.set_text(words[:48])
        self.update_btn.set_tooltip_text(words)

    def forget_password(self, ok):
        """Socket down, helper gone - and after a failure the ticket too.

        The chain ends in "sudo -k", but a chain stops at its first failing
        step: an installer that failed or ran out of time never reached it,
        and the ticket "sudo -S -v" took stayed valid for its full timeout.
        Every "sudo -n" switch in this window would have gone through as root
        without a question in that time. Only after a failure: on success the
        chain's own last step has already dropped it.
        """
        if getattr(self, "askpass", None) is None:
            return
        self.askpass.stop()
        self.askpass = None
        if not ok:
            process.run_async(["sudo", "-k"], lambda *_a: None, timeout=10)

    def updates_done(self, ok, out):
        """Everything ran, or something did not.

        The socket goes down and the password is forgotten first, before
        anything can return early - every way out of a batch comes through
        here, the ones that failed and the one that timed out included.
        """
        self.forget_password(ok)
        self.set_busy(False)
        if not ok:
            self.show_update_count()
            self.toast(_("Could not install the updates"))
            # A wrong password shows up here as sudo's own words, which say
            # it better than anything this window could invent.
            self.report(out or _("No output."))
            return
        # Nothing is left waiting, and the window that is running is now the
        # old program - possibly of itself. Restarting is the only way the
        # new one reaches the screen, and it was asked for in the dialog.
        self.updates = {}
        self.show_update_count()
        self.restart_self()

    def say_missing_packages(self, missing, tool=None):
        """Nothing is started: which packages are missing, and the one line
        that installs them - selectable, so it can be copied."""
        command = "sudo apt install " + " ".join(missing)
        body = ((_("{tool} needs packages this phone does not have:")
                 .format(tool=tool)) if tool else
                _("The updates need packages this phone does not have:"))
        body += "\n\n" + "\n".join("• " + p for p in missing) + "\n\n"
        body += _("Install them in a terminal, then try again:")
        dlg = Adw.AlertDialog(heading=_("Missing packages"), body=body)
        line = Gtk.Label(label=command, selectable=True, wrap=True)
        line.add_css_class("monospace")
        dlg.set_extra_child(line)
        dlg.add_response("ok", _("Got it"))
        dlg.set_default_response("ok")
        dlg.set_close_response("ok")
        dlg.present(self)
        self.missing_shown = (missing, command)

    def ask_component(self, comp, state):
        """Ask before fetching anything, and say exactly what will happen.

        Including the part that is easy to gloss over: this runs a script from
        the internet, and for three of the four it runs commands as root.
        """
        if self.busy:
            return
        # Before anything is fetched: an installer that stops at a missing
        # compiler leaves a clone and half a build behind, and says so in a
        # page of make output.
        missing = components.missing_packages(comp)
        if missing:
            self.say_missing_packages(missing, comp["tool"])
            return
        path = self.comp_rows.get(comp["tool"], {}).get("path") or clone_path(comp)
        steps = [source_steps(comp, state, path)[1],
                    _("run %s from that clone") % installer_said(comp)]
        text = "\n".join("%d. %s" % (n, t) for n, t in enumerate(steps, 1))
        body = text + "\n\n"
        if comp["root"]:
            body += _("That is code from the internet, running on this phone. "
                      "The installer writes to /usr/local, so sudo will ask "
                      "for your password below - it goes to sudo and nowhere "
                      "else, and the ticket is dropped when this is done.")
        else:
            body += _("That is code from the internet, running on this phone. "
                      "Nothing here needs root.")
        if state == "update" and not path.startswith(CLONE_HOME):
            body += "\n\n" + _("This is your own clone. With anything "
                                 "uncommitted in it, nothing is touched at all.")

        dlg = Adw.AlertDialog(heading=comp["tool"] + "?", body=body)
        entry = None
        if comp["root"]:
            entry = Adw.PasswordEntryRow(title=_("Your password (for sudo)"))
            grp = Adw.PreferencesGroup()
            grp.add(entry)
            dlg.set_extra_child(grp)
        dlg.add_response("go", _("Fetch and install") if state == "install"
                         else _("Update"))
        dlg.add_response("cancel", _("Cancel"))
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
            self.component_says(comp, _("no password helper: {error}").format(error=self.askpass.error))
        self.component_says(comp, _("working …"))
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
        """Where a single install reports: the row on the tool's own page.

        That page only exists while the tool does not - it is the tab that
        offers to fetch it. Updates do not come through here at all any more;
        they are a batch and report in the header. Something has to carry it
        either way: a window that goes busy for two minutes without a word
        reads as one that has hung."""
        row = self.comp_rows.get(comp["tool"], {}).get("state")
        if row is not None:
            row.set_subtitle(words)
        else:
            self.update_progress(words)

    def component_done(self, comp, ok, out):
        # First thing, before anything can return early: socket down, helper
        # deleted, password forgotten. Every way out of an install comes
        # through here, the ones that failed and the one that timed out
        # included.
        self.forget_password(ok)
        self.set_busy(False)
        if ok and self.live.get(comp["key"]):
            # Already there before this ran - so this was not a fetch of
            # something missing. Nothing to swap in; say so and stop.
            self.toast(_("{tool} is up to date").format(tool=comp["tool"]))
        elif ok and comp is PHOSH:
            # Not a tab of its own: the Phosh tab is rebuilt around it.
            self.live[comp["key"]] = find_component(comp)
            if self.live[comp["key"]]:
                self.rebuild_other_page()
                self.toast(_("{tool} is in place - phosh picks it up at the "
                             "next reboot").format(tool=comp["tool"]))
            else:
                self.toast(_("{tool} ran, but is not on the phone").format(
                    tool=comp["tool"]))
                self.report(out or _("No output."))
        elif ok:
            # The page first, the words after it: if the tab is already the
            # real one by the time the toast is read, the sentence is a
            # description and not a promise.
            if self.swap_in_page(comp):
                self.toast(_("{tool} is in place - this tab is live").format(
                    tool=comp["tool"]))
            else:
                # Everything ran and the tool is still not findable. There is
                # no sentence this window can invent that beats what the
                # installer said, so show that.
                self.toast(_("{tool} ran, but is not on the phone").format(
                    tool=comp["tool"]))
                self.report(out or _("No output."))
        elif comp is not PHOSH and self.swap_in_page(comp):
            # The installer said no, and the tool is there all the same - a
            # step after the install proper failed. The tab is live either
            # way; what went wrong is still shown, not swallowed. Found on
            # 30.9.2026: a status line at the very end of killswitch's
            # installer turned every first install into "Something went
            # wrong" and left the tab saying "not installed".
            self.toast(_("{tool} is installed, but its installer reported "
                         "an error").format(tool=comp["tool"]))
            self.report(out or _("No output."))
        else:
            self.toast(_("Could not set up {tool}").format(tool=comp["tool"]))
            # A wrong password shows up here as sudo's own words, which say it
            # better than anything this window could invent.
            self.report(out or _("No output."))
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
            self.toast(_("Could not restart: {error}").format(error=err))
