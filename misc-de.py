#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The switches for a FuriPhone that has been repaired by hand.

Three pages, and each is one switch: the audio stack talks to the Android HAL
through PipeWire or through PulseAudio as shipped, the modem runs with the
repairs from furios_modem_fixes or exactly as it came, and geoclue either has
the filter that throws away positions derived from the carrier's IP address or
it does not. The tools do the work - audioctl, modemctl and gpsctl - and this
front end only calls them and shows what is actually running.

Every page is there, whether its tool is or not. Where one is missing the tab
says what it would do, where it comes from, and offers to fetch it - and the
moment that has run, the tab is the real one.

Deliberately plain: on a phone you want a button, not a control room.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio, GLib, Gtk  # noqa: E402

# This app used to carry a polkit authentication agent, because switching the
# stack meant masking system units and writing into /etc, and phosh registers
# no agent of its own. It does not need one any more: audioctl keeps the
# profile under $HOME, where the session may write anyway, so there is nothing
# left to authenticate and no password for this app to handle.

APP_ID = "de.misc-de.tools"
import json
import os
import shutil
import sys
import tempfile

# From the package it lives in /usr/bin, from the source tree in /usr/local/bin.
#
# The installed paths are tried BEFORE $PATH. What is started here goes on to
# ask polkit for root, and this app registers the agent that answers - so the
# one thing not to do is let the search order decide which "audioctl" that is.
# $PATH stays as the last resort for an install somewhere else entirely.
def _tool(name):
    for path in ("/usr/local/bin/" + name, "/usr/bin/" + name):
        if os.access(path, os.X_OK):
            return path
    return shutil.which(name) or "/usr/bin/" + name


# Like _tool, but it admits when the program is not there at all. The modem
# page is built from this: present or absent, never present-and-broken.
def _tool_maybe(name):
    # ~/.local/bin is searched too, and last: a tool that needs no root at all
    # is installed there, and killswitch-indicator is one of those.
    home_bin = os.path.expanduser("~/.local/bin/" + name)
    for path in ("/usr/local/bin/" + name, "/usr/bin/" + name, home_bin):
        if os.access(path, os.X_OK):
            return path
    return shutil.which(name)


# Like the other three, audioctl has no constant here: it can be installed
# from the Audio tab while this window is open, and a path read at import
# would still say /usr/bin afterwards - where nothing is. The window keeps
# what it found in self.live; furios-audio-dmnr comes with the same installer
# and is looked up when it is used.
DMNR = "furios-audio-dmnr"
CONTRIB = "furios-gps-contribute"


# Where the kernel driver puts the switch positions. Taken from
# killswitch-indicator, which reads the same two files and honours the same
# override - this is the one place the app needs to know a path of another
# tool, and it needs it before that tool is installed.
KILLSWITCH_SYSFS = "/sys/devices/platform/custom-keys"


def phone_has_switches():
    """Does this phone have the hardware switches at all?

    Asked before the tab is built, not after. A phone without them would
    otherwise get a Switches tab offering to fetch a tool that could never
    show anything on it - an offer for a repair to a fault the device does
    not have.

    The camera and network switches are what can be read; the microphone
    switch cuts the line and is invisible to software, so it cannot serve as
    the test. A phone with only that one would be missed here, and there is
    no way to tell it apart from a phone with none.
    """
    base = os.environ.get("FURIOS_KILLSWITCH_BASE", KILLSWITCH_SYSFS)
    return any(os.path.exists(os.path.join(base, name))
               for name in ("cam_switch", "nwk_switch"))
# modemctl, gpsctl and killswitch-indicator have NO constant here on purpose.
# They ship in other packages, may simply not be on the phone, and - since the
# components page can fetch one - may arrive while this window is open. A
# constant would be the answer to "was it there when the app started", and
# every handler that read one would still be holding that answer an hour
# later. The window looks them up when it builds a page and keeps what it
# found in self.live; that is the one place asked afterwards.
# Switching the modem writes /usr/lib and /etc, so it needs root, and unlike
# audioctl there is no version of it that does not. polkit's own helper is how
# that is asked for; the action this phone carries allows it without a prompt
# for the session sitting at the device, which is why no authentication agent
# is needed here any more than on the audio side.
PKEXEC = _tool_maybe("pkexec")


def server_in_words(raw):
    """PipeWire's PulseAudio interface announces itself as
    "PulseAudio (on PipeWire 1.6.6)". Reading that underneath a switch which
    says "PipeWire holds the HAL" rightly looks like a contradiction. So
    translate it."""
    if not raw or raw == "-":
        return "not reachable"
    if "PipeWire" in raw:
        ver = ""
        for token in raw.replace(")", " ").split():
            if token[:1].isdigit():
                ver = " " + token
                break
        return f"PipeWire{ver} - also speaks PulseAudio for older apps"
    if raw.lower().startswith("pulseaudio"):
        return "PulseAudio - the shipped setup"
    return raw


PROFILE_WORDS = {
    "pw-hal": "PipeWire owns the HAL",
    "standard": "PulseAudio owns the HAL (as shipped)",
    "pw-tunnel": "PulseAudio owns the HAL, PipeWire gets a sink",
}


def profile_in_words(p):
    return PROFILE_WORDS.get(p, p)


# ------------------------------------------------------------ components
#
# What this window drives lives in four repositories, and none of them is this
# app. A phone with only audioctl installed shows one page and looks like an
# app that can do nothing else - so the components page says what the other
# pages would need, where it comes from and what it does, and offers to fetch
# it.
#
# Two rules this is built on:
#
#   Clone into our own place, never into somebody's working tree. If there is
#   already a clone of the same repository elsewhere (~/Projekte, typically),
#   it is REPORTED and left alone: it may carry uncommitted work, and a "git
#   pull" of ours would be the last thing anybody wants there.
#
#   The password goes to sudo and to nothing else. Three of the four installers
#   write to /usr/local and want root; this phone has no polkit agent, so
#   pkexec cannot ask (it answers "No authentication agent found"). What works
#   is what a person does in a terminal: sudo asks once, and the installer runs
#   as the user, with only its own sudo lines becoming root. Afterwards the
#   ticket is dropped again with "sudo -k".
CLONE_HOME = os.path.join(
    os.environ.get("XDG_DATA_HOME", os.path.expanduser("~/.local/share")),
    "misc-de")
# Where people keep their own clones. Only ever read from.
OWN_CLONES = os.path.expanduser("~/Projekte")

COMPONENTS = [
    {
        "tool": "audioctl",
        "page": "Audio",
        "key": "audio",
        "icon": "audio-speakers-symbolic",
        "url": "https://github.com/misc-de/furios_pipewire",
        "dir": "furios_pipewire",
        "root": True,
        "does": "PipeWire talks to the Android HAL directly instead of "
                "PulseAudio: playback, recording, calls and Bluetooth audio",
    },
    {
        "tool": "modemctl",
        "page": "Modem",
        "key": "modem",
        "icon": "network-cellular-symbolic",
        "url": "https://github.com/misc-de/furios_modem_fixes",
        "dir": "furios_modem_fixes",
        "root": True,
        "does": "the modem repairs: mobile data without Wi-Fi, signal bars "
                "that move, 26 cell broadcast channels instead of 8",
    },
    {
        "tool": "gpsctl",
        "page": "GPS",
        "key": "gps",
        "icon": "find-location-symbolic",
        "url": "https://github.com/misc-de/furios_gps",
        "dir": "furios_gps",
        "root": True,
        "does": "geoclue stops handing out the carrier's IP address as though "
                "it were a position",
    },
    {
        "tool": "killswitch-indicator",
        "page": "Switches",
        "key": "switches",
        "icon": "changes-prevent-symbolic",
        "url": "https://github.com/misc-de/furios_killswitch",
        "dir": "furios_killswitch",
        "root": False,
        "does": "an icon in the top bar while the camera or the network "
                "switch is engaged - nothing else on the phone says so",
        # Only on a phone that has the switches. Everything else here is
        # software this phone could have; this one is about hardware it
        # either has or does not.
        "needs": phone_has_switches,
    },
    {
        "tool": "battctl",
        "page": "Battery",
        "key": "battery",
        "icon": "battery-good-charging-symbolic",
        "url": "https://github.com/misc-de/furios_misc",
        "dir": "furios_misc",
        # furios_misc is a collection of small things, so the installer is
        # not at the root of the clone. The only component with this, and
        # the reason it is a key rather than a rule: the next small thing
        # will sit beside it in the same repository.
        "sub": "battery",
        "root": False,
        "does": "the battery icon goes green, amber or red with the charging "
                "power - a tired cable and a good one look the same otherwise",
    },
]

# The unit behind the Battery page. Its switch is the service, the way the
# indicator's is on the Switches page.
BATTERY_UNIT = "furios-battery-color.service"

# The window itself - a component like the four above, and deliberately not a
# tab.
#
# Same repository, same clone, same installer. What it is not is a thing on
# this phone somebody opens a page to operate: it IS the page. As a fifth tab
# it took a fifth of the switcher bar on every other page to say which file it
# runs from, and the one thing it was there for - taking the next version -
# has no reason to wait behind a tab nobody opens.
#
# So it lives in the header bar, and only when there is something to take: an
# icon on the left that appears once a newer version has been found, and that
# asks before it does anything. Nothing is offered until somebody has looked
# and found something - an update button that is always there says nothing.
SELF = {
    "tool": "misc-de",
    "key": "app",
    "url": "https://github.com/misc-de/furios_app",
    "dir": "furios_app",
    "root": True,
    "does": "this window - the tabs and the switches on them",
}


def clone_path(comp):
    """Where this app puts its own clone."""
    return os.path.join(CLONE_HOME, comp["dir"])


def installer_dir(comp, path):
    """The directory its install.sh is run from.

    The clone itself for a repository that is one project, a subdirectory
    for one that collects several.
    """
    return os.path.join(path, comp["sub"]) if comp.get("sub") else path


def installer_said(comp):
    """How the installer is named in front of somebody about to run it -
    the path they would type themselves."""
    return ("./%s/install.sh" % comp["sub"]) if comp.get("sub") else "./install.sh"


def is_clone(path):
    return bool(path) and os.path.isdir(os.path.join(path, ".git"))


def is_clone_of(path, url):
    """Is this directory a clone of that repository?

    By its origin, never by its name: the same repository sits in
    ~/Projekte/furios_gps_fix here and is called furios_gps upstream.
    """
    try:
        with open(os.path.join(path, ".git", "config")) as fh:
            return url in fh.read()
    except OSError:
        return False


def clone_elsewhere(url, base=None):
    """A clone of `url` the user keeps themselves, or None."""
    base = OWN_CLONES if base is None else base
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return None
    for name in names:
        path = os.path.join(base, name)
        if is_clone_of(path, url):
            return path
    return None


# The helper sudo runs when it has no terminal to ask at. Not a secret: it
# holds a socket path, connects, reads what comes back and prints it. The
# socket is in a directory only this user can enter, and the other end checks
# the caller's uid before it says anything.
ASKPASS_HELPER = """#!/usr/bin/env python3
# Written by misc-de for one install and deleted afterwards.
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
s.connect(%r)
parts = []
while True:
    piece = s.recv(4096)
    if not piece:
        break
    parts.append(piece)
sys.stdout.write(b"".join(parts).decode())
"""


class Askpass:
    """A way for sudo to ask for the password while nobody is at a terminal.

    The installers are ordinary scripts with their own sudo lines. This app
    takes a ticket first ("sudo -v", password through a pipe) and used to
    leave the rest to that ticket - which worked until this phone's sudoers
    changed on 14.9.2026. With no terminal sudo does not tie the ticket to a
    tty but to the parent process, and the installer's bash is not the parent
    "sudo -v" had: the GPS install stopped at its first sudo line with "a
    terminal is required to read the password", after cloning and with
    nothing installed. That the modem install had gone through an hour
    earlier was luck - a sudoers rule that shared the ticket, which is not
    ours to rely on.

    sudo's own message says what it wants instead, and this is it. The
    password stays in this process: the helper script carries none, the
    environment carries a path, and what crosses between them is one
    connection on a socket in $XDG_RUNTIME_DIR, inside a directory with mode
    0700, whose peer has to be this very user. Never in argv, where every
    "ps" reads along; never in a file; never in a log line.
    """

    def __init__(self, secret):
        self.secret = secret or ""
        self.verzeichnis = None
        self.dienst = None
        self.helfer = None
        self.error = None
        # Only processes descended from this one are answered. The uid check
        # below rules out other accounts; it does not rule out anything else
        # this account is running, and that is the gap that matters here: the
        # socket sits under a predictable name in $XDG_RUNTIME_DIR, any
        # process of this user can find it with a glob, and the window is as
        # long as an install - up to half an hour. Measured on 15.9.2026: five
        # reads in a row from an unrelated process, none of them sudo.
        self.root_dir = os.getpid()

    @staticmethod
    def _stammt_ab(pid, root_dir, grenze=24):
        """Does pid's parent chain reach root_dir?

        Measured against real sudo on 15.9.2026: the helper it starts is a
        direct descendant (helper -> sudo -> the installer's shell -> us), so
        the chain holds. A count-based guard would not have worked - sudo asks
        three times for three attempts, from three different helper processes.
        """
        gesehen = 0
        while pid and pid > 1 and gesehen < grenze:
            if pid == root_dir:
                return True
            try:
                with open("/proc/%d/stat" % pid) as fh:
                    roh = fh.read()
                # comm sits in brackets and may contain spaces and brackets
                # itself, so everything before the LAST one is skipped.
                pid = int(roh[roh.rindex(")") + 2:].split()[1])
            except (OSError, ValueError, IndexError):
                return False
            gesehen += 1
        return False

    def start(self):
        """The helper's path, or None if it could not be set up.

        None is not an error worth stopping for: it only means the install
        goes back to depending on the ticket, which is where it was before.
        """
        try:
            # $XDG_RUNTIME_DIR is tmpfs and belongs to this user; mkdtemp
            # makes the directory 0700, so the socket in it is out of reach
            # for everybody else no matter what its own mode says.
            self.verzeichnis = tempfile.mkdtemp(
                prefix="misc-de-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
            path = os.path.join(self.verzeichnis, "ask.sock")
            self.helfer = os.path.join(self.verzeichnis, "askpass")
            with open(self.helfer, "w") as fh:
                fh.write(ASKPASS_HELPER % path)
            os.chmod(self.helfer, 0o700)
            self.dienst = Gio.SocketService.new()
            self.dienst.add_address(Gio.UnixSocketAddress.new(path),
                                    Gio.SocketType.STREAM,
                                    Gio.SocketProtocol.DEFAULT, None)
            os.chmod(path, 0o600)
            self.dienst.connect("incoming", self.on_incoming)
            self.dienst.start()
            return self.helfer
        except (OSError, GLib.Error) as error:
            # Saying why matters more than it looks. The install then stops at
            # its first sudo line with "a terminal is required to read the
            # password" - the very thing this class exists to prevent - and
            # without this line there is nothing anywhere that connects the
            # two. The likeliest cause is length: a unix socket path stops at
            # 108 characters, and $XDG_RUNTIME_DIR plus the directory and the
            # name eat into that.
            self.error = str(error) or error.__class__.__name__
            if self.verzeichnis and len(self.verzeichnis) > 70:
                self.error += " (the runtime directory is long - a unix" \
                               " socket path stops at 108 characters)"
            self.stop()
            return None

    def on_incoming(self, _dienst, verbindung, _source):
        """Answer one question from sudo - after asking who is asking."""
        try:
            if not self.secret:
                return True
            creds = verbindung.get_socket().get_credentials()
            if creds.get_unix_user() != os.getuid():
                return True                    # not ours, so not a word
            # Same user is not enough: it has to be something we started.
            if not self._stammt_ab(creds.get_unix_pid(), self.root_dir):
                return True                    # not ours either
            verbindung.get_output_stream().write_all(
                (self.secret + "\n").encode(), None)
            verbindung.close(None)
        except (GLib.Error, OSError):
            pass
        return True

    def stop(self):
        """Socket down, helper gone, password forgotten. Called on every way
        out of an install, the ones that failed included. self.error is left
        alone - it is the one thing worth keeping after a failed start."""
        self.secret = ""
        if self.dienst is not None:
            try:
                self.dienst.stop()
                self.dienst.close()
            except (GLib.Error, AttributeError):
                pass
            self.dienst = None
        if self.verzeichnis:
            shutil.rmtree(self.verzeichnis, ignore_errors=True)
            self.verzeichnis = None
        self.helfer = None


def source_steps(comp, state, path):
    """Getting the code here: the commands, and the sentence somebody is asked
    to agree to. Both from one place, because the question in front of a
    person and what actually runs must not be able to drift apart.

    Four cases, and the two in the middle are the ones this used to get wrong.
    A second press of Install ran "git clone" into the clone the first press
    had already made and died with "destination path already exists and is
    not an empty directory" - for ever, with no way out from inside the app.
    Seen on the phone on 14.9.2026, after an install that had failed further
    down for another reason.
    """
    if state == "reinstall":
        # Nothing to fetch: what is wanted is what is already in the clone.
        # A pull here would be the wrong question, and with uncommitted work
        # in that clone its guard would refuse the install as well.
        return ([], "nothing is fetched - the clone in " + path
                + " is used exactly as it is")
    if state == "update":
        guard = (["bash", "-c",
                  'test -z "$(git -C "$1" status --porcelain)" || '
                  '{ echo "This clone has uncommitted changes. Nothing was '
                  'touched - finish or stash them first, then update '
                  'again."; exit 1; }', "guard", path], None, None, None)
        return ([guard,
                 (["git", "-C", path, "pull", "--ff-only"], None, None, None)],
                "git pull --ff-only in " + path)
    if is_clone_of(path, comp["url"]):
        # Ours, from an earlier press. Bring it up to date if that works and
        # install from it either way: no network is a reason to install what
        # is here, not a reason to refuse.
        return ([(["bash", "-c",
                   'git -C "$1" pull --ff-only || echo "Could not update the '
                   'clone - installing what is already in it."',
                   "retry", path], None, None, None)],
                "the clone in " + path + " is already here - update it if "
                "possible, install from it either way")
    if os.path.exists(path):
        # Not a clone of this repository, and not ours to delete.
        return ([(["bash", "-c",
                   'echo "$1 is in the way: it exists and is not a clone of '
                   '$2. Nothing was touched - move it aside, then try '
                   'again."; exit 1', "in_the_way", path, comp["url"]],
                  None, None, None)],
                path + " is in the way - it is not a clone of " + comp["url"])
    return ([(["git", "clone", comp["url"], path], None, None, None)],
            "git clone " + comp["url"] + " to " + path)


def installer_env(askpass):
    """What the installer is told, beyond where it runs.

    DISPLAY is in here for one reason, and it is sudo's: it reaches for
    SUDO_ASKPASS only when it has no terminal AND believes somebody could see
    a graphical prompt, which it decides by DISPLAY being set. It never opens
    it. Under phosh it is set anyway (phoc brings XWayland along), so this is
    for the session where it is not - without it sudo answers "a terminal is
    required to read the password" with a perfectly good helper standing by.
    """
    if not askpass:
        return None
    umgebung = {"SUDO_ASKPASS": askpass}
    if not os.environ.get("DISPLAY"):
        umgebung["DISPLAY"] = ":0"
    return umgebung


def component_steps(comp, state, secret, path=None, askpass=None):
    """The commands one fetch consists of, as (argv, stdin, cwd, env).

    A list, not a method: what runs as root, in which directory, where the
    password goes and what the installer is told about asking for it is the
    part worth being able to read - and to check without starting anything.

    An update may point at a clone somebody keeps themselves, so it starts by
    refusing to touch one that has local changes: "git status --porcelain" as
    a guard, with its own sentence, because a bare exit code would leave
    somebody staring at a failure with no reason attached. --ff-only does the
    rest - a merge is not something an app decides on behalf of a working
    tree.

    The installer is NOT run with sudo. It runs as the user, exactly as it
    would in a terminal, and only its own sudo lines become root: run as root
    it would write its user files into /root, and killswitch-indicator's
    installer refuses to be root altogether. What sudo is used for here is a
    ticket, taken once, dropped again at the end - and SUDO_ASKPASS, so that
    the installer's own sudo lines can ask again if the phone's sudoers does
    not let them use that ticket. Which it may not: see Askpass.
    """
    path = path or clone_path(comp)
    steps = list(source_steps(comp, state, path)[0])
    if comp["root"]:
        # -S reads the password from the pipe; -p "" keeps sudo's prompt out
        # of the output this window shows. It stays even though the helper
        # below could answer this one too: a wrong password has to stop the
        # chain HERE, before an installer is half-way through.
        steps.append((["sudo", "-S", "-p", "", "-v"], (secret or "") + "\n",
                         None, None))
    steps.append((["./install.sh"], None, installer_dir(comp, path),
                     installer_env(askpass)))
    if comp["root"]:
        steps.append((["sudo", "-k"], None, None, None))
    return steps


def behind_count(out):
    """How many commits the clone is behind, from "git rev-list --count".

    Anything that is not a number means the question could not be answered -
    no upstream, no network, not a clone - and that is not "up to date".
    """
    text = (out or "").strip().splitlines()
    if not text:
        return None
    try:
        return int(text[-1].strip())
    except ValueError:
        return None


# Long enough that nothing honest is ever cut off - audioctl alone may wait 15
# seconds for a sink, and a switch behind pkexec runs several systemctl calls
# after that - and short enough that a phone is not left with a greyed-out
# window and a pulsing bar until somebody kills the app.
CALL_TIMEOUT = 90


def run_async(argv, on_done, on_line=None, timeout=CALL_TIMEOUT, cwd=None,
              stdin=None, env=None):
    """audioctl runs for up to 15 seconds (it waits for a sink), so never
    call it blocking - the window would freeze.

    If on_line is passed, lines arrive one by one while the program is still
    running. That is the difference between "something is happening" and a
    window that looks dead for ten seconds.

    Every call is bounded. systemctl can block on a job that is itself
    waiting, and a helper that never returns used to mean set_busy(True) with
    nothing to ever set it back: the switches stay grey, the progress bar
    keeps pulsing, and the only way out is to kill the window. A bounded wait
    turns that into an error message, which is a state somebody can act on.
    """
    flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
    if stdin is not None:
        # The password reaches sudo through this pipe and nowhere else. Not in
        # argv, where every "ps" on the phone would read it; not in a file, not
        # in the environment, not in a log line.
        flags |= Gio.SubprocessFlags.STDIN_PIPE
    try:
        if cwd is None and stdin is None and not env:
            proc = Gio.Subprocess.new(argv, flags)
        else:
            launcher = Gio.SubprocessLauncher.new(flags)
            if cwd is not None:
                launcher.set_cwd(cwd)
            for name, value in (env or {}).items():
                launcher.setenv(name, value, True)
            proc = launcher.spawnv(argv)
    except GLib.Error as err:
        on_done(False, str(err))
        return

    # on_done exactly once, whichever of the two gets there first. The caller's
    # callback is held under its own name: the readers below look "on_done" up
    # when they run, so rebinding it without this would have settle calling
    # itself for ever.
    finish = on_done
    state = {"done": False, "timer": 0}

    def settle(ok, out):
        if state["done"]:
            return
        state["done"] = True
        if state["timer"]:
            GLib.source_remove(state["timer"])
            state["timer"] = 0
        finish(ok, out)

    def give_up():
        state["timer"] = 0
        if not state["done"]:
            # force_exit, not a polite signal: what is being waited on is a
            # program that has already stopped answering.
            proc.force_exit()
        # Handed to settle either way rather than checked twice here. Whether
        # an answer is too late is one question and it has one place to be
        # asked, which is also the place a reader answering twice runs into.
        settle(False, f"{argv[0]} did not answer within {timeout} seconds")
        return False

    if timeout:
        state["timer"] = GLib.timeout_add_seconds(timeout, give_up)
    on_done = settle

    if on_line is None:
        def finished(p, res):
            try:
                _ok, out, _ = p.communicate_utf8_finish(res)
                on_done(p.get_successful(), (out or "").strip())
            except GLib.Error as err:
                on_done(False, str(err))

        proc.communicate_utf8_async(stdin, None, finished)
        return

    stream = Gio.DataInputStream.new(proc.get_stdout_pipe())
    collected = []

    def read_next():
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, got_line)

    def got_line(src, res):
        try:
            line, _length = src.read_line_finish_utf8(res)
        except GLib.Error as err:
            on_done(False, str(err))
            return
        if line is None:                      # end of output
            proc.wait_async(None, waited)
            return
        line = line.strip()
        if line:
            collected.append(line)
            on_line(line)
        read_next()

    def waited(p, res):
        try:
            p.wait_finish(res)
            on_done(p.get_successful(), "\n".join(collected))
        except GLib.Error as err:
            on_done(False, str(err))

    read_next()


class Window(Adw.ApplicationWindow):
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
        # The socket sudo asks at while an install runs, and nothing outside
        # of one.
        self.askpass = None
        self.comp_rows = {}
        self.modem_rows = []
        # Whether there is anything behind each control. A switch whose tool
        # did not answer must not look operable - and it must not become
        # operable again the moment something else finishes, which is what
        # happened as long as set_busy was the only hand on the sensitivity.
        self.audio_ok = True
        self.dmnr_ok = True
        self.modem_ok = True
        self.gps_ok = True
        self.gps_rows = []
        self.batt_rows = []

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
        # by itself: take its own next version. It appears when there is one
        # and is gone the rest of the time, which makes its presence the
        # message.
        self.update_btn = Gtk.Button(icon_name="software-update-available-symbolic")
        self.update_btn.set_tooltip_text("A newer version of this app is available")
        self.update_btn.set_visible(False)
        self.update_btn.connect("clicked", lambda *_: self.ask_self_update())
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

        # --- Was gerade wirklich runs ---
        info = Adw.PreferencesGroup(title="Status")
        self.row_profile = Adw.ActionRow(title="Owns the Android HAL", subtitle="reading …")
        self.row_server = Adw.ActionRow(title="Sound server", subtitle="…")
        self.row_sinks = Adw.ActionRow(title="Outputs", subtitle="…")
        for row in (self.row_profile, self.row_server, self.row_sinks):
            row.set_subtitle_selectable(True)
            info.add(row)
        page.add(info)


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
        self.comp_rows = {}
        # Kept, not local: a tool fetched from the components page gets its
        # real page built right there, and that needs the same builder.
        self.builders = {"audio": lambda: page,
                      "modem": self.build_modem_page,
                      "gps": self.build_gps_page,
                      "switches": self.build_switches_page,
                      "battery": self.build_battery_page}
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
        self.live["app"] = _tool_maybe(SELF["tool"])
        # The page widget of each tab, so one of them can be replaced later
        # without the others being rebuilt underneath somebody.
        self.pages = {}
        for comp in COMPONENTS:
            if not comp.get("needs", lambda: True)():
                continue
            self.build_component_page(comp)

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


    # ------------------------------------------------------------ components

    def build_component_page(self, comp):
        """Build one tab and put it in the stack: the real page if its tool is
        there, otherwise the one that offers to fetch it."""
        tool = _tool_maybe(comp["tool"])
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
        if self.live.get(comp["key"]) or not _tool_maybe(comp["tool"]):
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
            if not _tool_maybe(comp["tool"]) or comp["tool"] not in self.comp_rows:
                continue
            self.look_for_update(comp)
        self.check_self_update()

    def look_for_update(self, comp, other=None):
        """Where an update for this component would come from, in the order
        that leaves other people's work alone: our own clone first, somebody
        else's only to read, and `other` when neither had anything to say."""
        mine = clone_path(comp) if is_clone(clone_path(comp)) else None
        if mine:
            self.check_component(comp, mine, other)
            return
        foreign_path = clone_elsewhere(comp["url"])
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

        def geholt(ok, _out):
            if ok:
                run_async(["git", "-C", mine, "rev-list", "--count",
                           "HEAD..@{u}"], counted, timeout=30)
            elif other:
                other()

        run_async(["git", "-C", mine, "fetch", "--quiet"], geholt, timeout=60)

    def check_app_program(self, comp=SELF):
        """Is the program that is running the one the clone has?

        The git comparison answers a different question, and for this one
        component it is usually the wrong one: the clone on this phone is
        where the next version of the window is WRITTEN. It is never behind
        the server - what it is, regularly, is newer than the program that is
        installed, and until now the only way to close that gap was a
        terminal.

        Answered by comparing the two files, not by asking git: whether the
        clone is committed, pushed or dirty is a different matter entirely.
        """
        source = (clone_path(comp) if is_clone_of(clone_path(comp), comp["url"])
                  else clone_elsewhere(comp["url"]))
        laufend = self.live.get("app")
        if not source or not laufend:
            return
        try:
            with open(os.path.join(source, "misc-de.py"), "rb") as fh:
                im_klon = fh.read()
            with open(laufend, "rb") as fh:
                installiert = fh.read()
        except OSError:
            return                             # nothing to compare, nothing said
        if im_klon != installiert:
            self.offer_update(
                comp, "the misc-de.py in this clone is not the program that "
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
        def verglichen(ok, out, oben):
            hier = (out or "").strip().split()
            if not ok or not oben or not hier or hier[0] == oben:
                if other:
                    other()
                return                         # nothing to say, so nothing said
            self.offer_update(comp, "something new in " + comp["url"], foreign_path)

        def oben_gelesen(ok, out):
            head = (out or "").split()
            oben = head[0] if ok and head else None
            run_async(["git", "-C", foreign_path, "rev-parse", "HEAD"],
                      lambda ok2, out2: verglichen(ok2, out2, oben), timeout=30)

        run_async(["git", "ls-remote", comp["url"], "HEAD"], oben_gelesen,
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
        self.askpass = Askpass(secret) if comp["root"] else None
        helfer = self.askpass.start() if self.askpass else None
        steps = component_steps(comp, state, secret, path, helfer)

        # A helper that could not be set up is not fatal - the install falls
        # back on sudo's ticket, which is where it was before this existed.
        # But it is the reason an install can stop at its first sudo line, so
        # it is said out loud rather than left to be guessed at.
        if self.askpass is not None and helfer is None and self.askpass.error:
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
            run_async(argv, step, timeout=deadline, cwd=cwd, stdin=stdin,
                      env=env)

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

    # ------------------------------------------------ Der Weg zurueck
    #
    # One way back, built the same way on every page: same group title, same
    # button, same words, same place - the foot of the page, below everything
    # the page is about. (An update offer can appear under it; that one is
    # about the tool itself, not about what the page does.) Only the
    # description differs, because what "as it came" costs is a different
    # thing on each of them.
    #
    # Before this, audio had a blue "Restore sound" and the modem a red
    # "Restore shipped state" while the other two pages had none at all. Three
    # different shapes for one idea, and the colours made a claim on top of
    # it: blue said "do this", red said "careful". Neither is true in general
    # - whether going back is a rescue or a loss depends on the page, and the
    # description is where that belongs. So the button is plain everywhere.

    RESTORE_TITLE = "Back to how it shipped"
    RESTORE_LABEL = "Restore shipped state"

    def restart_self(self):
        """Replace this process with the program that was just installed.

        execv and not "start a copy, then quit": the application id makes a
        second instance hand its activation to the one already running, so the
        copy would present the OLD window and then die with it. Replacing the
        image keeps the pid, releases the bus name with the connection, and
        the new program takes the same place in the shell.
        """
        prog = _tool_maybe("misc-de") or os.path.abspath(sys.argv[0])
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

    # ------------------------------------------------------------ Switches

    def build_switches_page(self):
        """The three sliders on the housing, and what each of them really does.

        They look alike and work nothing alike. Camera and network are software
        kills: a GPIO tells the Android side, which stops a service with signal
        9. The microphone one cuts the line, which is why it is the only one
        the system cannot see at all - and the only one that is beyond doubt.
        It is therefore also the only one with no reading here: finding out
        would mean listening, and this page says so instead of guessing.
        """
        spage = Adw.PreferencesPage()

        # No paragraphs on this page. Each group is a switch, each row says
        # what it is, and what needed explaining sits in the row's own
        # subtitle - where it is read next to the thing it is about.
        grp = Adw.PreferencesGroup(title="Indicator")
        self.sw_row = Adw.SwitchRow(
            title="Icons for the camera and network switch",
            subtitle="reading …")
        self.sw_row.connect("notify::active", self.on_indicator_switch)
        grp.add(self.sw_row)
        self.sw_persist = Adw.SwitchRow(
            title="Remember this choice",
            subtitle="Off: gone again after the next boot",
            active=True,
        )
        self.sw_persist.connect("notify::active", self.on_indicator_persist)
        grp.add(self.sw_persist)
        spage.add(grp)

        cam = Adw.PreferencesGroup(title="1 · Camera")
        self.srow_cam = Adw.ActionRow(title="Position", subtitle="…")
        self.srow_cam_hal = Adw.ActionRow(title="Camera service", subtitle="…")
        self.srow_cams = Adw.ActionRow(title="Cameras affected", subtitle="…")
        for row in (self.srow_cam, self.srow_cam_hal, self.srow_cams):
            row.set_subtitle_selectable(True)
            cam.add(row)
        spage.add(cam)

        net = Adw.PreferencesGroup(title="2 · Network")
        self.srow_net = Adw.ActionRow(title="Position", subtitle="…")
        self.srow_net.set_subtitle_selectable(True)
        net.add(self.srow_net)
        # Shown as a switch like the other two, but fixed on: the Android side
        # stops the RIL before any program here learns the slider moved. The
        # only way to "deselect" it would be to start the modem back up behind
        # the switch - undermining the very thing somebody flipped it for.
        self.sw_modem = Adw.SwitchRow(
            title="The mobile network goes with the switch",
            subtitle="always, and not ours to change - firmware does it. "
            "(Settings switches mobile data off separately, any time.)",
            active=True,
        )
        self.sw_modem.set_sensitive(False)
        net.add(self.sw_modem)
        self.sw_wifi = Adw.SwitchRow(
            title="Take Wi-Fi down with it as well",
            subtitle="reading …",
        )
        self.sw_wifi.connect("notify::active", self.on_extra_wifi)
        net.add(self.sw_wifi)
        self.sw_bt = Adw.SwitchRow(
            title="Take Bluetooth down with it as well",
            subtitle="reading …",
        )
        self.sw_bt.connect("notify::active", self.on_extra_bt)
        net.add(self.sw_bt)
        spage.add(net)

        mic = Adw.PreferencesGroup(title="3 · Microphone")
        # The one line that cannot go: without it the row reads like a defect.
        # It cuts the built-in microphones for real, and reading the position
        # would mean opening them - which is what the switch is flipped
        # against. The long version lives in the project's FINDINGS.md.
        self.srow_mic = Adw.ActionRow(
            title="Position",
            subtitle="not readable - finding out would mean opening the "
            "microphone, which is what this switch is against")
        self.srow_mic.set_subtitle_selectable(True)
        mic.add(self.srow_mic)
        # For anyone who does want a number: one measurement, asked for by
        # hand, on the terminal. Deliberately not a button here - a button is
        # an invitation, and this one should be a decision.
        hint = Adw.ActionRow(
            title="Measure once by hand",
            subtitle="killswitch-indicator mic-check")
        hint.set_subtitle_selectable(True)
        mic.add(hint)
        spage.add(mic)

        # Nothing here can undo what the sliders do - they are hardware, and
        # Android acts on them before this program hears about it. What this
        # page added is the indicator and the two extra radios, and that is
        # exactly what goes away again.
        back, self.sw_restore_btn = self.build_restore_group(
            "Stops the icons in the top bar and takes them out of the next "
            "boot, and leaves Wi-Fi and Bluetooth out of the network switch. "
            "The sliders themselves keep doing what they do - that is "
            "hardware, and nothing here reaches it.",
            self.on_switches_restore)
        spage.add(back)

        self.sw_rows = [self.sw_row, self.sw_persist, self.sw_wifi, self.sw_bt,
                        self.sw_restore_btn]
        return spage

    def on_switches_status(self, ok, out):
        if not ok:
            for row in (self.srow_cam, self.srow_net):
                row.set_subtitle("killswitch-indicator did not answer")
            return
        try:
            data = json.loads(out)
        except ValueError:
            self.srow_cam.set_subtitle("unreadable answer")
            return

        def stellung(value):
            return {"0": "engaged", "1": "free"}.get(value, "unknown")

        self.srow_cam.set_subtitle(stellung(data.get("switches", {}).get("cam_switch")))
        self.srow_net.set_subtitle(stellung(data.get("switches", {}).get("nwk_switch")))

        hal = data.get("camera_hal")
        self.srow_cam_hal.set_subtitle(
            "running" if hal else "stopped" if hal is False else "unknown")

        cams = data.get("cameras")
        if cams:
            sides = ", ".join(c.lower() for c in cams)
            self.srow_cams.set_subtitle(f"all {len(cams)} ({sides}) - never one alone")
        else:
            self.srow_cams.set_subtitle(
                "all of them - list not fetched yet "
                "(sudo killswitch-indicator cameras --refresh)")

        extras = data.get("network_extras", {})
        radios = data.get("radios", {})
        self._loading = True
        self.sw_wifi.set_active(bool(extras.get("wifi")))
        self.sw_bt.set_active(bool(extras.get("bluetooth")))
        self._loading = False
        for row, key in ((self.sw_wifi, "wifi"), (self.sw_bt, "bluetooth")):
            state = radios.get(key)
            row.set_subtitle("currently on" if state else
                             "currently off" if state is False else "not reachable")

    def on_indicator_active(self, ok, out):
        aktiv = ok and out.strip() == "active"
        self._loading = True
        self.sw_row.set_active(aktiv)
        self._loading = False
        self.sw_row.set_subtitle("running" if aktiv else "not running")

    def on_indicator_enabled(self, ok, out):
        self._loading = True
        self.sw_persist.set_active(ok and out.strip() == "enabled")
        self._loading = False

    def on_indicator_switch(self, row, _param):
        if getattr(self, "_loading", False):
            return
        verb = "start" if row.get_active() else "stop"
        run_async(["systemctl", "--user", verb, "killswitch-indicator"],
                  lambda ok, out: self.after_indicator(ok, out, verb))

    def after_indicator(self, ok, out, verb):
        if not ok:
            self.toasts.add_toast(Adw.Toast(title=f"Could not {verb} the indicator"))
        self.refresh()

    def on_indicator_persist(self, row, _param):
        if getattr(self, "_loading", False):
            return
        verb = "enable" if row.get_active() else "disable"
        run_async(["systemctl", "--user", verb, "killswitch-indicator"],
                  lambda ok, out: self.after_indicator(ok, out, verb))

    def on_extra_wifi(self, row, _param):
        self.set_extra("wifi", row)

    def on_extra_bt(self, row, _param):
        self.set_extra("bluetooth", row)

    def set_extra(self, radio, row):
        if getattr(self, "_loading", False):
            return
        value = "on" if row.get_active() else "off"
        run_async([self.live["switches"], "config", radio, value],
                  lambda ok, out: self.after_extra(ok, radio, value))

    def after_extra(self, ok, radio, value):
        if not ok:
            self.toasts.add_toast(Adw.Toast(title=f"Could not change {radio}"))
            self.refresh()
            return
        if value == "on":
            self.toasts.add_toast(Adw.Toast(
                title=f"{radio} will go off with the network switch"))

    def on_switches_restore(self, _btn):
        """Everything this page added, taken back out - in one go.

        Three commands, not one: the tool owns the two extra radios and
        systemd owns the unit. They run one after the other and stop at the
        first failure, so a half-done state is reported rather than passed off
        as success.
        """
        if self.busy:
            return
        self.set_busy(True)
        self.run_chain([
            [self.live["switches"], "config", "wifi", "off"],
            [self.live["switches"], "config", "bluetooth", "off"],
            ["systemctl", "--user", "disable", "--now", "killswitch-indicator"],
        ], self.on_switches_restored)

    def on_switches_restored(self, ok, out):
        if ok:
            self.toast("Shipped state - no icons, and the switch takes only "
                       "the modem")
        else:
            self.toast("Could not restore the shipped state")
            self.report(out or "No output.")
        self.refresh()

    # ------------------------------------------------------------ Battery

    def build_battery_page(self):
        """One switch, one option, and the numbers behind them.

        The reading is the point of this page: a percentage and a lightning
        bolt look the same at one watt and at six, and that difference is
        hours. So "Now" says what is actually going in, in watts, whether the
        colouring is on or not.
        """
        bpage = Adw.PreferencesPage()

        grp = Adw.PreferencesGroup(title="Battery icon")
        self.batt_row = Adw.SwitchRow(
            title="Colour it by charging power",
            subtitle="reading …")
        self.batt_row.connect("notify::active", self.on_battery_switch)
        grp.add(self.batt_row)
        # The second option, and the reason it is a switch of its own: on
        # battery the colour means the opposite, and it is on all day. Wanted
        # by some, noise to others.
        self.batt_drain = Adw.SwitchRow(
            title="On battery too",
            subtitle="White until the drain is unusual, then amber, then red")
        self.batt_drain.connect("notify::active", self.on_battery_discharge)
        grp.add(self.batt_drain)
        self.batt_persist = Adw.SwitchRow(
            title="Remember this choice",
            subtitle="Off: gone again after the next boot")
        self.batt_persist.connect("notify::active", self.on_battery_persist)
        grp.add(self.batt_persist)
        bpage.add(grp)

        # Two halves, two rows: the icon says two different things at once -
        # the shell how fast the battery is moving, the filling how full it
        # is - and a single "Colour" row would have to hide one of them.
        info = Adw.PreferencesGroup(title="Status")
        self.brow_now = Adw.ActionRow(title="Now", subtitle="…")
        self.brow_colour = Adw.ActionRow(title="Shell", subtitle="…")
        self.brow_fill = Adw.ActionRow(title="Filling", subtitle="…")
        self.brow_theme = Adw.ActionRow(title="Theme", subtitle="…")
        for row in (self.brow_now, self.brow_colour, self.brow_fill,
                    self.brow_theme):
            row.set_subtitle_selectable(True)
            info.add(row)
        bpage.add(info)

        back, self.batt_restore_btn = self.build_restore_group(
            "Stops the colouring, takes it out of the next boot, puts your "
            "own theme back and removes the three it generated. What the "
            "battery reports is untouched - that is the kernel's.",
            self.on_battery_restore)
        bpage.add(back)

        self.batt_rows = [self.batt_row, self.batt_drain, self.batt_persist,
                          self.batt_restore_btn]
        return bpage

    def on_battery_status(self, ok, out):
        if not ok:
            for row in (self.brow_now, self.brow_colour, self.brow_fill,
                        self.brow_theme):
                row.set_subtitle("battctl did not answer")
            return
        try:
            data = json.loads(out)
        except ValueError:
            self.brow_now.set_subtitle("unreadable answer")
            return

        prozent = data.get("percent")
        stand = "" if prozent is None else ", %d %%" % prozent
        if data.get("readable") and data.get("plausible"):
            direction = {"Charging": "going in", "Discharging": "coming out"}
            whither = direction.get(data.get("state"), data.get("state", "?"))
            self.brow_now.set_subtitle("%.1f W %s%s"
                                       % (data.get("watt", 0.0), whither, stand))
        elif data.get("readable"):
            # The one failure that looks like a working phone: a driver
            # reporting the wrong unit would put the icon permanently green.
            self.brow_now.set_subtitle("implausible reading - not coloured")
        else:
            self.brow_now.set_subtitle("battery not readable")

        cfg = data.get("config", {})

        def colour_line(shows, would_be, rule):
            """What is showing, and - when they differ - what the reading
            says it would be. The two differ while a colour is waiting out
            its dwell time, and while the service is off entirely."""
            secret = "plain" if shows == "none" else shows
            if shows != would_be:
                secret += " - would be %s" % ("plain" if would_be == "none" else would_be)
            return "%s · %s" % (secret, rule)

        # Two states that would otherwise look like the colouring simply
        # not working, and both are things the phone is doing, not faults.
        rule = ("green from %.1f W, amber from %.1f W while charging"
                 % (cfg.get("charge_green_w", 0.0),
                    cfg.get("charge_amber_w", 0.0)))
        if not data.get("sources_agree", True):
            rule = ("the kernel and UPower disagree about the direction, "
                     "so the shell stays plain")
        self.brow_colour.set_subtitle(colour_line(
            data.get("showing", "none"), data.get("bucket", "none"), rule))
        stand_regel = ("amber below %d %%, red below %d %%"
                       % (int(cfg.get("level_amber_pct", 0)),
                          int(cfg.get("level_red_pct", 0))))
        if not data.get("split_icon", True):
            stand_regel += (" · this icon is one shape, so both halves take "
                            "the more urgent colour")
        self.brow_fill.set_subtitle(colour_line(
            data.get("level_showing", "none"), data.get("level_bucket", "none"),
            stand_regel))
        self.brow_theme.set_subtitle(
            "%s (on top of %s)" % (data.get("theme", "?"),
                                   data.get("base_theme", "?")))
        if not data.get("can_theme", True):
            # Everything else can look healthy while this is the reason
            # nothing ever changes colour.
            self.brow_theme.set_subtitle(
                "%s - no GTK3 stylesheet, nothing can be coloured"
                % data.get("base_theme", "?"))

        self._loading = True
        self.batt_drain.set_active(bool(cfg.get("discharging")))
        self._loading = False
        # The switch says what it is for; the numbers live in the status
        # rows, next to the colour they decide. Saying them in both places
        # was the same sentence twice on a 360-pixel page.
        if cfg:
            self.batt_row.set_subtitle(
                "The bolt follows the charging power, the frame the drain")
            self.batt_drain.set_subtitle(
                "White below %.1f W, then amber, red from %.1f W"
                % (cfg.get("drain_amber_w", 0.0), cfg.get("drain_red_w", 0.0)))

    def on_battery_active(self, ok, out):
        aktiv = ok and out.strip() == "active"
        self._loading = True
        self.batt_row.set_active(aktiv)
        self._loading = False
        if not aktiv:
            self.batt_row.set_subtitle("not running - the icon stays white")

    def on_battery_enabled(self, ok, out):
        self._loading = True
        self.batt_persist.set_active(ok and out.strip() == "enabled")
        self._loading = False

    def on_battery_switch(self, row, _param):
        if getattr(self, "_loading", False):
            return
        verb = "start" if row.get_active() else "stop"
        run_async(["systemctl", "--user", verb, BATTERY_UNIT],
                  lambda ok, out: self.after_battery(ok, out, verb))

    def on_battery_persist(self, row, _param):
        if getattr(self, "_loading", False):
            return
        verb = "enable" if row.get_active() else "disable"
        run_async(["systemctl", "--user", verb, BATTERY_UNIT],
                  lambda ok, out: self.after_battery(ok, out, verb))

    def on_battery_discharge(self, row, _param):
        """The second option. battctl re-reads its file, so this takes effect
        without the service being restarted - which is the whole reason the
        switch can sit here and not next to a "restart to apply"."""
        if getattr(self, "_loading", False):
            return
        value = "on" if row.get_active() else "off"
        run_async([self.live["battery"], "config", "discharging", value],
                  lambda ok, out: self.after_battery(ok, out, "change"))

    def after_battery(self, ok, out, verb):
        if not ok:
            self.toast("Could not %s the colouring" % verb)
            if out:
                self.report(out)
        self.refresh()

    def on_battery_restore(self, _btn):
        """The service first, then the tool.

        In that order on purpose: battctl restore puts the theme back and
        deletes what it generated, and a daemon still running would write
        both again within the minute.
        """
        if self.busy:
            return
        self.set_busy(True)
        self.run_chain([
            ["systemctl", "--user", "disable", "--now", BATTERY_UNIT],
            [self.live["battery"], "restore"],
        ], self.on_battery_restored)

    def on_battery_restored(self, ok, out):
        if ok:
            self.toast("Shipped state - your own theme, no colouring")
        else:
            self.toast("Could not restore the shipped state")
            self.report(out or "No output.")
        self.refresh()

    # ------------------------------------------------------------ Modem

    def build_modem_page(self):
        """The same shape as the audio page, because it is the same question:
        the phone as it shipped, or the phone as somebody repaired it."""
        mpage = Adw.PreferencesPage()

        # No paragraph under the heading. It was the last one left, and it
        # showed: a group with a description puts its title higher than a
        # group without one, so this page's heading sat twelve pixels above
        # the heading of every other tab. What it said is in the row below
        # ("Off: the state the phone shipped in") and, in full, at the foot of
        # the page under "Back to how it shipped".
        grp = Adw.PreferencesGroup(title="Modem")
        self.modem_row = Adw.SwitchRow(
            title="Repairs active",
            subtitle="reading …",
        )
        self.modem_row.connect("notify::active", self.on_modem_switch)
        grp.add(self.modem_row)

        self.modem_persist = Adw.SwitchRow(
            title="Remember this choice",
            subtitle="Off: the next boot returns to what was recorded",
            active=True,
        )
        grp.add(self.modem_persist)

        self.modem_progress = Gtk.ProgressBar(show_text=True, text="")
        for m in ("top", "bottom"):
            getattr(self.modem_progress, "set_margin_" + m)(6)
        for m in ("start", "end"):
            getattr(self.modem_progress, "set_margin_" + m)(12)
        self.modem_revealer = Gtk.Revealer(
            child=self.modem_progress,
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            reveal_child=False,
        )
        grp.add(self.modem_revealer)
        mpage.add(grp)

        info = Adw.PreferencesGroup(title="Status")
        self.mrow_profile = Adw.ActionRow(title="Profile", subtitle="…")
        self.mrow_health = Adw.ActionRow(title="Checks", subtitle="…")
        self.mrow_signal = Adw.ActionRow(title="Signal", subtitle="…")
        for row in (self.mrow_profile, self.mrow_health, self.mrow_signal):
            row.set_subtitle_selectable(True)
            info.add(row)
        mpage.add(info)

        # What it costs here is the opposite of the audio page: that one
        # brings something back, this one takes function away. Same button,
        # and the description carries the difference.
        back, self.modem_restore_btn = self.build_restore_group(
            "Takes every repair out, restarts the modem stack and remembers "
            "it. With Wi-Fi off there is then no route out and no name "
            "resolution.",
            self.on_modem_restore)
        mpage.add(back)

        self.modem_rows = [self.modem_row, self.modem_persist,
                           self.modem_restore_btn]
        return mpage

    # ------------------------------------------------------------ GPS

    def build_gps_page(self):
        """Where the phone says it is.

        The same question as the other two pages - as shipped, or repaired -
        but the "off" side is the one that needs explaining here. Off does not
        mean "no location". It means geoclue publishes the position of the
        carrier's exit node as though the phone had been observed there.
        """
        gpage = Adw.PreferencesPage()

        grp = Adw.PreferencesGroup(title="Location")
        self.gps_row = Adw.SwitchRow(
            title="Filter active",
            subtitle="reading …",
        )
        self.gps_row.connect("notify::active", self.on_gps_switch)
        grp.add(self.gps_row)

        self.gps_persist = Adw.SwitchRow(
            title="Remember this choice",
            subtitle="Off: the next boot returns to what was recorded",
            active=True,
        )
        grp.add(self.gps_persist)

        # Giving back, in its own group: this is the opposite direction of
        # everything above it. The filter decides what this phone accepts;
        # this decides what it hands out, and conflating the two in one group
        # would be the wrong question in the wrong place.
        # No description on the group: one paragraph here lifts the heading
        # above every other tab's, which was measured on the phone. What has
        # to be said sits in the row it is about.
        contribution = Adw.PreferencesGroup(title="Contribute to beaconDB")
        self.gps_contrib = Adw.SwitchRow(
            title="Send my observations",
            subtitle="reading …",
        )
        self.gps_contrib.connect("notify::active", self.on_gps_contrib)
        contribution.add(self.gps_contrib)
        self.gps_contrib_stats = Adw.ActionRow(
            title="Sent so far", subtitle="—",
        )
        contribution.add(self.gps_contrib_stats)
        gpage.add(contribution)

        self.gps_progress = Gtk.ProgressBar(show_text=True, text="")
        for m in ("top", "bottom"):
            getattr(self.gps_progress, "set_margin_" + m)(6)
        for m in ("start", "end"):
            getattr(self.gps_progress, "set_margin_" + m)(12)
        self.gps_revealer = Gtk.Revealer(
            child=self.gps_progress,
            transition_type=Gtk.RevealerTransitionType.SLIDE_DOWN,
            reveal_child=False,
        )
        grp.add(self.gps_revealer)
        gpage.add(grp)

        info = Adw.PreferencesGroup(title="Status")
        self.grow_profile = Adw.ActionRow(title="Profile", subtitle="…")
        self.grow_seen = Adw.ActionRow(title="Since this boot", subtitle="…")
        self.grow_health = Adw.ActionRow(title="Checks", subtitle="…")
        for row in (self.grow_profile, self.grow_seen, self.grow_health):
            row.set_subtitle_selectable(True)
            info.add(row)
        gpage.add(info)

        # The switch above reaches the same state, and for a while that was
        # the argument against a button here. But a way back that exists on
        # some pages and not on others is one somebody has to go looking for -
        # so it is here too, worded so that nobody presses it by mistake.
        back, self.gps_restore_btn = self.build_restore_group(
            "Switches the filter off and remembers it. Asked where it is with "
            "no Wi-Fi it recognises, the phone then publishes the position of "
            "the carrier's IP address again - the exit node of their network, "
            "tens of kilometres away.",
            self.on_gps_restore)
        gpage.add(back)

        self.gps_rows = [self.gps_row, self.gps_persist, self.gps_contrib,
                         self.gps_restore_btn]
        return gpage

    def on_gps_profile(self, ok, out):
        """gpsctl prints the profile and *then* fails, when the two halves of
        the state disagree - the switch is "mixed" and it exits 1 to say so.

        So the return code is not what decides whether there was an answer.
        Reading it that way would turn the one state a person most needs to see
        into "gpsctl did not answer", on a phone where gpsctl answered
        perfectly well and had something important to report.
        """
        found = self._keyed(out)
        recorded, actual = found.get("recorded"), found.get("actual")
        if not recorded or not actual:
            self.gps_ok = False
            self.gps_row.set_sensitive(False)
            self.grow_profile.set_subtitle("gpsctl did not answer")
            return
        self.gps_ok = True

        if actual == "fixed":
            words = "IP positions are thrown away"
        elif actual == "shipped":
            words = "FuriOS as it came - the IP position is published"
        else:
            words = "half applied - use \"Filter active\" to settle it"
        if recorded != actual and actual in ("fixed", "shipped"):
            words += f" · not remembered, the next boot returns to \"{recorded}\""
        self.grow_profile.set_subtitle(words)

        self._syncing = True
        self.gps_row.set_active(actual == "fixed")
        self.gps_persist.set_active(recorded == actual)
        self._syncing = False
        self.gps_row.set_subtitle(
            "On: a position that is really just the carrier's IP address is refused"
            if actual == "fixed"
            else "Off: the carrier's IP address is published as a position"
        )

    def on_gps_status(self, ok, out):
        if not out:
            self.grow_health.set_subtitle("gpsctl did not answer")
            self.grow_seen.set_subtitle("nothing to count")
            return
        bad = sum(1 for line in out.splitlines() if "FAIL" in line)
        good = sum(1 for line in out.splitlines() if " ok " in line)
        self.grow_health.set_subtitle(
            f"{good} in place" if bad == 0 else f"{good} in place, {bad} not"
        )
        # "since boot: 5 asked, 0 located, 5 IP fallbacks rejected" - said back
        # as it was printed. Counting nothing is a normal state and reads as one
        # on a phone that has not asked yet, so it is not dressed up as a fault.
        for line in out.splitlines():
            if line.strip().startswith("since boot:"):
                self.grow_seen.set_subtitle(line.split(":", 1)[1].strip())
                break
        else:
            self.grow_seen.set_subtitle("nothing counted yet")

    def on_gps_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        if not PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        mode = "set" if self.gps_persist.get_active() else "try"
        want = "fixed" if row.get_active() else "shipped"
        self.set_busy(True)
        self.gps_progress.set_text("Switching …")
        self.gps_revealer.set_reveal_child(True)
        self.pulse_start("Switching the location filter …")
        run_async([PKEXEC, self.live["gps"], mode, want], self.on_gps_switched,
                  on_line=self.on_progress_line)

    def on_gps_switched(self, ok, out):
        self.pulse_stop()
        self.gps_revealer.set_reveal_child(False)
        if not ok:
            self.toast("Switching the location filter failed")
            self.report(out or "No output.")
        elif not self.gps_row.get_active():
            # Not a neutral "done": the switch has just been turned off, and
            # what that means is the thing somebody should be told.
            self.toast("Filter off - the IP position is published again")
        else:
            self.toast("Filter on - IP positions are refused")
        self.refresh()

    def on_gps_contrib(self, row, _param):
        """On or off, and nothing in between - the tool keeps the marker."""
        if self._syncing or self.busy:
            return
        tool = _tool_maybe(CONTRIB)
        if not tool:
            return
        self.set_busy(True)
        run_async([tool, "on" if row.get_active() else "off"],
                  self.on_gps_contrib_done)

    def on_gps_contrib_done(self, ok, out):
        self.set_busy(False)
        if not ok:
            self.toast("Could not change the contribution setting")
            self.report(out or "No output.")
        self.refresh_gps_contrib()

    def refresh_gps_contrib(self):
        tool = _tool_maybe(CONTRIB)
        if not tool:
            # Not installed is not "off": saying "off" would claim we looked.
            self._syncing = True
            self.gps_contrib.set_active(False)
            self._syncing = False
            self.gps_contrib.set_sensitive(False)
            self.gps_contrib.set_subtitle("not installed")
            self.gps_contrib_stats.set_subtitle("—")
            return
        run_async([tool, "status"], self.on_gps_contrib_status)

    def on_gps_contrib_status(self, ok, out):
        if not ok:
            self.gps_contrib.set_subtitle("did not answer")
            return
        values = dict(z.split("=", 1) for z in out.splitlines() if "=" in z)
        an = values.get("contributing") == "yes"
        self._syncing = True
        self.gps_contrib.set_active(an)
        self._syncing = False
        self.gps_contrib.set_sensitive(True)
        # Asked for and actually happening are two facts, and the row must not
        # pass the first off as the second: the service exits when the marker
        # is missing, so "on" with nothing running is a state that exists.
        runs = values.get("running") == "yes"
        if an and not runs:
            self.gps_contrib.set_subtitle(
                "Switched on, but the service is not running - "
                "nothing is being collected")
        elif an:
            self.gps_contrib.set_subtitle(
                "Networks in range with the satellite position, over Wi-Fi only")
        else:
            self.gps_contrib.set_subtitle(
                "Off - nothing is collected or sent. On: networks in range, "
                "never hidden or _nomap ones")
        # Both numbers, because they answer different questions: whether it is
        # measuring at all, and whether any of it has reached beaconDB.
        self.gps_contrib_stats.set_subtitle(
            "%s sent, %s waiting" % (values.get("submitted", "0"),
                                     values.get("queued", "0")))

    def on_gps_restore(self, _btn):
        if self.busy:
            return
        if not PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        self.set_busy(True)
        self.gps_progress.set_text("Restoring …")
        self.gps_revealer.set_reveal_child(True)
        self.pulse_start("Back to the shipped state …")
        # "set", not "try", like the other pages: what it restores is what the
        # phone comes back to after the next boot.
        run_async([PKEXEC, self.live["gps"], "set", "shipped"], self.on_gps_restored,
                  on_line=self.on_progress_line)

    def on_gps_restored(self, ok, out):
        self.pulse_stop()
        self.gps_revealer.set_reveal_child(False)
        if ok:
            # Again not a neutral "done" - what was switched off is the part
            # that matters.
            self.toast("Shipped state - the IP position is published again")
        else:
            self.toast("Could not restore the shipped state")
            self.report(out or "No output.")
        self.refresh()

    # -------------------------------------------------------------- state

    def refresh(self):
        """Ask every tool whose page was actually built.

        self.live, not the module constants: a page that was not built has no
        rows for an answer to arrive at, and an answer that arrives anyway
        takes the callback down with an AttributeError nobody sees.
        """
        if self.live.get("audio"):
            run_async([self.live["audio"], "status"], self.on_status)
            dmnr = _tool_maybe(DMNR)
            if dmnr:
                run_async([dmnr, "status"], self.on_dmnr_status)
            else:
                # Same installer, so this only happens in the seconds after
                # one that stopped half way. The row says so and closes.
                self.on_dmnr_status(False, "")
        if self.live.get("modem"):
            # Both read-only, and neither needs root - which is the whole
            # reason the page can show something before anybody touches it.
            run_async([self.live["modem"], "profile"], self.on_modem_profile)
            run_async([self.live["modem"], "status"], self.on_modem_status)
        if self.live.get("gps"):
            run_async([self.live["gps"], "profile"], self.on_gps_profile)
            run_async([self.live["gps"], "status"], self.on_gps_status)
            # Same installer as gpsctl, so this is normally there - and when
            # it is not, the row says so rather than showing a false "off".
            self.refresh_gps_contrib()
        if self.live.get("switches"):
            run_async([self.live["switches"], "status", "--json"],
                      self.on_switches_status)
            run_async(["systemctl", "--user", "is-active",
                       "killswitch-indicator"], self.on_indicator_active)
            run_async(["systemctl", "--user", "is-enabled",
                       "killswitch-indicator"], self.on_indicator_enabled)
        if self.live.get("battery"):
            run_async([self.live["battery"], "status", "--json"],
                      self.on_battery_status)
            run_async(["systemctl", "--user", "is-active", BATTERY_UNIT],
                      self.on_battery_active)
            run_async(["systemctl", "--user", "is-enabled", BATTERY_UNIT],
                      self.on_battery_enabled)


    # "recorded: x" and "actual: y", split on the colon rather than matched
    # against a prefix. modemctl lives in another package, so this is a
    # contract between two repositories - it is checked from the other side
    # too, where the words are printed.
    @staticmethod
    def _keyed(out):
        found = {}
        for line in out.splitlines():
            key, sep, value = line.partition(":")
            if sep:
                found[key.strip()] = value.strip()
        return found

    def on_modem_profile(self, ok, out):
        if not ok:
            self.modem_ok = False
            self.modem_row.set_sensitive(False)
            self.mrow_profile.set_subtitle("modemctl did not answer")
            return
        self.modem_ok = True
        found = self._keyed(out)
        recorded, actual = found.get("recorded", "?"), found.get("actual", "?")

        if actual == "fixed":
            words = "the repairs are in place"
        elif actual == "shipped":
            words = "FuriOS as it came"
        else:
            # "mixed" is a real state and saying either of the other two would
            # be wrong in both directions.
            words = "half repaired - use \"Repairs active\" to settle it"
        if recorded != actual and actual in ("fixed", "shipped"):
            words += f" · not remembered, the next boot returns to \"{recorded}\""
        self.mrow_profile.set_subtitle(words)

        self._syncing = True
        self.modem_row.set_active(actual == "fixed")
        self.modem_persist.set_active(recorded == actual)
        self._syncing = False
        self.modem_row.set_subtitle(
            "On: patched, with a route and a resolver that work without Wi-Fi"
            if actual == "fixed"
            else "Off: as it shipped - no route and no resolver without Wi-Fi"
        )

    def on_modem_status(self, ok, out):
        if not ok and not out:
            self.mrow_health.set_subtitle("modemctl did not answer")
            return
        bad = sum(1 for line in out.splitlines() if "FAIL" in line)
        good = sum(1 for line in out.splitlines() if " ok " in line)
        self.mrow_health.set_subtitle(
            f"{good} in place" if bad == 0 else f"{good} in place, {bad} not"
        )
        for line in out.splitlines():
            if "signal quality" in line:
                self.mrow_signal.set_subtitle(line.split("signal quality", 1)[1].strip())
                break
        else:
            self.mrow_signal.set_subtitle("not readable")

    def on_modem_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        if not PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        mode = "set" if self.modem_persist.get_active() else "try"
        want = "fixed" if row.get_active() else "shipped"
        self.set_busy(True)
        self.modem_progress.set_text("Switching …")
        self.modem_revealer.set_reveal_child(True)
        self.pulse_start("Switching the modem …")
        run_async([PKEXEC, self.live["modem"], mode, want], self.on_modem_switched,
                  on_line=self.on_progress_line)

    def on_modem_restore(self, _btn):
        if self.busy:
            return
        if not PKEXEC:
            self.toast("pkexec is missing - cannot ask for the rights to switch")
            return
        self.set_busy(True)
        self.modem_progress.set_text("Restoring …")
        self.modem_revealer.set_reveal_child(True)
        self.pulse_start("Back to the shipped state …")
        # "set", not "try": the same promise the audio button makes - what it
        # restores is what the phone comes back to. And the same command a
        # person would type, so there is one truth about what this does.
        run_async([PKEXEC, self.live["modem"], "set", "shipped"], self.on_modem_restored,
                  on_line=self.on_progress_line)

    def on_modem_restored(self, ok, out):
        self.pulse_stop()
        self.modem_revealer.set_reveal_child(False)
        if ok:
            self.toast("Shipped state - no network without Wi-Fi")
        else:
            self.toast("Could not restore the shipped state")
            self.report(out or "No output.")
        self.refresh()

    def on_modem_switched(self, ok, out):
        self.pulse_stop()
        self.modem_revealer.set_reveal_child(False)
        if not ok:
            # A refusal from polkit looks like any other failure from here, and
            # it is the likely one on a phone where this is not authorised.
            self.toast("Switching the modem failed")
            self.report(out or "No output.")
        else:
            last = [l for l in out.splitlines() if l.strip()]
            self.toast(last[-1].strip() if last else "Done")
        self.refresh()

    def on_dmnr_status(self, ok, out):
        if not ok:
            self.dmnr_ok = False
            self.dmnr_row.set_sensitive(False)
            self.dmnr_row.set_subtitle("not available on this device")
            return
        self.dmnr_ok = True
        on = "state=on" in out
        self._syncing = True
        self.dmnr_row.set_active(on)
        self._syncing = False
        # The tool reports both, because one cannot be read off the other:
        # switched on now and not remembered looks identical until the reboot.
        gemerkt = "persistent=yes" in out
        if on:
            self.dmnr_row.set_subtitle(
                "On, remembered" if gemerkt else "On until the next reboot")
        else:
            self.dmnr_row.set_subtitle(
                "Off, and stays off" if not gemerkt else
                "Off now - but comes back at the next reboot")

    def on_status(self, ok, out):
        profile, persistent, server, sinks = "unknown", "unknown", "-", "-"
        warn = None
        testmode = False
        for line in out.splitlines():
            if line.startswith("Profile (active):"):
                profile = line.split(":", 1)[1].strip()
            elif line.startswith("Profile (persistent):"):
                persistent = line.split(":", 1)[1].strip()
            elif line.startswith("WARNING:"):
                warn = line.split(":", 1)[1].strip()
            elif line.startswith("Test mode:"):
                testmode = line.split(":", 1)[1].strip().startswith("yes")
            elif line.startswith("Pulse server:"):
                server = line.split(":", 1)[1].strip()
            elif line.startswith("Sinks:"):
                sinks = line.split(":", 1)[1].strip()

        # What survives a reboot is not what is running: audioctl keeps both,
        # and "try" changes only the first of them. Showing one and calling it
        # the state is how this window claimed the shipped stack was set while
        # the phone had been on pw-hal permanently for two days.
        sticks = profile != "unknown" and persistent == profile and not testmode

        # Nothing came back that names a profile: say that, and leave both
        # switches where they are. Showing them off would be a statement about
        # a phone this window knows nothing about - and "off" happens to be
        # the shipped state, so it would be a plausible, wrong one.
        self.audio_ok = profile != "unknown"
        if not self.audio_ok:
            self.row_profile.set_subtitle("audioctl did not answer")
            self.row_server.set_subtitle(server_in_words(server))
            self.row_sinks.set_subtitle(sinks.replace(",", ", ") or "none")
            self.persist_row.set_subtitle("audioctl did not answer")
            self.set_busy(False)
            return

        text = profile_in_words(profile)
        if persistent == "unknown":
            pass
        elif sticks:
            text += " - permanent"
        else:
            text += f" - until the next reboot, then {profile_in_words(persistent)}"
        if warn:
            text += f" | {warn}"
        self.row_profile.set_subtitle(text)
        self.row_server.set_subtitle(server_in_words(server))
        self.row_sinks.set_subtitle(sinks.replace(",", ", ") or "none")

        # Follow the switch without triggering a toggle while doing it.
        self._syncing = True
        self.switch_row.set_active(profile == "pw-hal")
        # This one is both a report and a choice: it says whether what is
        # running now is what the phone comes back to, and it decides between
        # "set" and "try" for the next switch.
        self.persist_row.set_active(sticks)
        self._syncing = False
        if persistent == "unknown":
            self.persist_row.set_subtitle("Off: a reboot returns to the shipped state")
        elif sticks:
            self.persist_row.set_subtitle("On: this is what the phone comes back to")
        else:
            self.persist_row.set_subtitle(
                f"Off: a reboot returns to {profile_in_words(persistent)}"
            )
        self.set_busy(False)

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
        self.update_btn.set_sensitive(not busy)
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

    # ------------------------------------------------------------ actions

    def on_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        want_pw = row.get_active()
        mode = "set" if self.persist_row.get_active() else "try"
        audioctl = self.live["audio"]
        argv = ([audioctl, mode, "pw-hal"] if want_pw
                else [audioctl, "set", "standard"])
        self.set_busy(True)
        self.pulse_start("Switching …")
        run_async(argv, self.on_switched, on_line=self.on_progress_line)

    def on_progress_line(self, line):
        """Shows the step audioctl is currently reporting - shortened so it
        fits on one line."""
        self.progress.set_text(line[:60])

    def on_switched(self, ok, out):
        self.pulse_stop()
        if not ok:
            self.toast("Switching failed")
            self.report(out or "No output.")
        else:
            last = [l for l in out.splitlines() if l.strip()]
            self.toast(last[-1].strip() if last else "Done")
        self.refresh()

    def on_dmnr(self, row, _param):
        if self._syncing or self.busy:
            return
        self.set_busy(True)
        self.pulse_start("Switching echo suppression …")
        # The same reading of the persist switch as the stack switch above:
        # "set" is now and after the next reboot, the bare word is now only.
        secret = "on" if row.get_active() else "off"
        argv = [_tool_maybe(DMNR) or DMNR]
        argv += ["set", secret] if self.persist_row.get_active() else [secret]
        run_async(argv, self.on_dmnr_done, on_line=self.on_progress_line)

    def on_dmnr_done(self, ok, out):
        self.pulse_stop()
        if not ok:
            self.toast("Could not switch echo suppression")
            self.report(out or "No output.")
        else:
            self.toast("Echo suppression changed - try a call")
        self.refresh()

    def on_rescue(self, _btn):
        if self.busy:
            return
        self.set_busy(True)
        self.pulse_start("Restoring …")
        # The same recovery as on the command line - one truth, not two
        # versions that can drift apart.
        run_async([self.live["audio"], "rescue"], self.on_rescued,
                  on_line=self.on_progress_line)

    def on_rescued(self, ok, out):
        self.pulse_stop()
        self.toast(
            "Shipped state, speaker, 65 %"
            if ok
            else "Restore failed"
        )
        if not ok:
            self.report(out or "No output.")
        self.refresh()

    def run_chain(self, commands, done):
        """Run several commands one after another, stopping at the first that
        fails. The last output seen is what `done` is handed, because that is
        the one worth showing."""
        rest = list(commands)

        def step(ok=True, out=""):
            if not ok or not rest:
                done(ok, out)
                return
            run_async(rest.pop(0), step)

        step()

    # ------------------------------------------------------------ Meldungen

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


if __name__ == "__main__":
    sys.exit(App().run(sys.argv))
