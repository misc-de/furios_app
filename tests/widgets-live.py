#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Every widget method the app calls, held against the real PyGObject.

tests/gi_stub.py answers to anything, on purpose - that is what lets the rest
of the suite run over ssh. The price is that a method libadwaita does not
have passes all of it: `set_subtitle_wrap` on an Adw.ActionRow was in the
Security tab, green in 1939 tests, and the app died in do_activate on the
phone the moment that tab was built.

So this takes the names the stub was asked for and asks the real libraries
whether they exist. It needs PyGObject but no display: classes are looked up
and their methods counted, nothing is constructed and no main loop runs.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))

# The namespaces whose classes come from the libraries. Anything else in the
# dump is the app's own, and not for this file to judge.
CHECKED = ("Gtk", "Adw", "Gio", "GLib", "Gdk", "GObject")


def dump_of_a_test_run(path):
    """Run the suite with the stub, and collect what it asked for."""
    env = dict(os.environ, MISCDE_WIDGET_CALLS=path)
    subprocess.run([sys.executable, os.path.join(HERE, "test-app.py")],
                   env=env, stdout=subprocess.DEVNULL,
                   stderr=subprocess.DEVNULL)
    return open(path).read().splitlines() if os.path.exists(path) else []


def real_namespaces():
    import gi
    gi.require_version("Gtk", "4.0")
    gi.require_version("Adw", "1")
    from gi.repository import Adw, Gdk, Gio, GLib, GObject, Gtk
    return {"Gtk": Gtk, "Adw": Adw, "Gio": Gio,
            "GLib": GLib, "Gdk": Gdk, "GObject": GObject}


def main():
    given = sys.argv[1] if len(sys.argv) > 1 else os.environ.get(
        "MISCDE_WIDGET_CALLS")
    if given and os.path.exists(given):
        names = open(given).read().splitlines()
    else:
        with tempfile.NamedTemporaryFile(suffix=".txt") as tmp:
            names = dump_of_a_test_run(tmp.name)
    if not names:
        print("  \033[33mskipped\033[0m - no record of what the stub was "
              "asked for")
        return 0

    try:
        namespaces = real_namespaces()
    except Exception as exc:                      # no PyGObject, no libraries
        print("  \033[33mskipped\033[0m - %s" % exc)
        return 0

    missing = []
    checked = 0
    for name in names:
        if not name.endswith("()"):               # read, never called
            continue
        parts = name[:-2].split(".")
        if len(parts) != 3 or parts[0] not in CHECKED:
            continue
        module = namespaces.get(parts[0])
        klass = getattr(module, parts[1], None)
        if klass is None:
            missing.append((name, "%s has no %s" % (parts[0], parts[1])))
            continue
        checked += 1
        if not hasattr(klass, parts[2]):
            missing.append((name, "%s.%s has no %s"
                            % (parts[0], parts[1], parts[2])))

    for name, why in missing:
        print("  \033[31mfail\033[0m %s - %s" % (name, why))
    if missing:
        print("\n  %d call(s) the stub allowed and the library does not have."
              % len(missing))
        return 1
    print("  \033[32mok\033[0m   %d calls, all of them real" % checked)
    return 0


if __name__ == "__main__":
    sys.exit(main())
