#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The askpass socket, against the real GLib - not the stub.

test-app.py replaces PyGObject before it imports anything, which is right for
everything else in this app and useless here: what has to be true of Askpass
is that a helper process really gets the password over a real socket, that the
password is in no file, and that nothing is left behind afterwards. A stub
would agree with all of that without any of it being so.

Runs as an ordinary user, needs no password and no root. With --with-sudo it
also asks the real sudo - with a deliberately wrong password - whether it
calls an askpass helper at all when there is no terminal. That one writes
failed authentication attempts to the journal, which is why it is not part of
the ordinary run.
"""
import importlib.util
import os
import subprocess
import tempfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SECRET = "not-the-real-password"


def load():
    spec = importlib.util.spec_from_file_location("switcher", ROOT / "misc-de.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def ok(condition, words):
    print(("  \033[32mok\033[0m   " if condition else "  \033[31mFAIL\033[0m ")
          + words)
    return bool(condition)


def main():
    sw = load()
    from gi.repository import GLib

    good = True
    a = sw.Askpass(SECRET)
    helper = a.start()
    good &= ok(helper, "the helper is set up at all")
    if not helper:
        return 1
    directory = os.path.dirname(helper)
    text = open(helper).read()

    good &= ok(SECRET not in text, "the helper script carries no password")
    good &= ok(os.stat(directory).st_mode & 0o777 == 0o700,
              "its directory is closed to everybody else (0700)")
    good &= ok(os.stat(helper).st_mode & 0o777 == 0o700, "the helper is 0700")
    good &= ok(str(directory).startswith(
        os.environ.get("XDG_RUNTIME_DIR", "/run/user")),
        "it lives in the runtime directory, which is tmpfs")

    # The real thing: a process that is not this one asks, over the socket.
    # The main loop has to run for that, so the helper is started first and
    # read while GLib serves - exactly the order sudo produces.
    result = {}
    proc = subprocess.Popen([helper], stdout=subprocess.PIPE)

    def wait_():
        try:
            result["out"] = proc.communicate(timeout=10)[0].decode().strip()
        except subprocess.TimeoutExpired:
            proc.kill()
            result["out"] = "(the helper never got an answer)"
        loop.quit()
        return False

    loop = GLib.MainLoop()
    GLib.timeout_add(200, wait_)
    GLib.timeout_add_seconds(15, lambda: (loop.quit(), False)[1])
    loop.run()
    good &= ok(result.get("out") == SECRET,
              "a separate process gets the password through the socket")

    # The other half, and the one this was missing: same user is not enough.
    # The socket sits under a predictable name in $XDG_RUNTIME_DIR and any
    # process of this account can find it with a glob, so what keeps it shut
    # is that the asker has to be something we started. Checked from a process
    # that is a SIBLING, not a descendant - started by this test's own parent,
    # which sudo's helper never is.
    fremd = Path(__file__).parent / "_fremd_tmp.py"
    fremd.write_text(
        "import socket,sys\n"
        "s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); s.settimeout(5)\n"
        "try:\n"
        "    s.connect(sys.argv[1]); t=[]\n"
        "    while True:\n"
        "        c=s.recv(4096)\n"
        "        if not c: break\n"
        "        t.append(c)\n"
        "    open(sys.argv[2],'w').write(b''.join(t).decode())\n"
        "except Exception: pass\n")
    answer = Path(__file__).parent / "_fremd_tmp.out"
    try:
        sock = os.path.join(directory, "ask.sock")
        # "setsid --fork", not os.setsid: setsid alone changes the session and
        # leaves the parent in place, so the process is still our child and
        # would be answered - correctly. The --fork is what makes init adopt
        # it, which is the case that has to be refused. (Getting this wrong
        # once made this very check pass against a socket that was still
        # wide open.)
        subprocess.run(["setsid", "--fork", sys.executable, str(fremd),
                        sock, str(answer)], timeout=20)
        result2 = {}

        def wait2():
            result2["out"] = answer.read_text().strip() if answer.exists() else ""
            loop2.quit()
            return False

        loop2 = GLib.MainLoop()
        GLib.timeout_add_seconds(6, wait2)
        GLib.timeout_add_seconds(20, lambda: (loop2.quit(), False)[1])
        loop2.run()
        good &= ok(result2.get("out") != SECRET,
                  "a process we did not start gets nothing")
    finally:
        fremd.unlink(missing_ok=True)
        answer.unlink(missing_ok=True)

    a.stop()
    good &= ok(not os.path.exists(directory),
              "socket, helper and directory are gone afterwards")
    good &= ok(a.secret == "", "and the password is not kept either")

    # A helper that cannot be set up used to return None and say nothing, and
    # the install then stopped at its first sudo line with "a terminal is
    # required to read the password" - the exact failure this class exists to
    # prevent, with nothing connecting the two. The likeliest cause is length:
    # a unix socket path stops at 108 characters.
    depth = Path(tempfile.mkdtemp()) / ("x" * 60) / ("y" * 40)
    depth.mkdir(parents=True)
    alt_runtime = os.environ.get("XDG_RUNTIME_DIR")
    os.environ["XDG_RUNTIME_DIR"] = str(depth)
    try:
        b = sw.Askpass(SECRET)
        good &= ok(b.start() is None, "an impossible socket path fails, as it must")
        good &= ok(bool(b.error), "and says why, instead of failing silently")
        good &= ok("108" in (b.error or ""),
                  "naming the limit that was hit")
        b.stop()
    finally:
        if alt_runtime is None:
            os.environ.pop("XDG_RUNTIME_DIR", None)
        else:
            os.environ["XDG_RUNTIME_DIR"] = alt_runtime

    if "--with-sudo" in sys.argv:
        good &= sudo_frage(sw)
    return 0 if good else 1


def sudo_frage(sw):
    """Does sudo use the helper when nobody is at a terminal?

    With a wrong password on purpose: what is measured is whether sudo asks at
    all. "a terminal is required to read the password" means it did not.

    DISPLAY is what decides it. sudo only reaches for SUDO_ASKPASS when it
    believes somebody could see a graphical prompt, and phosh sets DISPLAY
    because phoc brings XWayland - over ssh it is not set, and this check
    would fail against a sudo that is behaving exactly as it does on the
    phone.
    """
    a = sw.Askpass("not-the-real-one-either")
    helper = a.start()
    environment = dict(os.environ, SUDO_ASKPASS=helper)
    environment.setdefault("DISPLAY", ":0")
    try:
        p = subprocess.run(["setsid", "sudo", "-k", "-v"], env=environment,
                           stdin=subprocess.DEVNULL, capture_output=True,
                           timeout=30)
        said = (p.stderr or b"").decode()
    except subprocess.TimeoutExpired:
        said = "(sudo never came back)"
    finally:
        a.stop()
    return ok("terminal is required" not in said,
              "sudo asks the helper instead of asking for a terminal"
              + ("" if "terminal is required" not in said
                 else " - it said: " + said.strip()))


if __name__ == "__main__":
    sys.exit(main())
