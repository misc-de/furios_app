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
# ssh-keygen (openssh-client) is what git checks a signature with.
ALWAYS = ["git", "openssh-client"]


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


# Directories that are never anybody's clone and can be large: not looked into.
NOT_CLONES = {"node_modules", "__pycache__", "venv", ".venv", "build",
              "target", ".cache", ".git"}


def candidate_dirs(base, depth=2):
    """Every directory down to `depth` levels below base, hidden ones too.

    Two levels and not one: this phone keeps its working clones in
    ~/Projekte/.dev (since 30.9.2026), and a scan of the first level found
    only the stale ~/Projekte/furios_app beside them. A clone is not looked
    into - what is below it is its own work, not another clone - and neither
    is anything in NOT_CLONES. Nothing is read but directory listings, which
    is why this costs a few milliseconds and not a git call per directory.
    """
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return []
    found = []
    for name in names:
        path = os.path.join(base, name)
        if name in NOT_CLONES or not os.path.isdir(path):
            continue
        found.append(path)
        if depth > 1 and not os.path.isdir(os.path.join(path, ".git")):
            found += candidate_dirs(path, depth - 1)
    return found


def head_time(path):
    """When the clone's HEAD was committed, as a unix time; 0 if unknown."""
    try:
        out = subprocess.run(["git", "-C", path, "log", "-1", "--format=%ct",
                              "HEAD"], capture_output=True, text=True,
                             timeout=5)
        return int(out.stdout.strip() or 0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0


def clone_elsewhere(url, base=None):
    """A clone of `url` the user keeps themselves, or None.

    With several clones of one repository - an old checkout beside the one
    being worked in - the one whose HEAD was committed last, the place the
    next version is being written. git is only asked when there is a choice
    to make; ties go to the first one in the listing.
    """
    base = OWN_CLONES if base is None else base
    clones = [path for path in candidate_dirs(base) if is_clone_of(path, url)]
    if len(clones) < 2:
        return clones[0] if clones else None
    return max(clones, key=head_time)


# ------------------------------------------------------------ signatures
#
# Whatever is fetched here is run by an installer that becomes root. Until
# 6.10.2026 that meant: whoever controls the GitHub account controls this
# phone. Now a commit is only checked out, merged or installed when it carries
# an SSH signature by the one key below - the maintainer's, pinned in this
# repository (miscde/allowed_signers) and installed by install.sh beside the
# package, where only root can change it. Read from there and nowhere else: a
# copy the user's own processes could write would pin nothing.
#
# There is no "allow unsigned" anywhere. A refusal leaves the working tree
# exactly as it was and says so in one line.
ALLOWED_SIGNERS = "/usr/local/lib/misc-de/allowed_signers"
# Who has to own that file. Only the tests change this, along with the path.
SIGNERS_OWNER = 0
# Said by every refusal, and looked for in the output to say it on screen.
NOT_SIGNED = "not signed by misc-de - not installed"

# The shell every signature step starts with. Arguments: $1 the clone,
# $2 the allowed-signers file, $3 its owner's uid, $4 NOT_SIGNED, then the
# step's own. A commit is named by its hash once it is known, so what is
# checked is exactly what is merged, checked out or installed - never a ref
# that could move in between.
_SIGNED_SH = r'''
clone=$1 signers=$2 owner=$3 not_signed=$4
refuse() { echo "$1"; exit 1; }
signed() {
    if [ ! -f "$signers" ] || [ -L "$signers" ] \
       || [ "$(stat -c %u "$signers")" != "$owner" ] \
       || [ -n "$(find "$signers" -perm /022)" ]; then
        echo "no trusted signing key at $signers"
        return 1
    fi
    git -C "$clone" -c gpg.format=ssh \
        -c gpg.ssh.allowedSignersFile="$signers" verify-commit "$1" 2>&1
}
'''


def _signed_step(name, body, path, *extra):
    """One bash step with the signature check in front of `body`."""
    return (["bash", "-c", _SIGNED_SH + body, name, path, ALLOWED_SIGNERS,
             str(SIGNERS_OWNER), NOT_SIGNED] + list(extra), None, None, None)


def verified_head_step(path):
    """What every install runs right before it: the clone is clean, and the
    commit it has checked out is signed. The "reinstall" of this app takes no
    pull at all, and an update may stop half-way - so this is checked here,
    whatever came before."""
    return _signed_step("verified_head", r'''
[ -z "$(git -C "$clone" status --porcelain)" ] \
    || refuse "$clone has uncommitted changes - not installed"
head=$(git -C "$clone" rev-parse --verify --quiet "HEAD^{commit}") \
    || refuse "$clone has nothing checked out - not installed"
signed "$head" || refuse "$clone $head: $not_signed"
''', path)


def fetch_verified_step(path, tolerant=False):
    """git fetch, the fetched tip checked, and only then merged - by hash.

    `tolerant` is the second press of Install: no network, or a merge that is
    not a fast-forward, installs what is already there (and the check before
    the installer still looks at that). A tip that is not signed never is.
    """
    if tolerant:
        body = r'''
if git -C "$clone" fetch --quiet \
   && tip=$(git -C "$clone" rev-parse --verify --quiet "@{u}^{commit}"); then
    signed "$tip" || refuse "$clone $tip: $not_signed"
    git -C "$clone" merge --ff-only --quiet "$tip" && exit 0
fi
echo "Could not update the clone - installing what is already in it."
'''
    else:
        body = r'''
git -C "$clone" fetch --quiet || exit 1
tip=$(git -C "$clone" rev-parse --verify --quiet "@{u}^{commit}") \
    || refuse "$clone has no upstream to update from"
signed "$tip" || refuse "$clone $tip: $not_signed"
git -C "$clone" merge --ff-only --quiet "$tip"
'''
    return _signed_step("fetch_verified", body, path)


def clone_verified_step(url, path):
    """A fresh clone: nothing checked out until its tip is checked. A refused
    clone is removed again - it is ours, made a moment ago, and left behind it
    would turn the next press into an update of a clone with no files."""
    return _signed_step("clone_verified", r'''
git clone --quiet --no-checkout "$5" "$clone" || exit 1
tip=$(git -C "$clone" rev-parse --verify --quiet "HEAD^{commit}") \
    || { rm -rf -- "$clone"; refuse "$5 has nothing to check out"; }
signed "$tip" || { rm -rf -- "$clone"; refuse "$5 $tip: $not_signed"; }
git -C "$clone" reset --hard --quiet "$tip"
''', path, url)


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

    Nothing unsigned is merged or checked out in any of them (see
    ALLOWED_SIGNERS), and component_steps checks the result once more before
    the installer runs.
    """
    if state == "reinstall":
        # Nothing to fetch: what is wanted is what is already in the clone -
        # if it is clean and signed, which component_steps checks.
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
        return ([origin, guard, fetch_verified_step(path)],
                _("git fetch in {path}, the new commit checked for "
                  "misc-de's signature, then merged").format(path=path))
    if is_clone_of(path, comp["url"]):
        # Ours, from an earlier press. Bring it up to date if that works and
        # install from it either way: no network is a reason to install what
        # is here, not a reason to refuse.
        return ([fetch_verified_step(path, tolerant=True)],
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
    return ([clone_verified_step(comp["url"], path)],
            _("git clone {url} to {path}, checked for misc-de's signature "
              "before anything is checked out").format(url=comp["url"],
                                                       path=path))


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
    # Whatever the source steps did or did not do - a reinstall does
    # nothing - what the installer is about to run is clean and signed, or
    # it does not run. Before sudo: refused code gets no ticket either.
    steps.append(verified_head_step(path))
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
