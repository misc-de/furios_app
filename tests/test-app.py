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
import os
import re
import shutil as shutil_real
import subprocess as subprocess_real
import sys
import tempfile
import types
import unittest
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


switcher = load(ROOT / "misc-de.py", "switcher")


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
        cls.app = (ROOT / "misc-de.py").read_text()
        cls.audioctl = cls.installed(switcher.AUDIOCTL)
        cls.dmnr = cls.installed(switcher.DMNR)

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

    def labels_in_app(self):
        return re.findall(r'line\.startswith\("([^"]+)"\)', self.app)

    def test_every_label_the_app_looks_for_is_one_audioctl_prints(self):
        audioctl = self.tool(self.audioctl, "audioctl")
        for label in self.labels_in_app():
            with self.subTest(label=label):
                self.assertIn(label, audioctl,
                              "the app waits for a line audioctl never prints")

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
    """What each component offers, decided away from the widgets.

    The case that matters most is a clone somebody keeps themselves: this app
    fetches into its own directory and never pulls in a working tree that is
    not its own - there may be uncommitted work in it.
    """

    def test_a_missing_tool_is_offered(self):
        self.assertEqual(("install", "Install", True),
                         switcher.component_state(False, False, False, None))

    def test_a_clone_of_ours_that_is_behind_offers_an_update(self):
        zustand, text, aktiv = switcher.component_state(True, True, False, 3)
        self.assertEqual(("update", True), (zustand, aktiv))
        self.assertIn("3", text)

    def test_a_clone_that_is_current_offers_nothing(self):
        self.assertEqual(("current", "Up to date", False),
                         switcher.component_state(True, True, False, 0))

    def test_an_unanswerable_check_still_lets_you_try(self):
        """No network, no upstream: "up to date" would be a claim nobody
        checked."""
        zustand, _text, aktiv = switcher.component_state(True, True, False, None)
        self.assertEqual(("update", True), (zustand, aktiv))

    def test_somebody_elses_clone_is_reported_and_left_alone(self):
        zustand, text, aktiv = switcher.component_state(True, False, True, None)
        self.assertEqual(("own", False), (zustand, aktiv))
        self.assertIn("you", text.lower())

    def test_an_installed_tool_without_a_clone_can_fetch_its_source(self):
        """So that updates become visible at all - without a clone there is
        nothing to compare against."""
        self.assertEqual(("source", "Fetch the source", True),
                         switcher.component_state(True, False, False, None))

    def test_every_component_names_a_repository_and_what_it_does(self):
        for comp in switcher.COMPONENTS:
            with self.subTest(tool=comp["tool"]):
                self.assertTrue(comp["url"].startswith("https://github.com/"))
                self.assertGreater(len(comp["does"]), 30)
                self.assertIn(comp["page"], ("Audio", "Modem", "GPS", "Switches"))

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
                switcher.clone_elsewhere("https://github.com/misc-de/furios_gps", base))
            self.assertIsNone(switcher.clone_elsewhere(
                "https://github.com/misc-de/furios_pipewire", base))
        finally:
            shutil_real.rmtree(base, ignore_errors=True)

    def test_a_directory_without_a_git_config_is_not_a_clone(self):
        base = tempfile.mkdtemp()
        try:
            os.makedirs(os.path.join(base, "nur_ein_ordner"))
            self.assertIsNone(switcher.clone_elsewhere("https://x/y", base))
            self.assertIsNone(switcher.clone_elsewhere("https://x/y", base + "/weg"))
        finally:
            shutil_real.rmtree(base, ignore_errors=True)

    def test_what_git_answers_is_read_as_a_number_or_as_nothing(self):
        self.assertEqual(0, switcher.behind_count("0\n"))
        self.assertEqual(7, switcher.behind_count("7"))
        self.assertIsNone(switcher.behind_count(""))
        self.assertIsNone(switcher.behind_count("fatal: no upstream configured"))


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

    def tearDown(self):
        switcher.Gio.Subprocess.new = self.original_new
        switcher.Gio.DataInputStream.new = self.original_stream

    def arrange(self, **kwargs):
        process = FakeProcess(**kwargs)
        switcher.Gio.Subprocess.new = lambda *a, **k: process
        switcher.Gio.DataInputStream.new = lambda pipe: FakeStream(process)
        return process

    def test_output_is_collected_and_handed_over_at_the_end(self):
        self.arrange(lines=["one", "two"])
        seen = []
        switcher.run_async(["audioctl", "status"], lambda ok, out: seen.append((ok, out)))
        self.assertEqual(seen, [(True, "one\ntwo")])

    def test_with_a_line_callback_the_lines_arrive_as_they_come(self):
        self.arrange(lines=["step one", "step two", ""])
        lines, done = [], []
        switcher.run_async(["audioctl", "set", "pw-hal"],
                           lambda ok, out: done.append((ok, out)),
                           on_line=lines.append)
        self.assertEqual(lines, ["step one", "step two"])
        self.assertEqual(done, [(True, "step one\nstep two")])

    def test_a_command_that_fails_is_reported_as_such(self):
        self.arrange(lines=["went wrong"], ok=False)
        seen = []
        switcher.run_async(["audioctl", "status"], lambda ok, out: seen.append((ok, out)))
        self.assertEqual(seen[0][0], False)

    def test_a_command_that_will_not_start_is_reported(self):
        def refuse(*_a, **_k):
            raise switcher.GLib.Error("no such file")
        switcher.Gio.Subprocess.new = refuse
        seen = []
        switcher.run_async(["nothing"], lambda ok, out: seen.append((ok, out)))
        self.assertEqual(seen[0][0], False)
        self.assertIn("no such file", seen[0][1])

    def test_a_pipe_that_breaks_while_reading_is_reported(self):
        self.arrange(lines=["a"], fail_at="read")
        seen = []
        switcher.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)),
                           on_line=lambda _l: None)
        self.assertEqual(seen[0][0], False)

    def test_a_process_that_never_finishes_is_reported(self):
        self.arrange(lines=[], fail_at="wait")
        seen = []
        switcher.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)),
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
        switcher.run_async(["audioctl", "status"],
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
        switcher.run_async(["audioctl"], lambda ok, out: None)
        self.assertGreaterEqual(fired[0][0], 60)

    def test_an_answer_that_arrives_is_not_answered_twice(self):
        """Both the reader and the watchdog can reach the callback. Calling it
        twice would refresh the window on top of a switch already in flight."""
        self.arrange(lines=["done"])
        fired = self.catch_timer()
        seen = []
        switcher.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)))
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
        switcher.run_async(["audioctl"], lambda ok, out: seen.append(out))
        self.assertEqual(["fine"], seen)

    def test_a_line_reading_call_is_bounded_too(self):
        process = self.arrange(lines=["step one"], fail_at="hang")
        fired = self.catch_timer()
        seen = []
        switcher.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)),
                           on_line=lambda _l: None)
        fired[0][1]()
        self.assertIn("did not answer", seen[0][1])
        self.assertTrue(process.killed)

    def test_a_password_goes_into_the_pipe_and_a_launcher_sets_the_directory(self):
        """The two things the components page needs from run_async: a working
        directory, and a way in that is not the command line."""
        process = self.arrange(lines=["done"])
        gebaut = {}

        class FakeLauncher:
            def set_cwd(self, path):
                gebaut["cwd"] = path

            def spawnv(self, argv):
                gebaut["argv"] = argv
                return process

        real = switcher.Gio.SubprocessLauncher.new
        switcher.Gio.SubprocessLauncher.new = lambda flags: FakeLauncher()
        try:
            seen = []
            switcher.run_async(["./install.sh"], lambda ok, out: seen.append(ok),
                               cwd="/tmp/klon", stdin="wort\n")
        finally:
            switcher.Gio.SubprocessLauncher.new = real
        self.assertEqual("/tmp/klon", gebaut.get("cwd"))
        self.assertEqual(["./install.sh"], gebaut.get("argv"))
        self.assertEqual("wort\n", process.stdin)
        self.assertEqual([True], seen)

    def test_without_a_directory_or_a_pipe_nothing_is_launched_the_long_way(self):
        """The plain path stays plain - every other call in this app takes it."""
        self.arrange(lines=["x"])
        angefasst = []
        real = switcher.Gio.SubprocessLauncher.new
        switcher.Gio.SubprocessLauncher.new = lambda flags: angefasst.append(1)
        try:
            switcher.run_async(["audioctl", "status"], lambda ok, out: None)
        finally:
            switcher.Gio.SubprocessLauncher.new = real
        self.assertEqual([], angefasst)

    def test_a_broken_pipe_without_a_line_callback_is_reported(self):
        self.arrange(lines=["x"], fail_at="communicate")
        seen = []
        switcher.run_async(["audioctl"], lambda ok, out: seen.append((ok, out)))
        self.assertEqual(seen[0][0], False)


class Recording:
    """A widget that remembers what it was told, and answers what a test set."""

    def __init__(self, active=False):
        self.subtitle = None
        self.sensitive = True
        self.active = active
        self.label = None
        self.text = None
        self.fraction = None
        self.revealed = None

    def set_subtitle(self, text):
        self.subtitle = text

    def set_sensitive(self, value):
        self.sensitive = value

    def set_active(self, value):
        self.active = value

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

    def set_reveal_child(self, value):
        self.revealed = value

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
            self.assertIsNone(switcher._tool_maybe("modemctl"))
        finally:
            switcher.os.access, switcher.shutil.which = original_access, original_which

    def test_a_tool_only_on_the_search_path_is_still_found(self):
        original_access, original_which = switcher.os.access, switcher.shutil.which
        switcher.os.access = lambda path, mode: False
        switcher.shutil.which = lambda name: "/opt/bin/" + name
        try:
            self.assertEqual("/opt/bin/modemctl", switcher._tool_maybe("modemctl"))
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
                 "persist_row", "dmnr_row", "refresh_btn", "progress",
                 "progress_revealer", "toasts"]
        # The modem widgets only exist when the page was built, and the page is
        # only built when modemctl is installed - so they are swapped in the
        # same way, and only when they are there to swap.
        if switcher.MODEMCTL:
            names += ["modem_row", "modem_persist", "modem_progress",
                      "modem_revealer", "mrow_profile", "mrow_health",
                      "mrow_signal", "modem_restore_btn"]
        names.append("rescue_btn")
        if switcher.GPSCTL:
            names += ["gps_row", "gps_persist", "gps_progress", "gps_revealer",
                      "grow_profile", "grow_seen", "grow_health",
                      "gps_restore_btn"]
        if switcher.KILLSWITCH:
            names += ["sw_row", "sw_persist", "sw_wifi", "sw_bt", "sw_modem",
                      "srow_cam", "srow_cam_hal", "srow_cams", "srow_net",
                      "srow_mic", "sw_restore_btn"]
        for name in names:
            setattr(self.win, name, Recording())
        if switcher.MODEMCTL:
            self.win.modem_rows = [self.win.modem_row, self.win.modem_persist,
                                   self.win.modem_restore_btn]
        if switcher.GPSCTL:
            self.win.gps_rows = [self.win.gps_row, self.win.gps_persist,
                                 self.win.gps_restore_btn]
        if switcher.KILLSWITCH:
            self.win.sw_rows = [self.win.sw_row, self.win.sw_persist,
                                self.win.sw_wifi, self.win.sw_bt,
                                self.win.sw_restore_btn]
        self.ran = []
        self.original = switcher.run_async
        # Four fields, not three: the components page passes cwd, stdin and a
        # longer timeout, and a test that could not see them could not check
        # that the password goes through the pipe and never through argv.
        switcher.run_async = lambda argv, done, on_line=None, **kw: self.ran.append(
            (argv, done, on_line, kw))

    def tearDown(self):
        switcher.run_async = self.original

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
        self.win.on_dmnr_status(True, "state=on\nfile: ...\n")
        self.assertTrue(self.win.dmnr_row.active)
        self.assertIn("modified tuning file", self.win.dmnr_row.subtitle)
        self.win.on_dmnr_status(True, "state=off\n")
        self.assertFalse(self.win.dmnr_row.active)
        self.assertIn("Vendor setting", self.win.dmnr_row.subtitle)

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
        expected = (2 + (2 if switcher.MODEMCTL else 0)
                    + (2 if switcher.GPSCTL else 0)
                    # status --json, plus is-active and is-enabled for the unit
                    + (3 if switcher.KILLSWITCH else 0))
        self.assertEqual(expected, len(self.ran))

    def test_the_tabs_sit_under_the_header_not_at_the_foot(self):
        """Where they switch from, not where a page ends: at the foot the bar
        sat a thumb's width from "Restore shipped state"."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        oben = [c for c in recorder.calls
                if c[0] == "Adw.ToolbarView.add_top_bar()" and c[1]]
        unten = [c for c in recorder.calls
                 if c[0] == "Adw.ToolbarView.add_bottom_bar()" and c[1]]
        self.assertEqual([], unten)
        # header bar plus the switcher
        self.assertEqual(2, len(oben), oben)

    def test_the_switches_page_asks_for_json_and_for_the_unit(self):
        """The page needs both: the tool knows the switches, systemd knows
        whether the indicator runs and whether it survives a boot."""
        if not switcher.KILLSWITCH:
            self.skipTest("killswitch-indicator not installed")
        self.win.refresh()
        aufrufe = [" ".join(a[0]) for a in self.ran]
        self.assertTrue(any("status --json" in a for a in aufrufe), aufrufe)
        self.assertTrue(any("is-active killswitch-indicator" in a for a in aufrufe), aufrufe)
        self.assertTrue(any("is-enabled killswitch-indicator" in a for a in aufrufe), aufrufe)


    # --- the switches page -------------------------------------------------
    #
    # Three sliders that look alike and work nothing alike. What matters here
    # is that the page never claims more than the hardware does: the modem
    # cannot be opted out of, and a reading that failed must not be shown as
    # a state.

    def switches_win(self):
        if not switcher.KILLSWITCH:
            self.skipTest("killswitch-indicator not installed")
        return self.win

    JSON = """{
      "switches": {"cam_switch": "0", "nwk_switch": "1"},
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

    def test_the_page_reads_both_switch_positions(self):
        win = self.switches_win()
        win.on_switches_status(True, self.JSON)
        self.assertEqual("engaged", win.srow_cam.subtitle)
        self.assertEqual("free", win.srow_net.subtitle)

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
        gebaut = switcher.Window(switcher.Adw.Application())
        angelegt = [c for c in recorder.calls if c[0] == "Adw.SwitchRow"]
        modem = [c for c in angelegt
                 if "mobile network" in str(c[2].get("title", "")).lower()]
        self.assertTrue(modem, "no row for the mobile network")
        self.assertIs(True, modem[-1][2].get("active"))
        self.assertIsNotNone(gebaut)
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

    def test_the_indicator_switch_drives_the_user_unit(self):
        win = self.switches_win()
        self.ran.clear()
        win._loading = False
        win.sw_row.set_active(False)
        win.on_indicator_switch(win.sw_row, None)
        self.assertIn("stop", self.ran[-1][0])
        self.assertIn("killswitch-indicator", self.ran[-1][0])

    def test_remembering_the_choice_enables_the_unit(self):
        win = self.switches_win()
        self.ran.clear()
        win._loading = False
        win.sw_persist.set_active(True)
        win.on_indicator_persist(win.sw_persist, None)
        self.assertIn("enable", self.ran[-1][0])

    def test_a_reading_while_loading_does_not_write_anything_back(self):
        """Filling the switches from a status must not look like a user
        touching them - that would write the state back at itself."""
        win = self.switches_win()
        self.ran.clear()
        win.on_switches_status(True, self.JSON)
        self.assertEqual([], [r for r in self.ran if "config" in r[0]])

    def test_an_unreadable_answer_is_not_shown_as_a_position(self):
        win = self.switches_win()
        win.on_switches_status(True, "not json at all")
        self.assertNotIn("engaged", win.srow_cam.subtitle)
        self.assertNotIn("free", win.srow_cam.subtitle)

    def test_the_switches_page_explains_itself_in_rows_not_paragraphs(self):
        """The four groups on this page carry a title and nothing else. What
        needs saying sits in the row it is about - the way back keeps its
        description, because that text is also the question it asks."""
        self.switches_win()
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        titel = ("Indicator", "1 · Camera", "2 · Network", "3 · Microphone")
        mit_absatz = [c[2].get("title") for c in recorder.calls
                      if c[0] == "Adw.PreferencesGroup"
                      and c[2].get("title") in titel
                      and c[2].get("description")]
        self.assertEqual([], mit_absatz)

    def test_the_microphone_row_says_it_is_not_read(self):
        """The one switch that cuts the line is also the one nothing here can
        see. Saying so is the whole content of the row - checked against what
        the page actually built, not against a stand-in a test wrote."""
        self.switches_win()
        switcher.Window(switcher.Adw.Application())
        zeilen = [c for c in recorder.calls if c[0] == "Adw.ActionRow"]
        mic = [c for c in zeilen
               if "not readable" in str(c[2].get("subtitle", ""))]
        self.assertTrue(mic, "no row saying the microphone is not read")

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
        knoepfe = [str(c[2].get("label", "")).lower()
                   for c in recorder.calls if c[0] == "Gtk.Button"]
        self.assertEqual([], [b for b in knoepfe if "listen" in b], knoepfe)

    # --- the components page -----------------------------------------------
    #
    # Fetching a repository and running its installer is the most far-reaching
    # thing this window does. Three properties are checked here and would each
    # be a quiet disaster if they stopped holding: it asks first, the password
    # travels through the pipe and never through a command line, and the
    # ticket is dropped again when the work is done.

    def komponente(self, tool="gpsctl"):
        return next(c for c in switcher.COMPONENTS if c["tool"] == tool)

    def test_the_components_page_lists_every_tool_with_its_source(self):
        recorder.reset()
        self.win.open_components()
        gruppen = [str(c[2].get("title", "")) for c in recorder.calls
                   if c[0] == "Adw.PreferencesGroup"]
        for comp in switcher.COMPONENTS:
            with self.subTest(tool=comp["tool"]):
                self.assertTrue(any(comp["tool"] in g for g in gruppen), gruppen)
        zeilen = [str(c[2].get("subtitle", "")) for c in recorder.calls
                  if c[0] == "Adw.ActionRow"]
        for comp in switcher.COMPONENTS:
            self.assertIn(comp["url"], zeilen)

    def test_fetching_asks_first_and_runs_nothing_on_the_tap(self):
        self.win.open_components()
        self.ran.clear()
        self.win.ask_component(self.komponente())
        self.assertEqual([], self.ran)

    def test_the_question_says_what_will_be_run(self):
        recorder.reset()
        self.win.open_components()
        self.win.ask_component(self.komponente())
        dialoge = [c for c in recorder.calls if c[0] == "Adw.AlertDialog"]
        body = str(dialoge[-1][2].get("body", ""))
        self.assertIn("git clone", body)
        self.assertIn("install.sh", body)
        self.assertIn("sudo", body)

    def test_cancel_sits_on_top_here_too_and_answers_nothing(self):
        recorder.reset()
        self.win.open_components()
        self.win.ask_component(self.komponente())
        antworten = [c[1][0] for c in recorder.calls
                     if c[0] == "Adw.AlertDialog.add_response()" and c[1]]
        self.assertEqual(["go", "cancel"], antworten)
        self.ran.clear()
        self.win.on_component_response(None, "cancel")
        self.assertEqual([], self.ran)

    def test_only_a_component_that_needs_root_is_asked_for_a_password(self):
        recorder.reset()
        self.win.open_components()
        self.win.ask_component(self.komponente("gpsctl"))          # root
        self.assertTrue([c for c in recorder.calls
                         if c[0] == "Adw.PasswordEntryRow"])
        recorder.reset()
        self.win.ask_component(self.komponente("killswitch-indicator"))
        self.assertEqual([], [c for c in recorder.calls
                              if c[0] == "Adw.PasswordEntryRow"])

    def schritte(self, comp, zustand, wort="geheim"):
        """The steps as the app would run them - read, not executed.

        Checked against the list rather than against a chain that has been
        run: what runs as root, in which directory, and where the password
        goes is exactly the part that must be readable without starting
        anything.
        """
        return switcher.component_steps(comp, zustand, wort)

    def test_an_install_clones_asks_sudo_once_and_drops_the_ticket(self):
        gelaufen = self.schritte(self.komponente(), "install")
        befehle = [" ".join(argv) for argv, _stdin, _cwd in gelaufen]
        self.assertIn("git clone", befehle[0])
        self.assertEqual(1, len([b for b in befehle if b.startswith("sudo -S")]))
        self.assertTrue(any(b.endswith("install.sh") for b in befehle), befehle)
        self.assertEqual("sudo -k", befehle[-1],
                         "the ticket has to be dropped when the work is done")

    def test_the_password_never_reaches_a_command_line(self):
        """It goes to sudo through the pipe. In argv every "ps" on the phone
        would read it, and so would anything that logs a command."""
        gelaufen = self.schritte(self.komponente(), "install")
        for argv, _stdin, _cwd in gelaufen:
            with self.subTest(argv=argv):
                self.assertNotIn("geheim", " ".join(argv))
        durch_die_pipe = [stdin for _argv, stdin, _cwd in gelaufen if stdin]
        self.assertEqual(["geheim\n"], durch_die_pipe)

    def test_the_installer_runs_in_the_clone_as_the_user(self):
        """Not as root: killswitch-indicator's installer refuses to be root,
        and an installer run as root writes its user files into /root."""
        gelaufen = self.schritte(self.komponente(), "install")
        installer = [(argv, cwd) for argv, _stdin, cwd in gelaufen
                     if argv[0].endswith("install.sh")]
        self.assertEqual(1, len(installer))
        argv, cwd = installer[0]
        self.assertNotIn("sudo", argv)
        self.assertEqual(switcher.clone_path(self.komponente()), cwd)

    def test_a_component_without_root_never_calls_sudo(self):
        gelaufen = self.schritte(self.komponente("killswitch-indicator"),
                                 "install", None)
        self.assertEqual([], [argv for argv, _s, _c in gelaufen
                              if argv[0] == "sudo"])

    def test_an_update_pulls_instead_of_cloning(self):
        gelaufen = self.schritte(self.komponente(), "update")
        self.assertIn("pull", gelaufen[0][0])
        self.assertNotIn("clone", " ".join(gelaufen[0][0]))

    def test_fetching_only_the_source_installs_nothing(self):
        """The tool is already there; this is only so that updates become
        visible. Running an installer here would change a working phone."""
        gelaufen = self.schritte(self.komponente(), "source", None)
        self.assertEqual(1, len(gelaufen))
        self.assertIn("clone", " ".join(gelaufen[0][0]))

    def test_the_chain_runs_the_steps_in_order(self):
        """And hands each one what the list says - the cwd and the pipe
        included, which is the only place the password is."""
        self.win.open_components()
        self.ran.clear()
        self.win.busy = False
        comp = self.komponente()
        self.win.run_component(comp, "install", "geheim")
        erwartet = switcher.component_steps(comp, "install", "geheim")
        for argv, stdin, cwd in erwartet:
            lauf, done, _on_line, kw = self.ran.pop(0)
            self.assertEqual(argv, lauf)
            self.assertEqual(stdin, kw.get("stdin"))
            self.assertEqual(cwd, kw.get("cwd"))
            done(True, "")

    def test_a_step_that_fails_stops_the_chain_and_shows_what_it_said(self):
        self.win.open_components()
        self.ran.clear()
        self.win.busy = False
        self.win.run_component(self.komponente(), "install", "falsch")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "fatal: could not read from remote")
        self.assertEqual([], [r for r in self.ran if "install.sh" in " ".join(r[0])])
        self.assertIn("Could not set up", str(self.win.toasts.text))

    def mit_klon(self, behind=None):
        """Pretend our own clone is there, and answer the two git calls."""
        real_path, real_is, real_else = (switcher.clone_path, switcher.is_clone,
                                         switcher.clone_elsewhere)
        switcher.clone_path = lambda comp: "/tmp/klon/" + comp["dir"]
        switcher.is_clone = lambda path: True
        switcher.clone_elsewhere = lambda url, base=None: None
        try:
            self.win.open_components()
            for comp in switcher.COMPONENTS:
                self.win.comp_rows[comp["tool"]]["state"] = Recording()
            laeufe = [r for r in self.ran if "git" in r[0]]
            self.ran.clear()
            for _argv, done, _on_line, _kw in laeufe:
                done(True, "")                 # fetch
            for _argv, done, _on_line, _kw in list(self.ran):
                done(True, "" if behind is None else str(behind))
            self.ran.clear()
        finally:
            (switcher.clone_path, switcher.is_clone,
             switcher.clone_elsewhere) = real_path, real_is, real_else

    def test_a_clone_of_ours_is_checked_and_says_how_far_behind_it_is(self):
        self.win.open_components()
        self.ran.clear()
        self.mit_klon(behind=2)
        for comp in switcher.COMPONENTS:
            with self.subTest(tool=comp["tool"]):
                self.assertIn("2 commit",
                              self.win.comp_rows[comp["tool"]]["state"].subtitle)

    def test_a_clone_that_is_current_says_up_to_date(self):
        self.win.open_components()
        self.ran.clear()
        self.mit_klon(behind=0)
        gpsctl = self.win.comp_rows["gpsctl"]["state"].subtitle
        self.assertIn("up to date", gpsctl)

    def test_a_clone_somebody_else_keeps_is_named_and_not_touched(self):
        """Named, so nobody wonders where their repository went - and left
        alone, because it may have uncommitted work in it."""
        real = switcher.clone_elsewhere
        switcher.clone_elsewhere = lambda url, base=None: "/home/furios/Projekte/eigen"
        try:
            self.win.open_components()
            for comp in switcher.COMPONENTS:
                self.win.comp_rows[comp["tool"]]["state"] = Recording()
            self.ran.clear()
            self.win.read_components()
            for comp in switcher.COMPONENTS:
                with self.subTest(tool=comp["tool"]):
                    zeile = self.win.comp_rows[comp["tool"]]["state"]
                    self.assertIn("left untouched", zeile.subtitle)
                    self.assertIn("/home/furios/Projekte/eigen", zeile.subtitle)
            # Looked at, never changed: ls-remote and rev-parse only. A
            # fetch would already write into somebody else's .git, a pull
            # into their working tree.
            befehle = [" ".join(r[0]) for r in self.ran if r[0][0] == "git"]
            self.assertTrue(befehle, "nobody even looked")
            for b in befehle:
                with self.subTest(befehl=b):
                    self.assertTrue("ls-remote" in b or "rev-parse" in b, b)
            for verboten in ("fetch", "pull", "checkout", "reset"):
                self.assertEqual([], [b for b in befehle if verboten in b])
        finally:
            switcher.clone_elsewhere = real

    def test_something_new_upstream_is_said_but_not_acted_on(self):
        """The one thing this app can honestly do with a clone it does not
        own: say that the server has moved on."""
        real = switcher.clone_elsewhere
        switcher.clone_elsewhere = lambda url, base=None: "/home/furios/Projekte/eigen"
        try:
            self.win.open_components()
            zeile = Recording()
            self.win.comp_rows["gpsctl"]["state"] = zeile
            self.ran.clear()
            self.win.peek_upstream(self.komponente(), "/usr/bin/gpsctl",
                                   "/home/furios/Projekte/eigen")
            argv, done, _on_line, _kw = self.ran.pop(0)
            self.assertIn("ls-remote", argv)
            done(True, "abc123\tHEAD")
            argv, done, _on_line, _kw = self.ran.pop(0)
            self.assertIn("rev-parse", argv)
            done(True, "def456")
            self.assertIn("something new upstream", zeile.subtitle)
            self.assertIn("left untouched", zeile.subtitle)
            # the button stays out of reach
            self.assertEqual("Kept by you",
                             switcher.component_state(True, False, True, None)[1])
        finally:
            switcher.clone_elsewhere = real

    def test_a_clone_that_matches_the_server_says_up_to_date(self):
        self.win.open_components()
        zeile = Recording()
        self.win.comp_rows["gpsctl"]["state"] = zeile
        self.ran.clear()
        self.win.peek_upstream(self.komponente(), "/usr/bin/gpsctl", "/eigen")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "abc123\tHEAD")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "abc123\n")
        self.assertIn("up to date", zeile.subtitle)

    def test_no_answer_from_the_server_is_not_up_to_date(self):
        """A phone in a tunnel must not be told its clone is current."""
        self.win.open_components()
        zeile = Recording()
        self.win.comp_rows["gpsctl"]["state"] = zeile
        self.ran.clear()
        self.win.peek_upstream(self.komponente(), "/usr/bin/gpsctl", "/eigen")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "could not resolve host")
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(True, "abc123")
        self.assertIn("could not look upstream", zeile.subtitle)

    def test_nothing_is_offered_while_something_else_runs(self):
        self.win.open_components()
        self.ran.clear()
        self.win.busy = True
        try:
            self.win.ask_component(self.komponente())
            self.assertEqual([], self.ran)
        finally:
            self.win.busy = False

    def test_an_update_says_pull_in_the_question_and_a_source_fetch_says_clone(self):
        self.win.open_components()
        for zustand, wort in (("update", "git pull"), ("source", "git clone")):
            with self.subTest(zustand=zustand):
                self.win.comp_rows["gpsctl"]["state_name"] = zustand
                recorder.reset()
                self.win.ask_component(self.komponente())
                body = str([c for c in recorder.calls
                            if c[0] == "Adw.AlertDialog"][-1][2].get("body", ""))
                self.assertIn(wort, body)
        # and fetching only the source says so on its own button
        self.assertNotIn("install.sh", body)

    def test_answering_go_starts_the_chain_with_what_was_typed(self):
        self.win.open_components()
        self.win.comp_rows["gpsctl"]["state_name"] = "install"
        self.win.ask_component(self.komponente())
        comp, zustand, eingabe = self.win._comp_pending
        self.assertIsNotNone(eingabe)           # a password is asked for
        feld = Recording()
        feld.set_text("geheim")
        self.win._comp_pending = (comp, zustand, feld)
        self.ran.clear()
        self.win.busy = False
        self.win.on_component_response(None, "go")
        argv, _done, _on_line, _kw = self.ran[0]
        self.assertIn("clone", " ".join(argv))
        self.assertEqual([], [a for a in self.ran if "geheim" in " ".join(a[0])])
        self.assertEqual("", feld.text, "the password is wiped from the entry")

    def test_a_wrong_password_is_reported_in_sudos_own_words(self):
        """Better than anything this window could invent - and the chain stops
        there rather than running an installer that cannot finish."""
        self.win.open_components()
        self.win.component_done(self.komponente(), False,
                                "sudo: 3 incorrect password attempts")
        self.assertIn("Could not set up", str(self.win.toasts.text))

    def test_a_finished_fetch_says_the_tab_needs_a_restart(self):
        """The tabs are built once, when the window opens - a tool that
        arrives later cannot grow one by itself."""
        self.win.open_components()
        self.win.component_done(self.komponente(), True, "")
        self.assertIn("restart", str(self.win.toasts.text))

    def test_an_update_check_reads_how_far_behind_the_clone_is(self):
        self.win.open_components()
        comp = self.komponente()
        self.ran.clear()
        self.win.comp_rows[comp["tool"]]["state"] = Recording()
        self.win.check_component(comp, "/usr/bin/gpsctl", "/tmp/klon", None)
        argv, done, _on_line, _kw = self.ran.pop(0)
        self.assertIn("fetch", argv)
        done(True, "")
        argv, done, _on_line, _kw = self.ran.pop(0)
        self.assertIn("rev-list", argv)
        done(True, "4\n")
        self.assertIn("4 commit", self.win.comp_rows[comp["tool"]]["state"].subtitle)

    def test_a_check_that_fails_says_so_rather_than_up_to_date(self):
        self.win.open_components()
        comp = self.komponente()
        self.ran.clear()
        self.win.comp_rows[comp["tool"]]["state"] = Recording()
        self.win.check_component(comp, "/usr/bin/gpsctl", "/tmp/klon", None)
        _argv, done, _on_line, _kw = self.ran.pop(0)
        done(False, "could not resolve host")
        self.assertIn("could not check",
                      self.win.comp_rows[comp["tool"]]["state"].subtitle)

    # --- the way back, on every page ---------------------------------------
    #
    # One idea, one shape. Before this it was a blue "Restore sound" here, a
    # red "Restore shipped state" there and nothing at all on the other two -
    # and the colours made a claim ("do this" / "careful") that is not true
    # in general. What differs between the pages is the price, and that is
    # what the description says.

    def test_every_page_offers_the_same_way_back(self):
        """Counted, not named: adding a page must not quietly add a fifth
        shape of this."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        erwartet = (1 + bool(switcher.MODEMCTL) + bool(switcher.GPSCTL)
                    + bool(switcher.KILLSWITCH))
        knoepfe = [c for c in recorder.calls if c[0] == "Gtk.Button"
                   and c[2].get("label") == switcher.Window.RESTORE_LABEL]
        gruppen = [c for c in recorder.calls if c[0] == "Adw.PreferencesGroup"
                   and c[2].get("title") == switcher.Window.RESTORE_TITLE]
        self.assertEqual(erwartet, len(knoepfe))
        self.assertEqual(erwartet, len(gruppen))

    def test_no_way_back_is_painted_louder_than_another(self):
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        klassen = [a for c in recorder.calls
                   if c[0] == "Gtk.Button.add_css_class()" for a in c[1]]
        self.assertEqual([], [k for k in klassen if k.endswith("-action")])
        self.assertIn("pill", klassen)

    def test_each_way_back_says_what_it_costs(self):
        """The same button four times is only honest if the text next to it is
        not the same four times."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        texte = {str(c[2].get("description", ""))
                 for c in recorder.calls if c[0] == "Adw.PreferencesGroup"
                 and c[2].get("title") == switcher.Window.RESTORE_TITLE}
        erwartet = (1 + bool(switcher.MODEMCTL) + bool(switcher.GPSCTL)
                    + bool(switcher.KILLSWITCH))
        self.assertEqual(erwartet, len(texte))

    def test_a_way_back_asks_before_it_acts(self):
        """Nothing here is a tap to take back, so none of them acts on the tap
        alone."""
        gerufen = []
        self.ran.clear()
        self.win.confirm_restore("what it costs", gerufen.append, "btn")
        self.assertEqual([], gerufen)
        self.assertEqual([], self.ran)

    def test_cancelling_is_the_default_and_does_nothing(self):
        gerufen = []
        recorder.reset()
        self.win.confirm_restore("what it costs", gerufen.append, "btn")
        # c[1] filtered: the stub records the call AND the object it hands
        # back, and the second one carries no arguments.
        vorgabe = [c[1] for c in recorder.calls
                   if c[0] == "Adw.AlertDialog.set_default_response()" and c[1]]
        schliessen = [c[1] for c in recorder.calls
                      if c[0] == "Adw.AlertDialog.set_close_response()" and c[1]]
        self.assertEqual([("cancel",)], vorgabe)
        self.assertEqual([("cancel",)], schliessen)
        self.win.on_restore_response(None, "cancel")
        self.assertEqual([], gerufen)

    def test_cancel_is_the_answer_under_the_thumb(self):
        """libadwaita stacks the answers in reverse on a narrow screen: the one
        added LAST is drawn on top. Added the obvious way round, "Restore
        shipped state" sat exactly where a thumb reaches first - seen on the
        phone, which is the only place this can be seen at all."""
        recorder.reset()
        self.win.confirm_restore("what it costs", lambda _b: None, None)
        antworten = [c[1][0] for c in recorder.calls
                     if c[0] == "Adw.AlertDialog.add_response()" and c[1]]
        self.assertEqual(["restore", "cancel"], antworten)

    def test_answering_restore_is_what_runs_it(self):
        gerufen = []
        self.win.confirm_restore("what it costs", gerufen.append, "btn")
        self.win.on_restore_response(None, "restore")
        self.assertEqual(["btn"], gerufen)
        # Answering twice must not run it twice - the pending one is cleared.
        self.win.on_restore_response(None, "restore")
        self.assertEqual(["btn"], gerufen)

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
        """Three commands, because two owners: the tool holds the extra
        radios, systemd holds the unit. The sliders are not among them - they
        are hardware and nothing here reaches them."""
        win = self.switches_win()
        self.ran.clear()
        win.busy = False
        win.on_switches_restore(None)
        gelaufen = []
        for _ in range(3):
            argv, done, _on_line, _kw = self.ran.pop(0)
            gelaufen.append(" ".join(argv))
            done(True, "")
        self.assertTrue(any("config wifi off" in c for c in gelaufen), gelaufen)
        self.assertTrue(any("config bluetooth off" in c for c in gelaufen), gelaufen)
        self.assertTrue(any("disable --now killswitch-indicator" in c
                            for c in gelaufen), gelaufen)

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
        gerufen = []
        recorder.reset()
        _grp, btn = self.win.build_restore_group("what it costs", gerufen.append)
        klick = [c[1][1] for c in recorder.calls
                 if c[0] == "Gtk.Button.connect()" and c[1] and c[1][0] == "clicked"]
        self.assertEqual(1, len(klick))
        klick[0](btn)
        self.assertEqual([], gerufen)
        self.win.on_restore_response(None, "restore")
        self.assertEqual([btn], gerufen)

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
        real = switcher.PKEXEC
        try:
            switcher.PKEXEC = None
            self.ran.clear()
            win.busy = False
            win.on_gps_restore(None)
            self.assertEqual([], self.ran)
            self.assertIn("pkexec", str(win.toasts.text))
        finally:
            switcher.PKEXEC = real

    def test_a_location_way_back_that_fails_is_reported(self):
        win = self.gps_win()
        win.on_gps_restored(False, "gpsctl: no")
        self.assertIn("Could not", str(win.toasts.text))

    def test_the_indicator_rows_read_what_systemd_answers(self):
        """"active" and "enabled" are systemd's words, and they are the whole
        answer - anything else means not running, not remembered."""
        win = self.switches_win()
        win.on_indicator_active(True, "active\n")
        self.assertTrue(win.sw_row.get_active())
        self.assertEqual("running", win.sw_row.subtitle)
        win.on_indicator_active(True, "failed\n")
        self.assertFalse(win.sw_row.get_active())
        self.assertEqual("not running", win.sw_row.subtitle)
        # is-enabled exits non-zero for a disabled unit, so a failed call is
        # an answer here, not an error.
        win.on_indicator_enabled(True, "enabled\n")
        self.assertTrue(win.sw_persist.get_active())
        win.on_indicator_enabled(False, "disabled\n")
        self.assertFalse(win.sw_persist.get_active())

    def test_a_unit_that_would_not_start_says_so(self):
        win = self.switches_win()
        win.after_indicator(False, "", "start")
        self.assertIn("Could not start", str(win.toasts.text))

    def test_filling_the_switches_page_writes_nothing_back(self):
        """The rows are set from what was read; without the guard each of
        those writes would look like somebody flipping the switch."""
        win = self.switches_win()
        win._loading = True
        self.ran.clear()
        win.on_indicator_switch(win.sw_row, None)
        win.on_indicator_persist(win.sw_persist, None)
        win.set_extra("wifi", win.sw_wifi)
        self.assertEqual([], self.ran)
        win._loading = False

    def test_a_tool_that_did_not_answer_is_not_shown_as_a_position(self):
        win = self.switches_win()
        win.on_switches_status(False, "")
        self.assertIn("did not answer", win.srow_cam.subtitle)
        self.assertIn("did not answer", win.srow_net.subtitle)

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
        dialoge = [c for c in recorder.calls if c[0] == "Adw.AlertDialog"]
        self.assertEqual(1, len(dialoge))
        self.assertEqual("it takes the repairs out", dialoge[0][2].get("body"))

    # --- the modem page ----------------------------------------------------
    #
    # It is built only when modemctl is installed, so every check here says so
    # first. On a phone without the modem package there is no second tab and
    # nothing below has anything to test - which is itself the behaviour that
    # matters most: a tab that always says "not installed" would make a healthy
    # phone look broken.

    def test_without_modemctl_there_is_no_second_page(self):
        real = switcher.MODEMCTL
        try:
            switcher.MODEMCTL = None
            win = switcher.Window(switcher.Adw.Application())
            self.assertEqual([], win.modem_rows)
        finally:
            switcher.MODEMCTL = real

    def test_the_two_words_the_profile_is_read_by(self):
        """modemctl lives in another package. These two keys are the contract
        between them, and its other half is checked over there, where they are
        printed."""
        found = switcher.Window._keyed("recorded: fixed\nactual:   shipped\n")
        self.assertEqual({"recorded": "fixed", "actual": "shipped"}, found)

    def modem_win(self):
        if not switcher.MODEMCTL:
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

    def test_without_gpsctl_there_is_no_gps_page(self):
        real = switcher.GPSCTL
        try:
            switcher.GPSCTL = None
            win = switcher.Window(switcher.Adw.Application())
            self.assertEqual([], win.gps_rows)
        finally:
            switcher.GPSCTL = real

    def gps_win(self):
        if not switcher.GPSCTL:
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

    def test_the_location_group_carries_no_essay(self):
        """The switch's own subtitle says what on and off mean; the paragraph
        above it said the same thing a third time."""
        recorder.reset()
        switcher.Window(switcher.Adw.Application())
        ort = [c for c in recorder.calls if c[0] == "Adw.PreferencesGroup"
               and c[2].get("title") == "Location"]
        self.assertTrue(ort, "no Location group")
        self.assertNotIn("description", ort[0][2])

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
        real = switcher.PKEXEC
        try:
            switcher.PKEXEC = None
            before = len(self.ran)
            win.on_gps_switch(win.gps_row, None)
            self.assertEqual(before, len(self.ran), "ran the switch without pkexec")
            self.assertIn("pkexec", str(win.toasts.text))
        finally:
            switcher.PKEXEC = real

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
        real = switcher.PKEXEC
        try:
            switcher.PKEXEC = None
            win.modem_row.active = False
            win.on_modem_switch(win.modem_row, None)
            self.assertEqual([], self.ran, "it tried to switch without rights")
            self.assertIn("pkexec", str(win.toasts.text))
        finally:
            switcher.PKEXEC = real

    def test_without_pkexec_the_restore_button_says_so_and_runs_nothing(self):
        win = self.modem_win()
        real = switcher.PKEXEC
        try:
            switcher.PKEXEC = None
            win.on_modem_restore(None)
            self.assertEqual([], self.ran, "it tried to restore without rights")
            self.assertIn("pkexec", str(win.toasts.text))
        finally:
            switcher.PKEXEC = real

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
        the profile under $HOME these days, so there is nothing to authenticate
        - and an app that handles no passwords cannot mishandle them.
        """
        app = switcher.App()
        app.props.active_window = None
        app.do_activate()


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
