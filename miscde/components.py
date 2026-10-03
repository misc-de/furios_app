# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The five tools: where each lives, and the steps that fetch one.

Kept apart from the pages on purpose - what runs as root, in which
directory and where the password goes is the part worth being able to
read on its own, and to check without starting anything."""

import glob
import os
import subprocess

from .tools import phone_has_switches
from .i18n import _



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
        "url": "https://github.com/misc-de/furios_audio",
        "dir": "furios_audio",
        # The build packages it fetches itself (tools/build-plugin.sh).
        "packages": ["wireplumber"],
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
        # nrprobe is compiled on the phone (tools/5g/build.sh).
        "packages": ["gcc", "pkg-config", "libglib2.0-dev", "libgbinder-dev",
                     "libglibutil-dev"],
        "root": True,
        "does": "the modem repairs: mobile data without Wi-Fi, signal bars "
                "that move, 26 cell broadcast channels instead of 8",
    },
    {
        "tool": "furios-gps-contribute",
        "page": "GPS",
        "key": "gps",
        "icon": "find-location-symbolic",
        "url": "https://github.com/misc-de/furios_gps",
        "dir": "furios_gps",
        "root": False,
        "does": "sends the Wi-Fi networks around you with a satellite position "
                "to beaconDB, so Wi-Fi location works where it does not yet - "
                "off until you switch it on",
    },
    {
        "tool": "killswitch-indicator",
        "page": "Switches",
        "key": "switches",
        "icon": "changes-prevent-symbolic",
        "url": "https://github.com/misc-de/furios_killswitch",
        "dir": "furios_killswitch",
        "packages": ["build-essential", "pkg-config", "phosh-dev", "libgtk-3-dev",
                     "python3-gi"],
        # The installer itself runs as the user, but since the icons became
        # a phosh plugin it has one sudo line of its own (make install into
        # /usr/lib) - without the ticket and the helper it dies on it.
        "root": True,
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
        "packages": ["nftables", "iproute2", "kmod", "gcc", "libpam0g-dev"],
        "root": True,
        "does": "fewer routes into the kernel: unprivileged BPF, modules "
                "that load themselves - and a lock screen that locks after "
                "wrong PINs",
    },
    {
        "tool": "battctl",
        "page": "Battery",
        "key": "battery",
        "icon": "battery-good-charging-symbolic",
        "url": "https://github.com/misc-de/furios_misc",
        "dir": "furios_misc",
        "packages": ["libglib2.0-bin", "python3-gi", "build-essential",
                     "pkg-config", "phosh-dev", "libgtk-3-dev"],
        # furios_misc is a collection of small things, so the installer is
        # not at the root of the clone. The only component with this, and
        # the reason it is a key rather than a rule: the next small thing
        # will sit beside it in the same repository.
        "sub": "battery",
        # Since 30.9.2026 its installer also builds the widget that draws
        # the colour and the time (phosh-battery-time) and puts it where
        # phosh looks: one sudo line, and a compiler.
        "root": True,
        "does": "the battery icon goes green, amber or red with the charging "
                "power - a tired cable and a good one look the same otherwise",
    },
]

# The folder dock behind three switches of the Phosh tab - a component, but not
# a tab of its own: that tab has switches that need nothing installed, and a
# "not installed" page in its place would hide them. So the offer sits on the
# Phosh tab, in the rows it would bring to life. Its installer installs the
# guard along with it (folder-dock/install.sh calls guard/install.sh).
#
# There is no program to look for, so "installed" is the plugin file where
# phosh looks - the same file the Phosh tab asks about.
PHOSH_PLUGIN = "furios-folder-dock"


def folder_dock_plugin():
    """The installed plugin file, or None."""
    found = sorted(glob.glob("/usr/lib/*/phosh/plugins/%s.plugin" % PHOSH_PLUGIN))
    return found[0] if found else None


PHOSH = {
    "tool": "furios-folder-dock",   # PHOSH_PLUGIN, as a literal for the tests
    "page": "Phosh",
    "key": "phosh",
    "icon": "video-display-symbolic",
    "url": "https://github.com/misc-de/furios_phosh",
    "dir": "furios_phosh",
    "packages": ["build-essential", "pkg-config", "phosh-dev", "libgtk-3-dev"],
    "sub": "folder-dock",
    # make install into phosh's plugin directory, and the guard into /etc.
    "root": True,
    "find": folder_dock_plugin,
}


def find_component(comp):
    """Where this component is installed, or None - its program, or for the
    folder dock the plugin file."""
    from .tools import _tool_maybe
    return comp["find"]() if comp.get("find") else _tool_maybe(comp["tool"])


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


# ------------------------------------------------------------ packages
#
# What an installer needs before it can run, as Debian packages - asked
# before it is started, so a missing compiler is a list with an apt command
# instead of an installer that dies half-way with its error in a dialog.
# git fetches every one of them. Checked by name with dpkg-query, like the
# audio installer checks its own build packages.
ALWAYS = ["git"]


def packages_needed(comp):
    return ALWAYS + [p for p in comp.get("packages", []) if p not in ALWAYS]


def installed_packages(out):
    """The names dpkg-query reported as installed, from
    `dpkg-query -W -f '${Package} ${Status}\\n' ...`."""
    names = set()
    for line in (out or "").splitlines():
        parts = line.split()
        if len(parts) >= 4 and parts[1:4] == ["install", "ok", "installed"]:
            names.add(parts[0].split(":")[0])
    return names


def missing_packages(comp):
    """The packages this component's installer needs and the phone lacks.

    One dpkg-query for all of them; it exits 1 when any is unknown and still
    prints the ones it knows, so the exit code says nothing here."""
    wanted = packages_needed(comp)
    try:
        out = subprocess.run(
            ["dpkg-query", "-W", "-f", "${Package} ${Status}\n"] + wanted,
            capture_output=True, text=True, timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []                  # nothing to ask - the installer still checks
    have = installed_packages(out)
    return [p for p in wanted if p not in have]


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


def same_repository(a, b):
    """Two ways of writing one GitHub address: with or without ".git" or a
    trailing slash, over https or ssh."""
    def plain(url):
        url = (url or "").strip()
        if url.startswith("git@github.com:"):
            url = "https://github.com/" + url[len("git@github.com:"):]
        url = url.rstrip("/")
        if url.endswith(".git"):
            url = url[:-4]
        return url.lower()
    return bool(a) and plain(a) == plain(b)


def origin_url(path):
    """The url of [remote "origin"] in the clone's own config, or None."""
    try:
        with open(os.path.join(path, ".git", "config")) as fh:
            lines = fh.read().splitlines()
    except OSError:
        return None
    inside = False
    for line in lines:
        text = line.strip()
        if text.startswith("["):
            inside = text.replace(" ", "") == '[remote"origin"]'
        elif inside and text.split("=", 1)[0].strip() == "url":
            return text.split("=", 1)[1].strip()
    return None


def is_clone_of(path, url):
    """Is this directory a clone of that repository?

    By its origin, never by its name: the same repository sits in
    ~/Projekte/furios_gps_fix here and is called furios_gps upstream. And by
    the whole origin: a substring of the config file also matched a fork
    called furios_audio-fork, and any other remote that happened to mention
    the address - and what is pulled from that clone runs as root.
    """
    return same_repository(origin_url(path), url)


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
        return ([], _("nothing is fetched - the clone in {path} is used "
                      "exactly as it is").format(path=path))
    if state == "update":
        guard = (["bash", "-c",
                  'test -z "$(git -C "$1" status --porcelain)" || '
                  '{ echo "This clone has uncommitted changes. Nothing was '
                  'touched - finish or stash them first, then update '
                  'again."; exit 1; }', "guard", path], None, None, None)
        # What a pull fetches is what the installer then runs as root, so
        # where it fetches from is asked again at the moment it happens -
        # not only when the update was counted. Written the way
        # same_repository writes it.
        origin = (["bash", "-c",
                   'u=$(git -C "$1" remote get-url origin 2>/dev/null | '
                   'sed -e "s#^git@github.com:#https://github.com/#" '
                   '-e "s#/*\$##" -e "s#\\.git\$##" | tr "A-Z" "a-z"); '
                   '[ "$u" = "$2" ] || { echo "$1 does not pull from $2 any '
                   'more. Nothing was touched."; exit 1; }',
                   "origin", path, comp["url"].lower()], None, None, None)
        return ([origin, guard,
                 (["git", "-C", path, "pull", "--ff-only"], None, None, None)],
                _("git pull --ff-only in {path}").format(path=path))
    if is_clone_of(path, comp["url"]):
        # Ours, from an earlier press. Bring it up to date if that works and
        # install from it either way: no network is a reason to install what
        # is here, not a reason to refuse.
        return ([(["bash", "-c",
                   'git -C "$1" pull --ff-only || echo "Could not update the '
                   'clone - installing what is already in it."',
                   "retry", path], None, None, None)],
                _("the clone in {path} is already here - update it if "
                  "possible, install from it either way").format(path=path))
    if os.path.exists(path):
        # Not a clone of this repository, and not ours to delete.
        return ([(["bash", "-c",
                   'echo "$1 is in the way: it exists and is not a clone of '
                   '$2. Nothing was touched - move it aside, then try '
                   'again."; exit 1', "in_the_way", path, comp["url"]],
                  None, None, None)],
                _("{path} is in the way - it is not a clone of {url}").format(
                    path=path, url=comp["url"]))
    return ([(["git", "clone", comp["url"], path], None, None, None)],
            _("git clone {url} to {path}").format(url=comp["url"], path=path))


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
