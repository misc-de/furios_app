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
switcher = importlib.import_module("miscde")


# Which of the optional tools this machine has. The app holds no constants for
# them any more - it looks while it builds a page, because one of them can
# arrive from the components page while the window is open - so a test that
# needs to know which widgets exist looks the same way.
AUDIOCTL = switcher.tools._tool_maybe("audioctl")
DMNR = switcher.tools._tool_maybe("furios-audio-dmnr")
CONTRIB = switcher.tools._tool_maybe("furios-gps-contribute")
MODEMCTL = switcher.tools._tool_maybe("modemctl")
GPSCTL = switcher.tools._tool_maybe("gpsctl")
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

    def labels_in_app(self):
        return re.findall(r'line\.startswith\("([^"]+)"\)', self.app)

    def test_every_label_the_app_looks_for_is_one_audioctl_prints(self):
        for label in self.labels_in_app():
            with self.subTest(label=label):
                other = self.OTHER_SOURCES.get(label)
                if other is None:
                    audioctl = self.tool(self.audioctl, "audioctl")
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
        self.assertRegex(audioctl, r"Test mode:\s+yes")

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

    def comp(self, tool="gpsctl"):
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
                "https://github.com/misc-de/furios_pipewire", base))
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
        comp = self.comp("gpsctl")
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
                         switcher.installer_said(self.comp("gpsctl")))

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
        with open(os.path.join(foreign, "meins.txt"), "w") as fh:
            fh.write("not ours")
        steps = switcher.component_steps(comp, "install", "x", foreign)
        self.assertEqual([], [a for a, _s, _c, _e in steps
                              if a[0] == "git" and "clone" in a])
        done_ = subprocess_real.run(steps[0][0], capture_output=True)
        self.assertNotEqual(0, done_.returncode)
        self.assertIn("in the way", done_.stdout.decode())
        self.assertIn(foreign, done_.stdout.decode())
        self.assertTrue(os.path.exists(os.path.join(foreign, "meins.txt")))

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
            self.comp("killswitch-indicator"), "install", None)
        self.assertEqual([], [argv for argv, _s, _c, _e in steps
                              if argv[0] == "sudo"])

    def test_an_update_guards_the_clone_before_it_pulls(self):
        """A clone with uncommitted work in it is left exactly as it is - and
        told so in a sentence, because a bare exit code explains nothing."""
        steps = switcher.component_steps(self.comp(), "update", "secret_word",
                                            "/home/furios/Projekte/eigen")
        guard = " ".join(steps[0][0])
        self.assertIn("status --porcelain", guard)
        self.assertIn("uncommitted", guard)
        self.assertIn("/home/furios/Projekte/eigen", steps[0][0])
        self.assertIn("pull", steps[1][0])
        self.assertIn("--ff-only", steps[1][0],
                      "a merge is not this app's decision to make")

    def test_an_update_works_in_the_clone_it_was_given(self):
        """Not always our own directory: the clone may be the one somebody
        keeps in ~/Projekte, and that is where the pull has to happen."""
        steps = switcher.component_steps(self.comp(), "update", None, "/woanders")
        for argv, _s, cwd, _e in steps:
            with self.subTest(argv=argv):
                if argv[0] == "git":
                    self.assertIn("/woanders", argv)
                if argv[0].endswith("install.sh"):
                    self.assertEqual("/woanders", cwd)


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

    def add_toast(self, toast):
        # The stub keeps constructor arguments as attributes, so the title of
        # the toast is readable rather than the object's name.
        self.text = getattr(toast, "title", toast)


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


class TheWindow(unittest.TestCase):
    """The window, driven through its own callbacks.

    Building it needs a stub, and a stub proves nothing about GTK. What it does
    prove is the part that has been wrong before: which words end up in front
    of someone, and whether the switch follows the state or fights it.
    """

    def setUp(self):
        self.win = switcher.Window(switcher.Adw.Application())
        names = ["row_profile", "row_server", "row_sinks", "switch_row",
                 "persist_row", "dmnr_row", "btsave_row", "update_btn",
                 "progress", "progress_revealer", "toasts"]
        # The modem widgets only exist when the page was built, and the page is
        # only built when modemctl is installed - so they are swapped in the
        # same way, and only when they are there to swap.
        if MODEMCTL:
            names += ["modem_row", "modem_persist", "modem_progress",
                      "modem_revealer", "mrow_profile", "mrow_health",
                      "mrow_signal", "modem_restore_btn"]
        names.append("rescue_btn")
        if GPSCTL:
            names += ["gps_row", "gps_persist", "gps_progress", "gps_revealer",
                      "grow_profile", "grow_seen", "grow_health",
                      "gps_contrib", "gps_contrib_stats", "gps_restore_btn"]
        if KILLSWITCH:
            names += ["sw_row", "sw_wifi", "sw_bt", "sw_modem",
                      "srow_cam_hal", "srow_cams", "srow_mic",
                      "sw_restore_btn"]
        if BATTCTL:
            names += ["batt_restore_btn"]
        if SECCTL:
            names += ["sec_kernel", "sec_lan", "sec_restore_btn"]
        for name in names:
            setattr(self.win, name, Recording())
        if MODEMCTL:
            self.win.modem_rows = [self.win.modem_row, self.win.modem_persist,
                                   self.win.modem_restore_btn]
        if GPSCTL:
            self.win.gps_rows = [self.win.gps_row, self.win.gps_persist,
                                 self.win.gps_contrib, self.win.gps_restore_btn]
        if KILLSWITCH:
            self.win.sw_rows = [self.win.sw_row, self.win.sw_wifi,
                                self.win.sw_bt, self.win.sw_restore_btn]
        if BATTCTL:
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
                                 + [self.win.sec_lan,
                                    self.win.sec_restore_btn])
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
        self.assertIn("PipeWire owns the HAL", self.win.row_profile.subtitle)
        self.assertIn("until the next reboot", self.win.row_profile.subtitle)
        self.assertIn("older apps", self.win.row_server.subtitle)
        self.assertEqual("droid-sink, droid-voip-sink", self.win.row_sinks.subtitle)
        self.assertTrue(self.win.switch_row.active)

    def test_a_profile_that_survives_a_reboot_says_so(self):
        """The state the phone had for two days while this window said nothing.

        "Profile (persistent)" was never read, so the remembered-switch sat at
        its default - off - on a phone that was on pw-hal for good.
        """
        self.win.on_status(True, self.PERMANENT)
        self.assertIn("permanent", self.win.row_profile.subtitle)
        self.assertTrue(self.win.persist_row.active,
                        "a permanent profile was shown as not remembered")
        self.assertIn("comes back to", self.win.persist_row.subtitle)

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
        self.win.switch_row.active = True
        self.win.on_status(False, "Failed to execute child process")
        self.assertIn("did not answer", self.win.row_profile.subtitle)
        self.assertIn("did not answer", self.win.persist_row.subtitle)
        self.assertTrue(self.win.switch_row.active,
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
        self.assertIn("PipeWire", self.win.switch_row.subtitle)

    def test_an_echo_switch_with_no_script_behind_it_stays_off_limits(self):
        self.win.on_dmnr_status(False, "")
        self.win.set_busy(True)
        self.win.set_busy(False)
        self.assertFalse(self.win.dmnr_row.sensitive)
        self.assertIn("not available", self.win.dmnr_row.subtitle)

    def test_the_shipped_state_is_named_as_such(self):
        self.win.on_status(True, "Profile (active):   standard\nSinks:              x\n")
        self.assertIn("as shipped", self.win.row_profile.subtitle)
        self.assertFalse(self.win.switch_row.active)

    def test_the_tunnel_profile_has_its_own_sentence(self):
        self.win.on_status(True, "Profile (active):   pw-tunnel\n")
        self.assertIn("PipeWire gets a sink", self.win.row_profile.subtitle)

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

    def test_flipping_the_switch_on_asks_for_pw_hal(self):
        self.win.switch_row.active = True
        self.win.persist_row.active = False
        self.win.on_switch(self.win.switch_row, None)
        argv = self.ran[0][0]
        self.assertEqual(["try", "pw-hal"], argv[1:])

    def test_and_with_remember_ticked_it_asks_for_set(self):
        self.win.switch_row.active = True
        self.win.persist_row.active = True
        self.win.on_switch(self.win.switch_row, None)
        self.assertEqual(["set", "pw-hal"], self.ran[0][0][1:])

    def test_flipping_it_off_always_sets_standard_persistently(self):
        """Off means off after a reboot too - a test-mode "off" would come back."""
        self.win.switch_row.active = False
        self.win.on_switch(self.win.switch_row, None)
        self.assertEqual(["set", "standard"], self.ran[0][0][1:])

    def test_the_switch_is_ignored_while_something_is_running(self):
        self.win.busy = True
        self.win.on_switch(self.win.switch_row, None)
        self.assertEqual([], self.ran)

    def test_progress_shows_what_audioctl_says_and_cuts_it_to_a_line(self):
        self.win.on_progress_line("x" * 200)
        self.assertEqual(60, len(self.win.progress.text))

    def test_a_finished_switch_shows_the_last_thing_it_said(self):
        self.win.on_switched(True, "step\nplease check telephony\n")
        self.assertIn("check telephony", str(self.win.toasts.text))

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
        self.assertIn("remembered", self.win.dmnr_row.subtitle)

        self.win.on_dmnr_status(True, "state=on\npersistent=no\n")
        self.assertTrue(self.win.dmnr_row.active)
        self.assertIn("until the next reboot", self.win.dmnr_row.subtitle)

        self.win.on_dmnr_status(True, "state=off\npersistent=no\n")
        self.assertFalse(self.win.dmnr_row.active)
        self.assertIn("stays off", self.win.dmnr_row.subtitle)

        # Switched off now but still marked: the next boot brings it back, and
        # a subtitle saying only "off" would be a lie by omission.
        self.win.on_dmnr_status(True, "state=off\npersistent=yes\n")
        self.assertFalse(self.win.dmnr_row.active)
        self.assertIn("comes back", self.win.dmnr_row.subtitle)

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
        remember = [i for i, t in enumerate(titles) if t.startswith("Remember")]
        self.assertTrue(echo and remember, "rows not built: %s" % titles)
        self.assertLess(echo[0], remember[0])

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
        with mock.patch.object(switcher.tools, "_tool_maybe", return_value=None):
            self.win.refresh_gps_contrib()
        self.assertFalse(self.win.gps_contrib.sensitive)
        self.assertIn("not installed", self.win.gps_contrib.subtitle)

    def test_switching_contribution_on_calls_the_tool(self):
        """With the tool present. Without it the switch does nothing at all,
        which is the subject of the test above."""
        self.win.gps_contrib.active = True
        with mock.patch.object(switcher.tools, "_tool_maybe",
                               return_value="/usr/local/bin/furios-gps-contribute"):
            self.win.on_gps_contrib(self.win.gps_contrib, None)
        self.assertEqual("on", self.ran[0][0][1])

    def test_switching_contribution_off_calls_the_tool_too(self):
        self.win.gps_contrib.active = False
        with mock.patch.object(switcher.tools, "_tool_maybe",
                               return_value="/usr/local/bin/furios-gps-contribute"):
            self.win.on_gps_contrib(self.win.gps_contrib, None)
        self.assertEqual("off", self.ran[0][0][1])

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
        self.win.write_battery_threshold("drain_red_w", 5.0)
        self.assertEqual(["config", "drain_red_w", "5"], self.ran[0][0][1:])

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
        """In that order: battctl restore puts the theme and the icons back
        and deletes what it generated, and a daemon still running would
        write both again within the minute."""
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
        """Two for audio, and two more for the modem when modemctl is here.

        Counted rather than named, because the point is that adding a page
        must not leave one of the others unasked - which is how a window ends
        up showing a state that stopped being true ten minutes ago."""
        self.win.refresh()
        # Audio is counted like the rest now: audioctl can be missing too, and
        # asking a tool that is not there was how a callback ended up at rows
        # nobody had built.
        expected = ((1 + bool(DMNR) if AUDIOCTL else 0)
                    + (2 if MODEMCTL else 0)
                    # profile and status, plus the contribution tool when it
                    # is installed - same installer, but it can be absent in
                    # the seconds after one that stopped half way.
                    + ((2 + bool(CONTRIB)) if GPSCTL else 0)
                    # status --json, plus is-active for the daemon. Not
                    # is-enabled any more: the icons are phosh's plugin list
                    # and the tool answers for them in the same status.
                    + (2 if KILLSWITCH else 0)
                    # one call for the whole security page: status --json
                    # answers the kernel, all three parts and what listens
                    + (1 if SECCTL else 0)
                    # the battery page asks the same three questions
                    + (3 if BATTCTL else 0))
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

    def test_a_status_still_says_what_the_switch_took_down(self):
        """What replaced the position: not where the slider sits, but what
        went with it - which is the part nothing else on the phone says."""
        win = self.switches_win()
        win.on_switches_status(True, self.JSON)
        self.assertEqual("stopped", win.srow_cam_hal.subtitle)

    def test_the_camera_row_says_all_of_them(self):
        """The switch stops one service every camera goes through, so picking
        a single one is not a thing that exists."""
        win = self.switches_win()
        win.on_switches_status(True, self.JSON)
        self.assertIn("all 3", win.srow_cams.subtitle)
        self.assertIn("never one alone", win.srow_cams.subtitle)

    def test_the_modem_row_cannot_be_switched_off(self):
        """Firmware stops the RIL before any program here hears about it, so
        the row is shown switched on and cannot be touched. Checked against
        what the page actually built, not against a stand-in a test wrote."""
        self.switches_win()
        built = switcher.Window(switcher.Adw.Application())
        created = [c for c in recorder.calls if c[0] == "Adw.SwitchRow"]
        modem = [c for c in created
                 if "mobile network" in str(c[2].get("title", "")).lower()]
        self.assertTrue(modem, "no row for the mobile network")
        self.assertIs(True, modem[-1][2].get("active"))
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
        self.assertIn("currently on", win.sw_wifi.subtitle)

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
        self.assertIn("unreadable", win.srow_cam_hal.subtitle)
        self.assertNotIn("running", win.srow_cam_hal.subtitle)

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
        """The four groups on this page carry a title and nothing else. What
        needs saying sits in the row it is about - the way back keeps its
        description, because that text is also the question it asks."""
        self.switches_win()
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        titles = ("Indicator", "1 · Camera", "2 · Network", "3 · Microphone")
        with_paragraph = [c[2].get("title") for c in recorder.calls
                      if c[0] == "Adw.PreferencesGroup"
                      and c[2].get("title") in titles
                      and c[2].get("description")]
        self.assertEqual([], with_paragraph)

    def test_the_microphone_row_says_software_does_not_reach_it(self):
        """The one switch that cuts the line is also the one nothing here can
        see or set. Saying so is the whole content of the row - checked
        against what the page actually built, not against a stand-in a test
        wrote. Without the reason it reads like a defect, so the reason stays
        even though the row got shorter."""
        self.switches_win()
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        rows = [c for c in recorder.calls if c[0] == "Adw.ActionRow"]
        mic = [c for c in rows
               if "not controlled by software" in str(c[2].get("title", "")).lower()]
        self.assertTrue(mic, "no row saying software does not reach it")
        self.assertIn("opening the microphone", str(mic[0][2].get("subtitle", "")))

    def test_an_old_tools_verdict_does_not_reach_the_row(self):
        """Older killswitch-indicators still send a measurement. Putting it on
        screen would turn a three-second-old guess into a position."""
        win = self.switches_win()
        win.on_switches_status(True, self.JSON)
        self.assertIsNone(win.srow_mic.subtitle)

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

    def component(self, tool="gpsctl"):
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
        while refresh asked the module constants, so gpsctl was asked for a
        status that arrived at rows which had never been created - an
        AttributeError inside a callback, where nobody sees it."""
        win = self.without_tool("gpsctl")
        asked = []
        real = switcher.process.run_async
        switcher.process.run_async = lambda argv, done, on_line=None, **kw: asked.append(argv)
        try:
            win.refresh()
        finally:
            switcher.process.run_async = real
        self.assertEqual([], [a for a in asked if "gpsctl" in a[0]])
        # And one that IS here is asked - whichever of them this machine has.
        # Naming audioctl would only measure whether this phone happens to
        # have it installed.
        da = [c["tool"] for c in switcher.COMPONENTS
              if c["tool"] != "gpsctl" and switcher.tools._tool_maybe(c["tool"])]
        if da:
            self.assertTrue([a for a in asked
                             if any(t in a[0] for t in da)], asked)

    def test_a_missing_tool_still_gets_its_tab(self):
        win = self.without_tool("modemctl", "gpsctl", "killswitch-indicator")
        pages = [c[1] for c in recorder.calls
                  if c[0] == "Adw.ViewStack.add_titled_with_icon()" and c[1]]
        self.assertEqual(["audio", "modem", "gps", "switches", "security",
                          "battery"],
                         [args[1] for args in pages])
        self.assertIsNotNone(win)

    def test_a_tab_without_its_tool_shows_the_offer_and_nothing_else(self):
        self.without_tool("gpsctl")
        groups = [c[2] for c in recorder.calls if c[0] == "Adw.PreferencesGroup"]
        offer = [g for g in groups
                   if "not installed" in str(g.get("title", ""))
                   and "gpsctl" in str(g.get("description", ""))]
        self.assertTrue(offer, "no offer on the page of a missing tool")
        # and none of the page's own controls were built
        titles = [str(c[2].get("title", "")) for c in recorder.calls
                 if c[0] == "Adw.SwitchRow"]
        self.assertEqual([], [t for t in titles if "Filter active" in t])

    def test_the_offer_says_where_it_comes_from_and_what_it_would_do(self):
        self.without_tool("gpsctl")
        comp = self.component()
        rows = [str(c[2].get("subtitle", "")) for c in recorder.calls
                  if c[0] == "Adw.ActionRow"]
        self.assertIn(comp["url"], rows)
        self.assertTrue(any(comp["does"] in z for z in rows))
        self.assertTrue(any(switcher.clone_path(comp) in z for z in rows),
                        "the offer has to say where it would put it")
        self.assertTrue(any("sudo" in z for z in rows),
                        "and that this one needs root")

    def test_a_tool_without_root_says_so_in_its_offer(self):
        self.without_tool("killswitch-indicator")
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
        self.win.comp_rows[self.component("gpsctl")["tool"]] = {}
        self.win.ask_component(self.component("gpsctl"), "install")
        self.assertTrue([c for c in recorder.calls
                         if c[0] == "Adw.PasswordEntryRow"])
        recorder.reset()
        self.win.comp_rows[self.component("killswitch-indicator")["tool"]] = {}
        self.win.ask_component(self.component("killswitch-indicator"), "install")
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
        """killswitch-indicator installs into $HOME. Nothing there ever asks
        for a password, so nothing hands one out."""
        log = self.with_stub_askpass(self.component("killswitch-indicator"),
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

    def running_package(self, content):
        """The tree the app would be running from, for PACKAGE_DIR."""
        d = tempfile.mkdtemp()
        self.addCleanup(shutil_real.rmtree, d, True)
        with open(os.path.join(d, "window.py"), "wb") as fh:
            fh.write(content)
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
        self.assertIn("9 new commit(s)", body)
        self.assertNotIn("http", body, "the list names repositories by URL")
        self.assertIn("restarts", body)
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

    def test_the_restart_replaces_this_process_instead_of_starting_a_second(self):
        """A second instance hands its activation to the one already running -
        it would present the OLD window and then die with it."""
        called = []
        real = switcher.os.execv
        switcher.os.execv = lambda prog, argv: called.append((prog, argv))
        try:
            self.win.restart_self()
        finally:
            switcher.os.execv = real
        self.assertEqual(1, len(called))
        prog, argv = called[0]
        self.assertTrue(prog.endswith("misc-de"), prog)
        self.assertEqual([prog], argv)

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

    def with_tool(self, name, path="/usr/local/bin/gpsctl"):
        """_tool_maybe answering as though `name` had just been installed."""
        real = switcher.tools._tool_maybe
        switcher.tools._tool_maybe = lambda n: path if n == name else real(n)
        return real

    def toast_texts(self):
        return [str(c[2].get("title", "")) for c in recorder.calls
                if c[0] == "Adw.Toast"]

    def freshly_installed(self, tool="gpsctl", path="/usr/local/bin/gpsctl"):
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
        self.assertEqual("/usr/local/bin/gpsctl", win.live["gps"])
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
        self.assertEqual(["gps", "switches", "security", "battery"], built)
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
        None to pkexec."""
        win = self.freshly_installed()
        if not switcher.tools.PKEXEC:
            self.skipTest("no pkexec here, so the switch runs nothing")
        self.ran.clear()
        win.busy = False
        win._syncing = False
        win.on_gps_switch(win.gps_row, None)
        argv = self.ran[0][0]
        self.assertIn("/usr/local/bin/gpsctl", argv)

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
        win = self.without_tool("gpsctl")
        recorder.reset()
        # Absent during the window AND during the answer: this machine may
        # well have gpsctl installed, and then the swap would succeed and the
        # test would measure the opposite of what it says.
        real = switcher.tools._tool_maybe
        switcher.tools._tool_maybe = lambda n: None if n == "gpsctl" else real(n)
        try:
            win.component_done(self.component(), True, "ln: Permission denied")
        finally:
            switcher.tools._tool_maybe = real
        self.assertTrue(any("not on the phone" in t
                            for t in self.toast_texts()))
        body = [str(c[2].get("body", "")) for c in recorder.calls
                   if c[0] == "Adw.AlertDialog"]
        self.assertTrue(any("Permission denied" in b for b in body))

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
        """ls-remote asks the server, rev-parse reads the clone. A fetch would
        already write into their .git, a pull into their working tree."""
        comp = self.component()
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.peek_upstream(comp, "/home/furios/Projekte/eigen")
        argv, done, _on_line, _kw = self.ran.pop(0)
        self.assertIn("ls-remote", argv)
        done(True, "abc123\tHEAD")
        argv, done, _on_line, _kw = self.ran.pop(0)
        self.assertIn("rev-parse", argv)
        done(True, "def456")
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
        done(True, "def456")
        return rows[comp["tool"]]["words"]

    def test_a_foreign_clone_that_matches_the_server_is_left_in_peace(self):
        comp = self.component()
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.peek_upstream(comp, "/eigen")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "abc123\tHEAD")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "abc123\n")
        self.assertEqual({}, rows, "a check that found nothing offered something")

    def test_no_answer_from_the_server_is_not_an_update(self):
        comp = self.component()
        rows = self.lines_for(comp)
        self.ran.clear()
        self.win.peek_upstream(comp, "/eigen")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "could not resolve host")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "abc123")
        self.assertEqual({}, rows, "a check that found nothing offered something")

    def test_our_own_clone_is_the_one_that_gets_fetched(self):
        """Where we cloned ourselves, a fetch is ours to run - and counting
        commits is more precise than comparing two hashes."""
        self.win.comp_rows = {}
        for comp in switcher.COMPONENTS:
            self.lines_for(comp)
        self.ran.clear()
        real = switcher.components.is_clone
        switcher.components.is_clone = lambda path: True
        try:
            self.win.check_updates()
        finally:
            switcher.components.is_clone = real
        commands = [" ".join(r[0]) for r in self.ran]
        self.assertTrue(commands)
        for b in commands:
            self.assertIn("fetch", b)
            self.assertIn(switcher.CLONE_HOME, b)

    def test_the_check_runs_once_for_every_installed_tool(self):
        self.win.comp_rows = {}
        for comp in switcher.COMPONENTS:
            self.lines_for(comp)
        self.ran.clear()
        real_is, real_else = switcher.components.is_clone, switcher.components.clone_elsewhere
        switcher.components.is_clone = lambda path: False
        switcher.components.clone_elsewhere = lambda url, base=None: "/eigen"
        try:
            self.win.check_updates()
        finally:
            switcher.components.is_clone, switcher.components.clone_elsewhere = real_is, real_else
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

    SEC_JSON = """{
      "kernel": {"release": "4.19.325-furiphone-radon", "base": "4.19.325",
                 "series": "4.19", "eol": "2024-12-05",
                 "last_release": "4.19.325", "maintained": false},
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

    def test_the_kernel_line_is_the_premise_not_a_banner(self):
        """Without it the three switches read as ordinary tightening of a
        healthy system, and somebody could reasonably switch them off for
        convenience."""
        win = self.security_win()
        win.on_security_status(True, self.SEC_JSON)
        self.assertIn("4.19.325", win.sec_kernel.title)
        self.assertIn("end of life", win.sec_kernel.subtitle)

    def test_a_maintained_kernel_stops_the_warning(self):
        """A phone that one day boots something current must not keep
        repeating a warning that has stopped being true - which is why this
        reads secctl's answer instead of carrying the version in the app."""
        win = self.security_win()
        win.on_security_status(True, self.SEC_JSON.replace(
            '"maintained": false', '"maintained": true'))
        self.assertNotIn("end of life", win.sec_kernel.subtitle)

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
        for key in ("sysctl", "modules", "firewall"):
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

    def test_a_switch_off_reverts_that_part(self):
        win = self.security_win()
        win._loading = False
        win.busy = False
        row = win.sec_switches["firewall"]
        row.set_active(False)
        self.ran.clear()
        win.on_security_switch(row, None, "firewall")
        self.assertEqual(self.ran[0][0][-3:], ["set", "firewall", "off"])

    def test_the_firewall_says_what_it_is_still_missing(self):
        """It refuses to come up without a home network, and the row has to
        say that before somebody presses a switch that cannot work."""
        win = self.security_win()
        win.on_security_status(True, self.SEC_JSON.replace(
            '"lan": "192.168.0.0/24"', '"lan": ""'))
        self.assertIn("home network",
                      win.sec_switches["firewall"].subtitle)

    def test_the_home_network_is_never_widened_by_an_empty_entry(self):
        """An empty field is somebody clearing it, not somebody asking for
        "any" - and the one value that decides who may reach SSH must not be
        set from nothing."""
        win = self.security_win()
        win.busy = False
        win.sec_lan.set_text("   ")
        self.ran.clear()
        win.on_security_lan(win.sec_lan)
        self.assertEqual([], self.ran)

    def test_the_home_network_is_handed_over_as_typed(self):
        """secctl validates it as CIDR and refuses anything else, so the app
        does not second-guess the text - it passes it and reports what comes
        back."""
        win = self.security_win()
        win.busy = False
        win.sec_lan.set_text("10.1.2.0/24")
        self.ran.clear()
        win.on_security_lan(win.sec_lan)
        self.assertEqual(self.ran[0][0][-2:], ["lan", "10.1.2.0/24"])

    def test_a_refusal_is_shown_with_its_reason(self):
        """The firewall's refusal is a sentence, not an error code, and it is
        the one thing somebody needs in order to act."""
        win = self.security_win()
        recorder.reset()
        win.after_security(False, "The firewall needs to know which network",
                           "firewall", "on")
        bodies = [str(c[2].get("body", "")) for c in recorder.calls
                  if c[0] == "Adw.AlertDialog"]
        self.assertTrue(any("which network" in b for b in bodies), bodies)

    def test_the_listening_list_is_capped(self):
        """A phone screen, and the list is here to make a point rather than
        be an inventory."""
        win = self.security_win()
        win.on_security_status(True, self.SEC_JSON)
        self.assertEqual(5, len(win.sec_open_rows))
        self.assertIn("and 1 more", win.sec_open_rows[-1].title)

    def test_an_open_port_says_whether_the_chain_covers_it(self):
        win = self.security_win()
        win.on_security_status(True, self.SEC_JSON)
        self.assertIn("only from the home network", win.sec_open_rows[0].subtitle)
        win.on_security_status(True, self.SEC_JSON.replace(
            '"firewall": {"state": "on"', '"firewall": {"state": "off"'))
        self.assertIn("mobile included", win.sec_open_rows[0].subtitle)

    def test_the_way_back_takes_all_three(self):
        win = self.security_win()
        win.busy = False
        self.ran.clear()
        win.on_security_restore(None)
        self.assertEqual(self.ran[0][0][-2:], ["revert", "all"])

    def test_a_tool_that_did_not_answer_is_not_shown_as_a_reading(self):
        win = self.security_win()
        win.on_security_status(False, "")
        self.assertIn("did not answer", win.sec_kernel.title)

    def test_every_page_offers_the_same_way_back(self):
        """Counted, not named: adding a page must not quietly add a fifth
        shape of this."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        expected = (1 + bool(MODEMCTL) + bool(GPSCTL)
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

    def test_each_way_back_says_what_it_costs(self):
        """The same button on every page is only honest if the text next to
        it is not the same every time."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        texts = {str(c[2].get("description", ""))
                 for c in recorder.calls if c[0] == "Adw.PreferencesGroup"
                 and c[2].get("title") == switcher.Window.RESTORE_TITLE}
        expected = (1 + bool(MODEMCTL) + bool(GPSCTL)
                    + bool(KILLSWITCH) + bool(BATTCTL) + bool(SECCTL))
        self.assertEqual(expected, len(texts))

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

    def test_the_location_way_back_switches_and_remembers(self):
        """"set", not "try": what it restores is what the next boot comes back
        to, the same promise the other pages make."""
        win = self.gps_win()
        self.ran.clear()
        win.busy = False
        win.on_gps_restore(None)
        self.assertEqual(["set", "shipped"], list(self.ran[-1][0][-2:]))
        win.on_gps_restored(True, "")
        self.assertIn("IP position", str(win.toasts.text))

    def test_the_switches_way_back_undoes_what_this_page_added(self):
        """Four commands, because two owners: the tool holds the extra radios
        and the shell's plugin list, systemd holds the unit. The sliders are
        not among them - they are hardware and nothing here reaches them."""
        win = self.switches_win()
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

    def test_a_step_that_fails_stops_the_rest(self):
        """Half done is reported, never passed off as success."""
        win = self.switches_win()
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

    def test_without_pkexec_the_location_way_back_says_so(self):
        win = self.gps_win()
        real = switcher.tools.PKEXEC
        try:
            switcher.tools.PKEXEC = None
            self.ran.clear()
            win.busy = False
            win.on_gps_restore(None)
            self.assertEqual([], self.ran)
            self.assertIn("pkexec", str(win.toasts.text))
        finally:
            switcher.tools.PKEXEC = real

    def test_a_location_way_back_that_fails_is_reported(self):
        win = self.gps_win()
        win.on_gps_restored(False, "gpsctl: no")
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
        self.assertIn("currently on", win.sw_wifi.subtitle)

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
        self.assertIn("did not answer", win.srow_cam_hal.subtitle)
        self.assertIn("did not answer", win.srow_cams.subtitle)

    def test_an_unfetched_camera_list_says_how_to_fetch_it(self):
        """The list needs root once. Until then the row must not imply that
        one camera is spared - the switch takes all of them either way."""
        win = self.switches_win()
        win.on_switches_status(True, self.JSON.replace(
            '"cameras": ["Back", "Front", "Back"]', '"cameras": []'))
        self.assertIn("all of them", win.srow_cams.subtitle)
        self.assertIn("--refresh", win.srow_cams.subtitle)

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
        self.assertIn("Could not change wifi", str(win.toasts.text))
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

    def test_the_switch_asks_for_the_rights_it_needs(self):
        win = self.modem_win()
        win.modem_persist.active = True
        win.modem_row.active = False
        win.on_modem_switch(win.modem_row, None)
        argv = self.ran[-1][0]
        self.assertIn("pkexec", argv[0])
        self.assertEqual(["set", "shipped"], argv[2:])

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

    # --- the GPS page ------------------------------------------------------
    #
    # Built only when gpsctl is installed, same as the modem page. What is
    # different here is the "off" side: it is not a neutral shipped state but
    # one that publishes the carrier's exit node as a position, and every row
    # on this page is checked for saying so.

    def test_without_gpsctl_the_page_has_no_controls(self):
        win = self.without_tool("gpsctl")
        self.assertEqual([], win.gps_rows)

    def gps_win(self):
        if not GPSCTL:
            self.skipTest("no gpsctl on this machine, so no GPS page")
        return self.win

    def test_the_row_names_whose_ip_address_it_is(self):
        """Not "this phone's" - the position comes from the carrier's exit
        node, and calling it the phone's reads as if it sat in the device."""
        win = self.gps_win()
        win.on_gps_profile(True, "recorded: fixed\nactual:   fixed\n")
        self.assertIn("carrier's IP address", win.gps_row.subtitle)
        win.on_gps_profile(True, "recorded: shipped\nactual:   shipped\n")
        self.assertIn("carrier's IP address", win.gps_row.subtitle)

    def test_the_fix_group_carries_no_essay(self):
        """The switch's own subtitle says what on and off mean; the paragraph
        above it said the same thing a third time."""
        self.gps_win()                         # skips when there is no page
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        place = [c for c in recorder.calls if c[0] == "Adw.PreferencesGroup"
               and c[2].get("title") == "GPS fix"]
        self.assertTrue(place, "no GPS fix group")
        self.assertNotIn("description", place[0][2])

    def test_beacondb_sits_under_the_fix_and_not_above_it(self):
        """Two directions, and the page is read top down: the fix decides what
        this phone accepts, contributing decides what it hands out. The switch
        somebody opened the tab for comes first."""
        self.gps_win()                         # skips when there is no page
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        titles = [str(c[1][0].title) for c in recorder.calls
                  if c[0] == "Adw.PreferencesPage.add()" and c[1]]
        self.assertIn("GPS fix", titles)
        self.assertLess(titles.index("GPS fix"),
                        titles.index("Contribute to beaconDB"), titles)

    def test_the_filter_being_on_reads_as_on(self):
        win = self.gps_win()
        win.on_gps_profile(True, "recorded: fixed\nactual:   fixed\n")
        self.assertTrue(win.gps_row.get_active())
        self.assertIn("thrown away", win.grow_profile.subtitle)

    def test_the_filter_being_off_says_what_off_means(self):
        """"Off" here is not an absence of something. It is the carrier's exit
        node being published as an observation, and a row that said "as
        shipped" and stopped there would be hiding the only part that
        matters."""
        win = self.gps_win()
        win.on_gps_profile(True, "recorded: shipped\nactual:   shipped\n")
        self.assertFalse(win.gps_row.get_active())
        self.assertIn("IP position is published", win.grow_profile.subtitle)

    def test_a_gps_try_says_the_next_boot_will_undo_it(self):
        win = self.gps_win()
        win.on_gps_profile(True, "recorded: fixed\nactual:   shipped\n")
        self.assertIn("next boot", win.grow_profile.subtitle)

    def test_mixed_survives_the_return_code_that_comes_with_it(self):
        """gpsctl prints recorded/actual and *then* exits 1 when the two halves
        disagree. Reading the return code first turns the one state somebody
        most needs to see into "gpsctl did not answer"."""
        win = self.gps_win()
        win.on_gps_profile(False, "recorded: fixed\nactual:   mixed\n")
        self.assertIn("half applied", win.grow_profile.subtitle)
        self.assertTrue(win.gps_ok, "a failing exit code was read as no answer")

    def test_gpsctl_not_answering_is_said_and_not_guessed(self):
        win = self.gps_win()
        win.on_gps_profile(False, "")
        self.assertIn("did not answer", win.grow_profile.subtitle)
        self.assertFalse(win.gps_row.sensitive,
                         "the switch stayed usable with nothing behind it")

    def test_a_gps_page_with_no_answer_stays_unusable(self):
        win = self.gps_win()
        win.on_gps_profile(False, "")
        win.set_busy(True)
        win.set_busy(False)
        self.assertFalse(win.gps_row.sensitive)
        self.assertFalse(win.gps_persist.sensitive)

    def test_the_counters_are_said_back_as_gpsctl_printed_them(self):
        win = self.gps_win()
        win.on_gps_status(True,
                          "  ok    [wifi] enable = true\n"
                          "  FAIL  furios-gps-proxy.service is not installed\n"
                          "since boot: 5 asked, 0 located, 5 IP fallbacks rejected\n")
        self.assertIn("1 in place, 1 not", win.grow_health.subtitle)
        self.assertIn("5 IP fallbacks rejected", win.grow_seen.subtitle)

    def test_having_counted_nothing_is_not_dressed_up_as_a_fault(self):
        win = self.gps_win()
        win.on_gps_status(True, "  ok    [wifi] enable = true\n")
        self.assertIn("nothing counted yet", win.grow_seen.subtitle)
        self.assertIn("1 in place", win.grow_health.subtitle)

    def test_no_gps_output_at_all_is_admitted(self):
        win = self.gps_win()
        win.on_gps_status(False, "")
        self.assertIn("did not answer", win.grow_health.subtitle)

    def test_the_gps_switch_asks_for_the_rights_it_needs(self):
        win = self.gps_win()
        win.gps_persist.active = True
        win.gps_row.active = False
        win.on_gps_switch(win.gps_row, None)
        argv = self.ran[-1][0]
        self.assertIn("pkexec", argv[0])
        self.assertEqual(["set", "shipped"], argv[2:])

    def test_a_gps_try_is_a_try(self):
        win = self.gps_win()
        win.gps_persist.active = False
        win.gps_row.active = True
        win.on_gps_switch(win.gps_row, None)
        self.assertEqual(["try", "fixed"], self.ran[-1][0][2:])

    def test_turning_the_filter_off_says_what_was_turned_off(self):
        """A toast saying "Done" after this switch would be the one moment the
        app had to tell somebody their phone now reports the carrier's exit
        node, and spent it on a word that means nothing."""
        win = self.gps_win()
        win.gps_row.active = False
        win.on_gps_switched(True, "")
        self.assertIn("published again", str(win.toasts.text))

    def test_turning_the_filter_on_says_so_too(self):
        win = self.gps_win()
        win.gps_row.active = True
        win.on_gps_switched(True, "")
        self.assertIn("refused", str(win.toasts.text))

    def test_a_failed_gps_switch_is_not_reported_as_success(self):
        win = self.gps_win()
        win.on_gps_switched(False, "pkexec: refused")
        self.assertIn("failed", str(win.toasts.text).lower())

    def test_the_gps_switch_needs_pkexec_to_exist(self):
        win = self.gps_win()
        real = switcher.tools.PKEXEC
        try:
            switcher.tools.PKEXEC = None
            before = len(self.ran)
            win.on_gps_switch(win.gps_row, None)
            self.assertEqual(before, len(self.ran), "ran the switch without pkexec")
            self.assertIn("pkexec", str(win.toasts.text))
        finally:
            switcher.tools.PKEXEC = real

    def test_a_gps_switch_while_busy_is_ignored(self):
        win = self.gps_win()
        win.busy = True
        before = len(self.ran)
        win.on_gps_switch(win.gps_row, None)
        self.assertEqual(before, len(self.ran))

    def test_the_checks_are_counted_the_way_modemctl_prints_them(self):
        win = self.modem_win()
        win.on_modem_status(True,
                            "  ok    utils.py\n"
                            "  ok    mobile default route: ccmni0\n"
                            "  FAIL  resolv.conf -> systemd-resolved\n"
                            "  ok    signal quality 26% (recent)\n")
        self.assertIn("3 in place, 1 not", win.mrow_health.subtitle)
        self.assertIn("26%", win.mrow_signal.subtitle)

    def test_everything_in_place_is_not_dressed_up_with_a_zero(self):
        win = self.modem_win()
        win.on_modem_status(True, "  ok    utils.py\n  ok    main.py\n")
        self.assertEqual("2 in place", win.mrow_health.subtitle)

    def test_a_status_without_a_signal_line_says_so(self):
        win = self.modem_win()
        win.on_modem_status(True, "  ok    utils.py\n")
        self.assertIn("not readable", win.mrow_signal.subtitle)

    def test_a_status_that_failed_but_printed_is_still_read(self):
        """modemctl exits non-zero when a check fails - and then its output is
        exactly the thing worth showing."""
        win = self.modem_win()
        win.on_modem_status(False, "  ok    utils.py\n  FAIL  mobile default route\n")
        self.assertIn("1 in place, 1 not", win.mrow_health.subtitle)

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

    def test_a_finished_switch_repeats_modemctls_last_word(self):
        win = self.modem_win()
        win.on_modem_switched(True, "Recorded: shipped. This survives a reboot.\n\n")
        self.assertIn("Recorded: shipped", str(win.toasts.text))

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

    def test_the_restore_button_ignores_the_remember_switch(self):
        win = self.modem_win()
        win.modem_persist.active = False
        win.on_modem_restore(None)
        self.assertEqual(["set", "shipped"], self.ran[-1][0][2:])

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

    def test_not_remembering_is_a_try_and_not_a_set(self):
        win = self.modem_win()
        win.modem_persist.active = False
        win.modem_row.active = True
        win.on_modem_switch(win.modem_row, None)
        self.assertEqual(["try", "fixed"], self.ran[-1][0][2:])

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
        self.assertIn("takes a moment", self.win.switch_row.subtitle)
        self.win.switch_row.active = True
        self.win.set_busy(False)
        self.assertTrue(self.win.switch_row.sensitive)
        self.assertIn("talks to the HAL", self.win.switch_row.subtitle)
        self.win.switch_row.active = False
        self.win.set_busy(False)
        self.assertIn("as shipped", self.win.switch_row.subtitle)

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

        systemctl is the last line and it fails here - there is no such unit
        - which is why the file is what gets checked and not the exit code.
        Everything this script does to the config happens before it.
        """
        with tempfile.NamedTemporaryFile("w", suffix=".conf",
                                         delete=False) as handle:
            handle.write(contents)
            path = handle.name
        try:
            subprocess_real.run(
                ["sh", "-c", self.audio.BTSAVE_SCRIPT, "sh", path,
                 "miscde-no-such-unit.service", value],
                capture_output=True)
            return Path(path).read_text()
        finally:
            os.unlink(path)

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
        off = switcher.Window.btsave_words(False)
        self.assertIn("stays on", off)

    def test_with_no_batman_the_row_says_that_rather_than_off(self):
        self.assertIn("batman", switcher.Window.btsave_words(None))


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
        self.assertIs(switcher.App, mod.App)

    def test_it_looks_beside_itself_first(self):
        """From the clone, ./misc-de.py has to run the clone - not whatever
        is installed in /usr/local. That is the whole point of running it
        from the source tree, and the order of that list is the only thing
        that decides it."""
        text = (ROOT / "misc-de.py").read_text()
        here = text.index("HERE")
        self.assertLess(here, text.index("/usr/local/lib/misc-de"))


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
        for tool in ("audioctl", "modemctl", "gpsctl",
                     "killswitch-indicator", "battctl"):
            self.assertNotIn("command -v " + tool, text)
        self.assertNotIn('command -v "$tool"', text)


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
    sys.exit(0 if result.wasSuccessful() else 1)
