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
    """The package, with the real gi behind it - not the stub.

    This file exists because Askpass is the one class a stand-in cannot test:
    what it does is hand a password to a socket, and whether that works is a
    question about GLib, unix credentials and a process tree, none of which a
    fake has. So it imports the app for real and drives it.
    """
    sys.path.insert(0, str(ROOT))
    return importlib.import_module("miscde")


def ok(condition, words):
    print(("  \033[32mok\033[0m   " if condition else "  \033[31mFAIL\033[0m ")
          + words)
    return bool(condition)


def main():
    sw = load()
    from gi.repository import GLib

    good = True
    a = sw.askpass.Askpass(SECRET)
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
    foreign_process = Path(__file__).parent / "_foreign_tmp.py"
    foreign_process.write_text(
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
    answer = Path(__file__).parent / "_foreign_tmp.out"
    try:
        sock = os.path.join(directory, "ask.sock")
        # "setsid --fork", not os.setsid: setsid alone changes the session and
        # leaves the parent in place, so the process is still our child and
        # would be answered - correctly. The --fork is what makes init adopt
        # it, which is the case that has to be refused. (Getting this wrong
        # once made this very check pass against a socket that was still
        # wide open.)
        subprocess.run(["setsid", "--fork", sys.executable, str(foreign_process),
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
        foreign_process.unlink(missing_ok=True)
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
        b = sw.askpass.Askpass(SECRET)
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

    good &= without_nopasswd(sw)

    if "--with-sudo" in sys.argv:
        good &= sudo_question(sw)
    return 0 if good else 1


# A sudo that always wants one, and runs the command once it has it. The gate
# is what a phone without "NOPASSWD:ALL" in its sudoers gives you; what sits
# behind it here is the ordinary user, because what is being tested is the
# plumbing, not whether anything reached root.
FAKE_SUDO = r"""#!/bin/bash
PW=%s
mode=none; askpass=0; validate=0
while [ $# -gt 0 ]; do
    case "$1" in
        -n) mode=nonint; shift;;
        -S) mode=stdin; shift;;
        -A) askpass=1; shift;;
        -p) shift 2;;
        -v) validate=1; shift;;
        -k) exit 0;;
        -E|-H) shift;;
        --) shift; break;;
        -*) shift;;
        *) break;;
    esac
done
check() {
    if [ "$mode" = stdin ]; then
        IFS= read -r given
        [ "$given" = "$PW" ] && return 0
        echo "Sorry, try again." >&2; return 1
    fi
    if [ "$askpass" = 1 ] || { [ -n "${SUDO_ASKPASS:-}" ] && [ -n "${DISPLAY:-}" ]; }; then
        [ -n "${SUDO_ASKPASS:-}" ] || { echo "sudo: no askpass program specified" >&2; return 1; }
        given=$("$SUDO_ASKPASS")
        [ "$given" = "$PW" ] && return 0
        echo "Sorry, try again." >&2; return 1
    fi
    if [ "$mode" = nonint ]; then
        echo "sudo: a password is required" >&2; return 1
    fi
    echo "sudo: a terminal is required to read the password; either use the -S option to read from standard input or configure an askpass helper" >&2
    return 1
}
check || exit 1
[ "$validate" = 1 ] && [ $# -eq 0 ] && exit 0
exec "$@"
"""


def without_nopasswd(sw):
    """Everything this app does as root, on a phone whose sudo asks.

    This one has `furios ALL=(ALL) NOPASSWD:ALL` in its sudoers, so every sudo
    line in this project succeeds here whether or not anybody thought about a
    password. That is a property of this phone, not of the app, and it is not
    one to build on: it is not the default anywhere, and it is the first thing
    somebody hardening a device removes.

    So sudo is replaced by one that always asks, and the app's own machinery
    is driven against it - not a copy of it. What is NOT covered here is
    pkexec: the modem and GPS switches go through polkit, which does not read
    sudoers at all, and their policies allow an active local session without
    asking anything (de.misc-de.modemctl.policy, allow_active=yes).
    """
    import shutil
    from gi.repository import Gio, GLib

    password = "not-the-real-password-either"
    home = tempfile.mkdtemp()
    binaries = os.path.join(home, "bin")
    os.makedirs(binaries)
    fake = os.path.join(binaries, "sudo")
    with open(fake, "w") as fh:
        fh.write(FAKE_SUDO % password)
    os.chmod(fake, 0o755)
    was = os.environ["PATH"]
    os.environ["PATH"] = binaries + ":" + was
    a = sw.askpass.Askpass(password)
    helper = a.start()
    good = ok(bool(helper), "a helper for the run below")

    def run(argv, env=None, cwd=None, stdin=None):
        """A child, while the main loop turns - the socket has to be served
        from this process while sudo's helper is asking it."""
        answer = {}

        def done(proc, res):
            try:
                proc.wait_check_finish(res)
                answer["code"] = 0
            except GLib.Error as error:
                answer["code"] = 1
                answer["said"] = error.message
            loop.quit()

        flags = Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_MERGE
        if stdin is not None:
            flags |= Gio.SubprocessFlags.STDIN_PIPE
        launcher = Gio.SubprocessLauncher.new(flags)
        for key, value in (env or {}).items():
            launcher.setenv(key, value, True)
        if cwd:
            launcher.set_cwd(cwd)
        proc = launcher.spawnv(argv)
        if stdin is not None:
            proc.get_stdin_pipe().write_all(stdin.encode(), None)
            proc.get_stdin_pipe().close(None)
        proc.wait_check_async(None, done)
        loop = GLib.MainLoop()
        GLib.timeout_add_seconds(30, lambda: (loop.quit(), False)[1])
        loop.run()
        return answer.get("code", 1), answer.get("said", "")

    # 1 - the one switch in the app that needs root by itself. It tries
    #     without a password first, and has to be able to tell that answer
    #     apart from the job failing, or it would report a broken switch.
    argv = sw.pages.audio.btsave_argv(True)
    probe = subprocess.run(argv[:2] + ["true"], capture_output=True, text=True)
    good &= ok(probe.returncode != 0
               and sw.pages.audio.needs_a_password(probe.stderr),
               "the BTSAVE switch sees that sudo wants a password")
    code, _ = run(sw.pages.audio.btsave_argv(True, password)[:4] + ["true"],
                  stdin=password + "\n")
    good &= ok(code == 0, "and goes through once it has one")
    code, _ = run(sw.pages.audio.btsave_argv(True, password)[:4] + ["true"],
                  stdin="wrong\n")
    good &= ok(code != 0, "a wrong password is not taken for a working switch")

    # 2 - an install: our own sudo lines, inside a script, with no terminal
    #     anywhere. This is the case that broke on 14.9. and the reason
    #     Askpass exists.
    script = os.path.join(home, "install.sh")
    with open(script, "w") as fh:
        fh.write("#!/bin/bash\nset -e\n"
                 "sudo touch '%s/was-root'\n" % home)
    os.chmod(script, 0o755)
    env = sw.components.installer_env(helper)
    code, said = run(["./install.sh"], env=env, cwd=home)
    good &= ok(code == 0 and os.path.exists(os.path.join(home, "was-root")),
               "an installer's own sudo lines are answered by the helper"
               + ("" if code == 0 else " - it said: " + said))

    # 3 - and the helper is what does it, rather than something about this
    #     phone. Without it the same script stops where the GPS install did.
    os.unlink(os.path.join(home, "was-root"))
    code, said = run(["./install.sh"], env={"DISPLAY": ":0"}, cwd=home)
    good &= ok(code != 0, "without the helper that same install stops dead")

    # 4 - the steps the install page builds, which is where the two meet.
    comp = dict(sw.components.COMPONENTS[0], root=True)
    steps = sw.components.component_steps(comp, {}, password, path=home,
                                          askpass=helper)
    tickets = [s for s in steps if s[0][:2] == ["sudo", "-S"]]
    good &= ok(len(tickets) == 1 and tickets[0][1] == password + "\n",
               "the ticket is taken with the password on the pipe")
    good &= ok(steps[-1][0] == ["sudo", "-k"], "and dropped again at the end")
    good &= ok(any((s[3] or {}).get("SUDO_ASKPASS") == helper for s in steps),
               "and the installer is told where to ask")

    a.stop()
    os.environ["PATH"] = was
    shutil.rmtree(home, ignore_errors=True)
    return good


def sudo_question(sw):
    """Does sudo use the helper when nobody is at a terminal?

    With a wrong password on purpose: what is measured is whether sudo asks at
    all. "a terminal is required to read the password" means it did not.

    DISPLAY is what decides it. sudo only reaches for SUDO_ASKPASS when it
    believes somebody could see a graphical prompt, and phosh sets DISPLAY
    because phoc brings XWayland - over ssh it is not set, and this check
    would fail against a sudo that is behaving exactly as it does on the
    phone.
    """
    a = sw.askpass.Askpass("not-the-real-one-either")
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
