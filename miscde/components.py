# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The five tools: where each lives, and the steps that fetch one.

Kept apart from the pages on purpose - what runs as root, in which
directory and where the password goes is the part worth being able to
read on its own, and to check without starting anything."""

import os

from .tools import phone_has_switches



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
        "tool": "secctl",
        "page": "Security",
        "key": "security",
        "icon": "security-high-symbolic",
        "url": "https://github.com/misc-de/furios_security",
        "dir": "furios_security",
        "root": True,
        "does": "the kernel is 4.19 and past end of life, so the routes to "
                "it get closed instead: unprivileged BPF, modules that load "
                "themselves, and SSH reachable over mobile",
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
    env = {"SUDO_ASKPASS": askpass}
    if not os.environ.get("DISPLAY"):
        env["DISPLAY"] = ":0"
    return env


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
