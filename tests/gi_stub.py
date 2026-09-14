# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""A stand-in for PyGObject, so the code that uses it can be imported.

The switcher app and the Bluetooth watcher are the only Python in this project
that matters, and both start with `import gi`. On a machine with a display that
is fine; in a test it pulls in GTK, libadwaita and a main loop, and none of
that says anything about whether the code is right.

So this fabricates whatever is asked of it. Classes come into being on first
use and remember how they were called, which is what a test wants to look at:
not what the app said, but which widget it built and with what.

It is a stub and behaves like one - nothing here proves the app works on the
phone. What it proves is that the parts which decide things decide them right.
"""
import sys
import types


class Recorder:
    """Every call anything on the stub receives, in order."""

    def __init__(self):
        self.calls = []

    def add(self, what, args, kwargs):
        self.calls.append((what, args, kwargs))

    def of(self, what):
        return [c for c in self.calls if c[0] == what]

    def reset(self):
        self.calls = []


recorder = Recorder()


class Fake:
    """An object that accepts anything and remembers it."""

    def __init__(self, _name="fake", *args, **kwargs):
        object.__setattr__(self, "_name", _name)
        object.__setattr__(self, "_props", dict(kwargs))
        recorder.add(_name, args, kwargs)

    def __getattr__(self, item):
        """Always the same child for the same name.

        Handing back a fresh object each time would look right and behave
        wrongly: a test that sets app.props.active_window would be setting it
        on something the code then never sees.
        """
        name = "%s.%s" % (object.__getattribute__(self, "_name"), item)
        props = object.__getattribute__(self, "_props")
        if item not in props:
            props[item] = Fake(name)
        return props[item]

    def __setattr__(self, key, value):
        object.__getattribute__(self, "_props")[key] = value

    def __or__(self, other):
        return self

    def __ror__(self, other):
        return self

    def __bool__(self):
        return True

    def __call__(self, *args, **kwargs):
        # Some of what the app reads back is itself callable - a class it
        # subclasses, a constructor it stored. Refusing that would fail in the
        # stub where the real thing would not.
        recorder.add(object.__getattribute__(self, "_name") + "()", args, kwargs)
        return Fake(object.__getattribute__(self, "_name") + "()")

    def __iter__(self):
        return iter(())

    def __str__(self):
        return object.__getattribute__(self, "_name")


class _AnyAttribute(type):
    """Class-level attribute access, for the enumerations.

    Gio.DBusCallFlags.NONE is read off the class, never off an instance, and
    without this the stub raises exactly where the real thing would not.
    """

    def __getattr__(cls, item):
        value = Fake("%s.%s" % (cls.__name__, item))
        setattr(cls, item, value)
        return value


def _factory(prefix):
    """A module whose every attribute is a class that builds a Fake."""

    class Namespace(types.ModuleType):
        def __getattr__(self, item):
            full = "%s.%s" % (prefix, item)

            class Built(Fake, metaclass=_AnyAttribute):
                def __init__(self, *args, **kwargs):
                    Fake.__init__(self, full, *args, **kwargs)

            Built.__name__ = full
            setattr(self, item, Built)
            return Built

    return Namespace(prefix)


def install():
    """Put the stub in place of PyGObject, and return the recorder."""
    recorder.reset()

    gi = types.ModuleType("gi")
    gi.require_version = lambda *a, **k: None
    repository = types.ModuleType("gi.repository")

    # GLibUnix is where GLib.unix_signal_add moved to. Without it here the
    # only path a test could take is the fallback, which is not the one the
    # phone takes.
    for name in ("Gtk", "Adw", "Gio", "GLib", "GLibUnix", "GObject", "Gdk",
                 "Polkit", "PolkitAgent"):
        module = _factory(name)
        setattr(repository, name, module)
        sys.modules["gi.repository." + name] = module

    # The few things the code treats as values rather than as constructors.
    repository.GLib.Error = type("Error", (Exception,), {})
    repository.GLib.PRIORITY_DEFAULT = 0
    repository.GLib.MainLoop = lambda *a, **k: Fake("GLib.MainLoop")
    repository.GLib.Variant = lambda *a, **k: Fake("GLib.Variant", *a)
    repository.GLib.VariantType = lambda *a, **k: Fake("GLib.VariantType", *a)

    gi.repository = repository
    sys.modules["gi"] = gi
    sys.modules["gi.repository"] = repository
    return recorder
