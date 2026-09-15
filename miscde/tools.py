# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Finding the programs this app drives, and the phone it runs on."""

import os
import shutil

import os
import shutil

# This app used to carry a polkit authentication agent, because switching the
# stack meant masking system units and writing into /etc, and phosh registers
# no agent of its own. It does not need one any more: audioctl keeps the
# profile under $HOME, where the session may write anyway, so there is nothing
# left to authenticate when a switch is thrown.
#
# It does handle a password, on one path and only there: INSTALLING a tool
# runs that repository's install.sh, and three of the five write to
# /usr/local. That password is asked for in the dialog that says what is
# about to run, it reaches sudo through a pipe and through the socket in
# Askpass, and it is dropped when the chain ends. Switching, reading state
# and restoring need none of it.

APP_ID = "de.misc-de.tools"

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


# Where this package sits, and what is in it. Both exist because the app can
# now offer to replace itself, and since 15.9.2026 it is no longer one file
# that a byte comparison settles - it is a directory.
PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))


def source_digest(package_dir):
    """A fingerprint of every .py file under package_dir.

    Content and name, in sorted order, so the answer does not depend on how
    the filesystem hands the directory over. It is not a version number and
    is not meant to be read: the only question asked of it is whether two
    trees are the same, which is what "is the running program the one in the
    clone" comes down to now that the program is a package.

    None when the directory cannot be read - and None never equals None here,
    because the caller treats an unanswerable question as "say nothing"
    rather than as "they differ".
    """
    import hashlib
    if not package_dir or not os.path.isdir(package_dir):
        return None
    digest = hashlib.sha256()
    found = []
    for root, dirs, files in os.walk(package_dir):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in sorted(files):
            if name.endswith(".py"):
                found.append(os.path.join(root, name))
    if not found:
        return None
    for path in sorted(found):
        try:
            with open(path, "rb") as fh:
                content = fh.read()
        except OSError:
            return None
        digest.update(os.path.relpath(path, package_dir).encode())
        digest.update(b"\0")
        digest.update(content)
    return digest.hexdigest()
