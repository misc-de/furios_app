#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The app, and the seams between it and the tools it drives.

The seams are the interesting part. The app reads audioctl's output line by
line and looks for labels; renaming a label over there - which happened once
while translating everything to English - breaks the app silently, and nothing
notices until somebody opens it and reads "unknown".

Those tools live in their own repositories, so the checks here read the
INSTALLED one: the contract that matters is the one against the binary this
phone actually runs. Where a tool is not installed the check says so and is
skipped, rather than passing on an empty comparison.

Runs without a display: gi_stub puts a stand-in in place of PyGObject, so the
window can be built, filled and clicked in this process.
"""
import importlib.util
import io
import json
import os
import re
import shlex
import shutil as shutil_real
import subprocess as subprocess_real
import sys
import tempfile
import types
import unittest
from unittest import mock
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tests"))

import gi_stub  # noqa: E402  - has to come before anything that imports gi

recorder = gi_stub.install()


def load(path, name):
    """Import a script by path, so its lines are the ones being measured.

    Running it as a subprocess would be simpler and would tell the coverage
    tracer nothing - it only sees what happens in this process.
    """
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# The app is a package since 15.9.2026, and `switcher` is that package. It
# re-exports everything under one name, so the tests below read as they did
# when it was one file - with one difference that matters and is meant to:
# where a test REPLACES something the app calls, it has to say which module
# holds it. switcher.process.run_async, not switcher.run_async. The latter is
# a second name for the same function; assigning to it changes nothing for a
# page that calls process.run_async, and the test would pass while measuring
# nothing at all.
sys.path.insert(0, str(ROOT))
# The Other page reads and writes ~/.config/gtk-3.0/gtk.css. Nothing in here
# may touch the real one.
os.environ["XDG_CONFIG_HOME"] = tempfile.mkdtemp(prefix="miscde-test-")
# And the folder dock's crash mark, which it removes from ~/.cache.
os.environ["XDG_CACHE_HOME"] = tempfile.mkdtemp(prefix="miscde-test-")
# And furios_phosh's record of phosh's plugin list, read from ~/.local/state:
# what this phone's own installer wrote down must not decide a test.
os.environ["XDG_STATE_HOME"] = tempfile.mkdtemp(prefix="miscde-test-")
# And the keyring prompter's service file and shim, under ~/.local.
os.environ["XDG_DATA_HOME"] = os.path.join(
    tempfile.mkdtemp(prefix="miscde-test-"), "share")
switcher = importlib.import_module("miscde")
# The records of what was there before a switch first changed anything
# (miscde/original.py). They live under the XDG_CONFIG_HOME above, shared by
# every test in this process - so a test that cares starts without them.
original = importlib.import_module("miscde.original")


def forget_all_records():
    shutil_real.rmtree(original.state_dir(), ignore_errors=True)
# The install offers ask dpkg what is installed. What this machine has must
# not decide whether a test sees a password field or a list of packages, so
# nothing is missing unless a test says so; the real function is kept for
# the tests of it.
REAL_MISSING_PACKAGES = switcher.components.missing_packages
switcher.components.missing_packages = lambda comp: []


# Which of the optional tools this machine has. The app holds no constants for
# them any more - it looks while it builds a page, because one of them can
# arrive from the components page while the window is open - so a test that
# needs to know which widgets exist looks the same way.
AUDIOCTL = switcher.tools._tool_maybe("audioctl")
DMNR = switcher.tools._tool_maybe("furios-audio-dmnr")
CONTRIB = switcher.tools._tool_maybe("furios-gps-contribute")
MODEMCTL = switcher.tools._tool_maybe("modemctl")
KILLSWITCH = switcher.tools._tool_maybe("killswitch-indicator")
BATTCTL = switcher.tools._tool_maybe("battctl")
SECCTL = switcher.tools._tool_maybe("secctl")


class AppReadsAudioctl(unittest.TestCase):
    """The app parses audioctl's output, and audioctl lives elsewhere now.

    So the comparison is against the INSTALLED tool - the one this phone runs
    and the app will actually talk to. A tool that is not installed is a skip
    with a reason, never a pass: comparing against an empty string would agree
    with everything.
    """

    @classmethod
    def setUpClass(cls):
        sys.modules.setdefault("gi", None)
        # Every line of the app, not the launcher. These tests read the
        # source as text and look for the exact string the code compares
        # against - the point being that the app must wait for a word
        # audioctl really prints. When the window was one file this was that
        # file; since it became a package on 15.9.2026 it is all of it, and
        # taking only misc-de.py would have left four tests searching a
        # thirty-line launcher and quietly finding nothing.
        cls.app = "\n".join(
            sorted(p.read_text() for p in (ROOT / "miscde").rglob("*.py")))
        cls.audioctl = cls.installed(AUDIOCTL)
        cls.dmnr = cls.installed(DMNR)

    @staticmethod
    def installed(path):
        """The tool's text, or None when it is not on this machine."""
        try:
            return Path(path).read_text()
        except (OSError, TypeError, ValueError):
            return None

    def tool(self, text, name):
        if not text:
            self.skipTest("%s is not installed, so there is nothing to check "
                          "the app against" % name)
        return text

    # A label the app looks for that is NOT audioctl's, and the file it does
    # belong to. Until 16.9.2026 there was one source and the search over the
    # whole package was the same thing as "everything audioctl prints"; the
    # Bluetooth powersave switch reads batman's config, so a second source
    # has to be named rather than quietly exempted. The check itself is the
    # same one - the label has to appear in the file it is read from.
    OTHER_SOURCES = {"BTSAVE=": switcher.BATMAN_CONFIG}

    # What an audioctl from before 4.10.2026 printed, and the app still reads
    # when "status --json" brings no JSON back. A current audioctl answers in
    # JSON instead, checked key by key below.
    LEGACY_STATUS_LABELS = {"Profile (active):", "Profile (persistent):",
                            "WARNING:", "Fell back:", "Test mode:",
                            "Pulse server:", "Sinks:"}

    def labels_in_app(self):
        return re.findall(r'line\.startswith\("([^"]+)"\)', self.app)

    def json_keys_in_app(self):
        return re.findall(r'status_json\.get\("([a-z_]+)"\)', self.app)

    def test_every_status_key_the_app_reads_is_one_audioctl_writes(self):
        keys = self.json_keys_in_app()
        self.assertGreaterEqual(len(keys), 5)
        audioctl = self.tool(self.audioctl, "audioctl")
        if '"profile":' not in audioctl:
            self.skipTest("this audioctl predates status --json")
        for key in keys:
            with self.subTest(key=key):
                self.assertIn('"%s":' % key, audioctl,
                              "the app reads a key audioctl does not write")

    def test_every_label_the_app_looks_for_is_one_audioctl_prints(self):
        for label in self.labels_in_app():
            with self.subTest(label=label):
                other = self.OTHER_SOURCES.get(label)
                if other is None:
                    audioctl = self.tool(self.audioctl, "audioctl")
                    if label in self.LEGACY_STATUS_LABELS and '"profile":' in audioctl:
                        continue      # answered in JSON by this audioctl
                    self.assertIn(
                        label, audioctl,
                        "the app waits for a line audioctl never prints")
                    continue
                text = self.installed(other)
                if text is None:
                    self.skipTest("%s is not on this phone, so there is "
                                  "nothing to check %s against"
                                  % (other, label))
                self.assertIn(label, text,
                              "the app reads a key that file does not have")

    def test_the_app_looks_for_something_at_all(self):
        """Guards the test above from passing by finding nothing."""
        self.assertGreaterEqual(len(self.labels_in_app()), 4)

    def test_test_mode_is_recognised_by_the_word_audioctl_uses(self):
        audioctl = self.tool(self.audioctl, "audioctl")
        self.assertIn('startswith("yes")', self.app)
        self.assertRegex(audioctl, r'Test mode:\s+yes|"test_mode":')

    def test_the_dmnr_switch_speaks_the_words_the_helper_understands(self):
        helper = self.tool(self.dmnr, "furios-audio-dmnr")
        self.assertIn('"on" if row.get_active() else "off"', self.app)
        # The helper dispatches on these exact words; the app sends them.
        for word in ("on)", "off)"):
            self.assertRegex(helper, r"(?m)^\s*%s$" % re.escape(word))

    def test_the_machine_readable_state_line_matches(self):
        helper = self.tool(self.dmnr, "furios-audio-dmnr")
        self.assertIn("state=on", helper)
        self.assertIn('"state=on" in out', self.app)


class SwitcherWords(unittest.TestCase):
    """What the app puts in front of someone who is not reading code.

    This is the part where being wrong is invisible: a label that says the
    opposite of what is happening reads as a bug in the audio, and the person
    goes looking in the wrong place. It happened once already - the app showed
    "PipeWire holds the HAL" above "Sound server: PulseAudio", which is not a
    contradiction but reads exactly like one.
    """

    def test_pipewires_pulse_interface_is_explained_rather_than_quoted(self):
        said = switcher.server_in_words("PulseAudio (on PipeWire 1.6.6)")
        self.assertIn("PipeWire", said)
        self.assertIn("1.6.6", said)
        self.assertIn("older apps", said)

    def test_a_version_it_cannot_find_still_reads_sensibly(self):
        said = switcher.server_in_words("PulseAudio (on PipeWire)")
        self.assertIn("PipeWire", said)

    def test_the_shipped_server_is_named_as_such(self):
        self.assertIn("shipped", switcher.server_in_words("pulseaudio"))
        self.assertIn("shipped", switcher.server_in_words("PulseAudio"))

    def test_nothing_at_all_is_not_dressed_up(self):
        self.assertEqual("not reachable", switcher.server_in_words(""))
        self.assertEqual("not reachable", switcher.server_in_words("-"))
        self.assertEqual("not reachable", switcher.server_in_words(None))

    def test_something_unexpected_is_passed_through_unchanged(self):
        self.assertEqual("jackd", switcher.server_in_words("jackd"))


class ComponentTable(unittest.TestCase):
    """The four repositories this app drives, and the commands it would run.

    A list and a pure function, deliberately: what runs as root, in which
    directory, and where the password goes should be readable without starting
    anything at all.
    """

    def comp(self, tool="modemctl"):
        return next(c for c in switcher.COMPONENTS if c["tool"] == tool)

    def test_every_component_names_a_repository_a_tab_and_what_it_does(self):
        for comp in switcher.COMPONENTS:
            with self.subTest(tool=comp["tool"]):
                self.assertTrue(comp["url"].startswith("https://github.com/"))
                self.assertGreater(len(comp["does"]), 30)
                self.assertIn(comp["key"],
                              ("audio", "modem", "gps", "switches", "battery",
                               "security"))
                self.assertTrue(comp["icon"].endswith("-symbolic"))

    def test_a_clone_is_found_by_its_origin_not_by_its_name(self):
        """The same repository sits in ~/Projekte/furios_gps_fix here and is
        called furios_gps upstream. A name comparison would miss exactly the
        clone that must not be touched."""
        base = tempfile.mkdtemp()
        try:
            git = os.path.join(base, "anders_benannt", ".git")
            os.makedirs(git)
            with open(os.path.join(git, "config"), "w") as fh:
                fh.write('[remote "origin"]\n\turl = '
                         'https://github.com/misc-de/furios_gps.git\n')
            self.assertEqual(
                os.path.join(base, "anders_benannt"),
                switcher.components.clone_elsewhere("https://github.com/misc-de/furios_gps", base))
            self.assertIsNone(switcher.components.clone_elsewhere(
                "https://github.com/misc-de/furios_audio", base))
        finally:
            shutil_real.rmtree(base, ignore_errors=True)

    def make_clone(self, path, url, when=None):
        """A real git clone of `url` at path, its HEAD committed at `when`."""
        os.makedirs(path)
        subprocess_real.run(["git", "init", "-q", path], check=True)
        subprocess_real.run(["git", "-C", path, "remote", "add", "origin", url],
                            check=True)
        if when is not None:
            env = dict(os.environ, GIT_COMMITTER_DATE="@%d +0000" % when,
                       GIT_AUTHOR_DATE="@%d +0000" % when)
            subprocess_real.run(
                ["git", "-C", path, "-c", "user.name=t", "-c", "user.email=t@t",
                 "commit", "-q", "--allow-empty", "-m", "x"],
                check=True, env=env)

    def test_a_clone_one_level_down_in_a_hidden_directory_is_found(self):
        """~/Projekte/.dev/furios_app was never found: the scan stopped at
        the first level, and the stale ~/Projekte/furios_app was compared."""
        base = tempfile.mkdtemp()
        url = "https://github.com/misc-de/furios_app"
        try:
            self.make_clone(os.path.join(base, ".dev", "furios_app"), url)
            self.assertEqual(os.path.join(base, ".dev", "furios_app"),
                             switcher.components.clone_elsewhere(url, base))
        finally:
            shutil_real.rmtree(base, ignore_errors=True)

    def test_of_two_clones_the_one_committed_last_wins(self):
        base = tempfile.mkdtemp()
        url = "https://github.com/misc-de/furios_app"
        try:
            self.make_clone(os.path.join(base, "furios_app"), url, 1000)
            self.make_clone(os.path.join(base, ".dev", "furios_app"), url, 2000)
            self.assertEqual(os.path.join(base, ".dev", "furios_app"),
                             switcher.components.clone_elsewhere(url, base))
            # And the other way round: the place is not what decides.
            shutil_real.rmtree(base)
            self.make_clone(os.path.join(base, "furios_app"), url, 3000)
            self.make_clone(os.path.join(base, ".dev", "furios_app"), url, 2000)
            self.assertEqual(os.path.join(base, "furios_app"),
                             switcher.components.clone_elsewhere(url, base))
        finally:
            shutil_real.rmtree(base, ignore_errors=True)

    def test_the_scan_stops_at_two_levels_and_skips_clones_and_heavy_dirs(self):
        base = tempfile.mkdtemp()
        url = "https://github.com/misc-de/furios_gps"
        try:
            for where in (("a", "b", "c"), ("node_modules", "x"),
                          ("other", "inner")):
                self.make_clone(os.path.join(base, *where), url)
            # "other" is a clone of something else: what is inside it is its
            # own work, not another clone.
            subprocess_real.run(["git", "init", "-q",
                                 os.path.join(base, "other")], check=True)
            self.assertIsNone(switcher.components.clone_elsewhere(url, base))
        finally:
            shutil_real.rmtree(base, ignore_errors=True)

    def test_a_directory_without_a_git_config_is_not_a_clone(self):
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, "nur_ein_ordner"))
            self.assertIsNone(switcher.components.clone_elsewhere("https://x/y", base))
            self.assertIsNone(switcher.components.clone_elsewhere("https://x/y", base + "/removed"))
            self.assertFalse(switcher.components.is_clone(None))
            self.assertFalse(switcher.components.is_clone(base))
        finally:
            shutil_real.rmtree(base, ignore_errors=True)

    def nowhere(self):
        """A path that does not exist, and will not while the test runs."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil_real.rmtree, d, True)
        return os.path.join(d, "not-there-yet")

    def test_what_git_answers_is_read_as_a_number_or_as_nothing(self):
        self.assertEqual(0, switcher.behind_count("0\n"))
        self.assertEqual(7, switcher.behind_count("7"))
        self.assertIsNone(switcher.behind_count(""))
        self.assertIsNone(switcher.behind_count("fatal: no upstream configured"))

    def test_an_install_clones_asks_sudo_once_and_drops_the_ticket(self):
        # With a path, not the default: the default is a real directory on
        # this phone, and once it exists this test measures the retry instead
        # of the clone - which is how it first went green on a machine where
        # the clone was already there.
        steps = switcher.component_steps(self.comp(), "install", "secret_word",
                                            self.nowhere())
        commands = [" ".join(argv) for argv, _s, _c, _e in steps]
        self.assertIn("git clone", commands[0])
        self.assertEqual(1, len([b for b in commands if b.startswith("sudo -S")]))
        self.assertTrue(any(b.endswith("install.sh") for b in commands), commands)
        self.assertEqual("sudo -k", commands[-1],
                         "the ticket has to be dropped when the work is done")

    def test_a_collection_is_installed_from_its_subdirectory(self):
        """furios_misc holds several small things, so its install.sh is not
        at the root of the clone. The installer runs where it lives, or its
        own relative paths point at the wrong place."""
        comp = self.comp("battctl")
        path = self.nowhere()
        steps = switcher.component_steps(comp, "install", "", path)
        cwd = self.where_it_installs(steps)
        self.assertEqual(os.path.join(path, "battery"), cwd)
        # And the clone itself is still the clone - cloning into the
        # subdirectory would put a repository inside a directory of it.
        self.assertIn("git clone", " ".join(steps[0][0]))
        self.assertEqual(path, steps[0][0][-1])

    def test_a_single_project_still_installs_from_the_clone(self):
        comp = self.comp("furios-gps-contribute")
        path = self.nowhere()
        steps = switcher.component_steps(comp, "install", "secret_word", path)
        self.assertEqual(path, self.where_it_installs(steps))

    @staticmethod
    def where_it_installs(steps):
        """The working directory of the install.sh step - found by its
        argv, not by position: for a component that needs root the last
        step is "sudo -k"."""
        for argv, _stdin, cwd, _env in steps:
            if argv == ["./install.sh"]:
                return cwd
        return None

    def test_the_question_names_the_installer_it_will_run(self):
        """What somebody agrees to has to be the path they would type
        themselves."""
        self.assertEqual("./battery/install.sh",
                         switcher.installer_said(self.comp("battctl")))
        self.assertEqual("./install.sh",
                         switcher.installer_said(self.comp("furios-gps-contribute")))

    def clone_dir(self, url):
        """A directory that git would recognise as a clone of `url`."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil_real.rmtree, d, True)
        os.mkdir(os.path.join(d, ".git"))
        with open(os.path.join(d, ".git", "config"), "w") as fh:
            fh.write('[remote "origin"]\n\turl = %s\n' % url)
        return d

    def test_a_second_install_uses_the_clone_the_first_one_made(self):
        """Read off the phone on 14.9.2026: the first Install cloned and then
        failed further down, and every press after that ran "git clone" into
        that same clone - "destination path already exists and is not an empty
        directory", for ever, with no way out from inside the app."""
        comp = self.comp()
        steps = switcher.component_steps(comp, "install", "secret_word",
                                            self.clone_dir(comp["url"]))
        commands = [" ".join(argv) for argv, _s, _c, _e in steps]
        self.assertEqual([], [b for b in commands if "git clone" in b])
        self.assertTrue(any("pull --ff-only" in b for b in commands), commands)
        self.assertTrue(any(b.endswith("install.sh") for b in commands))

    def test_a_clone_that_cannot_be_updated_is_installed_anyway(self):
        """No network is a reason to install what is already here, not a
        reason to refuse. Run for real: the chain stops at the first non-zero
        exit, so this step has to end in one that is zero."""
        comp = self.comp()
        path = self.clone_dir(comp["url"])
        step = switcher.component_steps(comp, "install", "x", path)[0]
        done_ = subprocess_real.run(step[0], capture_output=True)
        self.assertEqual(0, done_.returncode, done_.stderr)
        self.assertIn("installing what is already in it",
                      done_.stdout.decode())

    def test_something_else_in_the_way_is_left_alone_and_said_so(self):
        """A directory that is not a clone of this repository. Deleting it is
        not this app's decision - saying which one it is, is."""
        comp = self.comp()
        foreign = tempfile.mkdtemp()
        self.addCleanup(shutil_real.rmtree, foreign, True)
        with open(os.path.join(foreign, "mine.txt"), "w") as fh:
            fh.write("not ours")
        steps = switcher.component_steps(comp, "install", "x", foreign)
        self.assertEqual([], [a for a, _s, _c, _e in steps
                              if a[0] == "git" and "clone" in a])
        done_ = subprocess_real.run(steps[0][0], capture_output=True)
        self.assertNotEqual(0, done_.returncode)
        self.assertIn("in the way", done_.stdout.decode())
        self.assertIn(foreign, done_.stdout.decode())
        self.assertTrue(os.path.exists(os.path.join(foreign, "mine.txt")))

    def test_the_password_never_reaches_a_command_line(self):
        """It goes to sudo through the pipe. In argv every "ps" on the phone
        would read it, and so would anything that logs a command."""
        steps = switcher.component_steps(self.comp(), "install", "secret_word")
        for argv, _stdin, _cwd, _env in steps:
            with self.subTest(argv=argv):
                self.assertNotIn("secret_word", " ".join(argv))
        through_the_pipe = [stdin for _a, stdin, _c, _e in steps if stdin]
        self.assertEqual(["secret_word\n"], through_the_pipe)

    def test_the_installer_is_told_where_sudo_can_ask(self):
        """The ticket from "sudo -v" is not ours to rely on: with no terminal
        sudo ties it to the parent process, and the installer's bash is a
        different parent. On 14.9.2026 a sudoers rule that had been sharing it
        went away and the GPS install stopped at its first sudo line."""
        steps = switcher.component_steps(self.comp(), "install", "secret_word",
                                            askpass="/run/user/1/x/askpass")
        env = [e for argv, _s, _c, e in steps
               if argv[0].endswith("install.sh")][0]
        self.assertEqual("/run/user/1/x/askpass", env["SUDO_ASKPASS"])

    def test_the_password_is_in_no_environment_either(self):
        """argv is read by every "ps"; the environment of a child is read by
        anything that can read /proc, which is the same audience."""
        steps = switcher.component_steps(self.comp(), "install", "secret_word",
                                            askpass="/run/user/1/x/askpass")
        for argv, _stdin, _cwd, env in steps:
            with self.subTest(argv=argv):
                self.assertNotIn("secret_word", " ".join((env or {}).values()))
                self.assertNotIn("secret_word", " ".join((env or {}).keys()))

    def test_without_a_helper_the_environment_stays_as_it_was(self):
        steps = switcher.component_steps(self.comp(), "install", "secret_word")
        self.assertEqual([], [e for *_rest, e in steps if e])

    def test_a_display_is_only_added_where_there_is_none(self):
        """sudo reaches for SUDO_ASKPASS only if it thinks a prompt could be
        seen, and it decides that by DISPLAY alone - it never opens it. Under
        phosh it is set; measured 14.9.2026: without it sudo says "a terminal
        is required" with a working helper standing by."""
        before = os.environ.get("DISPLAY")
        try:
            os.environ["DISPLAY"] = ":9"
            self.assertNotIn("DISPLAY", switcher.installer_env("/x/askpass"))
            os.environ.pop("DISPLAY")
            self.assertEqual(":0",
                             switcher.installer_env("/x/askpass")["DISPLAY"])
            self.assertIsNone(switcher.installer_env(None))
        finally:
            if before is None:
                os.environ.pop("DISPLAY", None)
            else:
                os.environ["DISPLAY"] = before

    def test_the_installer_runs_in_the_clone_as_the_user(self):
        """Not as root: killswitch-indicator's installer refuses to be root,
        and an installer run as root writes its user files into /root."""
        steps = switcher.component_steps(self.comp(), "install", "secret_word")
        installer = [(argv, cwd) for argv, _s, cwd, _e in steps
                     if argv[0].endswith("install.sh")]
        self.assertEqual(1, len(installer))
        argv, cwd = installer[0]
        self.assertNotIn("sudo", argv)
        self.assertEqual(switcher.clone_path(self.comp()), cwd)

    def test_a_component_without_root_never_calls_sudo(self):
        steps = switcher.component_steps(
            self.comp("furios-gps-contribute"), "install", None)
        self.assertEqual([], [argv for argv, _s, _c, _e in steps
                              if argv[0] == "sudo"])

    def test_an_installer_that_calls_sudo_gets_the_password(self):
        """Read from the installers themselves, not from what this table
        believes about them: killswitch-indicator grew a sudo line with its
        phosh plugin and stayed "root": False - on a phone where sudo asks,
        the Switches tab died with "a terminal is required"."""
        homes = [os.path.expanduser("~/Projekte"),
                 os.path.expanduser("~/Projekte/.dev"),
                 os.path.expanduser("~/.local/share/misc-de")]
        seen = 0
        for comp in switcher.COMPONENTS + [switcher.PHOSH]:
            for home in homes:
                script = os.path.join(home, comp["dir"], comp.get("sub", ""),
                                      "install.sh")
                if not os.path.isfile(script):
                    continue
                seen += 1
                # And the installers it runs itself ("$SRC/../guard/
                # install.sh"): battctl's brought the widget's sudo line
                # along on 30.9.2026, and a look at install.sh alone
                # missed it.
                text = Path(script).read_text()
                scripts = [script] + [
                    os.path.normpath(os.path.join(os.path.dirname(script), m))
                    for m in re.findall(r'"\$SRC/([^"]*install\.sh)"', text)]
                calls = []
                for one in scripts:
                    if not os.path.isfile(one):
                        continue
                    with open(one) as fh:
                        calls += [l for l in fh
                                  if re.match(r"\s*(?!#).*\bsudo\s+(?!-k)", l)
                                  and "echo" not in l]
                if calls:
                    self.assertTrue(comp["root"], "%s: %s" % (
                        comp["tool"], calls[0].strip()))
                break
        if not seen:
            self.skipTest("no clone of any installer on this machine")

    def test_an_update_guards_the_clone_before_it_pulls(self):
        """A clone with uncommitted work in it is left exactly as it is - and
        told so in a sentence, because a bare exit code explains nothing."""
        steps = switcher.component_steps(self.comp(), "update", "secret_word",
                                            "/home/furios/Projekte/eigen")
        guard = " ".join(steps[1][0])
        self.assertIn("status --porcelain", guard)
        self.assertIn("uncommitted", guard)
        self.assertIn("/home/furios/Projekte/eigen", steps[1][0])
        self.assertIn("pull", steps[2][0])
        self.assertIn("--ff-only", steps[2][0],
                      "a merge is not this app's decision to make")

    def test_an_update_works_in_the_clone_it_was_given(self):
        """Not always our own directory: the clone may be the one somebody
        keeps in ~/Projekte, and that is where the pull has to happen."""
        steps = switcher.component_steps(self.comp(), "update", None, "/elsewhere")
        for argv, _s, cwd, _e in steps:
            with self.subTest(argv=argv):
                if argv[0] == "git":
                    self.assertIn("/elsewhere", argv)
                if argv[0].endswith("install.sh"):
                    self.assertEqual("/elsewhere", cwd)


class FakeProcess:
    """A Gio.Subprocess that hands back what a test wrote for it.

    audioctl takes up to fifteen seconds and the window must not freeze, so the
    app reads its output line by line as it arrives. That is the part worth
    testing: not that a subprocess runs, but that the lines are assembled and
    the end is noticed.
    """

    def __init__(self, lines=(), ok=True, fail_at=None):
        self.lines = list(lines)
        self.ok = ok
        self.fail_at = fail_at
        self.waited = False
        self.killed = False
        self.written = None
        self.closed = False

    def get_stdout_pipe(self):
        return self

    def get_successful(self):
        return self.ok

    def communicate_utf8_finish(self, _res):
        if self.fail_at == "communicate":
            raise switcher.GLib.Error("pipe broke")
        return True, "\n".join(self.lines), None

    def communicate_utf8_async(self, stdin, _cancellable, callback):
        self.stdin = stdin              # what was written into the pipe
        if self.fail_at == "hang":
            return                      # never calls back
        callback(self, None)

    def wait_async(self, _cancellable, callback):
        if self.fail_at == "hang":
            return                      # never calls back - the case with a watchdog
        callback(self, None)

    def force_exit(self):
        self.killed = True

    def wait_finish(self, _res):
        self.waited = True
        if self.fail_at == "wait":
            raise switcher.GLib.Error("never finished")

    # The stdin side, for the path that reads lines as they come. The other
    # path never touches these: communicate_utf8_async takes the input as an
    # argument and Gio does the writing.
    def get_stdin_pipe(self):
        if self.fail_at == "stdin":
            raise switcher.GLib.Error("stdin pipe is gone")
        return self

    def write_all(self, data, _cancellable):
        self.written = data
        return True, len(data)

    def close(self, _cancellable):
        self.closed = True
        return True


class FakeStream:
    """Gio.DataInputStream over the lines of a FakeProcess."""

    def __init__(self, process):
        self.process = process
        self.index = 0

    def read_line_async(self, _priority, _cancellable, callback):
        callback(self, None)

    def read_line_finish_utf8(self, _res):
        if self.process.fail_at == "read":
            raise switcher.GLib.Error("stream died")
        if self.index >= len(self.process.lines):
            return None, 0
        line = self.process.lines[self.index]
        self.index += 1
        if isinstance(line, bytes):
            # What the real GLib does with a line that is not UTF-8: the
            # line is consumed, and this read fails with a conversion error.
            err = switcher.GLib.Error("Invalid byte sequence in conversion input")
            err.domain = "g_convert_error"
            raise err
        return line, len(line)


class RunsAudioctl(unittest.TestCase):
    """How the app talks to audioctl."""

    def setUp(self):
        self.process = None
        self.original_new = switcher.Gio.Subprocess.new
        self.original_stream = switcher.Gio.DataInputStream.new
        self.original_launcher = switcher.Gio.SubprocessLauncher.new

    def tearDown(self):
        switcher.Gio.Subprocess.new = self.original_new
        switcher.Gio.DataInputStream.new = self.original_stream
        # Put back by name, not by whatever the last test left lying there:
        # arrange() replaces this one too now, and a test that saves it
        # itself would otherwise restore the stub.
        switcher.Gio.SubprocessLauncher.new = self.original_launcher

    def arrange(self, **kwargs):
        process = FakeProcess(**kwargs)
        switcher.Gio.Subprocess.new = lambda *a, **k: process
        switcher.Gio.DataInputStream.new = lambda pipe: FakeStream(process)

        # A call carrying stdin, a directory or an environment goes the long
        # way round, through the launcher. Both roads have to end at the same
        # process or a test cannot see what the one under stdin actually did.
        class Launcher:
            def set_cwd(self, _path):
                pass

            def setenv(self, *_a):
                pass

            def spawnv(self, _argv):
                return process

        switcher.Gio.SubprocessLauncher.new = lambda *_a, **_k: Launcher()
        return process

    def test_output_is_collected_and_handed_over_at_the_end(self):
        self.arrange(lines=["one", "two"])
        seen = []
        switcher.process.run_async(["audioctl", "status"], lambda ok, out: seen.append((ok, out)))
        self.assertEqual(seen, [(True, "one\ntwo")])

    def test_with_a_line_callback_the_lines_arrive_as_they_come(self):
        self.arrange(lines=["step one", "step two", ""])
        lines, done = [], []
        switcher.process.run_async(["audioctl", "set", "pw-hal"],
                           lambda ok, out: done.append((ok, out)),
                           on_line=lines.append)
        self.assertEqual(lines, ["step one", "step two"])
        self.assertEqual(done, [(True, "step one\nstep two")])

    def test_after_a_timeout_the_lines_are_read_but_not_passed_on(self):
        """An orphan's lines wrote over the header after the batch had
        already been reported as failed. Still drained - a program nobody
        reads from blocks - just no longer handed on."""
        self.arrange(lines=["one", "two", "three"])
        timers = []
        self.enterContext(mock.patch.object(
            switcher.GLib, "timeout_add_seconds",
            lambda _s, fn: timers.append(fn) or 7))
        self.enterContext(mock.patch.object(switcher.GLib, "source_remove",
                                            lambda _id: None))
        lines, done = [], []

        def on_line(line):
            lines.append(line)
            if line == "one":
                timers[0]()                  # the wait runs out here

        switcher.process.run_async(["./install.sh"],
                                   lambda ok, out: done.append(ok),
                                   on_line=on_line, timeout=5)
        self.assertEqual(["one"], lines)
        self.assertEqual([False], done)

    def test_work_handed_to_root_is_waited_for_past_the_timeout(self):
        """modemctl behind pkexec, or an installer with sudo lines: the
        window cannot kill it (EPERM), so calling it failed handed the window
        back while root was still changing the phone, and a second tap ran a
        second one beside it. It is waited for to its real end now."""
        for argv, env in ((["/usr/bin/pkexec", "/usr/local/bin/modemctl", "nr", "on"], None),
                          (["sudo", "-n", "dpkg-divert"], None),
                          (["./install.sh"], {"SUDO_ASKPASS": "/run/x/askpass"})):
            with self.subTest(argv=argv[0]):
                process = self.arrange(lines=["one", "two"])
                timers = []
                with mock.patch.object(switcher.GLib, "timeout_add_seconds",
                                       lambda _s, fn: timers.append(fn) or 7), \
                        mock.patch.object(switcher.GLib, "source_remove",
                                          lambda _id: None):
                    lines, done = [], []

                    def on_line(line):
                        lines.append(line)
                        if line == "one":
                            timers[0]()      # the wait runs out here

                    switcher.process.run_async(argv, lambda ok, out: done.append(ok),
                                               on_line=on_line, timeout=90, env=env)
                self.assertFalse(process.killed)
                self.assertEqual([True], done, "the real end is reported, once")
                self.assertIn("two", lines)
                self.assertTrue(any("still running" in l for l in lines))

    def test_a_command_that_fails_is_reported_as_such(self):
        self.arrange(lines=["went wrong"], ok=False)
        seen = []
        switcher.process.run_async(["audioctl", "status"], lambda ok, out: seen.append((ok, out)))
        self.assertEqual(seen[0][0], False)

    def test_a_command_that_will_not_start_is_reported(self):
        def refuse(*_a, **_k):
            raise switcher.GLib.Error("no such file")
        switcher.Gio.Subprocess.new = refuse
        seen = []
        switcher.process.run_async(["nothing"], lambda ok, out: seen.append((ok, out)))
        self.assertEqual(seen[0][0], False)
        self.assertIn("no such file", seen[0][1])

    def test_input_reaches_the_pipe_even_when_lines_are_read_back(self):
        """Both at once: something to write in, something to read out.

        The two halves used to be one or the other. With a line callback the
        stdin pipe was opened and then left alone - Gio fills it only on the
        other path, through communicate_utf8_async - so a "sudo -S" reading
        from it waited for input that never came, until the watchdog. It cost
        nothing as long as nobody passed both; the install chain now does.
        """
        process = self.arrange(lines=["one"])
        seen = []
        switcher.process.run_async(["sudo", "-S", "-v"],
                           lambda ok, out: seen.append((ok, out)),
                           on_line=lambda _l: None, stdin="word\n")
        self.assertEqual(b"word\n", process.written,
                         "the password never reached sudo")
        self.assertTrue(process.closed, "sudo waits for the pipe to close")
        self.assertEqual([(True, "one")], seen)

    def test_an_input_pipe_that_breaks_is_reported_rather_than_waited_out(self):
        self.arrange(lines=["one"], fail_at="stdin")
        seen = []
        switcher.process.run_async(["sudo", "-S", "-v"],
                           lambda ok, out: seen.append((ok, out)),
                           on_line=lambda _l: None, stdin="word\n")
        self.assertEqual(False, seen[0][0])
        self.assertIn("stdin pipe is gone", seen[0][1])

    def test_a_pipe_that_breaks_while_reading_is_reported(self):
        self.arrange(lines=["a"], fail_at="read")
        seen = []
        switcher.process.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)),
                           on_line=lambda _l: None)
        self.assertEqual(seen[0][0], False)

    def test_a_line_that_is_not_utf8_does_not_end_the_reading(self):
        """An installer is still running when one odd byte turns up in its
        output. Stopping there reported it failed, took the password socket
        down under it and left its pipe undrained."""
        process = self.arrange(lines=["building", b"\xfcber", "installed"])
        lines, seen = [], []
        switcher.process.run_async(["./install.sh"],
                                   lambda ok, out: seen.append((ok, out)),
                                   on_line=lines.append)
        self.assertEqual(1, len(seen))
        self.assertTrue(seen[0][0], seen)
        self.assertEqual("installed", lines[-1])
        self.assertTrue(process.waited)

    def test_a_process_that_never_finishes_is_reported(self):
        self.arrange(lines=[], fail_at="wait")
        seen = []
        switcher.process.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)),
                           on_line=lambda _l: None)
        self.assertEqual(seen[0][0], False)

    # --- the watchdog ------------------------------------------------------
    #
    # systemctl can block on a job that is itself waiting, and pkexec inherits
    # that. Without a bound, a helper that never answers meant set_busy(True)
    # with nothing left to set it back: switches grey, progress bar pulsing,
    # and the only way out is killing the window.

    def catch_timer(self):
        """Holds on to what run_async scheduled, so a test can fire it."""
        fired = []
        original = switcher.GLib.timeout_add_seconds
        switcher.GLib.timeout_add_seconds = lambda secs, fn: (
            fired.append((secs, fn)) or 4711)
        self.addCleanup(lambda: setattr(switcher.GLib, "timeout_add_seconds",
                                        original))
        return fired

    def test_a_helper_that_never_answers_is_given_up_on(self):
        process = self.arrange(lines=[], fail_at="hang")
        fired = self.catch_timer()
        seen = []
        switcher.process.run_async(["audioctl", "status"],
                           lambda ok, out: seen.append((ok, out)))
        self.assertEqual([], seen, "answered before the helper did")
        self.assertEqual(1, len(fired), "nothing was scheduled to give up")
        fired[0][1]()                                   # the watchdog fires
        self.assertEqual(False, seen[0][0])
        self.assertIn("did not answer", seen[0][1])
        self.assertTrue(process.killed, "gave up without stopping the process")

    def test_the_watchdog_waits_long_enough_for_an_honest_answer(self):
        """audioctl alone may wait 15 seconds for a sink, and a switch behind
        pkexec runs several systemctl calls after that. A bound that cuts off
        real work would be worse than none."""
        self.arrange(lines=[], fail_at="hang")
        fired = self.catch_timer()
        switcher.process.run_async(["audioctl"], lambda ok, out: None)
        self.assertGreaterEqual(fired[0][0], 60)

    def test_an_answer_that_arrives_is_not_answered_twice(self):
        """Both the reader and the watchdog can reach the callback. Calling it
        twice would refresh the window on top of a switch already in flight."""
        self.arrange(lines=["done"])
        fired = self.catch_timer()
        seen = []
        switcher.process.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)))
        self.assertEqual(1, len(seen))
        fired[0][1]()                                   # late watchdog
        self.assertEqual(1, len(seen), "the watchdog answered after the helper")

    def test_the_watchdog_does_not_call_itself(self):
        """run_async swaps the callback it hands to its readers. Swapping the
        name the wrapper itself calls would be endless recursion, and the stub
        would not notice - the recursion limit would."""
        self.arrange(lines=["fine"])
        self.catch_timer()
        seen = []
        switcher.process.run_async(["audioctl"], lambda ok, out: seen.append(out))
        self.assertEqual(["fine"], seen)

    def test_a_line_reading_call_is_bounded_too(self):
        process = self.arrange(lines=["step one"], fail_at="hang")
        fired = self.catch_timer()
        seen = []
        switcher.process.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)),
                           on_line=lambda _l: None)
        fired[0][1]()
        self.assertIn("did not answer", seen[0][1])
        self.assertTrue(process.killed)

    def test_a_password_goes_into_the_pipe_and_a_launcher_sets_the_directory(self):
        """The two things the components page needs from run_async: a working
        directory, and a way in that is not the command line."""
        process = self.arrange(lines=["done"])
        built = {}

        class FakeLauncher:
            def set_cwd(self, path):
                built["cwd"] = path

            def spawnv(self, argv):
                built["argv"] = argv
                return process

        real = switcher.Gio.SubprocessLauncher.new
        switcher.Gio.SubprocessLauncher.new = lambda flags: FakeLauncher()
        try:
            seen = []
            switcher.process.run_async(["./install.sh"], lambda ok, out: seen.append(ok),
                               cwd="/tmp/clone_dir", stdin="secret\n")
        finally:
            switcher.Gio.SubprocessLauncher.new = real
        self.assertEqual("/tmp/clone_dir", built.get("cwd"))
        self.assertEqual(["./install.sh"], built.get("argv"))
        self.assertEqual("secret\n", process.stdin)
        self.assertEqual([True], seen)

    def test_without_a_directory_or_a_pipe_nothing_is_launched_the_long_way(self):
        """The plain path stays plain - every other call in this app takes it."""
        self.arrange(lines=["x"])
        touched = []
        real = switcher.Gio.SubprocessLauncher.new
        switcher.Gio.SubprocessLauncher.new = lambda flags: touched.append(1)
        try:
            switcher.process.run_async(["audioctl", "status"], lambda ok, out: None)
        finally:
            switcher.Gio.SubprocessLauncher.new = real
        self.assertEqual([], touched)

    def test_a_broken_pipe_without_a_line_callback_is_reported(self):
        self.arrange(lines=["x"], fail_at="communicate")
        seen = []
        switcher.process.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)))
        self.assertEqual(seen[0][0], False)


class Recording:
    """A widget that remembers what it was told, and answers what a test set."""

    def __init__(self, active=False):
        self.title = None
        self.subtitle = None
        self.focus = False
        self.value = 0.0
        self.visible = None
        self.sensitive = True
        self.active = active
        self.label = None
        self.text = None
        self.fraction = None
        self.revealed = None
        self.tooltip = None

    def set_title(self, text):
        self.title = text

    def set_subtitle(self, text):
        self.subtitle = text

    def has_focus(self):
        """The security page refuses to overwrite the network somebody is
        typing into. A stub that always claims focus would hide the refresh
        entirely, so this answers what a test set."""
        return self.focus

    def set_sensitive(self, value):
        self.sensitive = value

    def set_active(self, value):
        self.active = value

    def set_value(self, value):
        self.value = value

    def get_value(self):
        return self.value

    def get_active(self):
        return self.active

    def set_label(self, text):
        self.label = text

    def set_text(self, text):
        self.text = text

    def get_text(self):
        return self.text

    def set_fraction(self, value):
        self.fraction = value

    def pulse(self):
        self.fraction = "pulsing"

    def set_tooltip_text(self, text):
        self.tooltip = text

    def set_reveal_child(self, value):
        self.revealed = value

    def set_visible(self, value):
        self.visible = value

    def set_model(self, model):
        self.model = model

    def set_selected(self, index):
        self.selected = index

    def get_selected(self):
        return getattr(self, "selected", 0)

    def add_toast(self, toast):
        # The stub keeps constructor arguments as attributes, so the title of
        # the toast is readable rather than the object's name.
        self.text = getattr(toast, "title", toast)


class KeepsTheComboValueVisible(unittest.TestCase):
    """combo.py walks a row's widgets. On 29.9.2026 that walk met the stub,
    whose "next sibling" is never None, ran without end and grew the test
    run to 17 GB - and the phone's shell went down with it."""

    def test_a_widget_tree_without_end_is_left_after_a_bounded_walk(self):
        class Endless:
            made = 0

            def get_first_child(self):
                Endless.made += 1
                return Endless()

            def get_next_sibling(self):
                Endless.made += 1
                return Endless()

        self.assertIsNone(switcher.combo.keep_value_visible(Endless()))
        self.assertLess(Endless.made, 1000)


class SpeaksTwoLanguages(unittest.TestCase):
    """English in the code, German beside it - and nothing on screen without
    both. Asked for on 29.9.2026: the owner describes a row in German, it is
    written in English, and the German goes into miscde/lang_de.py. This is
    what keeps the second half from being forgotten."""

    PLACEHOLDER = re.compile(r"\{[^{}]*\}|%[-#0 +]*(?:\*|\d+)?(?:\.(?:\*|\d+))?[sdfr]")

    @staticmethod
    def keys():
        import ast
        found = []
        for path in sorted((ROOT / "miscde").rglob("*.py")):
            for node in ast.walk(ast.parse(path.read_text())):
                if (isinstance(node, ast.Call)
                        and getattr(node.func, "id", None) == "_"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)
                        and isinstance(node.args[0].value, str)):
                    found.append((str(path.relative_to(ROOT)), node.lineno,
                                  node.args[0].value))
        # Shown through _() at the place they are displayed, so the text is
        # not a literal there: the tab names and what each tool does.
        for comp in switcher.COMPONENTS + [switcher.SELF]:
            for field in ("page", "does"):
                if comp.get(field):
                    found.append(("miscde/components.py", 0, comp[field]))
        return found

    def test_every_text_has_its_german(self):
        from miscde.lang_de import TRANSLATIONS
        missing = sorted({"%s:%d  %r" % (f, n, k) for f, n, k in self.keys()
                          if k not in TRANSLATIONS})
        self.assertEqual([], missing,
                         "no German for these - add them to miscde/lang_de.py")

    def test_the_german_keeps_every_placeholder(self):
        """A German text that drops or renames {tool} or %s would raise when
        it is filled in - on the phone, in German only."""
        from miscde.lang_de import TRANSLATIONS
        wrong = []
        for en, de in TRANSLATIONS.items():
            if sorted(self.PLACEHOLDER.findall(en)) != sorted(self.PLACEHOLDER.findall(de)):
                wrong.append((en, de))
        self.assertEqual([], wrong)

    def test_nothing_in_the_table_is_left_over(self):
        """An entry no code uses any more is a translation of nothing - and
        usually the sign that the English was changed without the German."""
        from miscde.lang_de import TRANSLATIONS
        used = {k for _f, _n, k in self.keys()}
        self.assertEqual([], sorted(set(TRANSLATIONS) - used))

    def test_the_choice_is_kept_and_nonsense_is_english(self):
        i18n = switcher.i18n
        self.assertEqual("en", i18n.load())
        self.assertTrue(i18n.save("de"))
        self.assertEqual("de", i18n.load())
        with open(i18n.config_file(), "w") as f:
            f.write("klingon\n")
        self.assertEqual("en", i18n.load())
        self.assertFalse(i18n.save("klingon"))
        os.remove(i18n.config_file())

    def test_the_window_builds_in_german(self):
        """A fresh process, the way the phone starts after choosing: every
        page built, in German, without one exception."""
        cfg = tempfile.mkdtemp(prefix="miscde-test-")
        os.makedirs(os.path.join(cfg, "misc-de"))
        with open(os.path.join(cfg, "misc-de", "language"), "w") as f:
            f.write("de\n")
        script = (
            "import sys; sys.path[:0] = [%r, %r]\n"
            "import gi_stub; rec = gi_stub.install()\n"
            "import miscde\n"
            "miscde.Window(miscde.Adw.Application())\n"
            "titles = [str(c[2].get('title', '')) for c in rec.calls]\n"
            "print('\\n'.join(titles))\n" % (str(ROOT / "tests"), str(ROOT)))
        env = dict(os.environ, XDG_CONFIG_HOME=cfg)
        out = subprocess_real.run([sys.executable, "-c", script], env=env,
                                  capture_output=True, text=True, timeout=60)
        self.assertEqual(0, out.returncode, out.stderr[-2000:])
        self.assertIn("Soundserver", out.stdout)
        self.assertIn("Musik-Codec", out.stdout)
        self.assertNotIn("Sound server", out.stdout)


class FindsItsTools(unittest.TestCase):
    """Which "audioctl" the app starts.

    The installed paths come before $PATH, because what is started here used to
    go on and ask polkit for root - and letting the search order decide which
    binary that is was the one thing not to do. The reason is gone, the order
    stays: $PATH is the last resort, not the first.
    """

    def test_an_installed_path_wins_over_the_search_path(self):
        original = switcher.os.access
        switcher.os.access = lambda path, mode: path == "/usr/bin/audioctl"
        try:
            self.assertEqual("/usr/bin/audioctl", switcher._tool("audioctl"))
        finally:
            switcher.os.access = original

    def test_usr_local_wins_over_usr(self):
        original = switcher.os.access
        switcher.os.access = lambda path, mode: True
        try:
            self.assertEqual("/usr/local/bin/audioctl", switcher._tool("audioctl"))
        finally:
            switcher.os.access = original

    def test_with_nothing_installed_it_falls_back(self):
        original_access, original_which = switcher.os.access, switcher.shutil.which
        switcher.os.access = lambda path, mode: False
        switcher.shutil.which = lambda name: "/opt/bin/" + name
        try:
            self.assertEqual("/opt/bin/audioctl", switcher._tool("audioctl"))
        finally:
            switcher.os.access, switcher.shutil.which = original_access, original_which


    def test_a_tool_that_is_nowhere_is_admitted_rather_than_invented(self):
        """_tool_maybe decides whether the modem page exists at all. Guessing a
        path here would build a whole tab around a program that is not
        installed, and every row in it would report a failure of its own."""
        original_access, original_which = switcher.os.access, switcher.shutil.which
        switcher.os.access = lambda path, mode: False
        switcher.shutil.which = lambda name: None
        try:
            self.assertIsNone(switcher.tools._tool_maybe("modemctl"))
        finally:
            switcher.os.access, switcher.shutil.which = original_access, original_which

    def test_a_tool_only_on_the_search_path_is_still_found(self):
        original_access, original_which = switcher.os.access, switcher.shutil.which
        switcher.os.access = lambda path, mode: False
        switcher.shutil.which = lambda name: "/opt/bin/" + name
        try:
            self.assertEqual("/opt/bin/modemctl", switcher.tools._tool_maybe("modemctl"))
        finally:
            switcher.os.access, switcher.shutil.which = original_access, original_which


class TheMenu(unittest.TestCase):
    """The list the window opens on, and the page behind it."""

    def setUp(self):
        self.win = switcher.Window(switcher.Adw.Application())

    def test_every_built_page_has_a_row_and_nothing_else_does(self):
        self.assertEqual(sorted(k for k, p in self.win.pages.items()
                                if p is not None),
                         sorted(self.win.menu_rows))

    def test_a_missing_tool_says_so_in_the_list(self):
        self.win.menu_rows["gps"] = row = Recording()
        self.win.live["gps"] = None
        self.win.mark_installed("gps")
        self.assertEqual("Not installed", row.subtitle)
        self.win.live["gps"] = "/usr/bin/furios-gps-contribute"
        self.win.mark_installed("gps")
        self.assertEqual("Helps Wi-Fi location via beaconDB", row.subtitle)

    def test_the_other_page_has_no_tool_to_miss(self):
        self.win.menu_rows["other"] = row = Recording()
        self.win.mark_installed("other")
        self.assertEqual("Dock, blur and app names", row.subtitle)

    def test_opening_pushes_the_page_once(self):
        pushed = []
        shown = []

        class Nav:
            visible = None

            def get_visible_page(nav):
                return nav.visible

            def push(nav, page):
                pushed.append(page)
                nav.visible = page

        class Stack:
            def set_visible_child_name(stack, name):
                shown.append(name)

        self.win.nav, self.win.stack = Nav(), Stack()
        self.win.open_page("modem")
        self.win.open_page("gps")
        self.assertEqual(["modem", "gps"], shown)
        self.assertEqual([self.win.detail], pushed)


class TheWindow(unittest.TestCase):
    """The window, driven through its own callbacks.

    Building it needs a stub, and a stub proves nothing about GTK. What it does
    prove is the part that has been wrong before: which words end up in front
    of someone, and whether the switch follows the state or fights it.
    """

    def setUp(self):
        # What an earlier test recorded as "before" is not this one's.
        forget_all_records()
        self.win = switcher.Window(switcher.Adw.Application())
        names = ["row_profile", "row_server", "row_sinks", "switch_row",
                 "persist_row", "dmnr_row", "btsave_row", "codec_row",
                 "codec_scope_row", "btx_row", "ringback_row",
                 "update_btn",
                 "progress", "progress_revealer", "toasts"]
        # The modem widgets only exist when the page was built, and the page is
        # only built when modemctl is installed - so they are swapped in the
        # same way, and only when they are there to swap.
        if MODEMCTL:
            names += ["modem_row", "modem_progress",
                      "modem_revealer", "mrow_profile", "mrow_health",
                      "mrow_signal", "modem_restore_btn",
                      "sim_group", "sim_row", "nr_group", "nr_row"]
        names.append("rescue_btn")
        # Always, unlike the others: every GPS handler asks self.live for
        # its tool, so a test says whether it is there by setting that, and
        # the page is tested on a phone that does not have it installed.
        names += ["gps_contrib", "gps_contrib_stats", "gps_firefox",
                  "gps_restore_btn"]
        if KILLSWITCH:
            names += ["sw_row", "sw_wifi", "sw_bt", "sw_modem",
                      "sw_restore_btn"]
        # Always, like GPS: the battery handlers ask self.live for battctl,
        # so the page is tested on a phone without it as well - found on
        # 30.9.2026, when a clean phone turned 17 of these into errors.
        names += ["batt_restore_btn"]
        if SECCTL:
            names += ["sec_restore_btn"]
        for name in names:
            setattr(self.win, name, Recording())
        if MODEMCTL:
            self.win.modem_rows = [self.win.modem_row,
                                   self.win.modem_restore_btn]
        self.win.gps_rows = [self.win.gps_contrib, self.win.gps_firefox,
                             self.win.gps_restore_btn]
        if KILLSWITCH:
            self.win.sw_rows = [self.win.sw_row, self.win.sw_wifi,
                                self.win.sw_bt, self.win.sw_restore_btn]
        # Assigned, not setdefault: on a phone without battctl the window
        # has already written None there, and every command would start
        # with it. Nothing is run - run_async is replaced below.
        self.win.live["battery"] = BATTCTL or "/nonexistent/battctl"
        # What the page builder sets up besides its widgets. Without
        # batt_cfg the stub answers with a Fake, and the slider write
        # compares against that.
        self.win.batt_cfg = None
        self.win._batt_pending = {}
        self.win._batt_write = 0
        # The page keeps its controls in two dictionaries, so the
        # stand-ins go in there rather than on attributes.
        self.win.batt_switches = {}
        self.win.batt_scales = {}
        for key, _head, _title, _sub, sliders in switcher.Window.BATTERY_OPTIONS:
            row = Recording()
            row.slider_rows = [Recording(), Recording()]
            self.win.batt_switches[key] = row
            for _label, ckey, _lo, _hi, _st, _di, _un in sliders:
                self.win.batt_scales[ckey] = Recording()
        self.win.batt_rows = (list(self.win.batt_switches.values())
                              + [self.win.batt_restore_btn])
        if SECCTL:
            # The three switches live in a dictionary, like the battery
            # page's, so the stand-ins go in there rather than on attributes.
            self.win.sec_switches = {key: Recording()
                                     for key, _t, _s in switcher.Window.PARTS}
            self.win.sec_rows = (list(self.win.sec_switches.values())
                                 + [self.win.sec_restore_btn])
        self.ran = []
        self.original = switcher.process.run_async
        # Four fields, not three: the components page passes cwd, stdin and a
        # longer timeout, and a test that could not see them could not check
        # that the password goes through the pipe and never through argv.
        switcher.process.run_async = lambda argv, done, on_line=None, **kw: self.ran.append(
            (argv, done, on_line, kw))

    def tearDown(self):
        switcher.process.run_async = self.original

    STATUS = ("Profile (active):   pw-hal\n"
              "Profile (persistent): standard\n"
              "Test mode:          yes - falls back on reboot\n"
              "Pulse server:       PulseAudio (on PipeWire 1.6.6)\n"
              "Sinks:              droid-sink,droid-voip-sink\n")

    PERMANENT = ("Profile (active):   pw-hal\n"
                 "Profile (persistent): pw-hal\n"
                 "Pulse server:       PulseAudio (on PipeWire 1.6.6)\n"
                 "Sinks:              droid-sink\n")

    def test_status_is_turned_into_something_a_person_can_read(self):
        self.win.on_status(True, self.STATUS)
        self.assertIn("PipeWire", self.win.row_profile.subtitle)
        self.assertIn("until the next restart", self.win.row_profile.subtitle)
        self.assertIn("older apps", self.win.row_server.subtitle)
        self.assertEqual("droid-sink, droid-voip-sink", self.win.row_sinks.subtitle)
        self.assertEqual(1, self.win.switch_row.selected)

    def test_a_profile_that_survives_a_reboot_says_so(self):
        """The state the phone had for two days while this window said nothing.

        "Profile (persistent)" was never read, so the remembered-switch sat at
        its default - off - on a phone that was on pw-hal for good.
        """
        self.win.on_status(True, self.PERMANENT)
        self.assertIn("kept after a restart", self.win.row_profile.subtitle)
        self.assertTrue(self.win.persist_row.active,
                        "a permanent profile was shown as not remembered")
        # The owner's description (29.9.), and nothing added: it holds.
        self.assertEqual(self.win.PERSIST_WORDS, self.win.persist_row.subtitle)

    JSON_TRY = ('{"profile": "pw-hal", "recorded": "pw-hal", "persistent": '
                '"standard", "test_mode": true, "fell_back": null, '
                '"ofono_dropin_conflict": null, "pulse_server": '
                '"PulseAudio (on PipeWire 1.6.6)", "sinks": ["droid-sink", '
                '"bluez_output.X"], "units": {}}')

    def test_json_status_is_read(self):
        self.win.on_status(True, self.JSON_TRY)
        sub = self.win.row_profile.subtitle
        self.assertIn("until the next restart", sub)
        self.assertEqual(self.win.row_sinks.subtitle, "droid-sink, bluez_output.X")

    def test_json_status_names_a_record_that_disagrees(self):
        self.win.on_status(True, self.JSON_TRY.replace('"recorded": "pw-hal"',
                                                       '"recorded": "standard"'))
        self.assertIn('recorded is "standard"', self.win.row_profile.subtitle)

    SHIPPED = ("Profile (active):   standard\n"
               "Profile (persistent): standard\n"
               "Pulse server:       pulseaudio\n"
               "Sinks:              sink.primary_output\n")

    def test_the_shipped_stack_has_nothing_remembered_yet(self):
        """A new phone showed the switch on before anybody chose anything
        (30.9.2026). Off, and the next switch is a trial until reboot."""
        self.win._persist_wish = False
        self.win.on_status(True, self.SHIPPED)
        self.assertFalse(self.win.persist_row.active)

    def test_switching_it_on_by_hand_survives_the_next_refresh(self):
        self.win._syncing = False
        row = Recording()
        row.active = True
        row.get_active = lambda: True
        self.win.on_persist_toggled(row, None)
        self.win.on_status(True, self.SHIPPED)
        self.assertTrue(self.win.persist_row.active)

    def test_what_on_status_sets_is_not_taken_for_a_wish(self):
        self.win._persist_wish = False
        self.win.on_status(True, self.PERMANENT)      # sets it on, as a report
        self.win._syncing = True
        self.win.on_persist_toggled(self.win.persist_row, None)
        self.win._syncing = False
        self.win.on_status(True, self.SHIPPED)
        self.assertFalse(self.win.persist_row.active)

    def _tap_remember(self):
        self.win._syncing = False
        self.win.busy = False
        row = Recording()
        row.active = True
        row.get_active = lambda: True
        self.win.on_persist_toggled(row, None)

    def test_remember_after_a_trial_makes_it_permanent(self):
        """4.10.2026: pw-hal chosen first, remember switched on second -
        nothing was written, and the reboot went back to PulseAudio."""
        self.win.live["audio"] = "audioctl"
        self.win.on_status(True, self.STATUS)
        self._tap_remember()
        self.assertEqual([["audioctl", "set", "pw-hal"]],
                         [argv for argv, *_ in self.ran])

    def test_remember_on_a_permanent_profile_runs_nothing(self):
        self.win.live["audio"] = "audioctl"
        self.win.on_status(True, self.PERMANENT)
        self._tap_remember()
        self.assertEqual([], self.ran)

    def test_remember_on_the_shipped_stack_stays_a_wish(self):
        self.win.live["audio"] = "audioctl"
        self.win.on_status(True, self.SHIPPED)
        self._tap_remember()
        self.assertEqual([], self.ran)

    def test_remember_without_a_persistent_line_runs_nothing(self):
        """An older audioctl: whether it holds is unknown, so nothing is set."""
        self.win.live["audio"] = "audioctl"
        self.win.on_status(True, "Profile (active):   pw-hal\nSinks:              x\n")
        self._tap_remember()
        self.assertEqual([], self.ran)

    def test_remember_also_keeps_echo_suppression_that_runs_for_now(self):
        self.win.live["audio"] = "audioctl"
        self.win.on_dmnr_status(True, "state=on\npersistent=no\n")
        self.win.on_status(True, self.PERMANENT)
        self._tap_remember()
        self.assertEqual([["set", "on"]],
                         [argv[1:] for argv, *_ in self.ran])

    def test_a_profile_that_only_holds_until_the_reboot_says_what_returns(self):
        self.win.on_status(True, self.STATUS)
        self.assertFalse(self.win.persist_row.active)
        self.assertIn("PulseAudio", self.win.persist_row.subtitle)

    def test_a_status_without_the_persistent_line_claims_nothing(self):
        """An audioctl too old to print it must not produce an invented state."""
        self.win.on_status(True, "Profile (active):   pw-hal\nSinks:              x\n")
        self.assertNotIn("permanent", self.win.row_profile.subtitle)
        self.assertNotIn("until the next reboot", self.win.row_profile.subtitle)
        self.assertFalse(self.win.persist_row.active)

    def test_audioctl_not_answering_claims_nothing_about_the_phone(self):
        """Off is the shipped state, so a switch left at off is not a blank -
        it is a plausible statement about a phone this window cannot see."""
        self.win.switch_row.selected = 1
        self.win.on_status(False, "Failed to execute child process")
        self.assertIn("did not answer", self.win.row_profile.subtitle)
        self.assertIn("did not answer", self.win.persist_row.subtitle)
        self.assertEqual(1, self.win.switch_row.selected,
                         "the switch was moved on the strength of no answer")
        self.assertFalse(self.win.switch_row.sensitive)
        self.assertFalse(self.win.persist_row.sensitive)

    def test_a_control_with_nothing_behind_it_stays_unusable(self):
        """set_busy used to be the only hand on the sensitivity, so the next
        finished action handed back a switch that leads nowhere."""
        self.win.on_status(False, "")
        self.win.set_busy(True)
        self.win.set_busy(False)
        self.assertFalse(self.win.switch_row.sensitive)
        self.assertFalse(self.win.persist_row.sensitive)
        self.assertIn("did not answer", self.win.switch_row.subtitle)

    def test_and_becomes_usable_again_once_audioctl_answers(self):
        self.win.on_status(False, "")
        self.win.on_status(True, self.PERMANENT)
        self.assertTrue(self.win.switch_row.sensitive)
        self.assertIn("main service", self.win.switch_row.subtitle)

    def test_an_echo_switch_with_no_script_behind_it_stays_off_limits(self):
        self.win.on_dmnr_status(False, "")
        self.win.set_busy(True)
        self.win.set_busy(False)
        self.assertFalse(self.win.dmnr_row.sensitive)
        self.assertIn("not available", self.win.dmnr_row.subtitle)

    def test_the_shipped_state_is_named_as_such(self):
        self.win.on_status(True, "Profile (active):   standard\nSinks:              x\n")
        self.assertIn("as shipped", self.win.row_profile.subtitle)
        self.assertEqual(0, self.win.switch_row.selected)

    def test_the_tunnel_profile_has_its_own_sentence(self):
        self.win.on_status(True, "Profile (active):   pw-tunnel\n")
        self.assertIn("with PipeWire on top", self.win.row_profile.subtitle)

    def test_a_profile_it_does_not_know_is_shown_as_it_is(self):
        self.win.on_status(True, "Profile (active):   something-else\n")
        self.assertIn("something-else", self.win.row_profile.subtitle)

    def test_a_warning_from_audioctl_is_passed_on(self):
        self.win.on_status(True, self.STATUS +
                           "WARNING:            recorded is \"standard\"\n")
        self.assertIn("recorded is", self.win.row_profile.subtitle)

    def test_no_sinks_reads_as_none_rather_than_as_a_dash(self):
        self.win.on_status(True, "Profile (active):   standard\nSinks:\n")
        self.assertEqual("none", self.win.row_sinks.subtitle)

    def test_the_switch_does_not_fire_while_it_is_being_synced(self):
        """Following the state must not look like someone flipping it."""
        self.win.on_status(True, self.STATUS)
        self.assertEqual([], self.ran, "syncing the switch started a command")

    def test_choosing_pipewire_asks_for_pw_hal(self):
        self.win.switch_row.selected = 1
        self.win.persist_row.active = False
        self.win.on_switch(self.win.switch_row, None)
        argv = self.ran[0][0]
        self.assertEqual(["try", "pw-hal"], argv[1:])

    def test_and_with_remember_ticked_it_asks_for_set(self):
        self.win.switch_row.selected = 1
        self.win.persist_row.active = True
        self.win.on_switch(self.win.switch_row, None)
        self.assertEqual(["set", "pw-hal"], self.ran[0][0][1:])

    def test_choosing_pulseaudio_always_sets_standard_persistently(self):
        """PulseAudio after a reboot too - a test-mode choice would come back."""
        self.win.switch_row.selected = 0
        self.win.on_switch(self.win.switch_row, None)
        self.assertEqual(["set", "standard"], self.ran[0][0][1:])

    def test_the_codec_list_makes_no_performance_claims(self):
        """Names only since 27.9.2026 - no CPU figures, no measurements."""
        for _k, name, note in switcher.pages.audio.CODECS:
            for word in ("%", "CPU", "measured"):
                self.assertNotIn(word, note, name)

    def test_the_codec_entries_are_bare_names(self):
        """No trailing " - " left over from the notes that were removed."""
        src = open(os.path.join(os.path.dirname(switcher.__file__),
                                "window.py")).read()
        self.assertNotIn('"%s - %s" % (name, note)', src)

    def test_the_server_choice_offers_exactly_the_two_servers(self):
        self.assertEqual(["standard", "pw-hal"],
                         [k for k, _ in switcher.pages.audio.SERVERS])

    def test_the_switch_is_ignored_while_something_is_running(self):
        self.win.busy = True
        self.win.on_switch(self.win.switch_row, None)
        self.assertEqual([], self.ran)

    def test_progress_shows_what_audioctl_says_and_cuts_it_to_a_line(self):
        self.win.on_progress_line("x" * 200)
        self.assertEqual(60, len(self.win.progress.text))

    def test_the_modem_page_pulses_its_own_bar(self):
        """The modem page showed its bar frozen and empty for 30 s while its
        words went into the audio bar, on a page nobody was looking at."""
        bar, shown = Recording(), Recording()
        self.win.pulse_start("Switching to SIM 2", bar, shown)
        self.win.on_progress_line("oFono is back")
        self.assertEqual("oFono is back", bar.text)
        self.assertNotEqual("oFono is back", self.win.progress.text)
        self.win.pulse_stop()
        self.win.pulse_start("Switching …")
        self.win.on_progress_line("audio")
        self.assertEqual("audio", self.win.progress.text, "and back to audio")

    def test_a_finished_switch_names_the_server_now_active(self):
        self.win.on_switched(True, "step\nswitched to pw-hal\n", "PipeWire")
        self.assertEqual("PipeWire is active now", str(self.win.toasts.text))

    def test_a_switch_with_no_output_still_says_something(self):
        self.win.on_switched(True, "")
        self.assertIsNotNone(self.win.toasts.text)

    def test_a_failed_switch_says_so_and_shows_the_output(self):
        self.win.on_switched(False, "it went wrong")
        self.assertIn("failed", str(self.win.toasts.text).lower())

    def test_a_failed_switch_without_output_still_reports(self):
        self.win.on_switched(False, "")
        self.assertIsNotNone(self.win.toasts.text)

    # --- Bluetooth powersave, driven through the row ---

    def watch_password_prompt(self):
        """Catch the password dialog without opening one.

        Patched on the CLASS, not on the instance: the window inherits from a
        stub whose __setattr__ files everything away in a dictionary, so
        assigning over a real method there changes nothing and the test would
        pass while measuring the untouched original.
        """
        asked = []
        patch = mock.patch.object(
            type(self.win), "ask_btsave_password",
            lambda _self, wanted: asked.append(wanted))
        patch.start()
        self.addCleanup(patch.stop)
        return asked

    def scratch_config(self, contents):
        """batman's config, somewhere this test may write."""
        audio = importlib.import_module("miscde.pages.audio")
        handle = tempfile.NamedTemporaryFile("w", suffix=".conf", delete=False)
        handle.write(contents)
        handle.close()
        self.addCleanup(os.unlink, handle.name)
        patch = mock.patch.object(audio, "BATMAN_CONFIG", handle.name)
        patch.start()
        self.addCleanup(patch.stop)
        return handle.name

    def test_the_powersave_row_follows_the_file(self):
        self.scratch_config("[Settings]\nBTSAVE=true\n")
        self.win.sync_btsave()
        self.assertTrue(self.win.btsave_row.active)
        self.assertTrue(self.win.btsave_ok)
        self.assertIn("headset", self.win.btsave_row.subtitle)

    def test_without_batmans_config_the_powersave_row_closes(self):
        """Not shown as off: nothing is powering the adapter down in that
        case, but a row that says so from a file it could not read is a
        guess dressed as a reading."""
        audio = importlib.import_module("miscde.pages.audio")
        patch = mock.patch.object(audio, "BATMAN_CONFIG",
                                  "/nonexistent/batman/config")
        patch.start()
        self.addCleanup(patch.stop)
        self.win.sync_btsave()
        self.assertFalse(self.win.btsave_ok)
        self.assertFalse(self.win.btsave_row.sensitive)
        self.assertIn("batman", self.win.btsave_row.subtitle)

    def test_syncing_the_powersave_row_does_not_switch_anything(self):
        """set_active on the row fires notify::active in the real widget, and
        a sync that ran a sudo command every time the page refreshed would
        rewrite batman's config on its own."""
        self.scratch_config("[Settings]\nBTSAVE=true\n")
        self.win.sync_btsave()
        self.assertEqual(self.ran, [])

    def test_the_powersave_switch_runs_one_command_as_root(self):
        self.win.btsave_row.active = False
        self.win.on_btsave(self.win.btsave_row, None)
        argv, _done, _line, kw = self.ran[0]
        self.assertEqual(argv, switcher.btsave_argv(False))
        self.assertIsNone(kw.get("stdin"))

    def test_a_password_is_asked_for_rather_than_reported(self):
        """sudo -n refusing is the one answer this switch can do something
        about. Reporting it would leave somebody with an error message and a
        switch that did nothing."""
        asked = self.watch_password_prompt()
        self.win.on_btsave_done(False, "sudo: a password is required", True)
        self.assertEqual(asked, [True])
        self.assertIsNone(self.win.toasts.text)

    def test_an_older_sudo_asking_for_a_helper_counts_as_the_same_question(self):
        asked = self.watch_password_prompt()
        self.win.on_btsave_done(
            False, "sudo: no tty present and no askpass program specified",
            False)
        self.assertEqual(asked, [False])

    def test_the_password_goes_through_the_pipe(self):
        self.win.apply_btsave(True, "hunter2")
        argv, _done, _line, kw = self.ran[0]
        self.assertEqual(kw.get("stdin"), "hunter2\n")
        self.assertNotIn("hunter2", argv)

    def test_a_cancelled_password_puts_the_row_back(self):
        self.scratch_config("[Settings]\nBTSAVE=true\n")
        entry = Recording()
        entry.text = "hunter2"
        self.win._btsave_pending = (False, entry)
        self.win.on_btsave_password(None, "cancel")
        # Nothing ran, the file still says true, and so does the row.
        self.assertEqual(self.ran, [])
        self.assertTrue(self.win.btsave_row.active)
        self.assertEqual(entry.text, "")

    def test_a_change_that_failed_leaves_the_row_at_the_file(self):
        """The row is a reading, not a memory of what was clicked."""
        self.scratch_config("[Settings]\nBTSAVE=true\n")
        self.win.btsave_row.active = False
        self.win.on_btsave_done(False, "sed: cannot write", False)
        self.assertTrue(self.win.btsave_row.active)
        self.assertIn("Could not change", str(self.win.toasts.text))

    def test_the_echo_switch_asks_the_dmnr_helper(self):
        self.win.dmnr_row.active = True
        self.win.on_dmnr(self.win.dmnr_row, None)
        self.assertEqual("on", self.ran[0][0][1])
        self.ran.clear()
        self.win.busy = False
        self.win.dmnr_row.active = False
        self.win.on_dmnr(self.win.dmnr_row, None)
        self.assertEqual("off", self.ran[0][0][1])

    def test_the_echo_switch_asks_for_a_password_when_sudo_wants_one(self):
        """Without a sudoers rule that asks for nothing, the helper's first
        sudo had no terminal and the switch simply failed."""
        asked = []
        patch = mock.patch.object(type(self.win), "ask_dmnr_password",
                                  lambda _self: asked.append(True))
        patch.start()
        self.addCleanup(patch.stop)
        self.win.dmnr_row.active = True
        self.win.on_dmnr(self.win.dmnr_row, None)
        self.assertIsNone(self.ran[0][3].get("env"),
                          "the first try asks nobody for anything")
        self.win.on_dmnr_done(False, "sudo: a terminal is required to read "
                              "the password; either use the -S option to "
                              "read from standard input or configure an "
                              "askpass helper")
        self.assertEqual([True], asked)
        self.assertNotIn("Could not", str(self.win.toasts.text))

    def test_the_password_reaches_the_helper_through_askpass_only(self):
        started = []

        class FakeAskpass:
            def __init__(self, secret):
                started.append(secret)
                self.error = None
                self.stopped = False

            def start(self):
                return "/run/user/0/askpass-helper"

            def stop(self):
                started.append("stopped")

        audio = importlib.import_module("miscde.pages.audio")
        patch = mock.patch.object(audio.askpass, "Askpass", FakeAskpass)
        patch.start()
        self.addCleanup(patch.stop)
        self.win._dmnr_args = ["set", "on"]
        self.win.apply_dmnr("hunter2")
        argv, done, _line, kw = self.ran[0]
        self.assertNotIn("hunter2", " ".join(argv))
        self.assertIsNone(kw.get("stdin"))
        self.assertEqual("/run/user/0/askpass-helper",
                         kw["env"]["SUDO_ASKPASS"])
        self.assertEqual(["set", "on"], argv[1:])
        # A wrong password is reported, not asked for again and again.
        done(False, "sudo: 1 incorrect password attempt; askpass")
        self.assertIn("Could not", str(self.win.toasts.text))
        self.assertEqual(["hunter2", "stopped"], started)

    def test_the_echo_switch_is_ignored_while_busy(self):
        self.win.busy = True
        self.win.on_dmnr(self.win.dmnr_row, None)
        self.assertEqual([], self.ran)

    def test_the_echo_result_is_reported_either_way(self):
        self.win.on_dmnr_done(True, "state=on")
        self.assertIn("Echo suppression", str(self.win.toasts.text))
        self.win.on_dmnr_done(False, "")
        self.assertIn("Could not", str(self.win.toasts.text))

    def test_a_device_without_the_helper_disables_the_switch(self):
        self.win.on_dmnr_status(False, "")
        self.assertFalse(self.win.dmnr_row.sensitive)
        self.assertIn("not available", self.win.dmnr_row.subtitle)

    def test_the_echo_switch_follows_the_state_of_the_file(self):
        """Four states, not two. Whether it is on now and whether it survives
        a reboot are separate facts - a bind mount is gone after a restart
        whatever the switch said - so neither may be read off the other."""
        self.win.on_dmnr_status(True, "state=on\npersistent=yes\n")
        self.assertTrue(self.win.dmnr_row.active)
        # The owner's description (29.9.); only a state that will not last
        # adds to it.
        self.assertEqual(self.win.DMNR_WORDS, self.win.dmnr_row.subtitle)

        self.win.on_dmnr_status(True, "state=on\npersistent=no\n")
        self.assertTrue(self.win.dmnr_row.active)
        self.assertIn("until the next reboot", self.win.dmnr_row.subtitle)

        self.win.on_dmnr_status(True, "state=off\npersistent=no\n")
        self.assertFalse(self.win.dmnr_row.active)
        self.assertEqual(self.win.DMNR_WORDS, self.win.dmnr_row.subtitle)

        # Switched off now but still marked: the next boot brings it back, and
        # a subtitle saying only "off" would be a lie by omission.
        self.win.on_dmnr_status(True, "state=off\npersistent=yes\n")
        self.assertFalse(self.win.dmnr_row.active)
        self.assertIn("on again after the next reboot", self.win.dmnr_row.subtitle)

    def test_the_echo_switch_is_remembered_when_the_persist_switch_is_on(self):
        """The same switch governs both rows above it, so the echo control
        has to read it exactly as the stack control does."""
        self.win.persist_row.active = True
        self.win.dmnr_row.active = True
        self.win.on_dmnr(self.win.dmnr_row, None)
        self.assertEqual(["set", "on"], self.ran[0][0][1:3])

    def test_without_it_the_echo_switch_only_holds_until_the_reboot(self):
        self.win.persist_row.active = False
        self.win.dmnr_row.active = True
        self.win.on_dmnr(self.win.dmnr_row, None)
        self.assertEqual(["on"], self.ran[0][0][1:])

    def test_turning_echo_off_is_remembered_too(self):
        """Otherwise "off" plus a reboot would silently turn it back on."""
        self.win.persist_row.active = True
        self.win.dmnr_row.active = False
        self.win.on_dmnr(self.win.dmnr_row, None)
        self.assertEqual(["set", "off"], self.ran[0][0][1:3])

    def test_the_echo_row_sits_above_the_one_that_qualifies_it(self):
        """Read off what the page built, not off the source. The remember
        switch now governs the echo row as well, and a qualifier that sits
        above what it qualifies reads as belonging to the row before it."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        titles = [str(c[2].get("title", "")) for c in recorder.calls
                 if c[0] == "Adw.SwitchRow"]
        echo = [i for i, t in enumerate(titles) if "echo suppression" in t.lower()]
        remember = [i for i, t in enumerate(titles) if t.startswith("Keep after")]
        self.assertTrue(echo and remember, "rows not built: %s" % titles)
        self.assertLess(echo[0], remember[0])

    # --- the Bluetooth helpers, apart from the server ---

    def test_under_pipewire_the_helpers_are_on_and_can_be_switched_off(self):
        self.win.busy = False
        self.win.on_btx_status(True, "bt-extras=on\nprofile=pw-hal\neffective=all\n")
        self.assertTrue(self.win.btx_row.visible)
        self.assertTrue(self.win.btx_row.get_active())
        self.assertTrue(self.win.btx_row.sensitive)
        self.assertIn("audio and microphone", self.win.btx_row.subtitle)
        self.assertNotIn("PulseAudio", self.win.btx_row.subtitle)
        self.win.on_btx_status(True, "bt-extras=off\nprofile=pw-hal\neffective=none\n")
        self.assertFalse(self.win.btx_row.get_active())

    def test_switching_them_off_under_pipewire_runs_audioctl(self):
        self.win.busy = False
        self.win.live["audio"] = "/usr/bin/audioctl"
        self.win.on_btx_status(True, "bt-extras=on\nprofile=pw-hal\neffective=all\n")
        self.win.btx_row.active = False
        self.win.on_btx(self.win.btx_row, None)
        self.assertEqual(["/usr/bin/audioctl", "bt-extras", "off"], self.ran[-1][0])

    def test_under_pulseaudio_they_are_not_offered(self):
        """Nothing of ours runs under PulseAudio (decided 29.9.2026)."""
        self.win.busy = False
        self.win.on_btx_status(True, "bt-extras=on\nprofile=pw-hal\noffered=yes\neffective=all\n")
        self.assertTrue(self.win.btx_row.visible)
        self.win.on_btx_status(True, "bt-extras=on\nprofile=standard\noffered=no\neffective=none\n")
        self.assertFalse(self.win.btx_row.visible)
        self.assertFalse(self.win.btx_ok)

    # --- the ringback tone ---

    def test_ringback_follows_audioctl_and_switches_through_it(self):
        self.win.busy = False
        self.win.live["audio"] = "/usr/bin/audioctl"
        self.win.on_ringback_status(True, "ringback=off\navailable=yes\n")
        self.assertTrue(self.win.ringback_row.visible)
        self.assertFalse(self.win.ringback_row.get_active())
        self.assertTrue(self.win.ringback_row.sensitive)
        self.win.ringback_row.active = True
        self.win.on_ringback(self.win.ringback_row, None)
        self.assertEqual(["/usr/bin/audioctl", "ringback", "on"], self.ran[-1][0])
        self.win.on_ringback_status(True, "ringback=on\navailable=yes\n")
        self.assertTrue(self.win.ringback_row.get_active())

    def test_reading_the_state_switches_nothing(self):
        self.win.busy = False
        self.win.live["audio"] = "/usr/bin/audioctl"
        before = len(self.ran)
        self.win.on_ringback_status(True, "ringback=on\navailable=yes\n")
        self.assertEqual(before, len(self.ran))

    def test_no_ringback_row_without_the_unit_or_the_command(self):
        self.win.on_ringback_status(True, "ringback=off\navailable=no\n")
        self.assertFalse(self.win.ringback_row.visible)
        # an older audioctl answers with its usage
        self.win.on_ringback_status(False, "audioctl - switch the audio stack\n")
        self.assertFalse(self.win.ringback_row.visible)
        self.assertFalse(self.win.ringback_ok)
        self.win.on_ringback(self.win.ringback_row, None)     # runs nothing

    def test_an_older_audioctl_is_judged_by_its_profile(self):
        self.win.on_btx_status(True, "bt-extras=on\nprofile=standard\neffective=basic\n")
        self.assertFalse(self.win.btx_row.visible)
        self.win.on_btx_status(True, "bt-extras=on\nprofile=pw-hal\neffective=all\n")
        self.assertTrue(self.win.btx_row.visible)

    def test_a_hidden_row_runs_nothing(self):
        self.win.busy = False
        self.win.live["audio"] = "/usr/bin/audioctl"
        self.win.on_btx_status(True, "bt-extras=off\nprofile=standard\noffered=no\neffective=none\n")
        before = len(self.ran)
        self.win.btx_row.active = True
        self.win.on_btx(self.win.btx_row, None)
        self.assertEqual(before, len(self.ran))

    def test_syncing_the_helpers_row_runs_nothing(self):
        self.win.busy = False
        self.win.live["audio"] = "/usr/bin/audioctl"
        before = len(self.ran)
        self.win._syncing = True
        self.win.on_btx(self.win.btx_row, None)
        self.win._syncing = False
        self.assertEqual(before, len(self.ran))

    def test_an_older_audioctl_shows_no_helpers_row(self):
        self.win.on_btx_status(False, "audioctl: unknown command bt-extras")
        self.assertFalse(self.win.btx_row.visible)

    def test_a_fallback_at_boot_is_said(self):
        """After an update the boot check may put the phone back on the
        shipped stack; the row must say it moved by itself, and why."""
        self.win.on_status(True, "Profile (active):   standard\n"
                           "Profile (persistent): standard\n"
                           "Fell back:          2026-09-28 17:50:01 pw-hal - that "
                           "profile gave no phone output at boot\n")
        self.assertIn("fell back by itself on 2026-09-28 17:50:01",
                      self.win.row_profile.subtitle)
        self.assertIn("gave no sound", self.win.row_profile.subtitle)

    # ------------------------------------------------------ Bluetooth codec

    CODEC = ("preference=sbc\ncard=bluez_card.F4_9D_8A_00_00_01\n"
             "active=sbc\noffered=aac sbc sbc_xq\n")

    def codec_keys(self):
        return [k for k, _n, _w in switcher.pages.audio.CODECS]

    def test_the_codec_row_follows_what_is_set(self):
        self.win.on_codec_status(True, self.CODEC)
        self.assertEqual(self.codec_keys().index("sbc"),
                         self.win.codec_row.get_selected())
        self.assertIn("Playing SBC", self.win.codec_row.subtitle)
        self.assertTrue(self.win.codec_ok)

    def test_a_codec_the_headset_lacks_is_said_with_what_it_plays(self):
        self.win.on_codec_status(True, self.CODEC.replace(
            "preference=sbc", "preference=ldac").replace("active=sbc", "active=aac"))
        self.assertIn("does not offer LDAC", self.win.codec_row.subtitle)
        self.assertIn("plays AAC", self.win.codec_row.subtitle)

    def test_without_a_headset_the_choice_still_stands(self):
        self.win.on_codec_status(True, "preference=sbc_xq\n")
        self.assertIn("no device connected", self.win.codec_row.subtitle)
        self.assertTrue(self.win.codec_ok)

    def test_no_wireplumber_setting_closes_the_row(self):
        """The shipped profile has no WirePlumber, an older furios_audio
        no setting; "Automatic" would claim a choice that cannot be made."""
        self.win.on_codec_status(True, "preference=unsupported\n")
        self.assertFalse(self.win.codec_ok)
        self.assertFalse(self.win.codec_row.sensitive)
        self.assertFalse(self.win.codec_row.visible)
        self.win.set_busy(False)
        self.assertFalse(self.win.codec_row.sensitive)

    def test_choosing_a_codec_runs_audioctl_with_it(self):
        self.win.live["audio"] = "/usr/bin/audioctl"
        self.win.busy = False
        self.win._syncing = False
        self.win.codec_row.set_selected(self.codec_keys().index("sbc_xq"))
        self.win.on_codec(self.win.codec_row, None)
        self.assertEqual(["/usr/bin/audioctl", "bt-codec", "sbc_xq"],
                         self.ran[-1][0])

    def test_following_the_status_does_not_choose_anything(self):
        self.win.live["audio"] = "/usr/bin/audioctl"
        self.win._syncing = True
        self.win.on_codec(self.win.codec_row, None)
        self.assertEqual([], [r for r in self.ran if "bt-codec" in r[0]])

    # --- one headset, its own codec ---

    KNOWN = ("per_device=yes\n"
             "known=F4:9D:8A:00:00:01|soundcore Liberty 4 Pro|default|aac,sbc,sbc_xq\n"
             "known=98:52:3D:00:00:02|Soundcore Liberty Air 2-L|sbc|sbc\n")

    def test_the_connected_headset_is_picked_until_somebody_chooses(self):
        self.win.on_codec_status(True, self.CODEC.replace(
            "card=", "device=F4:9D:8A:00:00:01\ncard=") + self.KNOWN)
        self.assertTrue(self.win.codec_scope_row.visible)
        self.assertEqual("F4:9D:8A:00:00:01", self.win._codec_scope)
        self.assertEqual(1, self.win.codec_scope_row.get_selected())
        self.assertIn("connected", self.win._codec_scope_labels[1])

    def test_a_headset_is_offered_only_what_it_has(self):
        self.win.on_codec_status(True, self.CODEC.replace(
            "card=", "device=F4:9D:8A:00:00:01\ncard=") + self.KNOWN)
        self.assertEqual(["default", "auto", "aac", "sbc_xq", "sbc"],
                         self.win._codec_keys)
        self.assertEqual(0, self.win.codec_row.get_selected())
        self.assertIn("all: SBC", self.win.codec_row.subtitle)

    def test_choosing_for_one_headset_names_it(self):
        self.win.busy = False
        self.win.live["audio"] = "/usr/bin/audioctl"
        self.win.on_codec_status(True, self.CODEC.replace(
            "card=", "device=F4:9D:8A:00:00:01\ncard=") + self.KNOWN)
        self.win.codec_row.set_selected(self.win._codec_keys.index("sbc_xq"))
        self.win.on_codec(self.win.codec_row, None)
        self.assertEqual(["/usr/bin/audioctl", "bt-codec", "sbc_xq",
                          "--device", "F4:9D:8A:00:00:01"], self.ran[-1][0])

    def test_picking_another_headset_shows_its_list_and_stays(self):
        self.win.busy = False
        out = self.CODEC.replace("card=", "device=F4:9D:8A:00:00:01\ncard=") + self.KNOWN
        self.win.on_codec_status(True, out)
        self.win.codec_scope_row.set_selected(2)
        self.win.on_codec_scope(self.win.codec_scope_row, None)
        self.assertEqual(["default", "auto", "sbc"], self.win._codec_keys)
        self.assertEqual(2, self.win.codec_row.get_selected())
        self.assertIn("Not connected", self.win.codec_row.subtitle)
        self.win.on_codec_status(True, out)
        self.assertEqual("98:52:3D:00:00:02", self.win._codec_scope,
                         "a refresh took the chosen headset away again")

    def test_all_headsets_keeps_the_full_list_and_runs_without_device(self):
        self.win.busy = False
        self.win.live["audio"] = "/usr/bin/audioctl"
        self.win.on_codec_status(True, self.CODEC + self.KNOWN)
        self.assertIsNone(self.win._codec_scope)
        self.assertEqual(self.codec_keys(), self.win._codec_keys)
        self.win.codec_row.set_selected(self.codec_keys().index("aac"))
        self.win.on_codec(self.win.codec_row, None)
        self.assertEqual(["/usr/bin/audioctl", "bt-codec", "aac"], self.ran[-1][0])

    def test_an_older_audioctl_shows_no_headset_list(self):
        self.win.on_codec_status(True, self.CODEC)
        self.assertFalse(self.win.codec_scope_row.visible)
        self.win.on_codec_status(True, self.CODEC + self.KNOWN.replace(
            "per_device=yes", "per_device=no"))
        self.assertFalse(self.win.codec_scope_row.visible)

    def test_a_failed_codec_change_is_reported(self):
        said = []
        self.enterContext(mock.patch.object(switcher.Window, "report",
                                            lambda self, text: said.append(text)))
        self.win.on_codec_done(False, "WirePlumber did not take the setting")
        self.assertIn("Could not", str(self.win.toasts.text))
        self.assertTrue(said)

    def test_the_contribution_switch_is_off_and_says_what_it_would_send(self):
        """Handing data to a public database is the one thing on these pages
        that cannot be taken back, so the row has to say what it does before
        anybody touches it - not after."""
        self.win.on_gps_contrib_status(True, "contributing=no\nqueued=0\nsubmitted=0\n")
        self.assertFalse(self.win.gps_contrib.active)
        text = self.win.gps_contrib.subtitle.lower()
        self.assertIn("nothing is collected", text)
        self.assertIn("_nomap", text)

    def test_on_but_not_running_is_not_reported_as_on(self):
        """The service exits when the marker is missing, so this state exists -
        and saying "on" for it would be the row claiming something it cannot
        see."""
        self.win.on_gps_contrib_status(
            True, "contributing=yes\nrunning=no\nqueued=0\nsubmitted=0\n")
        self.assertIn("not running", self.win.gps_contrib.subtitle)

    def test_when_it_is_on_the_row_says_what_leaves_the_phone(self):
        self.win.on_gps_contrib_status(
            True, "contributing=yes\nrunning=yes\nqueued=3\nsubmitted=7\n")
        self.assertTrue(self.win.gps_contrib.active)
        self.assertIn("satellite", self.win.gps_contrib.subtitle.lower())
        # Both numbers: one says it is measuring, the other that anything
        # actually arrived.
        self.assertIn("7", self.win.gps_contrib_stats.subtitle)
        self.assertIn("3", self.win.gps_contrib_stats.subtitle)

    def test_a_missing_contribution_tool_is_not_reported_as_off(self):
        """"Off" would claim we asked and got an answer."""
        self.win.live["gps"] = None
        self.win.refresh_gps_contrib()
        self.assertFalse(self.win.gps_contrib.sensitive)
        self.assertIn("not installed", self.win.gps_contrib.subtitle)

    def test_switching_contribution_on_calls_the_tool(self):
        """With the tool present. Without it the switch does nothing at all,
        which is the subject of the test above."""
        self.win.gps_contrib.active = True
        self.win.live["gps"] = "/usr/local/bin/furios-gps-contribute"
        self.win.on_gps_contrib(self.win.gps_contrib, None)
        self.assertEqual("on", self.ran[0][0][1])

    def test_switching_contribution_off_calls_the_tool_too(self):
        self.win.gps_contrib.active = False
        self.win.live["gps"] = "/usr/local/bin/furios-gps-contribute"
        self.win.on_gps_contrib(self.win.gps_contrib, None)
        self.assertEqual("off", self.ran[0][0][1])

    def firefox_beside(self):
        """A furios-gps-firefox next to the contribution tool, where the
        page looks for it."""
        d = self.enterContext(tempfile.TemporaryDirectory())
        for name in ("furios-gps-contribute", "furios-gps-firefox"):
            path = os.path.join(d, name)
            with open(path, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(path, 0o755)
        self.win.live["gps"] = os.path.join(d, "furios-gps-contribute")
        return os.path.join(d, "furios-gps-firefox")

    def test_the_firefox_switch_calls_the_tool_beside_contribute(self):
        ff = self.firefox_beside()
        self.win.busy = False
        self.win._syncing = False
        self.win.gps_firefox.active = True
        self.win.on_gps_firefox(self.win.gps_firefox, None)
        self.assertEqual([ff, "on"], list(self.ran[-1][0]))

    def test_without_the_firefox_tool_the_switch_says_so_and_does_nothing(self):
        """An older installation has contribute but not this one."""
        self.win.live["gps"] = "/nowhere/furios-gps-contribute"
        self.win.refresh_gps_contrib()
        self.assertFalse(self.win.gps_firefox.sensitive)
        self.assertIn("not installed", self.win.gps_firefox.subtitle)
        self.ran.clear()
        self.win.on_gps_firefox(self.win.gps_firefox, None)
        self.assertEqual([], self.ran)

    def test_firefox_on_says_how_many_profiles_carry_it(self):
        self.win.on_gps_firefox_status(
            True, "firefox_wait=yes\nprofiles=34\npatched=34\nleftover=0\n")
        self.assertTrue(self.win.gps_firefox.active)
        self.assertIn("34 of 34", self.win.gps_firefox.subtitle)

    def test_firefox_off_with_an_open_app_is_not_passed_off_as_done(self):
        self.win.on_gps_firefox_status(
            True, "firefox_wait=no\nprofiles=34\npatched=0\nleftover=2\n")
        self.assertFalse(self.win.gps_firefox.active)
        self.assertIn("2 open", self.win.gps_firefox.subtitle)

    def test_the_location_way_back_also_takes_the_firefox_prefs_out(self):
        ff = self.firefox_beside()
        self.win.busy = False
        steps = []
        self.enterContext(mock.patch.object(
            switcher.Window, "run_chain",
            lambda self, cmds, done: steps.extend(cmds)))
        self.win.on_gps_restore(None)
        self.assertEqual([self.win.live["gps"], "off"], steps[0])
        self.assertEqual([ff, "off"], steps[1])

    # ------------------------------------------------------------ Battery

    BATT = """{"config": {"charging": true, "discharging": false,
                          "level": true,
                          "charge_green_w": 7.0, "charge_amber_w": 3.0,
                          "drain_amber_w": 2.0, "drain_red_w": 4.0,
                          "level_amber_pct": 60.0, "level_red_pct": 15.0}}"""

    def batt(self, **changes):
        data = json.loads(self.BATT)
        data["config"].update(changes)
        return json.dumps(data)

    def test_each_option_is_a_box_of_its_own(self):
        """One box per option, headed by what the option is about.

        In a single box the six sliders read as one block of furniture and
        which pair belonged to which switch was a thing to work out rather
        than to see. Every box is named, which is what the one heading over
        the lot used to be for: unnamed blocks under each other are a list
        of switches, not an answer to a question."""
        recorder.reset()
        self.win.build_battery_page()
        titles = [c[2].get("title") for c in recorder.calls
                 if c[0] == "Adw.PreferencesGroup"]
        for _key, heading, _t, _s, _sl in switcher.Window.BATTERY_OPTIONS:
            self.assertEqual(1, titles.count(heading), heading)
        self.assertNotIn("Colour marking", titles)
        self.assertEqual([], [t for t in titles if not t], titles)

    def test_the_sliders_sit_in_the_box_of_their_own_switch(self):
        """Built in the order they are drawn in, so a slider made after the
        next heading would appear under the wrong option."""
        recorder.reset()
        self.win.build_battery_page()
        order = [str(c[2].get("title", "")) for c in recorder.calls
                 if c[0] in ("Adw.PreferencesGroup", "Adw.ActionRow")]
        headings = [h for _k, h, _t, _s, _sl
                    in switcher.Window.BATTERY_OPTIONS]
        for i, (_key, heading, _t, _s, sliders) in enumerate(
                switcher.Window.BATTERY_OPTIONS):
            start = order.index(heading)
            end = (order.index(headings[i + 1]) if i + 1 < len(headings)
                   else len(order))
            for slider in sliders:
                self.assertIn(slider[0], order[start:end],
                              "%s: %s" % (heading, slider[0]))

    def test_each_slider_carries_its_unit(self):
        """Watts and percent in the same column of controls, and no
        sentence anywhere to say which is which."""
        self.assertEqual("7.0 W", switcher.Window.threshold_text(7.0, 1, "W"))
        self.assertEqual("60 %", switcher.Window.threshold_text(60.0, 0, "%"))
        units = {ckey: unit
                     for _k, _h, _t, _s, sliders in switcher.Window.BATTERY_OPTIONS
                     for (_l, ckey, _lo, _hi, _st, _di, unit) in sliders}
        self.assertEqual("W", units["charge_green_w"])
        self.assertEqual("W", units["drain_red_w"])
        self.assertEqual("%", units["level_amber_pct"])

    def test_the_battery_page_offers_the_options_in_order(self):
        """In the order somebody thinks about them: going in, how full,
        going out - and then the two that are not colours at all."""
        self.assertEqual(["charging", "level", "discharging", "runtime",
                          "charge_time"],
                         [k for k, _h, _t, _s, _sl
                          in switcher.Window.BATTERY_OPTIONS])

    def test_and_says_nothing_else(self):
        """No readings on this page - a watt figure belongs where somebody
        is measuring. Checked by building the page and looking for a row
        with a subtitle: the option rows and the sliders carry a title and
        nothing more.

        Two exceptions, and they are the reason this is a count rather than
        an emptiness: the two time options say WHERE the time appears, which
        is not the same on every phone - a status icon of its own where the
        phosh plugin is installed, the percentage's place where it is not -
        and no switch title can carry that. What a box heading and a switch
        title can say between them gets no subtitle."""
        recorder.reset()
        self.win.build_battery_page()
        subtitles = [str(c[2].get("subtitle")) for c in recorder.calls
                      if c[0] in ("Adw.ActionRow", "Adw.SwitchRow")
                      and c[2].get("subtitle")]
        wanted = [sub for _key, _head, _title, sub, _sliders
                  in switcher.Window.BATTERY_OPTIONS if sub]
        self.assertEqual(2, len(wanted), "a third option grew a subtitle")
        self.assertEqual(sorted(wanted), sorted(subtitles))

    def test_the_thresholds_move_only_on_a_tap(self):
        """Not sliders: on the phone the page is scrolled with the same
        finger, and a swipe that began on a slider moved it - every
        threshold shifted while somebody only scrolled past (25.9.2026). A
        button acts on a tap; a swipe that starts on it is the scroll's."""
        recorder.reset()
        self.win.build_battery_page()
        self.assertEqual([], [c[0] for c in recorder.calls
                              if c[0].startswith("Gtk.Scale")])
        icons = [c[2].get("icon_name") for c in recorder.calls
                 if c[0] == "Gtk.Button"]
        n = sum(len(sl) for _k, _h, _t, _s, sl
                in switcher.Window.BATTERY_OPTIONS)
        self.assertEqual(6, n)
        self.assertEqual(n, icons.count("list-remove-symbolic"))
        self.assertEqual(n, icons.count("list-add-symbolic"))

    def test_the_sliders_appear_with_their_option(self):
        """Six sliders at once ask to be studied; this is a page to glance
        at. They are rows of the same group, hidden and shown - a revealer
        would be sorted to the end of the card, away from its switch."""
        self.win.on_battery_active(True, "active")
        self.win.on_battery_status(True, self.batt(charging=False,
                                                   level=True))
        self.assertFalse(
            self.win.batt_switches["charging"].slider_rows[0].visible)
        self.assertTrue(
            self.win.batt_switches["level"].slider_rows[0].visible)

    def test_a_switch_is_only_on_when_something_is_behind_it(self):
        """The setting AND the service: an option left on in the file while
        the daemon is stopped would be a switch with nothing behind it."""
        self.win.on_battery_active(True, "inactive")
        self.win.on_battery_status(True, self.BATT)
        self.assertFalse(self.win.batt_switches["charging"].active)
        self.win.on_battery_active(True, "active")
        self.assertTrue(self.win.batt_switches["charging"].active)

    def test_the_switches_follow_the_config(self):
        self.win.on_battery_active(True, "active")
        self.win.on_battery_status(True, self.batt(discharging=True))
        self.assertTrue(self.win.batt_switches["charging"].active)
        self.assertTrue(self.win.batt_switches["discharging"].active)

    def test_and_so_do_the_sliders(self):
        self.win.on_battery_status(True, self.batt(drain_amber_w=2.5))
        self.assertEqual(2.5, self.win.batt_scales["drain_amber_w"].value)
        self.assertEqual(7.0, self.win.batt_scales["charge_green_w"].value)

    def test_a_tool_that_did_not_answer_closes_the_switches(self):
        self.win.on_battery_status(False, "")
        for row in self.win.batt_switches.values():
            self.assertFalse(row.sensitive)

    def test_an_unreadable_answer_changes_nothing(self):
        """Half a line of JSON is not a reason to redraw the page.

        The name used to be the whole test - the body called the method and
        asserted nothing, so it passed on anything that did not raise,
        including a version that wiped the page. What "changes nothing"
        means is written out here: the readings stay, the sliders stay, and
        the switches stay usable, which is what separates this from a tool
        that did not answer at all.
        """
        self.win.on_battery_status(True, self.batt(drain_amber_w=2.5))
        before = dict(self.win.batt_cfg)
        self.win.on_battery_status(True, "{ not json")
        self.assertEqual(before, self.win.batt_cfg)
        self.assertEqual(2.5, self.win.batt_scales["drain_amber_w"].value)
        for row in self.win.batt_switches.values():
            self.assertTrue(row.sensitive,
                            "unreadable output greyed the page out")

    def test_switching_an_option_on_writes_it_and_starts_the_service(self):
        self.ran.clear()
        self.win._loading = False
        row = self.win.batt_switches["discharging"]
        row.active = True
        self.win.on_battery_option(row, None, "discharging")
        commands = [" ".join(a) for a, _d, _o, _k in self.ran]
        self.assertTrue(commands[0].endswith("config discharging on"), commands)
        for argv, done, _o, _k in list(self.ran):
            done(True, "")
        commands = [" ".join(a) for a, _d, _o, _k in self.ran]
        self.assertTrue(any("enable --now" in b for b in commands), commands)

    def test_switching_the_last_one_off_stops_the_service(self):
        self.ran.clear()
        self.win._loading = False
        for key, row in self.win.batt_switches.items():
            row.active = False
        row = self.win.batt_switches["charging"]
        self.win.on_battery_option(row, None, "charging")
        for argv, done, _o, _k in list(self.ran):
            done(True, "")
        commands = [" ".join(a) for a, _d, _o, _k in self.ran]
        self.assertTrue(any("disable --now" in b for b in commands), commands)

    def test_but_not_while_another_one_is_still_on(self):
        self.ran.clear()
        self.win._loading = False
        self.win.batt_switches["level"].active = True
        row = self.win.batt_switches["charging"]
        row.active = False
        self.win.on_battery_option(row, None, "charging")
        for argv, done, _o, _k in list(self.ran):
            done(True, "")
        commands = [" ".join(a) for a, _d, _o, _k in self.ran]
        self.assertFalse(any("disable" in b for b in commands), commands)

    def test_the_sliders_hide_and_show_with_the_switch(self):
        self.win._loading = False
        row = self.win.batt_switches["level"]
        row.active = True
        self.win.on_battery_option(row, None, "level")
        self.assertTrue(all(r.visible for r in row.slider_rows))
        row.active = False
        self.win.on_battery_option(row, None, "level")
        self.assertFalse(any(r.visible for r in row.slider_rows))

    def test_a_threshold_is_written_after_a_moment_not_per_pixel(self):
        """Dragging a slider fires continuously; battctl is called once,
        when it stops."""
        self.ran.clear()
        self.win._loading = False
        self.win.batt_scales["drain_red_w"].value = 5.0
        self.win.on_battery_slider(self.win.batt_scales["drain_red_w"],
                                   "drain_red_w")
        self.assertEqual([], self.ran)
        self.win.write_battery_thresholds()
        written = [a[1:] for a, _d, _o, _k in self.ran]
        self.assertIn(["config", "drain_red_w", "5"], written)

    def battctl_accepts(self, cfg):
        """battctl's own check, run after every single config write."""
        return (cfg["charge_green_w"] > cfg["charge_amber_w"]
                and cfg["drain_amber_w"] < cfg["drain_red_w"]
                and cfg["level_red_pct"] < cfg["level_amber_pct"])

    def replay_into(self, cfg):
        """Run what was queued, one write at a time, as battctl would."""
        written = []
        # Up to the refresh that follows the last write, which is not ours.
        while self.ran and self.ran[0][0][1:2] == ["config"]:
            argv, done, _o, _k = self.ran.pop(0)
            key, value = argv[-2], float(argv[-1])
            cfg[key] = value
            written.append(key)
            done(self.battctl_accepts(cfg), "")
            self.assertTrue(self.battctl_accepts(cfg),
                            "battctl refuses %s=%g after %s" % (key, value, written))
        return written

    FILE = {"charge_amber_w": 3.0, "charge_green_w": 7.0,
            "drain_amber_w": 3.0, "drain_red_w": 6.0,
            "level_red_pct": 20.0, "level_amber_pct": 50.0}

    def fill_battery_page(self):
        self.ran.clear()
        self.win._loading = False
        self.win.batt_cfg = dict(self.FILE)
        for key, value in self.FILE.items():
            self.win.batt_scales[key].value = value

    def test_a_pushed_neighbour_reaches_the_file_too(self):
        """Amber up to green's value pushes green along on screen - and only
        amber used to be written, which battctl refused because it crossed
        green's OLD value. The push never happened anywhere but the page."""
        self.fill_battery_page()
        self.win.batt_scales["charge_amber_w"].value = 7.0
        self.win.on_battery_slider(self.win.batt_scales["charge_amber_w"],
                                   "charge_amber_w")
        self.win.write_battery_thresholds()
        cfg = dict(self.FILE)
        written = self.replay_into(cfg)
        self.assertEqual(["charge_green_w", "charge_amber_w"], written)
        self.assertEqual((7.0, 7.5), (cfg["charge_amber_w"],
                                      cfg["charge_green_w"]))

    def test_and_the_same_when_the_upper_one_pushes_down(self):
        self.fill_battery_page()
        self.win.batt_scales["level_amber_pct"].value = 20.0
        self.win.on_battery_slider(self.win.batt_scales["level_amber_pct"],
                                   "level_amber_pct")
        self.win.write_battery_thresholds()
        cfg = dict(self.FILE)
        self.replay_into(cfg)
        self.assertEqual((15.0, 20.0), (cfg["level_red_pct"],
                                        cfg["level_amber_pct"]))

    def test_a_refresh_inside_the_quiet_moment_does_not_eat_the_tap(self):
        """The file's values go back on screen with every refresh; what is
        written is what was tapped, not what the steppers show by then."""
        self.fill_battery_page()
        self.win.batt_scales["drain_red_w"].value = 7.0
        self.win.on_battery_slider(self.win.batt_scales["drain_red_w"],
                                   "drain_red_w")
        self.win.batt_scales["drain_red_w"].value = 6.0     # a refresh
        self.win.write_battery_thresholds()
        cfg = dict(self.FILE)
        self.replay_into(cfg)
        self.assertEqual(7.0, cfg["drain_red_w"])

    def test_a_second_threshold_does_not_cancel_the_first(self):
        """Two taps on two rows inside the quiet moment: the second one's
        timer used to replace the first one's write."""
        self.fill_battery_page()
        self.win.batt_scales["drain_red_w"].value = 6.5
        self.win.on_battery_slider(self.win.batt_scales["drain_red_w"],
                                   "drain_red_w")
        self.win.batt_scales["level_red_pct"].value = 25.0
        self.win.on_battery_slider(self.win.batt_scales["level_red_pct"],
                                   "level_red_pct")
        self.win.write_battery_thresholds()
        cfg = dict(self.FILE)
        written = self.replay_into(cfg)
        self.assertEqual(["drain_red_w", "level_red_pct"], sorted(written))

    def test_the_neighbour_is_pushed_along_not_refused(self):
        """battctl will not take a pair that crosses, and a slider that
        stops dead under the thumb feels broken."""
        self.win._loading = False
        self.win.batt_scales["drain_amber_w"].value = 2.0
        self.win.batt_scales["drain_red_w"].value = 4.0
        self.win.batt_scales["drain_amber_w"].value = 6.0
        self.win.keep_thresholds_apart("drain_amber_w")
        self.assertEqual(6.5, self.win.batt_scales["drain_red_w"].value)
        self.win.batt_scales["drain_red_w"].value = 3.0
        self.win.keep_thresholds_apart("drain_red_w")
        self.assertEqual(2.5, self.win.batt_scales["drain_amber_w"].value)

    def test_the_level_pair_keeps_its_own_distance(self):
        self.win._loading = False
        self.win.batt_scales["level_amber_pct"].value = 60.0
        self.win.batt_scales["level_red_pct"].value = 70.0
        self.win.keep_thresholds_apart("level_red_pct")
        self.assertEqual(75.0, self.win.batt_scales["level_amber_pct"].value)

    def test_nothing_is_written_while_the_page_is_being_filled(self):
        self.ran.clear()
        self.win._loading = True
        self.win.on_battery_option(self.win.batt_switches["level"], None,
                                   "level")
        self.win.on_battery_slider(self.win.batt_scales["level_red_pct"],
                                   "level_red_pct")
        self.win._loading = False
        self.assertEqual([], self.ran)

    def test_a_change_that_did_not_take_says_so(self):
        self.win.after_battery(False, "nope", "change")
        self.assertIn("Could not change", str(self.win.toasts.text))

    def test_the_way_back_stops_the_service_before_it_cleans_up(self):
        """In that order: battctl restore takes the colour, the time and
        the widget out of the bar, and a daemon still running would put
        them back within the minute."""
        self.ran.clear()
        self.win.busy = False
        self.win.on_battery_restore(None)
        ran = []
        for _ in range(2):
            argv, done, _on_line, _kw = self.ran.pop(0)
            ran.append(" ".join(argv))
            done(True, "")
        self.assertIn("disable --now", ran[0])
        self.assertTrue(ran[1].endswith("restore"), ran)

    def test_the_way_back_reports_a_failure(self):
        self.win.on_battery_restored(False, "")
        self.assertIn("Could not", str(self.win.toasts.text))

    def test_a_phone_without_the_switches_gets_no_switches_tab(self):
        """Not just "no controls" - no tab. On a phone that has no such
        hardware the tab could only offer to fetch a tool that would never
        have anything to show: an offer to repair a fault the device does not
        have."""
        empty_dir = tempfile.mkdtemp()
        with mock.patch.dict(os.environ, {"FURIOS_KILLSWITCH_BASE": empty_dir}):
            self.assertFalse(switcher.phone_has_switches())
            recorder.reset()
            switcher.Window(switcher.Adw.Application())
        titles = [str(c[1][2]) for c in recorder.calls
                 if c[0].endswith("add_titled_with_icon()") and len(c[1]) > 2]
        self.assertNotIn("Switches", titles, titles)

    def test_a_phone_with_them_still_gets_it(self):
        base = tempfile.mkdtemp()
        open(os.path.join(base, "cam_switch"), "w").write("1\n")
        with mock.patch.dict(os.environ, {"FURIOS_KILLSWITCH_BASE": base}):
            self.assertTrue(switcher.phone_has_switches())
            recorder.reset()
            switcher.Window(switcher.Adw.Application())
        titles = [str(c[1][2]) for c in recorder.calls
                 if c[0].endswith("add_titled_with_icon()") and len(c[1]) > 2]
        self.assertIn("Switches", titles, titles)

    def test_one_switch_attribute_is_enough(self):
        """The two are read separately and a phone could have one of them."""
        base = tempfile.mkdtemp()
        open(os.path.join(base, "nwk_switch"), "w").write("1\n")
        with mock.patch.dict(os.environ, {"FURIOS_KILLSWITCH_BASE": base}):
            self.assertTrue(switcher.phone_has_switches())

    def test_restore_sound_runs_the_same_rescue_as_the_command_line(self):
        self.win.on_rescue(None)
        self.assertEqual("rescue", self.ran[0][0][1])

    def test_restore_is_ignored_while_busy(self):
        self.win.busy = True
        self.win.on_rescue(None)
        self.assertEqual([], self.ran)

    def test_a_finished_restore_says_what_it_did(self):
        self.win.on_rescued(True, "")
        self.assertIn("65 %", str(self.win.toasts.text))
        self.win.on_rescued(False, "no")
        self.assertIn("failed", str(self.win.toasts.text).lower())

    def test_refresh_asks_every_helper_there_is(self):
        """Two for audio, and three more for the modem when modemctl is here.

        Counted rather than named, because the point is that adding a page
        must not leave one of the others unasked - which is how a window ends
        up showing a state that stopped being true ten minutes ago."""
        self.win.refresh()
        # Audio is counted like the rest now: audioctl can be missing too, and
        # asking a tool that is not there was how a callback ended up at rows
        # nobody had built.
        # status, bt-codec status, bt-extras status, ringback status and the
        # echo helper's
        expected = ((4 + bool(DMNR) if AUDIOCTL else 0)
                    # profile, status, sim and nr
                    + (4 if MODEMCTL else 0)
                    # status of the contribution tool, and of the Firefox
                    # one beside it when that is installed too
                    + (1 if CONTRIB else 0)
                    + (1 if switcher.pages.gps.firefox_tool(CONTRIB) else 0)
                    # status --json, plus is-active for the daemon. Not
                    # is-enabled any more: the icons are phosh's plugin list
                    # and the tool answers for them in the same status.
                    + (2 if KILLSWITCH else 0)
                    # one call for the whole security page: status --json
                    # answers the kernel, all three parts and what listens
                    + (1 if SECCTL else 0)
                    # the battery page asks the same three questions -
                    # always, because setUp gives the window a battctl
                    + 3)
        self.assertEqual(expected, len(self.ran))

    def test_the_tabs_sit_under_the_header_not_at_the_foot(self):
        """Where they switch from, not where a page ends: at the foot the bar
        sat a thumb's width from "Restore shipped state"."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        theirs = [c for c in recorder.calls
                if c[0] == "Adw.ToolbarView.add_top_bar()" and c[1]]
        below = [c for c in recorder.calls
                 if c[0] == "Adw.ToolbarView.add_bottom_bar()" and c[1]]
        self.assertEqual([], below)
        # header bar plus the switcher
        self.assertEqual(2, len(theirs), theirs)

    def test_the_switches_page_asks_for_json_and_for_the_unit(self):
        """The page needs both: the tool knows the switches and whether the
        icons are switched on, systemd knows whether the daemon that acts on
        the network switch is running."""
        if not KILLSWITCH:
            self.skipTest("killswitch-indicator not installed")
        self.win.refresh()
        calls_ = [" ".join(a[0]) for a in self.ran]
        self.assertTrue(any("status --json" in a for a in calls_), calls_)
        self.assertTrue(any("is-active killswitch-indicator" in a for a in calls_), calls_)
        # is-enabled is gone: stopping the daemon does not take the icons
        # away any more, so the unit answers no question this page asks.
        self.assertFalse(any("is-enabled killswitch-indicator" in a
                             for a in calls_), calls_)


    # --- the switches page -------------------------------------------------
    #
    # Three sliders that look alike and work nothing alike. What matters here
    # is that the page never claims more than the hardware does: the modem
    # cannot be opted out of, and a reading that failed must not be shown as
    # a state.

    def switches_win(self):
        if not KILLSWITCH:
            self.skipTest("killswitch-indicator not installed")
        return self.win

    JSON = """{
      "switches": {"cam_switch": "0", "nwk_switch": "1"},
      "icons": true,
      "network_extras": {"wifi": true, "bluetooth": false},
      "radios": {"wifi": true, "bluetooth": null},
      "we_disabled": [],
      "cameras": ["Back", "Front", "Back"],
      "camera_hal": false,
      "mic": {"median": 2.9, "peak": 34, "verdict": "GESPERRT",
              "when": 1789400000, "reason": "Start"}
    }"""
    # The "mic" field is what an OLDER killswitch-indicator still sends. It is
    # kept in this fixture on purpose: the page must ignore it rather than put
    # a three-second-old verdict on screen as if it were the position.

    def test_no_slider_position_is_put_on_screen(self):
        """A position is a reading with nothing to do: the hand on the case
        has already decided, and this page cannot switch it back. Against the
        microphone, which cannot be read at all, the word made the absence
        look like a fault - so it is gone from all three."""
        self.switches_win()
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        titled = [c for c in recorder.calls if c[0] == "Adw.ActionRow"
                  and str(c[2].get("title", "")) == "Position"]
        self.assertEqual([], titled, titled)

    def test_the_modem_row_is_a_fact_not_a_switch(self):
        """Firmware stops the RIL before any program here hears about it.
        It was a greyed switch fixed on, which read as a control somebody had
        locked - now a plain row. Checked against what the page actually
        built, not against a stand-in a test wrote."""
        self.switches_win()
        built = switcher.Window(switcher.Adw.Application())
        modem = [c for c in recorder.calls
                 if c[0] in ("Adw.ActionRow", "Adw.SwitchRow")
                 and "mobile network" in str(c[2].get("title", "")).lower()]
        self.assertTrue(modem, "no row for the mobile network")
        self.assertEqual("Adw.ActionRow", modem[-1][0])
        self.assertIsNotNone(built)
        # And it must not read as "mobile data cannot be turned off at all",
        # which is how the first wording landed: Settings switches it off
        # through NetworkManager any time, a path this switch never touches.
        self.assertIn("settings", str(modem[-1][2].get("subtitle", "")).lower())

    def test_a_radio_that_is_not_reachable_is_not_called_off(self):
        """null is not false: bluetoothd being away must not read as
        'Bluetooth is off', which would be a claim about the hardware."""
        win = self.switches_win()
        win.on_switches_status(True, self.JSON)
        self.assertIn("not reachable", win.sw_bt.subtitle)
        self.assertIn("Wi-Fi is on right now", win.sw_wifi.subtitle)

    def test_choosing_a_radio_is_written_through_the_tool(self):
        win = self.switches_win()
        self.ran.clear()
        win._loading = False
        win.sw_wifi.set_active(True)
        win.on_extra_wifi(win.sw_wifi, None)
        self.assertEqual(["config", "wifi", "on"], list(self.ran[-1][0][1:]))

    def test_the_indicator_switch_goes_through_the_tool(self):
        """The icons are a phosh plugin, and the tool owns the shell's list of
        them - the app must not edit that list itself, because it may hold
        somebody else's plugin."""
        win = self.switches_win()
        self.ran.clear()
        win._loading = False
        win.sw_row.set_active(False)
        win.on_indicator_switch(win.sw_row, None)
        self.assertEqual(["icons", "off"], list(self.ran[-1][0][1:]))
        self.assertNotIn("gsettings", self.ran[-1][0][0])

    def test_the_icons_are_read_from_the_tools_own_answer(self):
        """Not from systemd: stopping the daemon does not take the icons away
        any more, and a switch that showed the unit would be answering a
        different question than the one it asks."""
        win = self.switches_win()
        win.on_switches_status(True, self.JSON)
        self.assertTrue(win.sw_row.get_active())
        self.assertIn("top bar", win.sw_row.subtitle)

    def test_a_tool_too_old_to_know_the_icons_is_not_blamed_on_phosh(self):
        """The installed killswitch-indicator on this phone prints no "icons"
        key at all; that is an old tool, not an unreadable plugin list."""
        win = self.switches_win()
        old = json.loads(self.JSON)
        del old["icons"]
        win.on_switches_status(True, json.dumps(old))
        self.assertFalse(win.sw_row.sensitive)
        self.assertIn("too old", win.sw_row.subtitle)
        self.assertNotIn("phosh", win.sw_row.subtitle)
        old["icons"] = None
        win.on_switches_status(True, json.dumps(old))
        self.assertIn("phosh", win.sw_row.subtitle)

    def test_a_reading_while_loading_does_not_write_anything_back(self):
        """Filling the switches from a status must not look like a user
        touching them - that would write the state back at itself."""
        win = self.switches_win()
        self.ran.clear()
        win.on_switches_status(True, self.JSON)
        self.assertEqual([], [r for r in self.ran if "config" in r[0]])

    def test_an_unreadable_answer_is_not_shown_as_a_reading(self):
        win = self.switches_win()
        win.on_switches_status(True, "not json at all")
        self.assertIn("unreadable", win.sw_row.subtitle)

    def test_no_page_starts_with_a_paragraph_under_its_heading(self):
        """A group with a description draws its title higher than one without,
        so a single paragraph put the Modem heading twelve pixels above every
        other tab's. Seen on the phone, measured in a screenshot.

        Two kinds of group may still carry a description: the way back, whose
        text is also the question it asks, and the offer on a page whose tool
        is missing, which has nothing else to show.
        """
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        with_paragraph = [str(c[2].get("title", "")) for c in recorder.calls
                      if c[0] == "Adw.PreferencesGroup" and c[2].get("description")]
        allowed = [t for t in with_paragraph
                   if t == switcher.Window.RESTORE_TITLE or "not installed" in t]
        self.assertEqual(sorted(with_paragraph), sorted(allowed), with_paragraph)

    def test_the_switches_page_explains_itself_in_rows_not_paragraphs(self):
        """The groups on this page carry a title and nothing else. What
        needs saying sits in the row it is about - the way back keeps its
        description, because that text is also the question it asks."""
        self.switches_win()
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        titles = ("Indicator", "Network switch")
        with_paragraph = [c[2].get("title") for c in recorder.calls
                      if c[0] == "Adw.PreferencesGroup"
                      and c[2].get("title") in titles
                      and c[2].get("description")]
        self.assertEqual([], with_paragraph)

    def test_only_the_network_switch_group_is_left(self):
        """Camera and microphone went on 28.9.: they described the sliders
        and set nothing. The network switch is what this page sets."""
        self.switches_win()
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        groups = [str(c[2].get("title", "")) for c in recorder.calls
                  if c[0] == "Adw.PreferencesGroup"]
        self.assertIn("Network switch", groups)
        for gone in ("1 · Camera", "2 · Network", "3 · Microphone"):
            self.assertNotIn(gone, groups)

    def test_the_page_never_opens_the_microphone_itself(self):
        """Measuring means listening, and listening is what the switch is
        flipped to prevent. There is no button for it, and a status reaching
        the page must not start one behind the user's back."""
        win = self.switches_win()
        self.ran.clear()
        win.refresh()
        win.on_switches_status(True, self.JSON)
        self.assertEqual([], [r for r in self.ran if "mic-check" in r[0]])
        switcher.Window(switcher.Adw.Application())
        buttons = [str(c[2].get("label", "")).lower()
                   for c in recorder.calls if c[0] == "Gtk.Button"]
        self.assertEqual([], [b for b in buttons if "listen" in b], buttons)

    # --- what a tab does without its tool ----------------------------------
    #
    # A phone with only audioctl used to show one page and look like an app
    # that can do nothing else. Now every tab exists; a tab whose tool is
    # missing shows what it would need and offers to fetch it, and nothing
    # else - switches and status rows with nothing behind them would be
    # furniture, and a page full of greyed-out controls reads like a broken
    # phone rather than a missing package.

    def component(self, tool="modemctl"):
        return next(c for c in switcher.COMPONENTS if c["tool"] == tool)

    def without_tool(self, *missing):
        """A window built as though those tools were not installed."""
        real = switcher.tools._tool_maybe
        switcher.tools._tool_maybe = lambda name: (None if name in missing
                                             else real(name))
        try:
            recorder.reset()
            return switcher.Window(switcher.Adw.Application())
        finally:
            switcher.tools._tool_maybe = real

    def test_a_tool_whose_page_was_not_built_is_never_asked(self):
        """Found on the phone, not here: the page was built from _tool_maybe
        while refresh asked the module constants, so gpsctl (the GPS tool of
        the time) was asked for a
        status that arrived at rows which had never been created - an
        AttributeError inside a callback, where nobody sees it."""
        win = self.without_tool("furios-gps-contribute")
        asked = []
        real = switcher.process.run_async
        switcher.process.run_async = lambda argv, done, on_line=None, **kw: asked.append(argv)
        try:
            win.refresh()
        finally:
            switcher.process.run_async = real
        self.assertEqual([], [a for a in asked
                              if "furios-gps-contribute" in a[0]])
        # And one that IS here is asked - whichever of them this machine has.
        # Naming audioctl would only measure whether this phone happens to
        # have it installed.
        da = [c["tool"] for c in switcher.COMPONENTS
              if c["tool"] != "furios-gps-contribute"
              and switcher.tools._tool_maybe(c["tool"])]
        if da:
            self.assertTrue([a for a in asked
                             if any(t in a[0] for t in da)], asked)

    def test_a_missing_tool_still_gets_its_tab(self):
        win = self.without_tool("modemctl", "furios-gps-contribute",
                                "killswitch-indicator")
        pages = [c[1] for c in recorder.calls
                  if c[0] == "Adw.ViewStack.add_titled_with_icon()" and c[1]]
        self.assertEqual(["audio", "modem", "gps", "switches", "security",
                          "battery", "other", "vibration"],
                         [args[1] for args in pages])
        self.assertIsNotNone(win)

    def test_a_tab_without_its_tool_shows_the_offer_and_nothing_else(self):
        self.without_tool("furios-gps-contribute")
        groups = [c[2] for c in recorder.calls if c[0] == "Adw.PreferencesGroup"]
        offer = [g for g in groups
                   if "not installed" in str(g.get("title", ""))
                   and "furios-gps-contribute" in str(g.get("description", ""))]
        self.assertTrue(offer, "no offer on the page of a missing tool")
        # and none of the page's own controls were built
        titles = [str(c[2].get("title", "")) for c in recorder.calls
                 if c[0] == "Adw.SwitchRow"]
        self.assertEqual([], [t for t in titles if "Send my observations" in t])

    def test_the_offer_says_where_it_comes_from_and_what_it_would_do(self):
        self.without_tool("modemctl")
        comp = self.component("modemctl")
        rows = [str(c[2].get("subtitle", "")) for c in recorder.calls
                  if c[0] == "Adw.ActionRow"]
        self.assertIn(comp["url"], rows)
        self.assertTrue(any(comp["does"] in z for z in rows))
        self.assertTrue(any(switcher.clone_path(comp) in z for z in rows),
                        "the offer has to say where it would put it")
        self.assertTrue(any("sudo" in z for z in rows),
                        "and that this one needs root")

    def test_a_tool_without_root_says_so_in_its_offer(self):
        self.without_tool("furios-gps-contribute")
        rows = [str(c[2].get("subtitle", "")) for c in recorder.calls
                  if c[0] == "Adw.ActionRow"]
        self.assertTrue(any("no root needed" in z for z in rows), rows)

    def test_installing_asks_first_and_runs_nothing_on_the_tap(self):
        self.win.comp_rows[self.component()["tool"]] = {}
        self.ran.clear()
        self.win.ask_component(self.component(), "install")
        self.assertEqual([], self.ran)

    def test_the_question_says_the_commands_it_will_run(self):
        recorder.reset()
        empty_dir = tempfile.mkdtemp()
        self.addCleanup(shutil_real.rmtree, empty_dir, True)
        self.win.comp_rows[self.component()["tool"]] = {
            "path": os.path.join(empty_dir, "not-there-yet")}
        self.win.ask_component(self.component(), "install")
        body = str([c for c in recorder.calls
                    if c[0] == "Adw.AlertDialog"][-1][2].get("body", ""))
        self.assertIn("git clone", body)
        self.assertIn("install.sh", body)
        self.assertIn("sudo", body)

    def test_updating_somebody_elses_clone_says_whose_it_is(self):
        recorder.reset()
        self.win.comp_rows[self.component()["tool"]] = {
            "path": "/home/furios/Projekte/eigen"}
        self.win.ask_component(self.component(), "update")
        body = str([c for c in recorder.calls
                    if c[0] == "Adw.AlertDialog"][-1][2].get("body", ""))
        self.assertIn("your own clone", body)
        self.assertIn("uncommitted", body)

    def test_cancel_sits_on_top_here_too_and_answers_nothing(self):
        recorder.reset()
        self.win.comp_rows[self.component()["tool"]] = {}
        self.win.ask_component(self.component(), "install")
        answers = [c[1][0] for c in recorder.calls
                     if c[0] == "Adw.AlertDialog.add_response()" and c[1]]
        self.assertEqual(["go", "cancel"], answers)
        self.ran.clear()
        self.win.on_component_response(None, "cancel")
        self.assertEqual([], self.ran)

    def test_only_a_component_that_needs_root_asks_for_a_password(self):
        recorder.reset()
        self.win.comp_rows[self.component("modemctl")["tool"]] = {}
        self.win.ask_component(self.component("modemctl"), "install")
        self.assertTrue([c for c in recorder.calls
                         if c[0] == "Adw.PasswordEntryRow"])
        recorder.reset()
        self.win.comp_rows[self.component("furios-gps-contribute")["tool"]] = {}
        self.win.ask_component(self.component("furios-gps-contribute"), "install")
        self.assertEqual([], [c for c in recorder.calls
                              if c[0] == "Adw.PasswordEntryRow"])

    def test_answering_go_starts_the_chain_with_what_was_typed(self):
        comp = self.component()
        self.win.comp_rows[comp["tool"]] = {"state": Recording()}
        self.win.ask_component(comp, "install")
        _c, state, entry, path = self.win._comp_pending
        self.assertIsNotNone(entry)
        field = Recording()
        field.set_text("secret_word")
        self.win._comp_pending = (comp, state, field, path)
        self.ran.clear()
        self.win.busy = False
        self.win.on_component_response(None, "go")
        argv, _done, _on_line, _kw = self.ran[0]
        self.assertIn("clone", " ".join(argv))
        self.assertEqual([], [a for a in self.ran if "secret_word" in " ".join(a[0])])
        self.assertEqual("", field.text, "the password is wiped from the entry")

    def test_the_chain_hands_each_step_what_the_list_says(self):
        comp = self.component()
        self.ran.clear()
        self.win.busy = False
        self.win.comp_rows[comp["tool"]] = {"state": Recording()}
        self.win.run_component(comp, "install", "secret_word")
        for argv, stdin, cwd, _env in switcher.component_steps(
                comp, "install", "secret_word"):
            ran_argv, done, _on_line, kw = self.ran.pop(0)
            self.assertEqual(argv, ran_argv)
            self.assertEqual(stdin, kw.get("stdin"))
            self.assertEqual(cwd, kw.get("cwd"))
            done(True, "")

    def test_the_installer_reports_while_it_runs(self):
        """The longest step used to be the quietest one.

        Every step announced itself once, with its own name, and then said
        nothing until it was over - for ./install.sh that is up to half an
        hour, while a three-second audio switch reported line by line. On a
        phone a window that shows nothing for that long is a window that has
        hung, and there was no way to tell the two apart.
        """
        comp = self.component()
        self.ran.clear()
        self.win.busy = False
        row = Recording()
        self.win.comp_rows[comp["tool"]] = {"state": row}
        self.win.run_component(comp, "install", "secret_word")
        for argv, _stdin, _cwd, _env in switcher.component_steps(
                comp, "install", "secret_word"):
            ran_argv, done, on_line, _kw = self.ran.pop(0)
            self.assertEqual(argv, ran_argv)
            self.assertIsNotNone(
                on_line, "%s runs without a word until it is over" % argv[0])
            on_line("Building the SPA plugin")
            self.assertEqual("Building the SPA plugin", row.subtitle)
            done(True, "")

    def test_a_long_line_is_cut_to_what_a_row_holds(self):
        comp = self.component()
        self.ran.clear()
        self.win.busy = False
        row = Recording()
        self.win.comp_rows[comp["tool"]] = {"state": row}
        self.win.run_component(comp, "install", "secret_word")
        _argv, _done, on_line, _kw = self.ran[0]
        on_line("x" * 200)
        self.assertEqual(60, len(row.subtitle))

    def catch_execv(self):
        """Hold on to os.execv for the length of one test.

        At os.execv and NOT by replacing Window.restart_self: the gi stub
        gives every window an `__setattr__` of its own that files unknown
        attributes away as properties, so assigning a method on an instance
        looks like it worked and changes nothing. Written down because it
        cost a debugging round - the test process was replaced by the app
        mid-run, the output stopped in the middle of a line and the exit code
        was 0.
        """
        started = []
        real = os.execv
        os.execv = lambda *args: started.append(args)
        self.addCleanup(lambda: setattr(os, "execv", real))
        return started

    def stub_askpass(self):
        """switcher.askpass.Askpass replaced by one that only writes down what it was
        asked to do. The real one needs a real GLib - tests/askpass-live.py
        drives that one."""
        log = []

        class Stub:
            def __init__(self, secret):
                log.append(("new", secret))

            def start(self):
                log.append(("start", None))
                return "/run/user/1/misc-de-x/askpass"

            def stop(self):
                log.append(("stop", None))

        return log, Stub

    def with_stub_askpass(self, comp, state="install", secret="secret_word"):
        log, stub = self.stub_askpass()
        real = switcher.askpass.Askpass
        switcher.askpass.Askpass = stub
        self.win.comp_rows[comp["tool"]] = {"state": Recording()}
        self.win.busy = False
        self.ran.clear()
        try:
            self.win.run_component(comp, state, secret)
        finally:
            switcher.askpass.Askpass = real
        return log

    def test_the_socket_stands_while_the_installer_runs(self):
        comp = self.component()
        log = self.with_stub_askpass(comp)
        self.assertEqual([("new", "secret_word"), ("start", None)], log)
        # The chain hands out one step at a time, so walk it to the installer.
        env = None
        for _ in range(len(switcher.component_steps(comp, "install", "x"))):
            argv, done, _on_line, kw = self.ran.pop(0)
            if argv[0].endswith("install.sh"):
                env = kw.get("env")
                break
            done(True, "")
        self.assertEqual("/run/user/1/misc-de-x/askpass",
                         (env or {}).get("SUDO_ASKPASS"))
        self.assertNotIn(("stop", None), log,
                         "taken down while the installer is still running")

    def test_a_chain_that_breaks_takes_the_socket_down_with_it(self):
        """Not only the way that worked: a password that sudo refuses ends the
        chain at the second step, and a socket that outlives it is a socket
        handing out a password to anything that asks."""
        comp = self.component()
        log = self.with_stub_askpass(comp)
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "fatal: could not read from remote")
        self.assertIn(("stop", None), log)
        self.assertIsNone(self.win.askpass)

    def test_a_tool_that_needs_no_root_gets_no_socket(self):
        """furios-gps-contribute installs into $HOME. Nothing there ever asks
        for a password, so nothing hands one out."""
        log = self.with_stub_askpass(self.component("furios-gps-contribute"),
                                    secret=None)
        self.assertEqual([], log)
        self.assertIsNone(self.win.askpass)

    def test_the_installer_gets_longer_than_a_clone_does(self):
        """The audio installer builds an SPA plugin and may fetch build
        packages over a phone connection first. A wait that runs out in the
        middle of apt-get leaves a half-installed system behind."""
        comp = self.component()
        self.with_stub_askpass(comp)
        deadlines = {}
        for _ in range(len(switcher.component_steps(comp, "install", "x"))):
            argv, done, _on_line, kw = self.ran.pop(0)
            deadlines[argv[0]] = kw.get("timeout")
            if argv[0].endswith("install.sh"):
                break
            done(True, "")
        self.assertEqual(1800, deadlines["./install.sh"])
        self.assertTrue(all(w == 600 for k, w in deadlines.items()
                            if not k.endswith("install.sh")), deadlines)

    def test_a_fetch_that_is_over_gives_the_buttons_back(self):
        """Read off the phone on 14.9.2026: after one install - the one that
        failed - no Install button on any tab could be pressed again, on any
        page, until the app was restarted. run_component switched them off and
        nobody switched them on."""
        comp = self.component()
        buttons = {c["tool"]: Recording() for c in switcher.COMPONENTS}
        for tool, button in buttons.items():
            self.win.comp_rows[tool] = {"state": Recording(), "button": button}
        log, stub = self.stub_askpass()
        real = switcher.askpass.Askpass
        switcher.askpass.Askpass = stub
        try:
            self.win.busy = False
            self.ran.clear()
            self.win.run_component(comp, "install", "secret_word")
            self.assertEqual([False] * len(buttons),
                             [k.sensitive for k in buttons.values()],
                             "nothing else may be started while one runs")
            _argv, done, _on_line, _kw = self.ran.pop(0)
            done(False, "fatal: could not read from remote")
        finally:
            switcher.askpass.Askpass = real
        self.assertEqual([True] * len(buttons),
                         [k.sensitive for k in buttons.values()])
        del log

    # --- the window updating itself ----------------------------------------

    def clone_with_program(self, url, content):
        """A clone of `url` with a miscde package in it.

        A package, not a file: what the app compares itself against is a
        fingerprint of every .py under miscde/, so a fixture writing one
        misc-de.py would be comparing something the app no longer looks at
        and would agree with anything.
        """
        d = tempfile.mkdtemp()
        self.addCleanup(shutil_real.rmtree, d, True)
        os.mkdir(os.path.join(d, ".git"))
        with open(os.path.join(d, ".git", "config"), "w") as fh:
            fh.write('[remote "origin"]\n\turl = %s\n' % url)
        os.mkdir(os.path.join(d, "miscde"))
        with open(os.path.join(d, "miscde", "window.py"), "wb") as fh:
            fh.write(content)
        return d

    def running_package(self, content, commit=None):
        """The tree the app would be running from, for PACKAGE_DIR - inside
        a directory of its own, where install.sh leaves installed-commit."""
        outer = tempfile.mkdtemp()
        self.addCleanup(shutil_real.rmtree, outer, True)
        d = os.path.join(outer, "miscde")
        os.mkdir(d)
        with open(os.path.join(d, "window.py"), "wb") as fh:
            fh.write(content)
        if commit is not None:
            with open(os.path.join(outer, "installed-commit"), "w") as fh:
                fh.write(commit + "\n")
        self.addCleanup(setattr, switcher.tools, "PACKAGE_DIR",
                        switcher.tools.PACKAGE_DIR)
        switcher.tools.PACKAGE_DIR = d
        return d

    def app_component(self):
        return switcher.SELF

    def test_the_app_is_a_component_but_not_one_of_the_tabs(self):
        """It is fetched and installed like the four tools - same repository,
        same clone, same installer - but it is not a thing on this phone
        somebody opens a page to operate: it IS the page."""
        comp = self.app_component()
        self.assertEqual("furios_app", comp["dir"])
        self.assertTrue(comp["url"].endswith("furios_app"))
        self.assertTrue(comp["root"], "install.sh writes to /usr/local")
        self.assertEqual([], [c for c in switcher.COMPONENTS
                              if c["tool"] == comp["tool"]],
                         "the window must not have a tab of its own")

    def test_nothing_is_offered_until_something_was_found(self):
        """A count that is always there says nothing - so the window builds
        it hidden and only a finding brings it out. "0 Updates" in the header
        would be furniture."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        shown = [c[1] for c in recorder.calls
                 if c[0] == "Gtk.Button.set_visible()" and c[1] == (True,)]
        self.assertEqual([], shown, "the count came up before anything looked")

    def test_every_repository_reports_into_the_same_place(self):
        """One dict for the window, so the count in the header and the list
        behind it cannot disagree - they are the same thing counted and read
        out."""
        self.win.updates = {}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        self.win.offer_update(self.app_component(), "2 new commit(s)",
                              "/home/furios/clone_dir")
        self.win.offer_update(self.component(), "1 new commit(s)", "/tmp/c")
        self.assertEqual({"misc-de", self.component()["tool"]},
                         set(self.win.updates))
        self.assertEqual("/home/furios/clone_dir",
                         self.win.updates["misc-de"]["path"])
        self.assertEqual(True, self.win.update_btn.visible)

    def test_the_header_counts_them_and_gets_the_plural_right(self):
        self.win.updates = {}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        self.win.offer_update(self.app_component(), "something", "/tmp/a")
        self.assertEqual("1 Update", str(self.win.update_label.text))
        self.win.offer_update(self.component(), "something", "/tmp/b")
        self.assertEqual("2 Updates", str(self.win.update_label.text))

    def test_no_updates_means_no_button_at_all(self):
        self.win.updates = {}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        self.win.show_update_count()
        self.assertEqual(False, self.win.update_btn.visible)

    def test_pressing_the_count_asks_and_starts_nothing(self):
        """It replaces the program somebody is looking at, among others. So
        it asks first, and it names what it would take."""
        self.win.updates = {}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        self.win.busy = False
        self.win.offer_update(self.app_component(), "2 new commit(s)", "/tmp/a")
        self.win.offer_update(self.component(), "9 new commit(s)", "/tmp/b")
        recorder.reset()
        self.ran.clear()
        self.win.ask_updates()
        self.assertEqual([], self.ran, "pressing the count started something")
        dialogs = [c for c in recorder.calls if c[0] == "Adw.AlertDialog"]
        self.assertEqual(1, len(dialogs), "one decision, one dialog")
        body = str(dialogs[0][2].get("body", ""))
        self.assertIn("misc-de", body)
        self.assertIn(self.component()["tool"], body)
        self.assertNotIn("commit", body, "one name per line, no detail")
        self.assertNotIn("sudo", body)
        self.assertNotIn("your own clones", body)
        self.assertNotIn("http", body, "the list names repositories by URL")
        self.assertNotIn("restarts", body, "the button already says so")
        answers = [str(c[1][1]) for c in recorder.calls
                     if c[0].endswith("add_response()") and c[1]]
        self.assertIn("Update and restart", answers)
        self.assertIn("Cancel", answers)

    def test_the_password_is_asked_once_for_all_of_them(self):
        """Four tools with updates used to mean four dialogs and four
        passwords for what is one decision."""
        self.win.updates = {}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        self.win.busy = False
        for comp in (self.app_component(), self.component()):
            self.win.offer_update(comp, "something", "/tmp/x")
        recorder.reset()
        self.win.ask_updates()
        entries = [c for c in recorder.calls if c[0] == "Adw.PasswordEntryRow"]
        self.assertEqual(1, len(entries), entries)

    def test_one_socket_carries_the_whole_batch(self):
        """One Askpass, not one per tool: it is the socket sudo asks at, and
        setting it up per tool would hand the password over again for every
        one of them."""
        log, stub = self.stub_askpass()
        real = switcher.askpass.Askpass
        switcher.askpass.Askpass = stub
        self.win.updates = {}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        self.win.busy = False
        for comp in (self.app_component(), self.component()):
            self.win.offer_update(comp, "something", "/tmp/x")
        self.ran.clear()
        try:
            self.win.run_updates("secret_word")
        finally:
            switcher.askpass.Askpass = real
        self.assertEqual(1, len([e for e in log if e[0] == "new"]), log)
        self.assertEqual([("new", "secret_word"), ("start", None)], log[:2])

    def test_what_was_found_decides_how_it_is_taken(self):
        """A reinstall pulls nothing; an update that pulled would run into
        the guard of a clone somebody keeps themselves. The kind is kept with
        the finding, not decided again when the button is pressed."""
        self.win.updates = {}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        self.win.offer_update(self.app_component(), "newer than what runs",
                              "/home/furios/clone_dir", "reinstall")
        waiting = self.win.updates["misc-de"]
        self.assertEqual("reinstall", waiting["mode"])
        self.assertEqual("/home/furios/clone_dir", waiting["path"])

    def test_a_clone_newer_than_the_program_is_offered_as_a_reinstall(self):
        """The git question is the wrong one for this component: the clone on
        this phone is where the next version is written, so it is never behind
        the server - it is regularly newer than what is installed."""
        comp = self.app_component()
        clone_dir = self.clone_with_program(comp["url"], b"a newer version")
        self.running_package(b"the old version")
        self.win.live["app"] = "/usr/local/bin/misc-de"
        self.win.update_btn = Recording()
        real = switcher.components.clone_elsewhere
        switcher.components.clone_elsewhere = lambda url, base=None: clone_dir
        try:
            self.win.check_app_program(comp)
        finally:
            switcher.components.clone_elsewhere = real
        self.assertEqual("reinstall", self.win.updates["misc-de"]["mode"])
        self.assertEqual(True, self.win.update_btn.visible)

    def check_against(self, commit, contains):
        comp = self.app_component()
        clone_dir = self.clone_with_program(comp["url"], b"another version")
        self.running_package(b"the installed version", commit=commit)
        self.win.live["app"] = "/usr/local/bin/misc-de"
        self.win.update_btn = Recording()
        asked = []

        def run_async(argv, done, **_kw):
            asked.append(argv)
            done(contains, "")

        self.enterContext(mock.patch.object(switcher.process, "run_async", run_async))
        self.enterContext(mock.patch.object(
            switcher.components, "clone_elsewhere", lambda url, base=None: clone_dir))
        self.win.check_app_program(comp)
        return asked

    def test_an_older_clone_is_not_offered_as_an_update(self):
        """Different is not newer: ~/Projekte/furios_app, an old checkout
        beside .dev/furios_app, was offered and would have installed the old
        code. Only a clone containing the installed commit is newer."""
        asked = self.check_against("abc123", contains=False)
        self.assertEqual(["merge-base", "--is-ancestor", "abc123", "HEAD"],
                         asked[0][3:])
        self.assertNotIn("misc-de", self.win.updates)

    def test_a_clone_that_contains_what_is_installed_is_offered(self):
        self.check_against("abc123", contains=True)
        self.assertEqual("reinstall", self.win.updates["misc-de"]["mode"])

    def test_an_install_that_named_no_commit_compares_files_as_before(self):
        asked = self.check_against(None, contains=False)
        self.assertEqual([], asked)
        self.assertIn("misc-de", self.win.updates)

    def test_a_program_that_matches_its_clone_is_not_offered(self):
        comp = self.app_component()
        clone_dir = self.clone_with_program(comp["url"], b"the same version")
        self.running_package(b"the same version")
        self.win.live["app"] = "/usr/local/bin/misc-de"
        self.win.update_btn = Recording()
        real = switcher.components.clone_elsewhere
        switcher.components.clone_elsewhere = lambda url, base=None: clone_dir
        try:
            self.win.check_app_program(comp)
        finally:
            switcher.components.clone_elsewhere = real
        self.assertIsNone(self.win.update_btn.visible,
                          "an offer that is always there says nothing")

    def test_a_reinstall_pulls_nothing_and_installs_what_is_there(self):
        """A pull would be the wrong question - and with uncommitted work in
        that clone its guard would refuse the install along with it."""
        steps = switcher.component_steps(self.app_component(), "reinstall",
                                            "secret_word", "/home/furios/Projekte/x")
        commands = [" ".join(argv) for argv, _s, _c, _e in steps]
        self.assertEqual([], [b for b in commands if b.startswith("git")])
        self.assertTrue(any(b.endswith("install.sh") for b in commands), commands)
        self.assertEqual("sudo -k", commands[-1])

    def test_a_finished_batch_restarts_without_asking_again(self):
        """The new program is on disk and this window is the old one. It was
        asked in the dialog - "Update and restart" - so asking a second time
        would be asking twice for one answer."""
        self.win.updates = {"x": {}}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        started = self.catch_execv()
        self.win.updates_done(True, "")
        self.assertEqual(1, len(started), "nothing was restarted")
        self.assertEqual({}, self.win.updates)
        self.assertEqual(False, self.win.update_btn.visible)

    def test_a_batch_that_failed_restarts_nothing_and_keeps_the_offer(self):
        """Half of them may be in. Restarting on top of that would hide the
        failure behind a window that looks new."""
        comp = self.component()
        self.win.updates = {comp["tool"]: {"comp": comp, "words": "x",
                                           "path": "/tmp/x", "mode": "update"}}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        started = self.catch_execv()
        self.win.updates_done(False, "sudo: 1 incorrect password attempt")
        self.assertEqual([], started, "a failed batch restarted anyway")
        self.assertIn(comp["tool"], self.win.updates)
        self.assertEqual(True, self.win.update_btn.visible)
        self.assertTrue(any("Could not" in t for t in self.toast_texts()))

    def test_a_failed_root_chain_drops_the_ticket_it_never_reached(self):
        """The chain's last step is "sudo -k", and a chain stops at its first
        failure. Whatever way out - a batch or a single install, a wrong step
        or a timeout - no ticket may outlive it, or every "sudo -n" switch in
        the window runs as root without asking."""
        class Helper:
            stopped = False
            def stop(self):
                self.stopped = True
        comp = self.component()
        for finish in (lambda: self.win.updates_done(False, "boom"),
                       lambda: self.win.component_done(comp, False, "boom")):
            self.ran.clear()
            helper = Helper()
            self.win.askpass = helper
            self.win.update_btn = Recording()
            self.win.update_label = Recording()
            self.catch_execv()
            finish()
            self.assertTrue(helper.stopped)
            self.assertIsNone(self.win.askpass)
            self.assertIn(["sudo", "-k"], [argv for argv, *_r in self.ran])

    def test_a_chain_that_got_through_does_not_drop_the_ticket_twice(self):
        class Helper:
            def stop(self):
                pass
        self.win.updates = {"x": {}}
        self.win.askpass = Helper()
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        self.catch_execv()
        self.win.updates_done(True, "")
        self.assertNotIn(["sudo", "-k"], [argv for argv, *_r in self.ran])

    def test_no_root_no_ticket_to_drop(self):
        self.win.askpass = None
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        self.win.updates_done(False, "boom")
        self.assertEqual([], [a for a, *_r in self.ran if a[:1] == ["sudo"]])

    def test_the_restart_replaces_this_process_instead_of_starting_a_second(self):
        """A second instance hands its activation to the one already running -
        it would present the OLD window and then die with it."""
        installed = os.path.join(tempfile.mkdtemp(prefix="miscde-test-"),
                                 "misc-de")
        called = self.restart_with(lambda name: installed
                                   if name == "misc-de" else None)
        self.assertEqual([(installed, [installed])], called)

    def test_without_an_installed_program_the_restart_takes_the_running_one(self):
        """Started from the source tree, with nothing installed: the program
        that is running is the one to come back as."""
        called = self.restart_with(lambda name: None)
        running = os.path.abspath(sys.argv[0])
        self.assertEqual([(running, [running])], called)

    def restart_with(self, maybe):
        """restart_self with _tool_maybe answering `maybe`, and execv caught."""
        called = []
        real, real_maybe = switcher.os.execv, switcher.tools._tool_maybe
        switcher.os.execv = lambda prog, argv: called.append((prog, argv))
        switcher.tools._tool_maybe = maybe
        try:
            self.win.restart_self()
        finally:
            switcher.os.execv, switcher.tools._tool_maybe = real, real_maybe
        return called

    def test_a_step_that_fails_stops_the_chain_and_shows_what_it_said(self):
        comp = self.component()
        self.ran.clear()
        self.win.busy = False
        self.win.comp_rows[comp["tool"]] = {"state": Recording()}
        self.win.run_component(comp, "install", "wrong")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "fatal: could not read from remote")
        self.assertEqual([], [r for r in self.ran if "install.sh" in " ".join(r[0])])
        self.assertIn("Could not set up", str(self.win.toasts.text))

    def with_tool(self, name,
                  path=os.path.expanduser("~/.local/bin/furios-gps-contribute")):
        """_tool_maybe answering as though `name` had just been installed."""
        real = switcher.tools._tool_maybe
        switcher.tools._tool_maybe = lambda n: path if n == name else real(n)
        return real

    def toast_texts(self):
        return [str(c[2].get("title", "")) for c in recorder.calls
                if c[0] == "Adw.Toast"]

    def freshly_installed(self, tool="furios-gps-contribute",
                          path=os.path.expanduser(
                              "~/.local/bin/furios-gps-contribute")):
        """A window whose tool was missing when it opened and is there now -
        the state the phone is in the moment an install finishes."""
        win = self.without_tool(tool)
        comp = self.component(tool)
        recorder.reset()
        real = self.with_tool(tool, path)
        try:
            win.component_done(comp, True, "")
        finally:
            switcher.tools._tool_maybe = real
        return win

    def test_a_finished_install_turns_the_tab_into_the_real_one(self):
        """This used to end in "restart the app to get its tab", which is the
        one thing left to do after watching a clone, a build and an install go
        by - and it reads like nothing happened."""
        win = self.freshly_installed()
        self.assertEqual(os.path.expanduser("~/.local/bin/furios-gps-contribute"),
                         win.live["gps"])
        self.assertTrue(any("live" in t for t in self.toast_texts()),
                        "nothing said the tab is usable now")
        self.assertFalse(any("restart" in t for t in self.toast_texts()))

    def test_the_new_tab_keeps_its_place_in_the_row(self):
        """Adw.ViewStack can only append, so the tabs after the swapped one
        are taken out and put back. Left to append, GPS would land behind
        Switches and the row would reorder itself under somebody's thumb."""
        win = self.freshly_installed()
        # Its own return value is recorded under the same name with no
        # arguments, so the calls are the ones that carry some.
        built = [c[1][1] for c in recorder.calls
                  if c[0] == "Adw.ViewStack.add_titled_with_icon()" and c[1]]
        # Other has no tool and is not in COMPONENTS, but it sits behind
        # them all and has to be put back last too.
        self.assertEqual(["gps", "switches", "security", "battery", "other"],
                         built)
        # One for the tab being swapped, one for each tab behind it.
        self.assertEqual(len(built), len([c for c in recorder.calls
                                           if c[0] == "Adw.ViewStack.remove()"
                                           and c[1]]))
        del win

    def test_the_tab_somebody_installed_from_is_the_one_they_end_up_on(self):
        """The page they were standing on went out with the swap."""
        self.freshly_installed()
        chosen = [c[1][0] for c in recorder.calls
                    if c[0] == "Adw.ViewStack.set_visible_child_name()" and c[1]]
        self.assertEqual(["gps"], chosen)

    def test_the_new_page_runs_the_tool_that_was_just_installed(self):
        """The window used to keep the answer to "was it there when the app
        started" in a module constant. A page built after that would have sent
        None to the switch."""
        win = self.freshly_installed()
        self.ran.clear()
        win.busy = False
        win._syncing = False
        win.on_gps_contrib(win.gps_contrib, None)
        argv = self.ran[0][0]
        self.assertIn(os.path.expanduser("~/.local/bin/furios-gps-contribute"),
                      argv)

    def test_a_tool_that_was_already_there_says_so(self):
        """component_done is the single-install path now - the tab that
        offers to fetch a missing tool. Reached with the tool already
        present, there is nothing to swap in and nothing to promise."""
        comp = self.component("modemctl") if MODEMCTL else None
        if comp is None:
            self.skipTest("no modemctl here")
        self.win.comp_rows[comp["tool"]] = {"state": Recording()}
        recorder.reset()
        self.win.component_done(comp, True, "")
        self.assertTrue(any("up to date" in t for t in self.toast_texts()))

    def test_an_install_that_leaves_nothing_behind_says_so(self):
        """Every step returned 0 and the tool is still not findable. The
        installer's own output is the only thing that can explain that."""
        win = self.without_tool("furios-gps-contribute")
        recorder.reset()
        # Absent during the window AND during the answer: this machine may
        # well have the tool installed, and then the swap would succeed and the
        # test would measure the opposite of what it says.
        real = switcher.tools._tool_maybe
        switcher.tools._tool_maybe = lambda n: (None if n == "furios-gps-contribute"
                                                else real(n))
        try:
            win.component_done(self.component("furios-gps-contribute"), True,
                               "ln: Permission denied")
        finally:
            switcher.tools._tool_maybe = real
        self.assertTrue(any("not on the phone" in t
                            for t in self.toast_texts()))
        body = [str(c[2].get("body", "")) for c in recorder.calls
                   if c[0] == "Adw.AlertDialog"]
        self.assertTrue(any("Permission denied" in b for b in body))

    def test_a_failed_installer_that_left_the_tool_still_makes_the_tab_live(self):
        """Found on 30.9.2026: killswitch's installer ended with exit 3 after
        a complete install (a status line at the very end), and the tab went
        on saying "not installed" next to a tool that was there. The tab
        goes live; the installer's words are still shown."""
        win = self.without_tool("furios-gps-contribute")
        recorder.reset()
        real = self.with_tool("furios-gps-contribute", os.path.expanduser(
            "~/.local/bin/furios-gps-contribute"))
        try:
            win.component_done(self.component("furios-gps-contribute"), False,
                               "Active: inactive (dead)")
        finally:
            switcher.tools._tool_maybe = real
        self.assertTrue(win.live["gps"])
        self.assertTrue(any("reported an error" in t
                            for t in self.toast_texts()))
        body = [str(c[2].get("body", "")) for c in recorder.calls
                   if c[0] == "Adw.AlertDialog"]
        self.assertTrue(any("inactive (dead)" in b for b in body))

    def test_a_failed_installer_without_the_tool_says_it_could_not(self):
        win = self.without_tool("furios-gps-contribute")
        recorder.reset()
        real = switcher.tools._tool_maybe
        switcher.tools._tool_maybe = lambda n: (None if n == "furios-gps-contribute"
                                                else real(n))
        try:
            win.component_done(self.component("furios-gps-contribute"), False,
                               "make: *** Error 1")
        finally:
            switcher.tools._tool_maybe = real
        self.assertFalse(win.live.get("gps"))
        self.assertTrue(any("Could not set up" in t for t in self.toast_texts()))

    def test_nothing_is_offered_while_something_else_runs(self):
        self.win.comp_rows[self.component()["tool"]] = {}
        self.ran.clear()
        self.win.busy = True
        try:
            self.win.ask_component(self.component(), "install")
            self.assertEqual([], self.ran)
        finally:
            self.win.busy = False

    # --- the update offer at the foot of a page ----------------------------

    def lines_for(self, comp):
        """The window's own record of what is waiting, emptied first.

        There are no per-tab update groups any more: one place collects what
        every repository has to say and the header counts it."""
        self.win.updates = {}
        self.win.update_btn = Recording()
        self.win.update_label = Recording()
        return self.win.updates

    def test_an_update_is_offered_only_once_somebody_has_looked(self):
        """A count that is always there says nothing, and an app that offers
        an update it never checked for is worse than one that offers none."""
        comp = self.component()
        rows = self.lines_for(comp)
        self.assertEqual({}, rows)
        self.ran.clear()
        self.win.check_component(comp, "/tmp/clone_dir")
        argv, done, _on_line, _kw = self.ran.pop(0)
        self.assertIn("fetch", argv)
        done(True, "")
        argv, done, _on_line, _kw = self.ran.pop(0)
        self.assertIn("rev-list", argv)
        done(True, "4\n")
        self.assertIn("4 new commit", rows[comp["tool"]]["words"])
        self.assertEqual("/tmp/clone_dir", rows[comp["tool"]]["path"])

    def test_a_clone_that_is_current_offers_nothing(self):
        comp = self.component()
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.check_component(comp, "/tmp/clone_dir")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "0\n")
        self.assertEqual({}, rows, "a check that found nothing offered something")

    def test_a_check_that_fails_offers_nothing_either(self):
        """No network is not "there is an update", and it is not "up to
        date" - it is nothing to say."""
        comp = self.component()
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.check_component(comp, "/tmp/clone_dir")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "could not resolve host")
        self.assertEqual([], self.ran)
        self.assertEqual({}, rows, "a check that found nothing offered something")

    def test_a_clone_somebody_else_keeps_is_read_and_never_written(self):
        """ls-remote asks the server, merge-base reads the clone. A fetch
        would already write into their .git, a pull into their working tree."""
        comp = self.component()
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.peek_upstream(comp, "/home/furios/Projekte/eigen")
        argv, done, _on_line, _kw = self.ran.pop(0)
        self.assertIn("ls-remote", argv)
        done(True, "abc123\tHEAD")
        argv, done, _on_line, _kw = self.ran.pop(0)
        self.assertEqual(["merge-base", "--is-ancestor", "abc123", "HEAD"],
                         argv[3:])
        done(False, "")                        # the clone does not have it
        self.assertIn(comp["tool"], rows)
        self.assertEqual("/home/furios/Projekte/eigen",
                         rows[comp["tool"]]["path"])

    def test_what_is_waiting_is_named_by_its_tool_and_never_by_a_url(self):
        """The list of updates is read on a phone. A github.com address in
        every line pushes the one thing it has to say - which tool, how far
        behind - off the edge, and the line already begins with the name."""
        comp = self.component()
        for check in (self.words_from_our_clone, self.words_from_a_foreign_clone):
            words = check(comp)
            self.assertNotIn("http", words)
            self.assertNotIn(comp["url"], words)

    def words_from_our_clone(self, comp):
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.check_component(comp, "/tmp/clone_dir")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "4\n")
        return rows[comp["tool"]]["words"]

    def words_from_a_foreign_clone(self, comp):
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.peek_upstream(comp, "/eigen")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "abc123\tHEAD")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "")
        return rows[comp["tool"]]["words"]

    def test_a_foreign_clone_that_matches_the_server_is_left_in_peace(self):
        comp = self.component()
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.peek_upstream(comp, "/eigen")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "abc123\tHEAD")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "")
        self.assertEqual({}, rows, "a check that found nothing offered something")

    def test_a_foreign_clone_ahead_of_the_server_is_not_behind_it(self):
        """Unpushed commits are not news from the server. Against a real
        repository: the clone has the server's commit and one more."""
        work = tempfile.mkdtemp(prefix="miscde-ahead-")
        git = ["git", "-C", work, "-c", "user.name=t", "-c", "user.email=t@t"]
        subprocess_real.run(["git", "init", "-q", work], check=True)
        subprocess_real.run(git + ["commit", "-q", "--allow-empty", "-m", "a"],
                            check=True)
        theirs = subprocess_real.run(git + ["rev-parse", "HEAD"], check=True,
                                     capture_output=True, text=True).stdout.strip()
        subprocess_real.run(git + ["commit", "-q", "--allow-empty", "-m", "b"],
                            check=True)
        comp = self.component()
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.peek_upstream(comp, work)
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, theirs + "\tHEAD")
        argv, done, _on_line, _kw = self.ran.pop(0)
        real = subprocess_real.run(argv, capture_output=True, text=True)
        done(real.returncode == 0, real.stdout)
        self.assertEqual({}, rows, "unpushed work was offered as an update")
        shutil_real.rmtree(work, ignore_errors=True)

    def test_no_answer_from_the_server_is_not_an_update(self):
        comp = self.component()
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.peek_upstream(comp, "/eigen")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "could not resolve host")
        self.assertEqual([], self.ran, "the clone was asked about nothing")
        self.assertEqual({}, rows, "a check that found nothing offered something")

    def test_our_own_clone_is_the_one_that_gets_fetched(self):
        """Where we cloned ourselves, a fetch is ours to run - and counting
        commits is more precise than comparing two hashes."""
        # About the tabs' tools: whether this phone has the folder dock
        # installed must not change the count.
        self.enterContext(mock.patch.dict(switcher.PHOSH, {"find": lambda: None}))
        self.win.comp_rows = {}
        for comp in switcher.COMPONENTS:
            self.lines_for(comp)
        self.ran.clear()
        # Every tool installed, and the app too: on a phone with none of
        # them the check has nothing to ask, and the loop below would pass
        # on an empty list.
        fake_bin = tempfile.mkdtemp(prefix="miscde-test-")
        real = switcher.components.is_clone_of
        real_maybe = switcher.tools._tool_maybe
        switcher.components.is_clone_of = lambda path, url: True
        switcher.tools._tool_maybe = lambda name: os.path.join(fake_bin, name)
        self.win.live["app"] = os.path.join(fake_bin, "misc-de")
        try:
            self.win.check_updates()
        finally:
            switcher.components.is_clone_of = real
            switcher.tools._tool_maybe = real_maybe
            shutil_real.rmtree(fake_bin, ignore_errors=True)
        commands = [" ".join(r[0]) for r in self.ran]
        # One fetch per tool, and one for the app itself.
        self.assertEqual(len(switcher.COMPONENTS) + 1, len(commands), commands)
        for b in commands:
            self.assertIn("fetch", b)
            self.assertIn(switcher.CLONE_HOME, b)

    def test_the_check_runs_once_for_every_installed_tool(self):
        # About the tabs' tools: whether this phone has the folder dock
        # installed must not change the count.
        self.enterContext(mock.patch.dict(switcher.PHOSH, {"find": lambda: None}))
        self.win.comp_rows = {}
        for comp in switcher.COMPONENTS:
            self.lines_for(comp)
        self.ran.clear()
        real_is, real_else = switcher.components.is_clone_of, switcher.components.clone_elsewhere
        switcher.components.is_clone_of = lambda path, url: False
        switcher.components.clone_elsewhere = lambda url, base=None: "/eigen"
        try:
            self.win.check_updates()
        finally:
            switcher.components.is_clone_of, switcher.components.clone_elsewhere = real_is, real_else
        asked = [r[0] for r in self.ran]
        # The window itself is asked about too, and it is not one of the tabs.
        expected = len([c for c in switcher.COMPONENTS
                        if switcher.tools._tool_maybe(c["tool"])])
        expected += bool(self.win.live.get("app"))
        self.assertEqual(expected, len(asked))
        for argv in asked:
            self.assertIn("ls-remote", argv)

    # --- the way back, on every page ---------------------------------------
    #
    # One idea, one shape. Before this it was a blue "Restore sound" here, a
    # red "Restore shipped state" there and nothing at all on the other two -
    # and the colours made a claim ("do this" / "careful") that is not true
    # in general. What differs between the pages is the price, and that is
    # what the description says.

    # ---------------------------------------------------------- Security
    #
    # The page of a tool that can lock somebody out of their own phone, so
    # the tests are about two things above all: that a reading never turns
    # into an action, and that the one value which is this phone's own
    # cannot be widened by accident.

    def security_win(self):
        if not SECCTL:
            self.skipTest("secctl not installed")
        return self.win

    def test_without_pkexec_security_runs_nothing_and_stays_usable(self):
        """[None, secctl, ...] reached Gio as argv, which raises a TypeError
        run_async does not catch - after set_busy(True), for good."""
        win = self.security_win()
        real = switcher.tools.PKEXEC
        try:
            switcher.tools.PKEXEC = None
            win._loading = False
            win.busy = False
            for act in (lambda: win.on_security_switch(
                            win.sec_switches["sysctl"], None, "sysctl"),
                        lambda: win.on_security_restore(None)):
                self.ran.clear()
                act()
                self.assertFalse(win.busy)
                self.assertFalse([r for r in self.ran if r[0][0] is None],
                                 "started a command with no program")
                self.assertIn("pkexec", str(win.toasts.text))
        finally:
            switcher.tools.PKEXEC = real

    SEC_JSON = """{
      "parts": {
        "sysctl": {"state": "on", "keys": {}},
        "modules": {"state": "on", "count": 14,
                    "modules": {"tipc": true, "rds": true, "x25": null}},
        "firewall": {"state": "on", "live": true, "lan": "192.168.0.0/24",
                     "iface": "wlan0"}
      },
      "exposure": {"readable": true, "open": [
        {"proto": "tcp", "addr": "0.0.0.0", "port": "22", "any": true},
        {"proto": "tcp", "addr": "0.0.0.0", "port": "5355", "any": true},
        {"proto": "udp", "addr": "0.0.0.0", "port": "5353", "any": true},
        {"proto": "udp", "addr": "10.0.3.1", "port": "53", "any": false},
        {"proto": "tcp", "addr": "10.0.3.1", "port": "53", "any": false}
      ]},
      "state": "on"
    }"""

    def test_filling_the_page_writes_nothing_back(self):
        """set_active fires notify::active. Without the guard, reading the
        state would switch the thing being read."""
        win = self.security_win()
        self.ran.clear()
        win.on_security_status(True, self.SEC_JSON)
        self.assertEqual([], self.ran)

    def test_each_switch_asks_secctl_for_its_own_part(self):
        win = self.security_win()
        win._loading = False
        win.busy = False
        for key in ("sysctl", "modules", "lockout"):
            # Reset per part: the handler locks the window while the helper
            # runs, and a second switch thrown while it is locked is
            # deliberately ignored.
            win.busy = False
            self.ran.clear()
            row = win.sec_switches[key]
            row.set_active(True)
            win.on_security_switch(row, None, key)
            argv = self.ran[0][0]
            self.assertEqual(argv[-3:], ["set", key, "on"])
            self.assertIn("secctl", argv[-4])

    def test_the_lockout_says_when_the_lock_screen_is_locked(self):
        """phosh refuses the right PIN during a lock without saying why, so
        this row has to."""
        win = self.security_win()
        data = json.loads(self.SEC_JSON)
        data["parts"]["lockout"] = {"state": "on", "module": True,
                                    "user": {"locked_for": 272}}
        win.on_security_status(True, json.dumps(data))
        self.assertIn("4:32 left", win.sec_switches["lockout"].subtitle)
        self.assertTrue(win.sec_switches["lockout"].active)

    def test_the_lockout_without_its_module_says_so(self):
        win = self.security_win()
        data = json.loads(self.SEC_JSON)
        data["parts"]["lockout"] = {"state": "off", "module": False}
        win.on_security_status(True, json.dumps(data))
        self.assertIn("not installed", win.sec_switches["lockout"].subtitle)

    def test_the_lockout_off_says_what_it_would_do(self):
        win = self.security_win()
        data = json.loads(self.SEC_JSON)
        data["parts"]["lockout"] = {"state": "off", "module": True}
        win.on_security_status(True, json.dumps(data))
        self.assertIn("5 min", win.sec_switches["lockout"].subtitle)

    def test_a_switch_off_reverts_that_part(self):
        win = self.security_win()
        win._loading = False
        win.busy = False
        row = win.sec_switches["modules"]
        row.set_active(False)
        self.ran.clear()
        win.on_security_switch(row, None, "modules")
        self.assertEqual(self.ran[0][0][-3:], ["set", "modules", "off"])

    def test_a_refusal_is_shown_with_its_reason(self):
        """secctl's refusal is a sentence, not an error code, and it is the
        one thing somebody needs in order to act."""
        win = self.security_win()
        recorder.reset()
        win.after_security(False, "lockout: the module does not load",
                           "lockout", "on")
        bodies = [str(c[2].get("body", "")) for c in recorder.calls
                  if c[0] == "Adw.AlertDialog"]
        self.assertTrue(any("does not load" in b for b in bodies), bodies)

    def test_there_is_no_firewall_and_no_home_network(self):
        """Removed 28.9. on request, with the home network it needed."""
        recorder.reset()
        self.security_win()
        switcher.Window(switcher.Adw.Application())
        titles = [str(c[2].get("title", "")) for c in recorder.calls
                  if c[0] in ("Adw.SwitchRow", "Adw.EntryRow")]
        self.assertNotIn("Firewall", titles)
        self.assertEqual([], [x for x in titles if "Home network" in x])

    def test_there_is_no_listening_list(self):
        """Removed on request 28.9.: the page shows the switches only."""
        recorder.reset()
        self.security_win()
        switcher.Window(switcher.Adw.Application())
        titles = [str(c[2].get("title", "")) for c in recorder.calls
                  if c[0] == "Adw.PreferencesGroup"]
        self.assertNotIn("Listening", titles)

    def test_the_way_back_takes_all_three(self):
        win = self.security_win()
        win.busy = False
        self.ran.clear()
        win.on_security_restore(None)
        self.assertEqual(self.ran[0][0][-2:], ["revert", "all"])

    def test_a_tool_that_did_not_answer_is_not_shown_as_a_reading(self):
        """Three switches at off is what a phone with nothing switched on
        looks like, so a failed reading has to say so on the rows that are
        readings - there is no kernel line left to carry the message."""
        win = self.security_win()
        win.on_security_status(False, "")
        for row in win.sec_switches.values():
            self.assertIn("did not answer", str(row.subtitle))

    def test_an_unreadable_answer_says_so_the_same_way(self):
        win = self.security_win()
        win.on_security_status(True, "not json at all")
        for row in win.sec_switches.values():
            self.assertIn("unreadable", str(row.subtitle))

    def test_every_page_offers_the_same_way_back(self):
        """Counted, not named: adding a page must not quietly add a fifth
        shape of this."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        expected = (1 + bool(MODEMCTL) + bool(CONTRIB)
                    + bool(KILLSWITCH) + bool(BATTCTL) + bool(SECCTL))
        buttons = [c for c in recorder.calls if c[0] == "Gtk.Button"
                   and c[2].get("label") == switcher.Window.RESTORE_LABEL]
        groups = [c for c in recorder.calls if c[0] == "Adw.PreferencesGroup"
                   and c[2].get("title") == switcher.Window.RESTORE_TITLE]
        self.assertEqual(expected, len(buttons))
        self.assertEqual(expected, len(groups))

    def test_no_way_back_is_painted_louder_than_another(self):
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        classes = [a for c in recorder.calls
                   if c[0] == "Gtk.Button.add_css_class()" for a in c[1]]
        self.assertEqual([], [k for k in classes if k.endswith("-action")])
        self.assertIn("pill", classes)

    def test_a_way_back_carries_no_text_on_the_page(self):
        """Only the button on the page; what it costs is said in the
        question, which the click test below covers."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        groups = [c for c in recorder.calls if c[0] == "Adw.PreferencesGroup"
                  and c[2].get("title") == switcher.Window.RESTORE_TITLE]
        self.assertTrue(groups)
        self.assertEqual([], [c for c in groups if c[2].get("description")])

    def test_a_way_back_asks_before_it_acts(self):
        """Nothing here is a tap to take back, so none of them acts on the tap
        alone."""
        called = []
        self.ran.clear()
        self.win.confirm_restore("what it costs", called.append, "btn")
        self.assertEqual([], called)
        self.assertEqual([], self.ran)

    def test_cancelling_is_the_default_and_does_nothing(self):
        called = []
        recorder.reset()
        self.win.confirm_restore("what it costs", called.append, "btn")
        # c[1] filtered: the stub records the call AND the object it hands
        # back, and the second one carries no arguments.
        default_ = [c[1] for c in recorder.calls
                   if c[0] == "Adw.AlertDialog.set_default_response()" and c[1]]
        closing = [c[1] for c in recorder.calls
                      if c[0] == "Adw.AlertDialog.set_close_response()" and c[1]]
        self.assertEqual([("cancel",)], default_)
        self.assertEqual([("cancel",)], closing)
        self.win.on_restore_response(None, "cancel")
        self.assertEqual([], called)

    def test_cancel_is_the_answer_under_the_thumb(self):
        """libadwaita stacks the answers in reverse on a narrow screen: the one
        added LAST is drawn on top. Added the obvious way round, "Restore
        shipped state" sat exactly where a thumb reaches first - seen on the
        phone, which is the only place this can be seen at all."""
        recorder.reset()
        self.win.confirm_restore("what it costs", lambda _b: None, None)
        answers = [c[1][0] for c in recorder.calls
                     if c[0] == "Adw.AlertDialog.add_response()" and c[1]]
        self.assertEqual(["restore", "cancel"], answers)

    def test_answering_restore_is_what_runs_it(self):
        called = []
        self.win.confirm_restore("what it costs", called.append, "btn")
        self.win.on_restore_response(None, "restore")
        self.assertEqual(["btn"], called)
        # Answering twice must not run it twice - the pending one is cleared.
        self.win.on_restore_response(None, "restore")
        self.assertEqual(["btn"], called)

    def test_the_location_way_back_switches_sending_off(self):
        win = self.gps_win()
        self.ran.clear()
        win.busy = False
        win.on_gps_restore(None)
        self.assertEqual([win.live["gps"], "off"], list(self.ran[-1][0]))
        win.on_gps_restored(True, "")
        self.assertIn("off", str(win.toasts.text))

    def test_the_switches_way_back_undoes_what_this_page_added(self):
        """Four commands, because two owners: the tool holds the extra radios
        and the shell's plugin list, systemd holds the unit. The sliders are
        not among them - they are hardware and nothing here reaches them."""
        win = self.switches_win()
        self.mask_state(False)
        self.ran.clear()
        win.busy = False
        win.on_switches_restore(None)
        ran = []
        for _ in range(4):
            argv, done, _on_line, _kw = self.ran.pop(0)
            ran.append(" ".join(argv))
            done(True, "")
        self.assertTrue(any("config wifi off" in c for c in ran), ran)
        self.assertTrue(any("config bluetooth off" in c for c in ran), ran)
        self.assertTrue(any("icons off" in c for c in ran), ran)
        self.assertTrue(any("disable --now killswitch-indicator" in c
                            for c in ran), ran)

    def mask_state(self, enabled):
        """The mask's state is the phone's - systemctl on this phone answers
        whatever it was last set to, and the test then depended on it."""
        sw = importlib.import_module("miscde.pages.switches")
        self.enterContext(mock.patch.object(sw, "nwk_mask_installed",
                                            lambda: True))
        self.enterContext(mock.patch.object(sw, "nwk_mask_enabled",
                                            lambda: enabled))

    def test_the_way_back_takes_the_mask_off_through_the_password(self):
        """sudo asks on this phone. The way back used a bare "sudo -n" for
        the mask and failed at its first step - nothing was undone."""
        win = self.switches_win()
        self.mask_state(True)
        win.sw_nwk_mask = Recording()
        asked = []
        self.enterContext(mock.patch.object(
            switcher.Window, "ask_nwk_mask_password",
            lambda self, wanted, then=None: asked.append((wanted, then))))
        self.ran.clear()
        win.busy = False
        win.on_switches_restore(None)
        argv, done, _l, _kw = self.ran.pop(0)
        self.assertEqual(["sudo", "-n", "systemctl", "disable"], argv[:4])
        done(False, "sudo: a password is required")
        self.assertEqual(1, len(asked))
        wanted, then = asked[0]
        self.assertFalse(wanted)
        self.assertEqual([], self.ran, "went on before the mask was off")
        then(True, "")                       # the password worked
        commands = []
        while self.ran:
            argv, done, _l, _kw = self.ran.pop(0)
            commands.append(" ".join(argv))
            done(True, "")
        self.assertTrue(any("disable --now killswitch-indicator" in c
                            for c in commands), commands)
        self.assertFalse(win.busy)

    def test_a_cancelled_password_stops_the_way_back(self):
        win = self.switches_win()
        self.mask_state(True)
        win.sw_nwk_mask = Recording()
        win._nwk_mask_pending = (None, None, None)
        self.ran.clear()
        win.busy = False
        win.on_switches_restore(None)
        _argv, done, _l, _kw = self.ran.pop(0)
        self.enterContext(mock.patch.object(
            switcher.Window, "ask_nwk_mask_password",
            lambda self, wanted, then=None: setattr(
                self, "_nwk_mask_pending", (wanted, None, then))))
        done(False, "sudo: a password is required")
        win.on_nwk_mask_password(None, "cancel")
        self.assertEqual([], [r for r in self.ran
                              if "config" in r[0] or "disable" in r[0]])
        self.assertFalse(win.busy)
        self.assertIn("Could not", str(win.toasts.text))

    def test_a_step_that_fails_stops_the_rest(self):
        """Half done is reported, never passed off as success."""
        win = self.switches_win()
        self.mask_state(False)
        self.ran.clear()
        win.busy = False
        win.on_switches_restore(None)
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "nope")
        self.assertEqual([], [r for r in self.ran if "config" in r[0]])
        self.assertIn("Could not", str(win.toasts.text))

    def test_the_click_itself_goes_through_the_question(self):
        """Not just confirm_restore in isolation: the button must be wired to
        it. Wired straight to the handler it would act on the tap, and every
        test above would still pass."""
        called = []
        recorder.reset()
        _grp, btn = self.win.build_restore_group("what it costs", called.append)
        click = [c[1][1] for c in recorder.calls
                 if c[0] == "Gtk.Button.connect()" and c[1] and c[1][0] == "clicked"]
        self.assertEqual(1, len(click))
        click[0](btn)
        self.assertEqual([], called)
        self.win.on_restore_response(None, "restore")
        self.assertEqual([btn], called)

    def test_a_way_back_does_nothing_while_something_else_runs(self):
        """Two switches at once is how a half-applied state is made."""
        for handler in (self.win.on_gps_restore, self.win.on_switches_restore):
            with self.subTest(handler=handler.__name__):
                self.win.busy = True
                self.ran.clear()
                handler(None)
                self.assertEqual([], self.ran)
        self.win.busy = False

    def test_the_location_way_back_needs_no_root(self):
        """Nothing on the page wants root any more, so nothing asks pkexec."""
        win = self.gps_win()
        self.ran.clear()
        win.busy = False
        win.on_gps_restore(None)
        self.assertNotIn("pkexec", " ".join(self.ran[-1][0]))

    def test_a_location_way_back_that_fails_is_reported(self):
        win = self.gps_win()
        win.on_gps_restored(False, "furios-gps-contribute: no")
        self.assertIn("Could not", str(win.toasts.text))

    def test_a_stopped_daemon_is_said_where_it_would_act(self):
        """"active" is systemd's word and the whole answer. The daemon draws
        nothing any more - it is what takes the extra radios down - so a
        stopped one has to show up on those rows, or the page promises
        something the phone will not do."""
        win = self.switches_win()
        win.on_indicator_active(True, "active\n")
        win.on_switches_status(True, self.JSON)
        self.assertNotIn("not running", win.sw_wifi.subtitle)
        win.on_indicator_active(True, "failed\n")
        self.assertIn("not running", win.sw_wifi.subtitle)
        self.assertIn("Wi-Fi is on right now", win.sw_wifi.subtitle)

    def test_icons_that_could_not_be_switched_say_so(self):
        win = self.switches_win()
        win.after_indicator(False, "", "on")
        self.assertIn("Could not switch the icons on", str(win.toasts.text))

    def test_switching_the_icons_on_says_when_they_appear(self):
        """The one surprise about this switch: phosh looks for new plugins
        only when it starts."""
        win = self.switches_win()
        win.after_indicator(True, "", "on")
        self.assertIn("next boot", str(win.toasts.text))

    def test_filling_the_switches_page_writes_nothing_back(self):
        """The rows are set from what was read; without the guard each of
        those writes would look like somebody flipping the switch."""
        win = self.switches_win()
        win._loading = True
        self.ran.clear()
        win.on_indicator_switch(win.sw_row, None)
        win.set_extra("wifi", win.sw_wifi)
        self.assertEqual([], self.ran)
        win._loading = False

    def test_a_tool_that_did_not_answer_is_not_shown_as_a_reading(self):
        win = self.switches_win()
        win.on_switches_status(False, "")
        self.assertIn("did not answer", win.sw_row.subtitle)

    def test_choosing_bluetooth_is_written_through_the_tool_too(self):
        """The Wi-Fi row is checked above; this one exists so that the second
        row cannot quietly write the first one's name."""
        win = self.switches_win()
        self.ran.clear()
        win._loading = False
        win.sw_bt.set_active(True)
        win.on_extra_bt(win.sw_bt, None)
        self.assertEqual(["config", "bluetooth", "on"], list(self.ran[-1][0][1:]))

    def test_switching_a_radio_on_says_what_it_will_do(self):
        """"on" is the half that changes behaviour later, when the slider
        moves - so it is the half that gets said out loud."""
        win = self.switches_win()
        win.after_extra(True, "wifi", "on")
        self.assertIn("go off with the network switch", str(win.toasts.text))
        win.toasts.text = None
        win.after_extra(True, "wifi", "off")
        self.assertIsNone(win.toasts.text)

    def test_a_radio_that_could_not_be_changed_is_read_back(self):
        win = self.switches_win()
        self.ran.clear()
        win.after_extra(False, "wifi", "on")
        self.assertIn("Could not change Wi-Fi", str(win.toasts.text))
        # and the page is re-read, so the switch returns to what is true
        self.assertTrue(self.ran)

    def test_the_question_repeats_the_words_the_page_carries(self):
        """Nothing new to read at the moment of deciding."""
        recorder.reset()
        self.win.confirm_restore("it takes the repairs out", lambda _b: None, None)
        dialogs = [c for c in recorder.calls if c[0] == "Adw.AlertDialog"]
        self.assertEqual(1, len(dialogs))
        self.assertEqual("it takes the repairs out", dialogs[0][2].get("body"))

    # --- the modem page ----------------------------------------------------
    #
    # It is built only when modemctl is installed, so every check here says so
    # first. On a phone without the modem package there is no second tab and
    # nothing below has anything to test - which is itself the behaviour that
    # matters most: a tab that always says "not installed" would make a healthy
    # phone look broken.

    def test_without_modemctl_the_page_has_no_controls(self):
        """The tab is there and offers to fetch modemctl; what is not there is
        a switch with nothing behind it."""
        win = self.without_tool("modemctl")
        self.assertEqual([], win.modem_rows)

    def test_the_two_words_the_profile_is_read_by(self):
        """modemctl lives in another package. These two keys are the contract
        between them, and its other half is checked over there, where they are
        printed."""
        found = switcher.Window._keyed("recorded: fixed\nactual:   shipped\n")
        self.assertEqual({"recorded": "fixed", "actual": "shipped"}, found)

    def modem_win(self):
        if not MODEMCTL:
            self.skipTest("no modemctl on this machine, so no modem page")
        return self.win

    def test_a_repaired_modem_reads_as_repaired(self):
        win = self.modem_win()
        win.on_modem_profile(True, "recorded: fixed\nactual:   fixed\n")
        self.assertTrue(win.modem_row.get_active())
        self.assertIn("repairs are in place", win.mrow_profile.subtitle)

    def test_a_try_says_the_next_boot_will_undo_it(self):
        win = self.modem_win()
        win.on_modem_profile(True, "recorded: fixed\nactual:   shipped\n")
        self.assertFalse(win.modem_row.get_active())
        self.assertIn("next boot", win.mrow_profile.subtitle)

    def test_half_repaired_is_not_dressed_up_as_either(self):
        win = self.modem_win()
        win.on_modem_profile(True, "recorded: fixed\nactual:   mixed\n")
        self.assertIn("half repaired", win.mrow_profile.subtitle)

    def test_half_repaired_is_read_although_modemctl_exits_1(self):
        """modemctl profile returns 1 for "mixed", after printing it - as
        its cmd_profile does. The switch that settles it must stay usable."""
        win = self.modem_win()
        win.on_modem_profile(False, "recorded: fixed\nactual:   mixed\n"
                             "  warn  half of the repairs are in place and "
                             "half are not\n")
        self.assertIn("half repaired", win.mrow_profile.subtitle)
        self.assertTrue(win.modem_ok)
        win.set_busy(False)
        self.assertTrue(win.modem_row.sensitive)

    def test_no_profile_lines_at_all_is_no_answer(self):
        win = self.modem_win()
        win.on_modem_profile(False, "pkexec: not found")
        self.assertIn("did not answer", win.mrow_profile.subtitle)
        self.assertFalse(win.modem_row.sensitive)

    def test_the_switch_asks_for_the_rights_it_needs(self):
        win = self.modem_win()
        win.modem_row.active = False
        win.on_modem_switch(win.modem_row, None)
        win.on_modem_off_confirmed(None, "go")
        argv = self.ran[-1][0]
        self.assertIn("pkexec", argv[0])
        self.assertEqual(["set", "shipped"], argv[2:])

    def test_switching_the_repairs_off_asks_first(self):
        """Off takes mobile data away without Wi-Fi - the cost the restore
        button asks about. The switch did it on one tap."""
        win = self.modem_win()
        self.ran.clear()
        win.modem_row.active = False
        win.on_modem_switch(win.modem_row, None)
        self.assertEqual([], self.ran, "nothing before the answer")
        win.on_modem_off_confirmed(None, "cancel")
        self.assertEqual([], self.ran)
        self.assertTrue(win.modem_row.get_active(), "the switch went back")
        win.modem_row.active = True
        win.on_modem_switch(win.modem_row, None)
        self.assertEqual(["set", "fixed"], self.ran[-1][0][2:],
                         "on needs no question")

    def test_modemctl_not_answering_is_said_and_not_guessed(self):
        """A profile row that invents "shipped" when it was told nothing would
        make a repaired phone look untouched."""
        win = self.modem_win()
        win.on_modem_profile(False, "")
        self.assertIn("did not answer", win.mrow_profile.subtitle)
        self.assertFalse(win.modem_row.sensitive,
                         "the switch stayed usable with nothing behind it")

    def test_a_modem_page_with_no_modemctl_answer_stays_unusable(self):
        win = self.modem_win()
        win.on_modem_profile(False, "")
        win.set_busy(True)
        win.set_busy(False)
        self.assertFalse(win.modem_row.sensitive)
        self.assertFalse(win.modem_restore_btn.sensitive,
                         "the restore button came back with nothing behind it")

    # --- which SIM ---------------------------------------------------------
    #
    # "modemctl sim" is the contract: slots, active, recorded, present. Its
    # other half is tests/test-sim-slot.sh in furios_modem_fixes.

    SIM_ONE_CARD = "slots: 2\nactive: 1\nrecorded: 1\npresent: 1\n"
    SIM_TWO_CARDS = "slots: 2\nactive: 1\nrecorded: 1\npresent: 1 2\n"

    def test_one_card_shows_the_row_greyed_and_says_why(self):
        """Wanted on 28.9.: the option must be findable before a second card
        is in - shown, but not usable, with the reason in the subtitle."""
        win = self.modem_win()
        win.busy = False
        win.on_sim_status(True, self.SIM_ONE_CARD)
        self.assertTrue(win.sim_group.visible)
        self.assertFalse(win.sim_ok)
        self.assertFalse(win.sim_row.sensitive)
        self.assertIn("second card", win.sim_row.subtitle)
        win.set_busy(False)
        self.assertFalse(win.sim_row.sensitive, "set_busy made it usable again")

    def test_labels_carry_the_provider_and_the_empty_slot(self):
        self.assertEqual(["SIM 1 · Willkommen", "SIM 2 · no card"],
                         switcher.Window.sim_labels([1], {1: "Willkommen"}))
        self.assertEqual(["SIM 1 · Willkommen", "SIM 2"],
                         switcher.Window.sim_labels([1, 2], {1: "Willkommen", 2: ""}))

    def test_the_names_reach_the_list(self):
        win = self.modem_win()
        win.on_sim_status(True, self.SIM_TWO_CARDS + "name1: Willkommen\nname2: Vodafone\n")
        self.assertEqual(["SIM 1 · Willkommen", "SIM 2 · Vodafone"], win._sim_labels)

    def test_two_cards_show_the_list_on_the_active_slot(self):
        win = self.modem_win()
        win.busy = False
        win.on_sim_status(True, self.SIM_TWO_CARDS.replace("active: 1", "active: 2"))
        self.assertTrue(win.sim_group.visible)
        self.assertEqual(1, win.sim_row.get_selected())
        self.assertIn("one radio", win.sim_row.subtitle)
        self.assertTrue(win.sim_row.sensitive)

    def test_on_slot_two_without_a_card_the_way_back_stays(self):
        """Switched to 2 and the card came out: the row must stay, or there is
        no button left that leads back to slot 1."""
        win = self.modem_win()
        win.busy = False
        win.on_sim_status(True, "slots: 2\nactive: 2\nrecorded: 2\npresent: 1\n")
        self.assertTrue(win.sim_group.visible)
        self.assertTrue(win.sim_row.sensitive)
        self.assertIn("slot 2", win.sim_row.subtitle)

    def test_an_older_modemctl_without_sim_hides_the_row(self):
        win = self.modem_win()
        win.on_sim_status(False, "unknown command: sim\nmodemctl 0.1.0 - ...")
        self.assertFalse(win.sim_group.visible)
        win.set_busy(False)
        self.assertFalse(win.sim_row.sensitive)

    def test_a_one_slot_phone_shows_no_row(self):
        win = self.modem_win()
        win.on_sim_status(True, "slots: 1\nactive: 1\nrecorded: 1\npresent: 1\n")
        self.assertFalse(win.sim_group.visible)

    def test_picking_a_slot_asks_for_rights_and_names_it(self):
        win = self.modem_win()
        win.busy = False
        win.on_sim_status(True, self.SIM_TWO_CARDS)
        win.sim_row.set_selected(1)
        win.on_sim_select(win.sim_row, None)
        argv = self.ran[-1][0]
        self.assertIn("pkexec", argv[0])
        self.assertEqual(["sim", "2"], argv[2:])

    def test_picking_an_empty_slot_runs_nothing_and_snaps_back(self):
        """28.9.: the tray came out and a switch to the empty slot went
        through. The list must not even ask for one."""
        win = self.modem_win()
        win.busy = False
        win.on_sim_status(True, "slots: 2\nactive: 1\nrecorded: 1\npresent: 2\n")
        before = len(self.ran)
        win.sim_row.set_selected(0)
        win.on_sim_select(win.sim_row, None)
        self.assertEqual(before, len(self.ran), "picking the active slot switched")
        win.on_sim_status(True, "slots: 2\nactive: 2\nrecorded: 2\npresent: 1\n")
        win.sim_row.set_selected(1)
        win.on_sim_select(win.sim_row, None)
        self.assertEqual(before, len(self.ran))
        win.on_sim_status(True, "slots: 2\nactive: 1\nrecorded: 1\npresent: 1\n")
        win.sim_ok = True
        win.sim_row.set_selected(1)
        win.on_sim_select(win.sim_row, None)
        self.assertEqual(before, len(self.ran), "switched to a slot with no card")
        self.assertEqual(0, win.sim_row.get_selected())
        self.assertIn("No card in slot 2", str(win.toasts.text))

    # --- 5G ----------------------------------------------------------------
    #
    # "modemctl nr" is the contract: recorded and allowed. Its other half is
    # tests/test-nr.sh in furios_modem_fixes.

    def test_5g_off_shows_the_switch_off_and_usable(self):
        win = self.modem_win()
        win.busy = False
        win.on_nr_status(True, "recorded: off\nallowed: no\n")
        self.assertTrue(win.nr_group.visible)
        self.assertFalse(win.nr_row.get_active())
        self.assertTrue(win.nr_row.sensitive)
        self.assertIn("LTE", win.nr_row.subtitle)

    def test_5g_on_but_taken_away_is_said(self):
        win = self.modem_win()
        win.on_nr_status(True, "recorded: on\nallowed: no\n")
        self.assertTrue(win.nr_row.get_active())
        self.assertIn("does not allow", win.nr_row.subtitle)
        win.on_nr_status(True, "recorded: on\nallowed: yes\n")
        self.assertIn("network offers", win.nr_row.subtitle)

    def test_reading_the_state_switches_nothing(self):
        win = self.modem_win()
        win.busy = False
        before = len(self.ran)
        win.on_nr_status(True, "recorded: on\nallowed: yes\n")
        self.assertEqual(before, len(self.ran), "showing the state ran modemctl nr on")

    def test_an_older_modemctl_without_nr_hides_the_row(self):
        win = self.modem_win()
        win.on_nr_status(False, "unknown command: nr\nmodemctl 0.1.0 - ...")
        self.assertFalse(win.nr_group.visible)
        win.set_busy(False)
        self.assertFalse(win.nr_row.sensitive, "set_busy made it usable again")

    def test_switching_5g_asks_for_rights_and_says_which_way(self):
        win = self.modem_win()
        win.busy = False
        win.on_nr_status(True, "recorded: off\nallowed: no\n")
        win.nr_row.set_active(True)
        win.on_nr_switch(win.nr_row, None)
        argv = self.ran[-1][0]
        self.assertIn("pkexec", argv[0])
        self.assertEqual(["nr", "on"], argv[2:])

    def test_no_card_anywhere_greys_the_list(self):
        win = self.modem_win()
        win.on_sim_status(True, "slots: 2\nactive: 1\nrecorded: 1\npresent: none\n")
        self.assertTrue(win.sim_group.visible)
        self.assertFalse(win.sim_ok)
        self.assertIn("tray", win.sim_row.subtitle)

    def test_syncing_the_list_starts_nothing(self):
        """Reading the state sets the selection; that must not switch."""
        win = self.modem_win()
        win.busy = False
        before = len(self.ran)
        win._syncing = True
        win.on_sim_select(win.sim_row, None)
        win._syncing = False
        self.assertEqual(before, len(self.ran))

    def test_a_refused_sim_switch_is_reported(self):
        win = self.modem_win()
        win.on_sim_switched(False, "  FAIL  a call is in progress - not switching the SIM now")
        self.assertIn("failed", str(win.toasts.text).lower())

    # --- the GPS page ------------------------------------------------------
    #
    # Contributing to beaconDB, and nothing else since the location filter was
    # retired. Tested whether or not the tool is on this phone: the handlers
    # ask self.live for it, and gps_win() says it is there.

    def test_without_the_tool_the_page_has_no_controls(self):
        win = self.without_tool("furios-gps-contribute")
        self.assertEqual([], win.gps_rows)

    def gps_win(self):
        self.win.live["gps"] = "/home/x/.local/bin/furios-gps-contribute"
        self.win.busy = False
        self.win._syncing = False
        return self.win

    def test_the_page_asks_no_filter_anything(self):
        """The filter is retired; a row for it would switch nothing."""
        recorder.reset()
        real = switcher.tools._tool_maybe
        switcher.tools._tool_maybe = lambda n: ("/x/furios-gps-contribute"
                                                if n == "furios-gps-contribute"
                                                else real(n))
        try:
            switcher.Window(switcher.Adw.Application())
        finally:
            switcher.tools._tool_maybe = real
        titles = [str(c[2].get("title", "")) for c in recorder.calls
                  if c[0] in ("Adw.SwitchRow", "Adw.PreferencesGroup")]
        self.assertIn("Contribute to beaconDB", titles)
        self.assertIn("Send my observations", titles)
        self.assertEqual([], [t for t in titles
                              if "Filter" in t or t == "GPS fix"])

    def test_a_contribution_switch_while_busy_is_ignored(self):
        win = self.gps_win()
        win.busy = True
        before = len(self.ran)
        win.on_gps_contrib(win.gps_contrib, None)
        self.assertEqual(before, len(self.ran))

    def test_the_checks_are_counted_the_way_modemctl_prints_them(self):
        win = self.modem_win()
        win.on_modem_status(True,
                            "  ok    utils.py\n"
                            "  ok    mobile default route: ccmni0\n"
                            "  FAIL  resolv.conf -> systemd-resolved\n"
                            "  ok    signal quality 26% (recent)\n")
        self.assertIn("3 OK, 1 failed", win.mrow_health.subtitle)
        self.assertIn("26%", win.mrow_signal.subtitle)

    def test_everything_in_place_is_not_dressed_up_with_a_zero(self):
        win = self.modem_win()
        win.on_modem_status(True, "  ok    utils.py\n  ok    main.py\n")
        self.assertEqual("2 OK", win.mrow_health.subtitle)

    def test_a_status_without_a_signal_line_says_so(self):
        win = self.modem_win()
        win.on_modem_status(True, "  ok    utils.py\n")
        self.assertIn("not readable", win.mrow_signal.subtitle)

    def test_a_status_that_failed_but_printed_is_still_read(self):
        """modemctl exits non-zero when a check fails - and then its output is
        exactly the thing worth showing."""
        win = self.modem_win()
        win.on_modem_status(False, "  ok    utils.py\n  FAIL  mobile default route\n")
        self.assertIn("1 OK, 1 failed", win.mrow_health.subtitle)

    def test_a_status_with_no_output_at_all_claims_nothing(self):
        win = self.modem_win()
        win.on_modem_status(False, "")
        self.assertIn("did not answer", win.mrow_health.subtitle)

    def test_without_pkexec_the_switch_says_so_and_runs_nothing(self):
        win = self.modem_win()
        real = switcher.tools.PKEXEC
        try:
            switcher.tools.PKEXEC = None
            win.modem_row.active = False
            win.on_modem_switch(win.modem_row, None)
            self.assertEqual([], self.ran, "it tried to switch without rights")
            self.assertIn("pkexec", str(win.toasts.text))
        finally:
            switcher.tools.PKEXEC = real

    def test_without_pkexec_the_restore_button_says_so_and_runs_nothing(self):
        win = self.modem_win()
        real = switcher.tools.PKEXEC
        try:
            switcher.tools.PKEXEC = None
            win.on_modem_restore(None)
            self.assertEqual([], self.ran, "it tried to restore without rights")
            self.assertIn("pkexec", str(win.toasts.text))
        finally:
            switcher.tools.PKEXEC = real

    def test_a_finished_switch_says_what_is_on_now(self):
        win = self.modem_win()
        win.on_modem_switched(True, "Recorded: shipped. This survives a reboot.\n\n",
                              "shipped")
        self.assertIn("Shipped state", str(win.toasts.text))

    def test_a_switch_that_printed_nothing_still_says_something(self):
        win = self.modem_win()
        win.on_modem_switched(True, "")
        self.assertIn("Done", str(win.toasts.text))

    def test_a_refused_switch_is_reported_as_a_failure(self):
        """polkit saying no looks like any other failure from here, and on a
        phone where this is not authorised it is the likely one."""
        win = self.modem_win()
        win.on_modem_switched(False, "Error executing command as another user")
        self.assertIn("failed", str(win.toasts.text).lower())

    def test_the_restore_button_asks_for_the_shipped_state_for_good(self):
        """The counterpart to "Restore sound": what it restores has to be what
        the phone comes back to, so "set" and never "try"."""
        win = self.modem_win()
        win.on_modem_restore(None)
        argv = self.ran[-1][0]
        self.assertIn("pkexec", argv[0])
        self.assertEqual(["set", "shipped"], argv[2:])

    def test_restoring_says_what_the_phone_is_now(self):
        win = self.modem_win()
        win.on_modem_restored(True, "")
        self.assertIn("no network without Wi-Fi", str(win.toasts.text))

    def test_a_failed_restore_is_not_reported_as_done(self):
        win = self.modem_win()
        win.on_modem_restored(False, "revert failed")
        self.assertIn("Could not restore", str(win.toasts.text))

    def test_the_restore_button_does_nothing_while_busy(self):
        win = self.modem_win()
        win.busy = True
        win.on_modem_restore(None)
        self.assertEqual([], self.ran)

    def test_switching_on_is_always_remembered(self):
        """No remember row any more: on means on after a reboot too."""
        win = self.modem_win()
        win.modem_row.active = True
        win.on_modem_switch(win.modem_row, None)
        self.assertEqual(["set", "fixed"], self.ran[-1][0][2:])

    def test_the_switch_does_not_fire_while_the_window_is_syncing(self):
        """Filling the switch from the status would otherwise switch the modem."""
        win = self.modem_win()
        win._syncing = True
        win.on_modem_switch(win.modem_row, None)
        win._syncing = False
        self.assertEqual([], self.ran)

    def test_busy_says_what_is_happening_and_locks_the_controls(self):
        self.win.set_busy(True)
        self.assertFalse(self.win.switch_row.sensitive)
        self.assertIn("a change is running", self.win.switch_row.subtitle)
        self.win.switch_row.selected = 1
        self.win.set_busy(False)
        self.assertTrue(self.win.switch_row.sensitive)
        # The owner's description (29.9.) once it is done, whichever server.
        self.assertIn("main service", self.win.switch_row.subtitle)
        self.win.switch_row.selected = 0
        self.win.set_busy(False)
        self.assertIn("main service", self.win.switch_row.subtitle)

    def test_an_audio_status_does_not_hand_back_controls_mid_switch(self):
        """Every refresh ends in on_status, and refreshes overlap other work -
        the one from start-up, the one after a battery change. It used to
        release busy, which made a running modem switch or install tappable
        again half way through."""
        self.win.set_busy(True)
        self.win.on_status(True, self.PERMANENT)
        self.assertTrue(self.win.busy)
        self.assertFalse(self.win.switch_row.sensitive)
        self.win.on_status(False, "")
        self.assertTrue(self.win.busy)

    def test_every_finished_action_releases_the_window_itself(self):
        """Not through audioctl's answer: on a phone without audioctl that
        answer never comes, and one modem switch left every control grey
        until the app was restarted."""
        handlers = ["on_switched", "on_dmnr_done", "on_rescued"]
        if MODEMCTL:
            handlers += ["on_modem_switched", "on_modem_restored"]
        handlers += ["on_gps_contrib_done", "on_gps_restored"]
        if KILLSWITCH:
            handlers.append("on_switches_restored")
        if BATTCTL:
            handlers.append("on_battery_restored")
        self.win.live["audio"] = None
        for name in handlers:
            for ok in (True, False):
                with self.subTest(handler=name, ok=ok):
                    self.win.set_busy(True)
                    getattr(self.win, name)(ok, "")
                    self.assertFalse(self.win.busy)

    def test_the_progress_bar_pulses_rather_than_inventing_a_percentage(self):
        self.win.pulse_start("Switching …")
        self.assertEqual("Switching …", self.win.progress.text)
        self.assertEqual("pulsing", self.win.progress.fraction)
        self.assertTrue(self.win.progress_revealer.revealed)
        self.assertTrue(self.win._pulse_tick())
        self.win.pulse_stop()
        self.assertFalse(self.win.progress_revealer.revealed)

    def test_the_application_opens_a_window(self):
        """Starting up, which is all there is to it now.

        This used to put a polkit authentication agent in place, because a
        switch needed root and phosh registers none of its own. audioctl keeps
        the profile under $HOME these days, so starting the app authenticates
        nothing and asks for nothing. A password appears on one path only -
        installing a tool - and Askpass is what tests it.

        No assertion: what is checked is that this raises nothing. A window
        that cannot be built throws here, which is the whole of the question.
        """
        app = switcher.App()
        app.props.active_window = None
        app.do_activate()



class OffersTheFolderDock(unittest.TestCase):
    """The folder dock has no tab of its own: the Phosh tab offers it in the
    rows it brings to life. Found on 30.9.2026, on a phone freshly set up
    from the app - three switches grey, and nothing on the page to change
    that."""

    def window(self, plugin):
        self.enterContext(mock.patch.object(switcher.pages.other,
                                            "folder_dock_plugin",
                                            lambda: plugin))
        self.enterContext(mock.patch.dict(switcher.PHOSH,
                                          {"find": lambda: plugin}))
        return switcher.Window(switcher.Adw.Application())

    def test_without_the_plugin_the_tab_offers_it(self):
        win = self.window(None)
        rows = win.comp_rows.get(switcher.PHOSH["tool"])
        self.assertIsNotNone(rows, "no offer on the Phosh tab")
        self.assertIs(win.dock_row, rows["state"])
        self.assertIsNone(win.live["phosh"])

    def test_with_the_plugin_there_is_no_offer(self):
        win = self.window("/usr/lib/x/phosh/plugins/furios-folder-dock.plugin")
        self.assertNotIn(switcher.PHOSH["tool"], win.comp_rows)
        self.assertTrue(win.live["phosh"])

    def test_the_offer_asks_for_the_password(self):
        """make install writes to phosh's plugin directory, the guard to /etc."""
        win = self.window(None)
        recorder.reset()
        win.ask_component(switcher.PHOSH, "install")
        self.assertTrue([c for c in recorder.calls
                         if c[0] == "Adw.PasswordEntryRow"])

    def test_the_installer_is_the_folder_docks_and_runs_as_the_user(self):
        steps = switcher.component_steps(switcher.PHOSH, "install", "pw")
        installer = [(argv, cwd) for argv, _s, cwd, _e in steps
                     if argv[0].endswith("install.sh")]
        self.assertEqual([(["./install.sh"], os.path.join(
            switcher.clone_path(switcher.PHOSH), "folder-dock"))], installer)
        self.assertIn(["sudo", "-S", "-p", "", "-v"],
                      [argv for argv, _s, _c, _e in steps])

    def test_an_install_that_worked_brings_the_rows_to_life(self):
        plugin = []
        self.enterContext(mock.patch.object(
            switcher.pages.other, "folder_dock_plugin",
            lambda: plugin[0] if plugin else None))
        self.enterContext(mock.patch.dict(
            switcher.PHOSH, {"find": lambda: plugin[0] if plugin else None}))
        said = []
        self.enterContext(mock.patch.object(switcher.Window, "toast",
                                            lambda self, text: said.append(text)))
        win = switcher.Window(switcher.Adw.Application())
        before = win.pages["other"]
        plugin.append("/usr/lib/x/phosh/plugins/furios-folder-dock.plugin")
        win.component_done(switcher.PHOSH, True, "")
        self.assertIsNot(before, win.pages["other"], "the tab was not rebuilt")
        self.assertNotIn(switcher.PHOSH["tool"], win.comp_rows)
        self.assertTrue(win.live["phosh"])
        self.assertIn("next reboot", said[-1])

    def test_an_install_that_left_nothing_says_so(self):
        win = self.window(None)
        said = []
        self.enterContext(mock.patch.object(switcher.Window, "toast",
                                            lambda self, text: said.append(text)))
        self.enterContext(mock.patch.object(switcher.Window, "report",
                                            lambda self, text: None))
        before = win.pages["other"]
        win.component_done(switcher.PHOSH, True, "")
        self.assertIs(before, win.pages["other"])
        self.assertIn("not on the phone", said[-1])


class AsksForPackagesFirst(unittest.TestCase):
    """An installer is not started while a package it needs is missing: a
    list and the apt line instead of a build that dies half-way."""

    def test_dpkg_says_which_are_installed(self):
        out = ("git install ok installed\n"
               "gcc:arm64 install ok installed\n"
               "phosh-dev deinstall ok config-files\n")
        self.assertEqual({"git", "gcc"},
                         switcher.components.installed_packages(out))

    def test_what_dpkg_does_not_know_is_missing(self):
        """dpkg-query exits 1 for an unknown name and still prints the rest -
        so the output decides, not the exit code."""
        done = subprocess_real.CompletedProcess(
            [], 1, stdout="git install ok installed\n", stderr="no packages")
        with mock.patch.object(switcher.components.subprocess, "run",
                               lambda *a, **k: done):
            self.assertEqual(["phosh-dev"], REAL_MISSING_PACKAGES(
                {"packages": ["phosh-dev"]}))

    def test_git_is_needed_by_every_one(self):
        for comp in switcher.COMPONENTS + [switcher.PHOSH]:
            self.assertEqual("git", switcher.components.packages_needed(comp)[0])

    def test_no_dpkg_means_nothing_is_claimed_missing(self):
        def fails(*a, **k):
            raise OSError("no dpkg-query")
        with mock.patch.object(switcher.components.subprocess, "run", fails):
            self.assertEqual([], REAL_MISSING_PACKAGES(switcher.PHOSH))

    def window_missing(self, missing):
        self.enterContext(mock.patch.object(
            switcher.components, "missing_packages", lambda comp: missing))
        return switcher.Window(switcher.Adw.Application())

    def test_a_missing_package_stops_the_install_before_anything_runs(self):
        win = self.window_missing(["phosh-dev", "libgtk-3-dev"])
        recorder.reset()
        started = []
        self.enterContext(mock.patch.object(
            switcher.Window, "run_component",
            lambda self, *a: started.append(a)))
        win.ask_component(switcher.PHOSH, "install")
        self.assertEqual([], [c for c in recorder.calls
                              if c[0] == "Adw.PasswordEntryRow"])
        self.assertEqual([], started)
        missing, command = win.missing_shown
        self.assertEqual(["phosh-dev", "libgtk-3-dev"], missing)
        self.assertEqual("sudo apt install phosh-dev libgtk-3-dev", command)

    def test_updates_are_held_back_too(self):
        win = self.window_missing(["gcc"])
        win.busy = False
        win.updates = {"secctl": {"comp": self_comp("secctl"), "words": "",
                                  "path": "/x", "mode": "update"}}
        recorder.reset()
        win.ask_updates()
        self.assertEqual([], [c for c in recorder.calls
                              if c[0] == "Adw.PasswordEntryRow"])
        self.assertEqual("sudo apt install gcc", win.missing_shown[1])

    def test_every_package_an_installer_names_is_in_the_list(self):
        """Read from the installers, not from what the table believes: a
        package one of them asks for and the app does not check would be
        the old failure again - a dialog full of make output."""
        homes = [os.path.expanduser("~/Projekte"),
                 os.path.expanduser("~/Projekte/.dev"),
                 os.path.expanduser("~/.local/share/misc-de")]
        seen = 0
        for comp in switcher.COMPONENTS + [switcher.PHOSH]:
            for home in homes:
                top = os.path.join(home, comp["dir"], comp.get("sub", ""))
                script = os.path.join(top, "install.sh")
                if not os.path.isfile(script):
                    continue
                seen += 1
                texts = [Path(script).read_text()]
                texts += [p.read_text() for p in Path(top).glob("tools/*/build.sh")]
                named = set()
                for text in texts:
                    for m in re.finditer(r"apt install ([\w.+ -]+?)(?:\)|\"|$| or)",
                                         text, re.M):
                        named.update(m.group(1).split())
                    named.update(re.findall(r"\(Paket ([\w.+-]+)\)", text))
                    named.update(re.findall(r'missing\+=\("([a-z0-9][\w.+-]+)"\)',
                                            text))
                self.assertEqual(set(), named - set(
                    switcher.components.packages_needed(comp)), comp["tool"])
                break
        if not seen:
            self.skipTest("no clone of any installer on this machine")


def self_comp(tool):
    return next(c for c in switcher.COMPONENTS if c["tool"] == tool)


class HidesTheSearchField(unittest.TestCase):
    """The Other page's one switch, against a gtk.css of its own."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.css = os.path.join(self.dir, "gtk-3.0", "gtk.css")
        self.other = switcher.pages.other

    def write(self, text):
        os.makedirs(os.path.dirname(self.css), exist_ok=True)
        Path(self.css).write_text(text)

    def test_on_and_off_leave_somebodys_own_rules_alone(self):
        own = "window { color: red; }\n"
        self.write(own)
        self.other.set_search_hidden(True, self.css)
        self.assertTrue(self.other.search_hidden(self.css))
        self.assertTrue(Path(self.css).read_text().startswith(own))
        self.other.set_search_hidden(False, self.css)
        self.assertFalse(self.other.search_hidden(self.css))
        self.assertEqual(own, Path(self.css).read_text())

    def test_switching_on_twice_writes_one_block(self):
        self.other.set_search_hidden(True, self.css)
        self.other.set_search_hidden(True, self.css)
        self.assertEqual(1, Path(self.css).read_text().count(self.other.BEGIN))

    def test_a_file_holding_only_our_block_goes_away(self):
        self.other.set_search_hidden(True, self.css)
        self.other.set_search_hidden(False, self.css)
        self.assertFalse(os.path.exists(self.css))

    def test_off_on_a_missing_file_creates_nothing(self):
        self.other.set_search_hidden(False, self.css)
        self.assertFalse(os.path.exists(self.css))

    def test_the_hand_written_rule_counts_and_is_removed(self):
        """Written before the switch existed: a header and no end marker."""
        self.write("/* Hide phosh app grid search (misc-de) */\n"
                   ".phosh-search-bar-box,\n.phosh-search-bar {\n"
                   "  opacity: 0;\n}\n")
        self.assertTrue(self.other.search_hidden(self.css))
        self.other.set_search_hidden(False, self.css)
        self.assertFalse(os.path.exists(self.css))

    def test_the_switch_writes_and_a_failure_puts_it_back(self):
        win = switcher.Window(switcher.Adw.Application())
        # On the class: the stub keeps instance attributes in a dict of its
        # own, so one set on win never shadows the method.
        said = []
        self.enterContext(mock.patch.object(switcher.Window, "toast",
                                            lambda self, text: None))
        self.enterContext(mock.patch.object(switcher.Window, "report",
                                            lambda self, text: said.append(text)))
        row = Recording()
        row.set_active(True)
        win._loading = False
        path = self.other.gtk_css_path()
        win.on_search_hidden(row, None)
        self.assertTrue(self.other.search_hidden(path))
        row.set_active(False)
        win.on_search_hidden(row, None)
        self.assertFalse(self.other.search_hidden(path))
        with mock.patch.object(self.other, "set_search_hidden",
                               side_effect=PermissionError("denied")):
            row.set_active(True)
            win.on_search_hidden(row, None)
        self.assertFalse(row.get_active())
        self.assertTrue(said)


class FixesTheKeyringPrompt(unittest.TestCase):
    """The service file and the shim, in a directory of their own."""

    def setUp(self):
        d = tempfile.mkdtemp()
        self.service = os.path.join(d, "share", "dbus-1", "services",
                                    "p.service")
        self.shim = os.path.join(d, "libexec", "keyring-prompter-wait")
        self.other = switcher.pages.other

    def test_on_writes_both_and_off_removes_both(self):
        self.other.set_prompter_fixed(True, self.service, self.shim)
        self.assertTrue(self.other.prompter_fixed(self.service, self.shim))
        self.assertIn("Exec=%s\n" % self.shim, Path(self.service).read_text())
        self.assertTrue(os.access(self.shim, os.X_OK))
        self.other.set_prompter_fixed(False, self.service, self.shim)
        self.assertFalse(self.other.prompter_fixed(self.service, self.shim))
        self.assertFalse(os.path.exists(self.service))
        self.assertFalse(os.path.exists(self.shim))

    def test_the_hand_made_fix_counts_and_is_removed(self):
        os.makedirs(os.path.dirname(self.shim))
        Path(self.shim).write_text(
            "#!/bin/sh\n" + self.other.PROMPTER_LEGACY + "\nexit 0\n")
        os.makedirs(os.path.dirname(self.service))
        Path(self.service).write_text(
            "[D-BUS Service]\nName=x\nExec=%s\n" % self.shim)
        self.assertTrue(self.other.prompter_fixed(self.service, self.shim))
        self.other.set_prompter_fixed(False, self.service, self.shim)
        self.assertFalse(os.path.exists(self.service))
        self.assertFalse(os.path.exists(self.shim))

    def test_somebody_elses_service_file_is_left_alone(self):
        os.makedirs(os.path.dirname(self.service))
        Path(self.service).write_text("[D-BUS Service]\nExec=/usr/bin/other\n")
        self.assertFalse(self.other.prompter_fixed(self.service, self.shim))
        self.other.set_prompter_fixed(False, self.service, self.shim)
        self.assertTrue(os.path.exists(self.service))

    def test_the_default_paths_stay_out_of_the_real_home(self):
        home = os.path.dirname(os.environ["XDG_DATA_HOME"])
        self.assertTrue(self.other.prompter_service_path().startswith(home))
        self.assertTrue(self.other.prompter_shim_path().startswith(home))

    def test_the_switch_writes_and_a_failure_puts_it_back(self):
        win = switcher.Window(switcher.Adw.Application())
        said = []
        self.enterContext(mock.patch.object(switcher.Window, "report",
                                            lambda self, text: said.append(text)))
        row = Recording()
        row.set_active(True)
        win._loading = False
        win.on_prompter_fixed(row, None)
        self.assertTrue(self.other.prompter_fixed())
        row.set_active(False)
        win.on_prompter_fixed(row, None)
        self.assertFalse(self.other.prompter_fixed())
        with mock.patch.object(self.other, "set_prompter_fixed",
                               side_effect=PermissionError("denied")):
            row.set_active(True)
            win.on_prompter_fixed(row, None)
        self.assertFalse(row.get_active())
        self.assertTrue(said)


class FixesThePortalWait(unittest.TestCase):
    """Our phosh-portals.conf in the user's config dir: the shipped one with
    the two wlr keys at none, and only ever ours to write or remove."""

    SHIPPED = ("[preferred]\n"
               "default=phosh;gtk;\n"
               "org.freedesktop.impl.portal.ScreenCast=wlr;\n"
               "org.freedesktop.impl.portal.Screenshot=gtk;wlr;\n"
               "org.freedesktop.impl.portal.Secret=gnome-keyring;\n")

    def setUp(self):
        d = tempfile.mkdtemp()
        self.path = os.path.join(d, "config", "xdg-desktop-portal",
                                 "phosh-portals.conf")
        self.shipped = os.path.join(d, "shipped.conf")
        Path(self.shipped).write_text(self.SHIPPED)
        self.other = switcher.pages.other

    def test_on_is_the_shipped_file_with_wlr_gone(self):
        self.other.set_portals_fixed(True, self.path, self.shipped)
        self.assertTrue(self.other.portals_fixed(self.path))
        text = Path(self.path).read_text()
        self.assertFalse([l for l in text.splitlines()
                          if "wlr" in l and not l.startswith("#")])
        self.assertIn("org.freedesktop.impl.portal.ScreenCast=none;\n", text)
        self.assertIn("org.freedesktop.impl.portal.Screenshot=none;\n", text)
        # Everything else as FuriOS ships it.
        self.assertIn("default=phosh;gtk;\n", text)
        self.assertIn("Secret=gnome-keyring;\n", text)

    def test_off_leaves_nothing(self):
        self.other.set_portals_fixed(True, self.path, self.shipped)
        self.other.set_portals_fixed(False, self.path, self.shipped)
        self.assertFalse(self.other.portals_fixed(self.path))
        self.assertFalse(os.path.exists(self.path))
        self.assertFalse(os.path.exists(os.path.dirname(self.path)))

    def test_keys_a_later_furios_dropped_are_still_set(self):
        Path(self.shipped).write_text("[preferred]\ndefault=phosh;gtk;\n")
        self.other.set_portals_fixed(True, self.path, self.shipped)
        text = Path(self.path).read_text()
        self.assertIn("[preferred]\norg.freedesktop.impl.portal.ScreenCast=none;", text)
        self.assertIn("org.freedesktop.impl.portal.Screenshot=none;", text)

    def test_somebody_elses_file_is_left_alone(self):
        os.makedirs(os.path.dirname(self.path))
        Path(self.path).write_text("[preferred]\ndefault=gtk;\n")
        self.assertFalse(self.other.portals_fixed(self.path))
        for on in (True, False):
            with self.assertRaises(OSError):
                self.other.set_portals_fixed(on, self.path, self.shipped)
        self.assertEqual("[preferred]\ndefault=gtk;\n",
                         Path(self.path).read_text())

    def test_the_default_path_stays_out_of_the_real_home(self):
        self.assertTrue(self.other.portals_path().startswith(
            os.environ["XDG_CONFIG_HOME"]))

    def test_the_switch_writes_and_a_failure_puts_it_back(self):
        win = switcher.Window(switcher.Adw.Application())
        said = []
        self.enterContext(mock.patch.object(switcher.Window, "report",
                                            lambda self, text: said.append(text)))
        self.enterContext(mock.patch.object(self.other, "PORTALS_SHIPPED",
                                            self.shipped))
        row = Recording()
        row.set_active(True)
        win._loading = False
        win.on_portals_fixed(row, None)
        self.assertTrue(self.other.portals_fixed())
        row.set_active(False)
        win.on_portals_fixed(row, None)
        self.assertFalse(self.other.portals_fixed())
        with mock.patch.object(self.other, "set_portals_fixed",
                               side_effect=PermissionError("denied")):
            row.set_active(True)
            win.on_portals_fixed(row, None)
        self.assertFalse(row.get_active())
        self.assertTrue(said)


class FakeAmbient:
    """gsd's ambient-enabled, unset (the default applies) or set."""

    def __init__(self, user=None, default=False):
        self.user, self.default = user, default

    def get_boolean(self, key):
        assert key == "ambient-enabled"
        return self.default if self.user is None else self.user

    def get_user_value(self, key):
        return None if self.user is None else types.SimpleNamespace(
            unpack=lambda: self.user)

    def set_boolean(self, key, value):
        assert key == "ambient-enabled"
        self.user = value

    def reset(self, key):
        self.user = None


class AutoBrightness(unittest.TestCase):
    """The light sensor service FuriOS ships disabled, and gsd's key - the
    switch is on only while both are, and off puts back what was there."""

    def setUp(self):
        forget_all_records()
        self.other = switcher.pages.other

    def test_on_only_with_both_halves(self):
        on = FakeAmbient(True)
        self.assertTrue(self.other.brightness_on(on, (True, True)))
        self.assertFalse(self.other.brightness_on(on, (False, False)))
        self.assertFalse(self.other.brightness_on(FakeAmbient(), (True, True)))
        self.assertFalse(self.other.brightness_on(None, (True, True)))

    def test_on_enables_and_starts_through_sudo(self):
        argv = self.other.sensor_argv(True, (False, False))
        self.assertEqual(["sudo", "-n", "systemctl", "enable", "--now",
                          "iio-sensor-proxy.service"], argv)

    def test_nothing_to_ask_when_the_unit_is_there_already(self):
        self.assertIsNone(self.other.sensor_argv(True, (True, True)))

    def test_off_goes_back_to_the_record(self):
        shipped = {"enabled": False, "active": False}
        self.assertEqual(["sudo", "-n", "systemctl", "disable", "--now",
                          "iio-sensor-proxy.service"],
                         self.other.sensor_argv(False, (True, True), shipped))
        # Enabled before the switch was first touched: stays enabled.
        self.assertIsNone(self.other.sensor_argv(
            False, (True, True), {"enabled": True, "active": True}))
        # No record: no guess either, the unit stays as it is.
        self.assertIsNone(self.other.sensor_argv(False, (True, True)))

    def test_the_password_is_never_an_argument(self):
        argv = self.other.sensor_argv(True, (False, False), None, "hunter2")
        self.assertEqual(argv[:4], ["sudo", "-S", "-p", ""])
        self.assertNotIn("hunter2", argv)

    def test_an_unset_key_is_reset_not_pinned(self):
        settings = FakeAmbient()
        self.other.remember_brightness(settings, (False, False))
        record = original.load(self.other.BRIGHTNESS_IDENT)
        self.assertIsNone(record["user_value"])
        self.other.set_ambient(True, settings, record)
        self.assertTrue(settings.user)
        self.other.set_ambient(False, settings, record)
        self.assertIsNone(settings.user)

    def test_the_first_original_is_the_one_that_counts(self):
        self.other.remember_brightness(FakeAmbient(False), (False, False))
        self.other.remember_brightness(FakeAmbient(True), (True, True))
        record = original.load(self.other.BRIGHTNESS_IDENT)
        self.assertIs(record["user_value"], False)
        self.assertFalse(record["enabled"])

    def window(self, settings, state, results):
        win = switcher.Window(switcher.Adw.Application())
        win.brightness_settings = settings
        win.brightness_row = Recording()
        ran = []

        def run_async(argv, done, stdin=None, **_kw):
            ran.append((argv, stdin))
            ok, out = results.pop(0)
            if ok:
                state[:] = [not any("disable" in a for a in argv)] * 2
            done(ok, out)

        self.enterContext(mock.patch.object(self.other, "sensor_state",
                                            lambda: tuple(state)))
        self.enterContext(mock.patch.object(switcher.process, "run_async",
                                            run_async))
        return win, ran

    def test_the_switch_round_trip_ends_where_it_began(self):
        settings, state = FakeAmbient(), [False, False]
        win, ran = self.window(settings, state, [(True, ""), (True, "")])
        win._loading = False
        win.apply_brightness(True)
        self.assertTrue(win.brightness_row.get_active())
        self.assertTrue(settings.user)
        win.apply_brightness(False)
        self.assertFalse(win.brightness_row.get_active())
        self.assertEqual([False, False], state)
        self.assertIsNone(settings.user)
        self.assertIsNone(original.load(self.other.BRIGHTNESS_IDENT))
        self.assertEqual(2, len(ran))

    def test_a_wanted_password_asks_and_leaves_the_key_alone(self):
        settings, state = FakeAmbient(), [False, False]
        win, ran = self.window(settings, state,
                               [(False, "sudo: a password is required")])
        asked = []
        self.enterContext(mock.patch.object(
            switcher.Window, "ask_brightness_password",
            lambda self, wanted: asked.append(wanted)))
        win._loading = False
        win.apply_brightness(True)
        self.assertEqual([True], asked)
        self.assertIsNone(settings.user)


class IgnoresTheNetworkSwitch(unittest.TestCase):
    """furios-switch-mask from the Switches tab: a system unit, through sudo."""

    def setUp(self):
        self.sw = importlib.import_module("miscde.pages.switches")

    def test_on_and_off_are_enable_and_disable_now(self):
        self.assertEqual(["sudo", "-n", "systemctl", "enable", "--now",
                          "furios-switch-mask.service"], self.sw.nwk_mask_argv(True))
        self.assertEqual("disable", self.sw.nwk_mask_argv(False)[3])

    def test_the_password_is_never_an_argument(self):
        argv = self.sw.nwk_mask_argv(True, "hunter2")
        self.assertEqual(argv[:4], ["sudo", "-S", "-p", ""])
        self.assertNotIn("hunter2", argv)

    def window(self, installed, enabled, results):
        win = switcher.Window(switcher.Adw.Application())
        win.sw_nwk_mask = Recording()
        state = {"enabled": enabled}
        ran = []

        def run_async(argv, done, stdin=None, **_kw):
            ran.append((argv, stdin))
            ok, out = results.pop(0)
            if ok:
                state["enabled"] = "enable" in argv
            done(ok, out)

        self.enterContext(mock.patch.object(self.sw, "nwk_mask_installed",
                                            lambda: installed))
        self.enterContext(mock.patch.object(self.sw, "nwk_mask_enabled",
                                            lambda: state["enabled"]))
        self.enterContext(mock.patch.object(switcher.process, "run_async",
                                            run_async))
        return win, ran

    def test_ignoring_the_sliders_asks_first_and_says_what_it_costs(self):
        """It weakens privacy: the camera slider stops protecting. One tap
        used to do it, with nothing on the row to say so."""
        win, ran = self.window(True, False, [(True, "")])
        win._loading = False
        win.sw_nwk_mask.set_active(True)
        win.on_nwk_mask(win.sw_nwk_mask, None)
        self.assertEqual([], ran, "nothing changed before the answer")
        win.on_nwk_mask_confirmed(None, "cancel")
        self.assertFalse(win.sw_nwk_mask.get_active())
        self.assertEqual([], ran)
        win.sw_nwk_mask.set_active(True)
        win.on_nwk_mask_confirmed(None, "go")
        self.assertEqual("enable", ran[0][0][3])
        self.assertIn("do nothing", win.sw_nwk_mask.subtitle)

    def test_switching_the_sliders_back_on_needs_no_question(self):
        win, ran = self.window(True, True, [(True, "")])
        win._loading = False
        win.sw_nwk_mask.set_active(False)
        win.on_nwk_mask(win.sw_nwk_mask, None)
        self.assertEqual("disable", ran[0][0][3])

    def test_without_the_unit_the_row_is_closed(self):
        win, _ran = self.window(False, False, [])
        win.sync_nwk_mask()
        self.assertFalse(win.sw_nwk_mask.sensitive)
        self.assertFalse(win.sw_nwk_mask.get_active())

    def test_the_row_follows_systemd_not_the_finger(self):
        win, ran = self.window(True, False, [(True, ""), (False, "boom")])
        said = []
        self.enterContext(mock.patch.object(switcher.Window, "report",
                                            lambda self, text: said.append(text)))
        win._loading = False
        win.apply_nwk_mask(True)
        self.assertTrue(win.sw_nwk_mask.get_active())
        win.apply_nwk_mask(False)
        # disable failed: still enabled, and said
        self.assertTrue(win.sw_nwk_mask.get_active())
        self.assertEqual(["boom"], said)

    def test_a_wanted_password_asks(self):
        win, _ran = self.window(True, False,
                                [(False, "sudo: a password is required")])
        asked = []
        self.enterContext(mock.patch.object(
            switcher.Window, "ask_nwk_mask_password",
            lambda self, wanted, then=None: asked.append(wanted)))
        win.apply_nwk_mask(True)
        self.assertEqual([True], asked)


class FakeFeedbackdSettings:
    """feedbackd's theme key: unset ("default") until something sets it."""

    def __init__(self, user=None):
        self.user = user

    def get_string(self, key):
        assert key == "theme"
        return self.user if self.user is not None else "default"

    def set_string(self, key, value):
        assert key == "theme"
        self.user = value

    def reset(self, key):
        assert key == "theme"
        self.user = None

    def get_user_value(self, key):
        assert key == "theme"
        if self.user is None:
            return None

        class V:
            def __init__(self, v):
                self.v = v

            def get_string(self):
                return self.v
        return V(self.user)


class TheVibrationTheme(unittest.TestCase):
    """The Vibration tab: a feedbackd theme of ours with only what changed,
    and everything back as it was once nothing is changed any more."""

    def setUp(self):
        self.v = switcher.pages.vibration
        self.v.reload_feedbackd = lambda: None
        # Never this phone's multiplier: whether somebody moved it aside in
        # the real app must not decide what a test writes.
        self.mult = tempfile.mkdtemp()
        self.v.MULTIPLIER = os.path.join(self.mult, "vibrator-sysfs-multiplier")
        self.v.MULTIPLIER_ASIDE = self.v.MULTIPLIER + ".misc-de-off"
        with open(self.v.MULTIPLIER, "w") as f:
            f.write("10\n")
        forget_all_records()
        try:
            os.remove(self.v.theme_path())
        except FileNotFoundError:
            pass

    def test_nothing_is_written_until_something_changes(self):
        s = FakeFeedbackdSettings()
        self.assertEqual("off", self.v.apply({"message-new-sms": "default"}, s))
        self.assertFalse(os.path.exists(self.v.theme_path()))
        self.assertIsNone(s.user)

    def test_a_choice_writes_a_minimal_theme_and_selects_it(self):
        s = FakeFeedbackdSettings()
        self.assertEqual("on", self.v.apply({"message-new-sms": "double",
                                             "phone-incoming-call": "default"}, s))
        with open(self.v.theme_path()) as f:
            theme = json.load(f)
        self.assertEqual("default", theme["parent-name"])
        self.assertEqual(["quiet"], [p["name"] for p in theme["profiles"]])
        self.assertEqual(["message-new-sms"],
                         [f["event-name"] for f in theme["profiles"][0]["feedbacks"]])
        self.assertEqual("misc-de", s.user)
        self.assertEqual({"message-new-sms": "double"}, self.v.read_choices())

    def test_off_is_a_pause_not_a_rumble(self):
        self.v.apply({"key-pressed": "off"}, FakeFeedbackdSettings())
        fb = json.load(open(self.v.theme_path()))["profiles"][0]["feedbacks"][0]
        self.assertEqual([0.0], fb["magnitudes"])

    def test_all_back_to_standard_puts_back_what_was_there(self):
        s = FakeFeedbackdSettings(user="strict")
        self.v.apply({"message-new-sms": "long"}, s)
        self.assertEqual("misc-de", s.user)
        self.assertEqual("off", self.v.apply({"message-new-sms": "default"}, s))
        self.assertEqual("strict", s.user)
        self.assertFalse(os.path.exists(self.v.theme_path()))

    def test_unset_before_is_unset_after(self):
        s = FakeFeedbackdSettings()
        self.v.apply({"message-new-sms": "long"}, s)
        self.v.apply({}, s)
        self.assertIsNone(s.user)

    def test_a_hand_written_entry_is_kept(self):
        os.makedirs(os.path.dirname(self.v.theme_path()), exist_ok=True)
        with open(self.v.theme_path(), "w") as f:
            json.dump({"name": "misc-de", "parent-name": "default", "profiles": [
                {"name": "quiet", "feedbacks": [
                    {"event-name": "message-new-sms", "type": "VibraRumble",
                     "duration": 333}]}]}, f)
        self.assertEqual({"message-new-sms": "custom"}, self.v.read_choices())
        self.v.apply({"message-new-email": "short"}, FakeFeedbackdSettings())
        fbs = json.load(open(self.v.theme_path()))["profiles"][0]["feedbacks"]
        self.assertIn({"event-name": "message-new-sms", "type": "VibraRumble",
                       "duration": 333}, fbs)

    def test_every_pattern_is_valid_for_feedbackd(self):
        for pid, _title, fb in self.v.PATTERNS:
            if fb is None:
                continue
            with self.subTest(pid=pid):
                self.assertEqual(len(fb["magnitudes"]), len(fb["durations"]))
                self.assertTrue(all(0.0 <= m <= 1.0 for m in fb["magnitudes"]))
                self.assertTrue(all(isinstance(d, int) and d > 0 for d in fb["durations"]))

    def test_the_default_feedbacks_play_as_steps(self):
        self.assertEqual({"magnitudes": [1.0, 0.0, 1.0], "durations": [150, 100, 150]},
                         self.v._as_pattern({"type": "VibraRumble", "duration": 500,
                                             "count": 2, "pause": 100}))
        self.assertEqual({"magnitudes": [1.0], "durations": [1000]},
                         self.v._as_pattern({"type": "VibraPeriodic", "duration": 1000}))

    def test_with_the_multiplier_aside_short_defaults_get_a_firm_tap(self):
        text = self.v.theme_text({"message-new-sms": "double"}, exact=True)
        fbs = {f["event-name"]: f for f in json.loads(text)["profiles"][0]["feedbacks"]}
        self.assertEqual([50], fbs["key-pressed"]["durations"])
        self.assertEqual([0.0], fbs["key-released"]["magnitudes"])
        self.assertEqual([50], fbs["button-pressed"]["durations"])
        self.assertEqual([40], fbs["window-close"]["durations"])

    def test_a_chosen_keyboard_pattern_wins_over_the_tap(self):
        text = self.v.theme_text({"key-pressed": "off"}, exact=True)
        fbs = {f["event-name"]: f for f in json.loads(text)["profiles"][0]["feedbacks"]}
        self.assertEqual([0.0], fbs["key-pressed"]["magnitudes"])

    def test_no_stand_ins_while_the_multiplier_is_in_place(self):
        text = self.v.theme_text({"message-new-sms": "double"}, exact=False)
        events = [f["event-name"] for f in json.loads(text)["profiles"][0]["feedbacks"]]
        self.assertEqual(["message-new-sms"], events)

    def test_stand_ins_are_not_read_as_hand_written(self):
        self.v.apply({"message-new-sms": "double"}, FakeFeedbackdSettings(), exact=True)
        self.assertEqual([], self.v.foreign_entries())
        s = FakeFeedbackdSettings(user="misc-de")
        self.v.apply({}, s, exact=True)
        self.v.apply({}, s, exact=False)
        self.assertFalse(os.path.exists(self.v.theme_path()))

    def test_standard_everywhere_keeps_the_taps_until_the_multiplier_is_back(self):
        """The theme came off before the sudo that puts the multiplier back -
        and with that password cancelled, FuriOS's 7-25 ms key and button
        taps stayed unmultiplied: too short to feel."""
        s = FakeFeedbackdSettings()
        self.v.apply({"message-new-sms": "double"}, s, exact=True)
        self.assertEqual("off", self.v.apply({"message-new-sms": "default"}, s,
                                             exact=True),
                         "off: the multiplier is wanted back")
        fbs = {f["event-name"]: f for f in
               json.load(open(self.v.theme_path()))["profiles"][0]["feedbacks"]}
        self.assertEqual([50], fbs["key-pressed"]["durations"])
        self.assertNotIn("message-new-sms", fbs)
        self.assertEqual("misc-de", s.user, "still the theme feedbackd plays")
        self.assertEqual("off", self.v.apply({"message-new-sms": "default"}, s,
                                             exact=False))
        self.assertFalse(os.path.exists(self.v.theme_path()))
        self.assertIsNone(s.user)

    def test_the_keyboard_stand_in_reads_as_standard(self):
        self.v.apply({"message-new-sms": "double"}, FakeFeedbackdSettings(), exact=True)
        self.assertEqual("default", self.v.read_choices()["key-pressed"])

    def test_the_multiplier_is_moved_by_dpkg_divert(self):
        d = tempfile.mkdtemp()
        m = os.path.join(d, "vibrator-sysfs-multiplier")
        open(m, "w").write("10\n")
        self.v.MULTIPLIER, self.v.MULTIPLIER_ASIDE = m, m + ".misc-de-off"
        try:
            argv = self.v.multiplier_argv(True)
            self.assertEqual(["sudo", "-n", "dpkg-divert", "--local", "--rename",
                              "--divert", m + ".misc-de-off", "--add", m], argv)
            self.assertIsNone(self.v.multiplier_argv(False))      # already in place
            os.rename(m, m + ".misc-de-off")
            self.assertTrue(self.v.multiplier_aside())
            self.assertIsNone(self.v.multiplier_argv(True))
            self.assertIn("--remove", self.v.multiplier_argv(False, secret="x"))
            self.assertEqual(["sudo", "-S", "-p", ""], self.v.multiplier_argv(False, "x")[:4])
        finally:
            pass

    def test_a_ringing_call_repeats_until_stopped(self):
        d = tempfile.mkdtemp()
        for a in ("duration", "activate"):
            open(os.path.join(d, a), "w").close()
        p = self.v.Player(d)
        ended = []
        p.play({"magnitudes": [1.0, 0.0], "durations": [100, 200]}, loop=True,
               on_end=lambda: ended.append(1))
        p._step(2)                         # past the end: starts over
        self.assertEqual("100\n", open(os.path.join(d, "duration")).read())
        self.assertTrue(p.playing())
        self.assertEqual([], ended)
        p.stop()
        self.assertEqual("0\n", open(os.path.join(d, "activate")).read())
        self.assertEqual([1], ended)

    def test_the_loop_has_a_limit(self):
        d = tempfile.mkdtemp()
        for a in ("duration", "activate"):
            open(os.path.join(d, a), "w").close()
        p = self.v.Player(d)
        ended = []
        p.play({"magnitudes": [1.0], "durations": [100]}, loop=True,
               on_end=lambda: ended.append(1))
        p.left_ms = 0
        p._step(1)
        self.assertEqual([1], ended)

    def test_only_the_call_loops(self):
        self.assertEqual({"phone-incoming-call"}, self.v.LOOPING)

    def test_the_player_writes_duration_then_activate(self):
        d = tempfile.mkdtemp()
        for a in ("duration", "activate"):
            open(os.path.join(d, a), "w").close()
        p = self.v.Player(d)
        self.assertTrue(p.available())
        p.steps = [(1.0, 120), (0.0, 50)]
        p._step(0)
        self.assertEqual("120\n", open(os.path.join(d, "duration")).read())
        self.assertEqual("1\n", open(os.path.join(d, "activate")).read())


class FakePluginSettings:
    def __init__(self, names):
        self.names = list(names)

    def get_strv(self, key):
        assert key == "status-icons"
        return list(self.names)

    def set_strv(self, key, names):
        assert key == "status-icons"
        self.names = list(names)


class PinsTheFolders(unittest.TestCase):
    """The folder dock's switch: one name in phosh's status-icons list."""

    def setUp(self):
        self.other = switcher.pages.other

    def test_on_adds_our_name_and_keeps_the_others(self):
        s = FakePluginSettings(["furios-killswitch", "furios-battery-time"])
        self.assertFalse(self.other.dock_enabled(s))
        self.other.set_dock_enabled(True, s)
        self.assertEqual(["furios-killswitch", "furios-battery-time",
                          "furios-folder-dock"], s.names)
        self.assertTrue(self.other.dock_enabled(s))

    def test_twice_on_is_one_entry_and_off_takes_only_ours(self):
        s = FakePluginSettings(["furios-killswitch"])
        self.other.set_dock_enabled(True, s)
        self.other.set_dock_enabled(True, s)
        self.assertEqual(1, s.names.count("furios-folder-dock"))
        self.other.set_dock_enabled(False, s)
        self.assertEqual(["furios-killswitch"], s.names)

    def test_switching_on_clears_the_crash_mark(self):
        """While the mark is there the plugin does nothing, so on has to
        mean: try again."""
        path = self.other.dock_guard_path()
        self.assertTrue(path.startswith(os.environ["XDG_CACHE_HOME"]))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text("")
        self.other.set_dock_enabled(True, FakePluginSettings([]))
        self.assertFalse(os.path.exists(path))

    def test_no_schema_means_off(self):
        self.assertFalse(self.other.dock_enabled(None))

    def test_one_row_is_a_key_file_the_plugin_reads(self):
        path = self.other.dock_config_path()
        self.assertTrue(path.startswith(os.environ["XDG_CONFIG_HOME"]))
        self.assertFalse(self.other.dock_one_row())
        self.other.set_dock_one_row(True)
        # The exact group and key the plugin's GKeyFile looks up.
        self.assertEqual("[dock]\none-row=true\n", Path(path).read_text())
        self.assertTrue(self.other.dock_one_row())
        self.other.set_dock_one_row(False)
        self.assertFalse(os.path.exists(path))
        self.other.set_dock_one_row(False)
        self.assertFalse(self.other.dock_one_row())

    def test_hide_labels_shares_the_file_and_leaves_one_row_alone(self):
        path = self.other.dock_config_path()
        self.other.set_dock_one_row(True)
        self.other.set_dock_setting(self.other.HIDE_LABELS, True)
        # The exact group and keys the plugin's GKeyFile looks up.
        self.assertEqual("[dock]\none-row=true\nhide-labels=true\n",
                         Path(path).read_text())
        self.other.set_dock_one_row(False)
        self.assertTrue(self.other.dock_setting(self.other.HIDE_LABELS))
        self.assertEqual("[dock]\nhide-labels=true\n", Path(path).read_text())
        self.other.set_dock_setting(self.other.HIDE_LABELS, False)
        self.assertFalse(os.path.exists(path))

    def test_a_broken_file_reads_as_rows(self):
        path = self.other.dock_config_path()
        Path(path).write_text("one-row=true\n")
        try:
            self.assertFalse(self.other.dock_one_row())
        finally:
            os.remove(path)


class BluetoothPowersave(unittest.TestCase):
    """The switch that decides whether Bluetooth survives a dark screen.

    It is the one control in this app that edits another program's config
    file, so the checks are about that file: what is read out of it, what is
    written back, and that the switch never shows a state it only wishes were
    true. The symptom behind it, measured on 16.9.2026: with BTSAVE=true the
    adapter is powered down when the screen goes off, earbuds taken out of
    their case page a controller that is not there, and nothing happens until
    the phone is woken.
    """

    audio = importlib.import_module("miscde.pages.audio")

    def test_the_key_is_read_out_of_the_file(self):
        self.assertIs(switcher.btsave_in_config("BTSAVE=true"), True)
        self.assertIs(switcher.btsave_in_config("BTSAVE=false"), False)

    def test_the_rest_of_the_file_is_not_in_the_way(self):
        text = "[Settings]\nOFFLINE=true\nBTSAVE=false\nWIFI=true\n"
        self.assertIs(switcher.btsave_in_config(text), False)

    def test_a_key_that_is_not_there_is_not_off(self):
        """None, not False - "batman does not know this setting" and "batman
        is set to leave Bluetooth alone" are different phones, and the row
        says so."""
        self.assertIsNone(switcher.btsave_in_config("[Settings]\nWIFI=true\n"))

    def test_the_value_is_read_the_way_a_shell_would(self):
        self.assertIs(switcher.btsave_in_config("BTSAVE=TRUE"), True)
        self.assertIs(switcher.btsave_in_config("  BTSAVE=true  "), True)

    def test_without_a_password_sudo_is_told_not_to_ask(self):
        argv = switcher.btsave_argv(True)
        self.assertEqual(argv[:2], ["sudo", "-n"])

    def test_with_a_password_sudo_reads_it_from_the_pipe(self):
        argv = switcher.btsave_argv(True, "hunter2")
        self.assertEqual(argv[:4], ["sudo", "-S", "-p", ""])

    def test_the_password_is_never_an_argument(self):
        """The same rule as everywhere else in this app: a secret goes
        through the pipe, never through argv, where every ps on the phone
        would read it."""
        self.assertNotIn("hunter2", switcher.btsave_argv(False, "hunter2"))

    def test_the_file_and_the_unit_are_arguments_not_text(self):
        argv = switcher.btsave_argv(False)
        self.assertEqual(argv[-3:], [switcher.BATMAN_CONFIG,
                                     switcher.BATMAN_UNIT, "false"])

    def run_script(self, contents, value):
        """The real script, against a scratch file.

        systemctl is the last line and it fails here, which is why the file
        is what gets checked and not the exit code. Everything this script
        does to the config happens before it.

        Not the real systemctl (4.10.2026): a system-wide restart, even of a
        unit that does not exist, goes through polkit first, and on a desktop
        with an agent that is a password dialog per test - three per run.
        """
        with tempfile.NamedTemporaryFile("w", suffix=".conf",
                                         delete=False) as handle:
            handle.write(contents)
            path = handle.name
        fake = tempfile.mkdtemp()
        Path(fake, "systemctl").write_text("#!/bin/sh\nexit 1\n")
        os.chmod(Path(fake, "systemctl"), 0o755)
        env = dict(os.environ, PATH=fake + os.pathsep + os.environ.get("PATH", ""))
        try:
            subprocess_real.run(
                ["sh", "-c", self.audio.BTSAVE_SCRIPT, "sh", path,
                 "miscde-no-such-unit.service", value],
                capture_output=True, env=env)
            return Path(path).read_text()
        finally:
            os.unlink(path)
            shutil_real.rmtree(fake, ignore_errors=True)

    def test_an_existing_line_is_rewritten_in_place(self):
        out = self.run_script("[Settings]\nBTSAVE=true\nWIFI=true\n", "false")
        self.assertEqual(out, "[Settings]\nBTSAVE=false\nWIFI=true\n")

    def test_a_missing_key_is_appended(self):
        out = self.run_script("[Settings]\nWIFI=true\n", "false")
        self.assertEqual(out, "[Settings]\nWIFI=true\nBTSAVE=false\n")

    def test_nothing_else_in_the_file_is_touched(self):
        """batman reads eight settings out of this file. Rewriting the one
        line has to leave the other seven exactly as they were."""
        before = ("[Settings]\nOFFLINE=true\nPOWERSAVE=true\nCHARGESAVE=true\n"
                  "BUSSAVE=true\nGPUSAVE=true\nBTSAVE=true\nHYBRIS=true\n"
                  "WIFI=true\n")
        after = self.run_script(before, "false")
        self.assertEqual(after, before.replace("BTSAVE=true", "BTSAVE=false"))

    def test_the_words_name_the_symptom_not_the_setting(self):
        """Somebody opens this page because a headset stayed silent, not
        because they were looking for a config key."""
        on = switcher.Window.btsave_words(True)
        self.assertIn("headset", on)
        # Off: the owner's description (29.9.) and nothing else.
        self.assertEqual("Turns Bluetooth off when possible to save energy",
                         switcher.Window.btsave_words(False))

    def test_with_no_batman_the_row_says_that_rather_than_off(self):
        self.assertIn("batman", switcher.Window.btsave_words(None))


def snapshot(base):
    """Every path under base with its content and mode - "as it was" in the
    one sense that counts: nothing can be told apart afterwards."""
    found = {}
    for p in sorted(Path(base).rglob("*")):
        found[str(p.relative_to(base))] = (
            p.read_bytes() if p.is_file() else "dir", p.stat().st_mode & 0o7777)
    return found


class FakeDconf(FakePluginSettings):
    """A key that can be unset (the default applies) or set, as in dconf."""

    def __init__(self, default, user=None):
        super().__init__(user if user is not None else default)
        self.default, self.user = list(default), user

    def get_user_value(self, key):
        assert key == "status-icons"
        return None if self.user is None else types.SimpleNamespace(
            unpack=lambda: list(self.user))

    def set_strv(self, key, names):
        super().set_strv(key, names)
        self.user = list(names)

    def reset(self, key):
        assert key == "status-icons"
        self.user, self.names = None, list(self.default)


class SwitchesPutBackWhatWasThere(unittest.TestCase):
    """The owner's rule (30.9.2026), switch by switch, from the outside:
    snapshot, on, off, and the snapshot again - for what was absent, for
    what was there with a value of its own, and for what somebody changed
    after us, which stays theirs. The record is written once: a second
    round must not replace the first original."""

    def setUp(self):
        forget_all_records()
        self.addCleanup(forget_all_records)
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil_real.rmtree, self.dir, True)
        self.other = switcher.pages.other
        self.audio = importlib.import_module("miscde.pages.audio")

    def path(self, *parts):
        return os.path.join(self.dir, *parts)

    # --- gtk.css ---

    def test_css_that_was_not_there_goes_with_its_directory(self):
        css = self.path("gtk-3.0", "gtk.css")
        before = snapshot(self.dir)
        self.other.set_search_hidden(True, css)
        self.other.set_search_hidden(False, css)
        self.assertEqual(before, snapshot(self.dir))

    def test_css_comes_back_byte_for_byte(self):
        """No final newline, and an empty file that is a file."""
        for text in ("window { color: red; }", ""):
            with self.subTest(text=text):
                css = self.path("gtk-3.0", "gtk.css")
                os.makedirs(os.path.dirname(css), exist_ok=True)
                Path(css).write_text(text)
                os.chmod(css, 0o600)
                before = snapshot(self.dir)
                self.other.set_search_hidden(True, css)
                self.other.set_search_hidden(False, css)
                self.assertEqual(before, snapshot(self.dir))

    def test_an_empty_gtk3_directory_of_somebodys_stays(self):
        os.makedirs(self.path("gtk-3.0"))
        before = snapshot(self.dir)
        css = self.path("gtk-3.0", "gtk.css")
        self.other.set_search_hidden(True, css)
        self.other.set_search_hidden(False, css)
        self.assertEqual(before, snapshot(self.dir))

    def test_css_changed_after_us_keeps_the_change(self):
        css = self.path("gtk-3.0", "gtk.css")
        self.other.set_search_hidden(True, css)
        Path(css).write_text(Path(css).read_text() + "label { color: blue; }\n")
        self.other.set_search_hidden(False, css)
        self.assertEqual("label { color: blue; }\n", Path(css).read_text())

    def test_the_first_original_is_the_one_kept(self):
        css = self.path("gtk-3.0", "gtk.css")
        os.makedirs(os.path.dirname(css))
        Path(css).write_text("a {}\n")
        self.other.set_search_hidden(True, css)
        Path(css).write_text(Path(css).read_text() + "b {}\n")
        self.other.set_search_hidden(False, css)    # theirs now: record stays
        self.other.set_search_hidden(True, css)     # a second round
        record = original.load(original.file_ident(css))
        self.assertEqual("a {}\n", record["content"])

    # --- the dock's key file ---

    def test_dock_config_that_was_not_there_goes(self):
        path = self.path("cfg", "furios-folder-dock.conf")
        before = snapshot(self.dir)
        self.other.set_dock_setting(self.other.ONE_ROW, True, path)
        self.other.set_dock_setting(self.other.HIDE_LABELS, True, path)
        self.other.set_dock_setting(self.other.ONE_ROW, False, path)
        self.other.set_dock_setting(self.other.HIDE_LABELS, False, path)
        self.assertEqual(before, snapshot(self.dir))

    def test_somebodys_dock_config_comes_back_as_it_was(self):
        """A comment, a key the plugin may read one day, one-row=false: the
        old switch rewrote the file from its two keys and lost all three."""
        path = self.path("furios-folder-dock.conf")
        Path(path).write_text("# mine\n[dock]\none-row=false\nspeed=3\n")
        before = snapshot(self.dir)
        self.other.set_dock_setting(self.other.ONE_ROW, True, path)
        self.assertIn("speed=3", Path(path).read_text())
        self.assertIn("# mine", Path(path).read_text())
        self.assertTrue(self.other.dock_one_row(path))
        self.other.set_dock_setting(self.other.ONE_ROW, False, path)
        self.assertEqual(before, snapshot(self.dir))

    def test_a_dock_config_the_old_switch_wrote_is_not_an_original(self):
        path = self.path("furios-folder-dock.conf")
        Path(path).write_text("[dock]\none-row=true\n")
        self.other.set_dock_setting(self.other.HIDE_LABELS, True, path)
        self.assertIsNone(original.load(original.file_ident(path)))
        self.other.set_dock_setting(self.other.HIDE_LABELS, False, path)
        self.other.set_dock_setting(self.other.ONE_ROW, False, path)
        self.assertFalse(os.path.exists(path))

    # --- the keyring prompter ---

    def test_a_prompter_service_of_somebodys_comes_back_with_its_mode(self):
        service = self.path("share", "dbus-1", "services", "p.service")
        shim = self.path("libexec", "keyring-prompter-wait")
        os.makedirs(os.path.dirname(service))
        Path(service).write_text("[D-BUS Service]\nName=x\nExec=/opt/mine\n")
        os.chmod(service, 0o600)
        before = snapshot(self.dir)
        self.other.set_prompter_fixed(True, service, shim)
        self.assertTrue(self.other.prompter_fixed(service, shim))
        self.other.set_prompter_fixed(False, service, shim)
        self.assertEqual(before, snapshot(self.dir))

    def test_a_prompter_file_changed_after_us_stays_and_is_named(self):
        service = self.path("share", "dbus-1", "services", "p.service")
        shim = self.path("libexec", "keyring-prompter-wait")
        self.other.set_prompter_fixed(True, service, shim)
        Path(service).write_text(Path(service).read_text() + "User=me\n")
        with self.assertRaises(original.ChangedSince) as caught:
            self.other.set_prompter_fixed(False, service, shim)
        self.assertEqual([service], caught.exception.paths)
        self.assertTrue(Path(service).read_text().endswith("User=me\n"))
        self.assertFalse(os.path.exists(shim), "the untouched shim stayed")

    # --- the portals file ---

    def test_an_empty_portal_directory_of_somebodys_stays(self):
        for existing in (True, False):
            with self.subTest(existing=existing):
                shutil_real.rmtree(self.path("xdg-desktop-portal"), True)
                if existing:
                    os.makedirs(self.path("xdg-desktop-portal"))
                path = self.path("xdg-desktop-portal", "phosh-portals.conf")
                before = snapshot(self.dir)
                self.other.set_portals_fixed(True, path, os.devnull)
                self.other.set_portals_fixed(False, path, os.devnull)
                self.assertEqual(before, snapshot(self.dir))

    def test_a_portals_file_changed_after_us_stays(self):
        path = self.path("xdg-desktop-portal", "phosh-portals.conf")
        self.other.set_portals_fixed(True, path, os.devnull)
        Path(path).write_text(Path(path).read_text() + "# mine\n")
        with self.assertRaises(original.ChangedSince):
            self.other.set_portals_fixed(False, path, os.devnull)
        self.assertTrue(os.path.exists(path))

    def test_an_empty_portals_file_of_somebodys_is_not_taken(self):
        path = self.path("phosh-portals.conf")
        Path(path).write_text("")
        with self.assertRaises(OSError):
            self.other.set_portals_fixed(True, path, os.devnull)
        self.assertEqual("", Path(path).read_text())

    def test_the_switch_says_changed_rather_than_could_not_write(self):
        win = switcher.Window(switcher.Adw.Application())
        said = []
        self.enterContext(mock.patch.object(switcher.Window, "report",
                                            lambda self, text: said.append(text)))
        row = Recording()
        row.set_active(False)
        win._loading = False
        with mock.patch.object(self.other, "set_portals_fixed",
                               side_effect=original.ChangedSince(["/x"])):
            win.on_portals_fixed(row, None)
        self.assertTrue(row.get_active(), "the switch claims it went off")
        self.assertIn("left as it is", said[0])
        self.assertIn("/x", said[0])

    # --- phosh's plugin list ---

    def test_an_unset_key_is_reset_not_written(self):
        s = FakeDconf(["wifi-hotspot"])
        self.other.set_dock_enabled(True, s)
        self.assertEqual(["wifi-hotspot", "furios-folder-dock"], s.names)
        self.other.set_dock_enabled(False, s)
        self.assertIsNone(s.user, "the default was pinned into dconf")
        self.assertEqual(["wifi-hotspot"], s.names)

    def test_a_key_set_to_the_default_stays_set(self):
        """The case "compare with the default" got wrong: set, by somebody,
        to exactly the default's value."""
        s = FakeDconf(["wifi-hotspot"], user=["wifi-hotspot"])
        self.other.set_dock_enabled(True, s)
        self.other.set_dock_enabled(False, s)
        self.assertEqual(["wifi-hotspot"], s.user)

    def test_another_plugin_added_after_us_stays(self):
        s = FakeDconf([])
        self.other.set_dock_enabled(True, s)
        s.set_strv("status-icons", s.names + ["furios-lockout"])
        self.other.set_dock_enabled(False, s)
        self.assertEqual(["furios-lockout"], s.user)

    def test_furios_phoshs_record_comes_first(self):
        """Older than the app's first change: then the app writes none of
        its own, and off goes back to what that one says."""
        state = os.path.join(os.environ["XDG_STATE_HOME"], "furios-phosh")
        os.makedirs(state, exist_ok=True)
        path = os.path.join(state, "original.json")
        self.addCleanup(os.remove, path)
        Path(path).write_text(json.dumps({"legacy": False, "key": {
            "set": False, "value": None, "default": ["wifi-hotspot"],
            "had_ours": False}}))
        s = FakeDconf(["wifi-hotspot"], user=["wifi-hotspot"])
        self.other.set_dock_enabled(True, s)
        self.assertIsNone(original.load(original.setting_ident(
            self.other.PLUGINS_SCHEMA, self.other.PLUGINS_KEY)))
        self.other.set_dock_enabled(False, s)
        self.assertIsNone(s.user, "it was unset before furios_phosh came")

    def test_a_legacy_furios_phosh_record_is_not_believed(self):
        state = os.path.join(os.environ["XDG_STATE_HOME"], "furios-phosh")
        os.makedirs(state, exist_ok=True)
        path = os.path.join(state, "original.json")
        self.addCleanup(os.remove, path)
        Path(path).write_text(json.dumps({"legacy": True, "key": {
            "set": False, "value": None, "default": [], "had_ours": False}}))
        self.assertIsNone(original.phosh_plugin_record())

    def test_off_without_our_name_writes_nothing(self):
        s = FakeDconf(["wifi-hotspot"])
        self.other.set_dock_enabled(False, s)
        self.assertIsNone(s.user)

    # --- batman's BTSAVE ---

    def batman(self, text):
        path = self.path("batman", "config")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        Path(path).write_text(text)
        self.enterContext(mock.patch.object(self.audio, "BATMAN_CONFIG", path))
        return path

    def test_btsave_is_recorded_before_the_first_change(self):
        path = self.batman("[Settings]\nBTSAVE=false\n")
        record = self.audio.remember_btsave()
        self.assertEqual(["BTSAVE=false"], record["lines"])
        self.assertEqual("batman.service", record["unit"])
        Path(path).write_text("[Settings]\nBTSAVE=true\n")
        self.assertEqual(["BTSAVE=false"], self.audio.remember_btsave()["lines"])

    def test_a_copy_taken_by_hand_is_the_better_original(self):
        path = self.batman("[Settings]\nBTSAVE=false\n")
        Path(path + ".bak-20260916-082123").write_text("[Settings]\nBTSAVE=true\n")
        record = self.audio.remember_btsave()
        self.assertEqual(["BTSAVE=true"], record["lines"])
        self.assertTrue(record["source"].endswith(".bak-20260916-082123"))

    def test_going_back_to_the_original_puts_its_lines_back(self):
        """Somebody's own "BTSAVE=TRUE": switching off and on again used
        to leave "BTSAVE=true" - the same meaning, not the same file."""
        path = self.batman("[Settings]\nBTSAVE=TRUE\nWIFI=true\n")
        record = self.audio.remember_btsave()
        self.assertFalse(self.audio.btsave_back_to_original(record, False))
        Path(path).write_text("[Settings]\nBTSAVE=false\nWIFI=true\n")
        original.wrote_lines(self.audio.BATMAN_CONFIG, "BTSAVE", ["BTSAVE=false"])
        record = original.load(original.lines_ident(path, "BTSAVE"))
        self.assertTrue(self.audio.btsave_back_to_original(record, True))
        argv = self.audio.btsave_restore_argv(record["lines"])
        self.assertEqual(argv[:2], ["sudo", "-n"])
        # The script itself, against the scratch file, with no unit.
        subprocess_real.run(argv[2:-1] + [""], check=True)
        self.assertEqual("[Settings]\nBTSAVE=TRUE\nWIFI=true\n",
                         Path(path).read_text())

    def test_the_window_records_and_then_forgets(self):
        path = self.batman("[Settings]\nBTSAVE=true\n")
        win = switcher.Window(switcher.Adw.Application())
        ran = []
        self.enterContext(mock.patch.object(
            switcher.process, "run_async",
            lambda argv, done, **kw: ran.append((argv, done))))
        win.apply_btsave(False)
        self.assertEqual(ran[0][0], switcher.btsave_argv(False))
        Path(path).write_text("[Settings]\nBTSAVE=false\n")
        ran[0][1](True, "")
        record = original.load(original.lines_ident(path, "BTSAVE"))
        self.assertEqual(["BTSAVE=true"], record["lines"])
        self.assertEqual(["BTSAVE=false"], record["written"])
        win.busy = False
        win.apply_btsave(True)
        self.assertEqual(ran[1][0], self.audio.btsave_restore_argv(["BTSAVE=true"]))
        Path(path).write_text("[Settings]\nBTSAVE=true\n")
        ran[1][1](True, "")
        self.assertIsNone(original.load(original.lines_ident(path, "BTSAVE")))

    def test_a_key_that_was_not_there_is_taken_out_again(self):
        path = self.path("config")
        Path(path).write_text("A=1\nBTSAVE=false\nB=2\n")
        subprocess_real.run(["sh", "-c", original.RESTORE_LINES_SCRIPT, "sh",
                             path, "BTSAVE", "", ""], check=True)
        self.assertEqual("A=1\nB=2\n", Path(path).read_text())

    # --- the colouring daemon ---

    def battery_window(self, enabled):
        win = switcher.Window(switcher.Adw.Application())
        win.live = dict(win.live, battery="battctl")
        win.batt_switches = {k: Recording() for k in ("charging", "level")}
        win.batt_enabled, win.batt_running = enabled, enabled
        chains = []
        self.enterContext(mock.patch.object(
            switcher.Window, "run_chain",
            lambda self, steps, done: chains.append(steps)))
        return win, chains

    def test_a_unit_that_was_disabled_is_disabled_again(self):
        win, chains = self.battery_window(False)
        row = win.batt_switches["charging"]
        row.active = True
        win.on_battery_option(row, None, "charging")
        row.active = False
        win.on_battery_option(row, None, "charging")
        self.assertIn("disable", " ".join(chains[-1][-1]))

    def test_a_unit_somebody_had_enabled_stays_enabled(self):
        win, chains = self.battery_window(True)
        row = win.batt_switches["charging"]
        row.active = True
        win.on_battery_option(row, None, "charging")
        row.active = False
        win.on_battery_option(row, None, "charging")
        self.assertFalse(any("disable" in " ".join(step) for step in chains[-1]))

    def test_enabled_by_an_earlier_option_is_not_an_original(self):
        win, chains = self.battery_window(True)
        win.batt_switches["level"].active = True
        row = win.batt_switches["charging"]
        row.active = True
        win.on_battery_option(row, None, "charging")
        self.assertIsNone(original.load(original.unit_ident(switcher.BATTERY_UNIT)))


class TheLauncherIcon(unittest.TestCase):
    """The icon file, as GdkPixbuf sees it.

    Measured on the phone on 15.9.2026: every lookup found the file and
    phosh drew the placeholder anyway. GdkPixbuf sniffs a format from the
    first 256 bytes and nothing else, so an SVG whose opening tag sits
    behind a long licence-and-rationale header is not an SVG to it - and
    GTK4's own loader has no such limit, which is why a test through the
    app itself would have passed.
    """

    ICON = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "de.misc-de.tools.svg")

    def test_the_opening_tag_is_inside_the_sniffing_window(self):
        with open(self.ICON, "rb") as fh:
            data = fh.read()
        self.assertLessEqual(
            data.find(b"<svg"), 256,
            "the <svg tag sits behind byte 256 - GdkPixbuf will not "
            "recognise this file and phosh draws the placeholder")

    def test_the_desktop_entry_names_the_icon_that_is_shipped(self):
        entry = os.path.join(os.path.dirname(self.ICON),
                             "de.misc-de.tools.desktop")
        with open(entry, encoding="utf-8") as fh:
            named = [l.split("=", 1)[1].strip()
                     for l in fh if l.startswith("Icon=")]
        self.assertEqual(
            [os.path.basename(self.ICON)[:-len(".svg")]], named)


class TheLauncher(unittest.TestCase):
    """misc-de.py, which is all that is left at the top.

    It is thirty lines and it is the only part of this repository whose path
    is written down somewhere else - in install.sh, in the .desktop entry and
    in the execv that restarts the app into a new version. So it gets a test
    of its own rather than being taken on trust because it is short.
    """

    def test_it_finds_the_package_and_hands_the_app_over(self):
        mod = load(ROOT / "misc-de.py", "launcher_under_test")
        ran = []
        with mock.patch.object(switcher.App, "run",
                               lambda self, argv: ran.append(argv) or 0):
            self.assertEqual(0, mod.main(["misc-de"]))
        self.assertEqual([["misc-de"]], ran)

    def test_it_finds_the_dependency_check_beside_the_package(self):
        mod = load(ROOT / "misc-de.py", "launcher_under_test")
        self.assertEqual(str(ROOT / "miscde" / "deps.py"), mod._deps().__file__)

    def test_a_missing_package_stops_it_before_the_window(self):
        """Said, not crashed: started from the app grid, a traceback about
        a missing typelib goes nowhere anybody looks."""
        mod = load(ROOT / "misc-de.py", "launcher_under_test")
        told = []

        class Deps:
            @staticmethod
            def check():
                told.append(True)
                return False

        ran = []
        with mock.patch.object(mod, "_deps", lambda: Deps), \
                mock.patch.object(switcher.App, "run",
                                  lambda self, argv: ran.append(argv) or 0):
            self.assertEqual(1, mod.main(["misc-de"]))
        self.assertEqual([True], told)
        self.assertEqual([], ran)

    def test_it_looks_beside_itself_first(self):
        """From the clone, ./misc-de.py has to run the clone - not whatever
        is installed in /usr/local. That is the whole point of running it
        from the source tree, and the order of that list is the only thing
        that decides it."""
        text = (ROOT / "misc-de.py").read_text()
        here = text.index("HERE")
        self.assertLess(here, text.index("/usr/local/lib/misc-de"))


class TheStartCheck(unittest.TestCase):
    """miscde/deps.py: what the window needs before it can open."""

    def setUp(self):
        self.deps = load(ROOT / "miscde" / "deps.py", "deps_under_test")

    def test_everything_there_is_nothing_missing(self):
        self.assertEqual([], self.deps.missing(lambda name, version: True))

    def test_each_missing_library_names_its_package(self):
        self.assertEqual(["gir1.2-adw-1"],
                         self.deps.missing(lambda name, version: name != "Adw"))
        self.assertEqual(["gir1.2-gtk-4.0", "gir1.2-adw-1"],
                         self.deps.missing(lambda name, version: False))

    def test_the_message_lists_them_and_how_to_install_them(self):
        heading, text = self.deps.message(["gir1.2-gtk-4.0", "gir1.2-adw-1"])
        self.assertIn("gir1.2-gtk-4.0", text)
        self.assertIn("sudo apt install gir1.2-gtk-4.0 gir1.2-adw-1", text)

    def test_it_imports_nothing_of_the_package(self):
        """The package imports GTK first - loading it would be the crash
        this is there to prevent."""
        text = (ROOT / "miscde" / "deps.py").read_text()
        self.assertNotRegex(text, r"(?m)^\s*from \.|^\s*import miscde|from miscde")

    def test_its_texts_have_their_german(self):
        from miscde.lang_de import TRANSLATIONS
        heading, text = self.deps.message(["p"])
        for key in ("misc-de cannot start", "Got it",
                    "These packages are missing:\n\n{packages}\n\nInstall "
                    "them in a terminal with:\n\n{command}"):
            self.assertIn(key, TRANSLATIONS)


class SourceDigest(unittest.TestCase):
    """The fingerprint the app compares itself against.

    One file against one file used to answer "is the running program the one
    in the clone". A package needs every file in it to count, and a file that
    was added or deleted has to change the answer as surely as an edited line
    - otherwise the offer to update would simply stop appearing one day.
    """

    def tree(self, files):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil_real.rmtree, d, True)
        for name, content in files.items():
            path = os.path.join(d, name)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(content)
        return d

    def digest(self, files):
        return switcher.tools.source_digest(self.tree(files))

    def test_the_same_files_give_the_same_answer(self):
        files = {"a.py": b"one", "pages/b.py": b"two"}
        self.assertEqual(self.digest(files), self.digest(dict(files)))

    def test_one_changed_line_changes_it(self):
        self.assertNotEqual(self.digest({"a.py": b"one"}),
                            self.digest({"a.py": b"one "}))

    def test_a_file_that_was_added_changes_it(self):
        self.assertNotEqual(self.digest({"a.py": b"one"}),
                            self.digest({"a.py": b"one", "b.py": b"two"}))

    def test_moving_a_line_between_two_files_changes_it(self):
        """The names go in with the contents. Without that, cutting a method
        out of one page and pasting it into another would leave the two trees
        looking identical."""
        self.assertNotEqual(self.digest({"a.py": b"x", "b.py": b"y"}),
                            self.digest({"a.py": b"y", "b.py": b"x"}))

    def test_byte_code_left_lying_about_is_ignored(self):
        """__pycache__ is written by whoever ran the thing last. Counting it
        would make the answer depend on that, and the offer to update would
        appear and disappear on its own."""
        plain = self.tree({"a.py": b"one"})
        with_cache = self.tree({"a.py": b"one", "__pycache__/a.pyc": b"junk"})
        self.assertEqual(switcher.tools.source_digest(plain),
                         switcher.tools.source_digest(with_cache))

    def test_a_directory_that_is_not_there_is_not_an_answer(self):
        """None, and the caller says nothing rather than claiming they
        differ - an unanswerable question is not a reason to offer an
        update."""
        self.assertIsNone(switcher.tools.source_digest("/does/not/exist"))
        self.assertIsNone(switcher.tools.source_digest(""))
        self.assertIsNone(self.digest({"README.md": b"no python here"}))


class TheInstallerLooksForTools(unittest.TestCase):
    """install.sh's own lookup, run as bash runs it.

    It is the last thing the installer prints - which of the five tools are
    not there yet - and on 17.9.2026 it named two that were: the script runs
    under sudo, so $PATH and $HOME are root's, while killswitch-indicator and
    battctl need no root and live in the user's own ~/.local/bin. An offer to
    install what is already installed is worse than no line at all, so the
    function is extracted from the script and exercised here rather than
    read and believed.
    """

    SCRIPT = ROOT / "install.sh"

    def lookup(self):
        """The block between the markers in install.sh, and nothing else -
        sourcing the whole script would install the app."""
        text = self.SCRIPT.read_text()
        start = text.index("# --- tool lookup")
        end = text.index("# --- end tool lookup ---")
        return text[start:end]

    def ask(self, name, home):
        """have_tool, with `home` standing in for the caller's home."""
        script = "\n".join([self.lookup(),
                            "user_home=" + shlex.quote(home),
                            "have_tool " + shlex.quote(name)])
        return subprocess_real.run(["bash", "-c", script],
                                   stdout=subprocess_real.DEVNULL,
                                   stderr=subprocess_real.DEVNULL).returncode

    def test_a_tool_in_the_callers_own_bin_is_found(self):
        with tempfile.TemporaryDirectory() as home:
            bin_dir = os.path.join(home, ".local", "bin")
            os.makedirs(bin_dir)
            tool = os.path.join(bin_dir, "battctl")
            with open(tool, "w") as fh:
                fh.write("#!/bin/sh\n")
            os.chmod(tool, 0o755)
            self.assertEqual(0, self.ask("battctl", home),
                             "a tool in ~/.local/bin was reported missing")

    def test_a_tool_that_is_nowhere_is_still_missing(self):
        with tempfile.TemporaryDirectory() as home:
            self.assertNotEqual(0, self.ask("no-such-tool-here", home))

    def test_the_installer_asks_nothing_the_other_way(self):
        """Every one of the five goes through have_tool. A single
        "command -v" left in the list would bring the wrong line back for
        whichever tool it checks."""
        text = self.SCRIPT.read_text()
        for tool in ("audioctl", "modemctl", "furios-gps-contribute",
                     "killswitch-indicator", "battctl"):
            self.assertNotIn("command -v " + tool, text)
        self.assertNotIn('command -v "$tool"', text)


class KnowsWhetherTheFaultIsThere(unittest.TestCase):
    """miscde/faults.py: one fact about the phone each, read from a file the
    test hands in - never this phone's."""

    def setUp(self):
        self.f = importlib.import_module("miscde.faults")
        self.dir = tempfile.mkdtemp(prefix="miscde-test-")

    def write(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as fh:
            fh.write(text)
        return path

    IRQ = (" 221:          0   mt-eint  21 Edge      cam_switch\n"
           " 222:         %d   mt-eint  22 Edge      nwk_switch\n")

    def test_a_slider_that_flaps_is_told_from_a_hand_that_moves_it(self):
        flaps = self.f.switch_flaps
        self.assertTrue(flaps(self.IRQ % 44, 12 * 3600))      # this phone
        self.assertFalse(flaps(self.IRQ % 6, 12 * 3600))      # a hand
        # Twelve in a day is somebody who uses it - not a loose contact.
        self.assertFalse(flaps(self.IRQ % 12, 24 * 3600))
        self.assertFalse(flaps("", 3600))
        self.assertIsNone(flaps(self.IRQ % 44, 0))

    def test_the_count_comes_from_every_cpu_column(self):
        line = " 222:   3   4   5   mt-eint  22 Edge      nwk_switch\n"
        self.assertEqual(12, self.f.switch_edges(line, "nwk_switch"))

    def test_sliders_read_the_two_proc_files(self):
        irq = self.write("interrupts", self.IRQ % 44)
        self.assertTrue(self.f.sliders_flap(irq, self.write("up", "43200.0 1\n")))
        self.assertIsNone(self.f.sliders_flap(irq, self.write("up2", "")))

    def test_echo_suppression_is_missing_when_the_vendor_says_no(self):
        good = ("state=off\nusip:  /dev/usip open to group audio - x\n"
                "  MTK_HANDSFREE_DMNR_SUPPORT = yes\n")
        self.assertFalse(self.f.dmnr_missing(good))
        self.assertTrue(self.f.dmnr_missing(
            good.replace("= yes", "= no")))
        self.assertTrue(self.f.dmnr_missing(
            "usip:  /dev/usip closed - the HAL cannot hand it over\n"))
        self.assertFalse(self.f.dmnr_missing(""))

    def test_the_prompter_falls_back_only_where_gcr_is_started(self):
        shipped = self.write("p.service", "[D-BUS Service]\nName=x\n"
                             "Exec=/usr/libexec/gcr-prompter\n")
        self.assertTrue(self.f.prompter_falls_back(shipped))
        other = self.write("q.service", "[D-BUS Service]\nExec=/bin/true\n")
        self.assertFalse(self.f.prompter_falls_back(other))
        self.assertFalse(self.f.prompter_falls_back(self.dir + "/none"))

    def test_the_portal_waits_only_where_wlr_is_installed(self):
        self.assertTrue(self.f.wlr_portal_waits(self.write("wlr.portal", "")))
        self.assertFalse(self.f.wlr_portal_waits(self.dir + "/none"))

    def test_modules_are_looked_up_in_the_kernels_own_list(self):
        dep = self.write("modules.dep",
                         "kernel/net/can/can.ko: \n"
                         "kernel/fs/hfsplus/hfsplus.ko.xz: kernel/a.ko\n")
        self.assertEqual(["can", "hfsplus"], self.f.loadable_modules(
            ["rds", "can", "hfsplus"], dep))
        self.assertTrue(self.f.modules_loadable(
            {"modules": {"can": False}}, dep))
        self.assertFalse(self.f.modules_loadable(
            {"modules": {"rds": False}}, dep))
        self.assertIsNone(self.f.modules_loadable({}, dep))

    def test_pin_tries_count_once_anything_in_the_stack_counts(self):
        bare = self.write("auth", "auth [success=1] pam_unix.so\n"
                          "#auth required pam_faillock.so\n")
        self.assertTrue(self.f.pin_tries_unlimited(bare))
        ours = self.write("auth2", "auth x pam_furios_lockout.so preauth\n")
        self.assertFalse(self.f.pin_tries_unlimited(ours))
        self.assertIsNone(self.f.pin_tries_unlimited(self.dir + "/none"))

    def test_the_rest_reads_the_tools_answers(self):
        self.assertTrue(self.f.sysctl_open({"keys": {"a": {"ok": False}}}))
        self.assertFalse(self.f.sysctl_open({"keys": {"a": {"ok": True},
                                                      "b": {"ok": None}}}))
        self.assertTrue(self.f.modem_checks_fail("  FAIL  utils.py NOT patched"))
        self.assertFalse(self.f.modem_checks_fail("  ok    utils.py"))
        self.assertTrue(self.f.firefox_profiles({"profiles": "3"}))
        self.assertFalse(self.f.firefox_profiles({"profiles": "0"}))
        self.assertFalse(self.f.firefox_profiles({"profiles": "x"}))
        self.assertTrue(self.f.btsave_bites(True))
        self.assertFalse(self.f.btsave_bites(None))
        self.assertTrue(self.f.sensor_unit_off((False, False)))
        self.assertFalse(self.f.sensor_unit_off((True, True)))


class OffersOnlyWhatIsBroken(unittest.TestCase):
    """A repair is shown where its fault is there or where ours is in place -
    then it is the way back. Neither: hidden, not greyed out."""

    def setUp(self):
        self.win = switcher.Window(switcher.Adw.Application())
        self.win._offered = set()
        self.faults = importlib.import_module("miscde.faults")

    def test_ours_or_the_fault_shows_it_neither_hides_it(self):
        for ours, fault, shown in ((True, False, True), (False, True, True),
                                   (False, None, False), (False, False, False)):
            with self.subTest(ours=ours, fault=fault):
                self.win._offered = set()
                row = Recording()
                self.win.offer("x", row, ours, fault)
                self.assertEqual(shown, row.visible)

    def test_a_row_once_shown_stays_while_the_window_is_open(self):
        """Switched off, the fault is gone - and the row with it, under the
        finger that just used it, if this did not hold."""
        row = Recording()
        self.win.offer("x", row, True, False)
        self.win.offer("x", row, False, False)
        self.assertTrue(row.visible)

    def test_echo_suppression_needs_a_vendor_no_or_ours(self):
        win = self.win
        win.dmnr_row = Recording()
        fine = ("state=off\npersistent=no\n"
                "usip:  /dev/usip open to group audio - x\n"
                "  MTK_HANDSFREE_DMNR_SUPPORT = yes\n")
        win.on_dmnr_status(True, fine)
        self.assertFalse(win.dmnr_row.visible)
        win.on_dmnr_status(True, fine.replace("= yes", "= no"))
        self.assertTrue(win.dmnr_row.visible)
        win._offered = set()
        win.on_dmnr_status(True, fine.replace("state=off", "state=on"))
        self.assertTrue(win.dmnr_row.visible)
        win._offered = set()
        win.on_dmnr_status(False, "")
        self.assertFalse(win.dmnr_row.visible)

    def test_the_modem_repairs_need_a_failing_check_or_ours(self):
        win = self.win
        for name in ("modem_group", "modem_row", "mrow_profile",
                     "mrow_health", "mrow_signal"):
            setattr(win, name, Recording())
        win._modem_actual = win._modem_fault = None
        win.on_modem_profile(True, "recorded: shipped\nactual: shipped\n")
        win.on_modem_status(True, "  ok    utils.py\n")
        self.assertFalse(win.modem_group.visible)
        win.on_modem_status(False, "  FAIL  utils.py NOT patched\n")
        self.assertTrue(win.modem_group.visible)
        win._offered = set()
        win._modem_fault = None
        win.on_modem_profile(True, "recorded: fixed\nactual: fixed\n")
        self.assertTrue(win.modem_group.visible)

    def test_hardening_rows_show_what_is_open_or_ours(self):
        win = self.win
        win.sec_group = Recording()
        win.sec_switches = {k: Recording() for k, _t, _s in switcher.Window.PARTS}
        self.enterContext(mock.patch.object(self.faults, "pin_tries_unlimited",
                                            lambda: False))
        self.enterContext(mock.patch.object(self.faults, "modules_loadable",
                                            lambda part: False))
        parts = {"sysctl": {"state": "off", "keys": {"a": {"ok": True}}},
                 "modules": {"state": "off", "modules": {"can": False}},
                 "lockout": {"state": "off", "module": True}}
        win.say_security_parts(parts)
        self.assertEqual([False] * 3,
                         [r.visible for r in win.sec_switches.values()])
        self.assertFalse(win.sec_group.visible, "a heading over nothing")
        parts["sysctl"]["keys"]["a"]["ok"] = False
        parts["lockout"]["state"] = "on"
        win.say_security_parts(parts)
        self.assertTrue(win.sec_switches["sysctl"].visible)
        self.assertFalse(win.sec_switches["modules"].visible)
        self.assertTrue(win.sec_switches["lockout"].visible)
        self.assertTrue(win.sec_group.visible)

    def test_powersave_shows_while_it_bites_or_while_our_off_stands(self):
        audio = importlib.import_module("miscde.pages.audio")
        win = self.win
        win.btsave_row = Recording()
        win.bt_group = Recording()
        win.codec_ok = False
        forget_all_records()
        conf = os.path.join(tempfile.mkdtemp(prefix="miscde-test-"), "config")
        self.enterContext(mock.patch.object(audio, "BATMAN_CONFIG", conf))
        with open(conf, "w") as fh:
            fh.write("BTSAVE=false\n")
        win.sync_btsave()
        self.assertFalse(win.btsave_row.visible, "FuriOS's own false")
        self.assertFalse(win.bt_group.visible)
        original.remember_lines(conf, "BTSAVE", "BTSAVE=true\n")
        win.sync_btsave()
        self.assertTrue(win.btsave_row.visible, "our false is the way back")
        forget_all_records()
        win._offered = set()
        with open(conf, "w") as fh:
            fh.write("BTSAVE=true\n")
        win.sync_btsave()
        self.assertTrue(win.btsave_row.visible)
        self.assertTrue(win.bt_group.visible)

    def test_the_mask_shows_for_a_flapping_slider_or_while_it_is_on(self):
        sw = importlib.import_module("miscde.pages.switches")
        win = self.win
        win.sw_nwk_mask = Recording()
        win.sw_nwk_mask_group = Recording()
        state = {"on": False, "flaps": False}
        self.enterContext(mock.patch.object(sw, "nwk_mask_installed", lambda: True))
        self.enterContext(mock.patch.object(sw, "nwk_mask_enabled",
                                            lambda: state["on"]))
        self.enterContext(mock.patch.object(self.faults, "sliders_flap",
                                            lambda: state["flaps"]))
        win.sync_nwk_mask()
        self.assertFalse(win.sw_nwk_mask_group.visible)
        state["flaps"] = True
        win.sync_nwk_mask()
        self.assertTrue(win.sw_nwk_mask_group.visible)
        win._offered = set()
        state.update(on=True, flaps=False)
        win.sync_nwk_mask()
        self.assertTrue(win.sw_nwk_mask_group.visible)
        win._offered = set()
        self.enterContext(mock.patch.object(sw, "nwk_mask_installed", lambda: False))
        win.sync_nwk_mask()
        self.assertFalse(win.sw_nwk_mask_group.visible, "not installed: hidden")

    def test_firefox_wait_needs_a_profile_or_ours(self):
        win = self.win
        win.gps_firefox = Recording()
        win.gps_firefox_group = Recording()
        win.on_gps_firefox_status(True, "firefox_wait=no\nprofiles=0\n")
        self.assertFalse(win.gps_firefox_group.visible)
        win.on_gps_firefox_status(True, "firefox_wait=no\nprofiles=2\n")
        self.assertTrue(win.gps_firefox_group.visible)

    def test_brightness_shows_for_a_unit_that_is_off_or_ours(self):
        other = importlib.import_module("miscde.pages.other")
        win = self.win
        win.brightness_row = Recording()
        win.brightness_group = Recording()
        settings = mock.Mock()
        settings.get_boolean.return_value = True
        win.brightness_settings = settings
        state = {"s": (True, True)}
        self.enterContext(mock.patch.object(other, "sensor_state",
                                            lambda: state["s"]))
        forget_all_records()
        win.sync_brightness()
        self.assertFalse(win.brightness_group.visible,
                         "the unit as FuriOS ships it: nothing to repair")
        state["s"] = (False, False)
        win.sync_brightness()
        self.assertTrue(win.brightness_group.visible)
        win._offered = set()
        win.brightness_settings = None
        win.sync_brightness()
        self.assertFalse(win.brightness_group.visible)


class ReadsJsonPastAWarning(unittest.TestCase):
    """stderr shares the pipe. A warning in front of the object is not an
    unreadable answer, and an answer that is not an object is none."""

    def test_the_object_after_a_warning_line_is_read(self):
        out = 'Gtk-WARNING: cannot open display\n{"a": 1,\n "b": [2]}\n'
        self.assertEqual({"a": 1, "b": [2]}, switcher.process.json_object(out))

    def test_what_is_not_an_object_is_no_answer(self):
        for out in ("null", "[1, 2]", "", None, "garbage", '{"a": '):
            with self.subTest(out=out):
                self.assertIsNone(switcher.process.json_object(out))

    def test_the_pages_survive_a_null(self):
        win = switcher.Window(switcher.Adw.Application())
        win.sw_row = Recording()
        win.on_switches_status(True, "null")
        self.assertIn("unreadable", win.sw_row.subtitle)
        win.sec_switches = {k: Recording() for k, _t, _s in switcher.Window.PARTS}
        win.on_security_status(True, "[]")
        self.assertTrue(all("unreadable" in r.subtitle
                            for r in win.sec_switches.values()))


class PullsOnlyFromItsOwnRepository(unittest.TestCase):
    """What an update pulls, the installer runs as root. A clone counts as
    ours only by its whole origin, and the origin is asked again when the
    pull happens."""

    URL = "https://github.com/misc-de/furios_audio"

    def clone(self, origin):
        path = tempfile.mkdtemp(prefix="miscde-test-")
        subprocess_real.run(["git", "init", "-q", path], check=True)
        if origin:
            subprocess_real.run(["git", "-C", path, "remote", "add", "origin",
                                 origin], check=True)
        self.addCleanup(shutil_real.rmtree, path, True)
        return path

    def test_one_address_written_four_ways_is_one_repository(self):
        same = switcher.components.same_repository
        for url in (self.URL, self.URL + ".git", self.URL + "/",
                    "git@github.com:misc-de/furios_audio.git"):
            self.assertTrue(same(url, self.URL), url)
        self.assertFalse(same(self.URL + "-fork", self.URL))
        self.assertFalse(same(None, self.URL))

    def test_a_fork_whose_name_contains_ours_is_not_ours(self):
        self.assertFalse(switcher.components.is_clone_of(
            self.clone(self.URL + "-fork"), self.URL))
        self.assertTrue(switcher.components.is_clone_of(
            self.clone(self.URL + ".git"), self.URL))
        self.assertFalse(switcher.components.is_clone_of(
            self.clone(None), self.URL))

    def test_only_origin_counts_not_another_remote(self):
        path = self.clone("https://example.org/evil")
        subprocess_real.run(["git", "-C", path, "remote", "add", "upstream",
                             self.URL], check=True)
        self.assertFalse(switcher.components.is_clone_of(path, self.URL))

    def test_the_guard_before_the_pull_refuses_a_changed_origin(self):
        """Run for real: the shell's way of writing the address has to agree
        with same_repository's, or every update would be refused."""
        comp = {"url": self.URL, "root": False, "tool": "audioctl"}
        for origin, passes in ((self.URL + ".git", True),
                               ("git@github.com:misc-de/furios_audio", True),
                               (self.URL + "-fork", False)):
            with self.subTest(origin=origin):
                path = self.clone(origin)
                argv = switcher.components.source_steps(comp, "update", path)[0][0][0]
                done = subprocess_real.run(argv, capture_output=True, text=True)
                self.assertEqual(passes, done.returncode == 0, done.stdout)


class StaysOpenWhileItInstalls(unittest.TestCase):
    def test_closing_is_refused_while_an_installer_runs(self):
        win = switcher.Window(switcher.Adw.Application())
        said = []
        self.enterContext(mock.patch.object(switcher.Window, "toast",
                                            lambda self, text: said.append(text)))
        win.installing = True
        self.assertTrue(win.on_close_request(win))
        self.assertTrue(said)
        win.forget_password(False)
        self.assertFalse(win.installing)
        self.assertFalse(win.on_close_request(win))


class LetsGoOfAHungInstall(unittest.TestCase):
    """A root install that hangs used to lock the window for good: run_async
    only says "still running" past the deadline, and closing was refused for
    as long as it ran. Past the deadline closing now asks, and stopping ends
    the whole process tree."""

    # Taken when the file is loaded: a test in TheWindow leaves its own
    # stand-in for run_async behind on the module.
    RUN_ASYNC = staticmethod(switcher.process.run_async)

    def setUp(self):
        self.win = switcher.Window(switcher.Adw.Application())
        self.said = []
        self.enterContext(mock.patch.object(
            switcher.Window, "toast", lambda _s, text: self.said.append(text)))
        self.closed = []
        self.win.close = lambda: self.closed.append(True)
        self.win.installing = True

    def tree(self):
        """A real installer stand-in: a shell with a child of its own."""
        proc = subprocess_real.Popen(["sh", "-c", "sleep 300 & sleep 300"],
                                     stderr=subprocess_real.DEVNULL)
        self.addCleanup(lambda: proc.poll() is None and proc.kill())
        for _ in range(100):                   # until the children exist
            if len(switcher.process.process_tree(proc.pid)) >= 3:
                break
            subprocess_real.run(["sleep", "0.02"])
        tree = switcher.process.process_tree(proc.pid)
        self.assertGreaterEqual(len(tree), 3)
        self.assertEqual(str(proc.pid), tree[0])
        return proc, tree

    def test_within_the_deadline_closing_is_still_refused(self):
        self.win.install_overdue_at = 10 ** 9
        with mock.patch("time.monotonic", lambda: 0):
            self.assertTrue(self.win.on_close_request(self.win))
        self.assertTrue(self.said)
        self.assertEqual([], self.closed)

    def test_past_the_deadline_closing_asks_instead(self):
        self.win.install_overdue_at = 1
        gi_stub.recorder.reset()
        self.assertTrue(self.win.on_close_request(self.win))
        self.assertTrue(gi_stub.recorder.of("Adw.AlertDialog"))
        self.assertEqual([], self.closed)
        self.win.on_abort_response(None, "cancel")
        self.assertTrue(self.win.installing)
        self.assertEqual([], self.closed)

    def test_the_installer_deadline_is_written_down(self):
        comp = dict(switcher.COMPONENTS[0], root=False)
        ran = []
        self.enterContext(mock.patch.object(
            switcher.process, "run_async",
            lambda argv, done, **kw: ran.append((argv, done)) or None))
        self.win.installing = False
        self.win.busy = False
        with mock.patch("time.monotonic", lambda: 100.0):
            self.win.run_component(comp, "reinstall", None, "/clone")
        self.assertEqual(["./install.sh"], ran[-1][0])
        self.assertEqual(1900.0, self.win.install_overdue_at)

    def test_stopping_kills_the_tree_and_closes(self):
        proc, tree = self.tree()
        self.win.install_proc = types.SimpleNamespace(
            get_identifier=lambda: str(proc.pid))
        self.win.install_overdue_at = 0
        self.win.on_abort_response(None, "abort")
        proc.wait(timeout=5)
        alive = [pid for pid in tree[1:]
                 if os.path.exists("/proc/%s" % pid)
                 and "Z" not in open("/proc/%s/stat" % pid).read().split()[2]]
        self.assertEqual([], alive)
        self.assertFalse(self.win.installing)
        self.assertEqual([True], self.closed)

    def test_a_root_tree_goes_through_sudo_and_the_askpass_helper(self):
        stopped = []
        self.win.askpass = types.SimpleNamespace(
            helper="/run/x/askpass", stop=lambda: stopped.append(True))
        self.win.install_proc = types.SimpleNamespace(get_identifier=lambda: "4242")
        ran, timers = [], []
        self.enterContext(mock.patch.object(
            switcher.process, "process_tree", lambda pid: [pid, "4243"]))
        self.enterContext(mock.patch.object(
            switcher.process, "run_async",
            lambda argv, done, **kw: ran.append((argv, done, kw))))
        self.enterContext(mock.patch.object(
            switcher.GLib, "timeout_add_seconds",
            lambda secs, fn: timers.append(fn) or 7))
        self.enterContext(mock.patch.object(switcher.os, "kill",
                                            lambda *_a: None))
        self.win.abort_install(self.win.close)
        kill = [r for r in ran if r[0][0] == "sudo" and "-A" in r[0]]
        self.assertEqual(1, len(kill))
        argv, done, kw = kill[0]
        self.assertEqual(["4242", "4243"], argv[-2:])
        self.assertEqual("/run/x/askpass", kw["env"]["SUDO_ASKPASS"])
        # Not closed and the socket still up while sudo may be asking at it.
        self.assertEqual([], self.closed)
        self.assertEqual([], stopped)
        done(True, "")
        self.assertEqual([True], stopped)
        self.assertEqual([True], self.closed)
        self.assertIn(["sudo", "-k"], [r[0] for r in ran])
        timers[0]()                            # late timer: nothing twice
        self.assertEqual([True], self.closed)

    def test_a_sudo_that_hangs_too_does_not_keep_the_window(self):
        self.win.askpass = types.SimpleNamespace(helper="/h", stop=lambda: None)
        self.win.install_proc = types.SimpleNamespace(get_identifier=lambda: "1")
        timers = []
        self.enterContext(mock.patch.object(
            switcher.process, "run_async", lambda *a, **k: None))
        self.enterContext(mock.patch.object(
            switcher.GLib, "timeout_add_seconds",
            lambda secs, fn: timers.append(fn) or 7))
        self.enterContext(mock.patch.object(switcher.os, "kill",
                                            lambda *_a: None))
        self.win.abort_install(self.win.close)
        self.assertEqual([], self.closed)
        timers[0]()
        self.assertEqual([True], self.closed)
        self.assertFalse(self.win.installing)

    def test_a_password_socket_does_not_outlive_the_window(self):
        stopped = []
        self.win.installing = False
        self.win._dmnr_askpass = types.SimpleNamespace(
            stop=lambda: stopped.append(True))
        self.assertFalse(self.win.on_close_request(self.win))
        self.assertEqual([True], stopped)
        self.assertIsNone(self.win._dmnr_askpass)

    def test_run_async_hands_back_the_process(self):
        process = FakeProcess(lines=["x"])
        self.enterContext(mock.patch.object(
            switcher.Gio.Subprocess, "new", lambda *a, **k: process))
        self.assertIs(process, self.RUN_ASYNC(["true"], lambda *_a: None))

if __name__ == "__main__":
    # Built by hand rather than through unittest.main(), which looks for tests
    # in sys.modules["__main__"] - and under the coverage tracer that is the
    # tracer, not this file. It finds nothing there and says so quietly.
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for obj in list(globals().values()):
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
            suite.addTests(loader.loadTestsFromTestCase(obj))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    # What the stub was asked for, for the process that has the real
    # PyGObject to check it against. Written even when tests failed: a wrong
    # method name is worth naming in the same run that found the failure.
    dump = os.environ.get("MISCDE_WIDGET_CALLS")
    if dump:
        with open(dump, "w") as fh:
            fh.write("\n".join(sorted(gi_stub.everything)) + "\n")
    sys.exit(0 if result.wasSuccessful() else 1)
