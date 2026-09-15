# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""How sudo asks for a password when nobody is at a terminal."""

import os
import shutil
import tempfile

from gi.repository import Gio, GLib



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
        self.directory = None
        self.service = None
        self.helper = None
        self.error = None
        # Only processes descended from this one are answered. The uid check
        # below rules out other accounts; it does not rule out anything else
        # this account is running, and that is the gap that matters here: the
        # socket sits under a predictable name in $XDG_RUNTIME_DIR, any
        # process of this user can find it with a glob, and the window is as
        # long as an install - up to half an hour. Measured on 15.9.2026: five
        # reads in a row from an unrelated process, none of them sudo.
        self.own_pid = os.getpid()

    @staticmethod
    def _descends_from(pid, ancestor, limit=24):
        """Does pid's parent chain reach ancestor?

        Measured against real sudo on 15.9.2026: the helper it starts is a
        direct descendant (helper -> sudo -> the installer's shell -> us), so
        the chain holds. A count-based guard would not have worked - sudo asks
        three times for three attempts, from three different helper processes.
        """
        seen = 0
        while pid and pid > 1 and seen < limit:
            if pid == ancestor:
                return True
            try:
                with open("/proc/%d/stat" % pid) as fh:
                    raw = fh.read()
                # comm sits in brackets and may contain spaces and brackets
                # itself, so everything before the LAST one is skipped.
                pid = int(raw[raw.rindex(")") + 2:].split()[1])
            except (OSError, ValueError, IndexError):
                return False
            seen += 1
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
            self.directory = tempfile.mkdtemp(
                prefix="misc-de-", dir=os.environ.get("XDG_RUNTIME_DIR") or None)
            path = os.path.join(self.directory, "ask.sock")
            self.helper = os.path.join(self.directory, "askpass")
            with open(self.helper, "w") as fh:
                fh.write(ASKPASS_HELPER % path)
            os.chmod(self.helper, 0o700)
            self.service = Gio.SocketService.new()
            self.service.add_address(Gio.UnixSocketAddress.new(path),
                                    Gio.SocketType.STREAM,
                                    Gio.SocketProtocol.DEFAULT, None)
            os.chmod(path, 0o600)
            self.service.connect("incoming", self.on_incoming)
            self.service.start()
            return self.helper
        except (OSError, GLib.Error) as error:
            # Saying why matters more than it looks. The install then stops at
            # its first sudo line with "a terminal is required to read the
            # password" - the very thing this class exists to prevent - and
            # without this line there is nothing anywhere that connects the
            # two. The likeliest cause is length: a unix socket path stops at
            # 108 characters, and $XDG_RUNTIME_DIR plus the directory and the
            # name eat into that.
            self.error = str(error) or error.__class__.__name__
            if self.directory and len(self.directory) > 70:
                self.error += " (the runtime directory is long - a unix" \
                               " socket path stops at 108 characters)"
            self.stop()
            return None

    def on_incoming(self, _service, connection, _source):
        """Answer one question from sudo - after asking who is asking."""
        try:
            if not self.secret:
                return True
            creds = connection.get_socket().get_credentials()
            if creds.get_unix_user() != os.getuid():
                return True                    # not ours, so not a word
            # Same user is not enough: it has to be something we started.
            if not self._descends_from(creds.get_unix_pid(), self.own_pid):
                return True                    # not ours either
            connection.get_output_stream().write_all(
                (self.secret + "\n").encode(), None)
            connection.close(None)
        except (GLib.Error, OSError):
            pass
        return True

    def stop(self):
        """Socket down, helper gone, password forgotten. Called on every way
        out of an install, the ones that failed included. self.error is left
        alone - it is the one thing worth keeping after a failed start."""
        self.secret = ""
        if self.service is not None:
            try:
                self.service.stop()
                self.service.close()
            except (GLib.Error, AttributeError):
                pass
            self.service = None
        if self.directory:
            shutil.rmtree(self.directory, ignore_errors=True)
            self.directory = None
        self.helper = None
