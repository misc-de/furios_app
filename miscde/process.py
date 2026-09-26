# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Running a helper without freezing the window."""

from gi.repository import Gio, GLib



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

    if stdin is not None:
        # The pipe was opened above, and on this path nothing fills it:
        # communicate_utf8_async does that for the other one and is not used
        # here. A "sudo -S" reading from a pipe nobody writes to waits until
        # the timeout runs out - so it is written and closed right here, and
        # the combination stays usable instead of being a trap for later.
        try:
            pipe = proc.get_stdin_pipe()
            pipe.write_all(stdin.encode(), None)
            pipe.close(None)
        except GLib.Error as err:
            on_done(False, str(err))
            return

    stream = Gio.DataInputStream.new(proc.get_stdout_pipe())
    collected = []

    def read_next():
        stream.read_line_async(GLib.PRIORITY_DEFAULT, None, got_line)

    def got_line(src, res):
        try:
            line, _length = src.read_line_finish_utf8(res)
        except GLib.Error as err:
            if getattr(err, "domain", None) != "g_convert_error":
                on_done(False, str(err))
                return
            # One line that is not UTF-8 - a build log quoting a Latin-1
            # source line is enough. The line is already consumed, and the
            # next read carries on behind it (checked against the real GLib).
            # Giving up here used to report an install as failed while it
            # was still running: the password socket went down under its next
            # sudo line, and with nobody draining the pipe any more the
            # installer blocked for good once 64 KiB of output had piled up.
            line = "(a line that is not UTF-8)"
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
