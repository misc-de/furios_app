# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The switches for a FuriPhone that has been repaired by hand.

Five pages, and each is one switch: the audio stack talks to the Android HAL
through PipeWire or through PulseAudio as shipped, the modem runs with the
repairs from furios_modem_fixes or exactly as it came, geoclue either has the
filter that throws away positions derived from the carrier's IP address or it
does not, the three sliders on the case are read rather than guessed at, and
the battery icon says how fast the battery is filling. The tools do the work -
audioctl, modemctl, gpsctl, killswitch-indicator and battctl - and this front
end only calls them and shows what is actually running.

Every page is there, whether its tool is or not. Where one is missing the tab
says what it would do, where it comes from, and offers to fetch it - and the
moment that has run, the tab is the real one.

Deliberately plain: on a phone you want a button, not a control room.

This package is what `misc-de` starts. It re-exports the pieces the tests and
the launcher reach for, so there is one name to import and the modules below
stay free to move.
"""

# Before anything below imports gi.repository. There is no second chance: the
# first module to pull Gtk or Adw in fixes the version for the process, and a
# submodule that got there first would take whatever is installed. It lived at
# the top of the single file until 15.9.2026 and this is the same place - the
# first lines that run when the app is imported at all.
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

# The gi namespaces, under one name. They are the same module objects every
# page holds, so a test that replaces Gio.Subprocess.new here replaces it for
# the whole app - which is what makes a window testable with no display at
# all. Listed rather than left implicit: this IS the seam.
# Two standard modules under this name as well, and for the same reason as
# the gi ones: a test that wants to know what happens when os.access says no
# replaces it here, once, for every module that asks.
import os
import shutil

from gi.repository import Adw, Gio, GLib, Gtk

from . import askpass, components, process, tools, words
from .askpass import ASKPASS_HELPER, Askpass
from .components import (BATTERY_UNIT, CLONE_HOME, COMPONENTS, OWN_CLONES,
                         SELF, behind_count, clone_elsewhere, clone_path,
                         component_steps, installer_dir, installer_env,
                         installer_said, is_clone, is_clone_of, source_steps)
# The Bluetooth powersave switch reads batman's config rather than a tool of
# its own, so what the tests need is the parsing and the command, not a path.
from .pages.audio import (BATMAN_CONFIG, BATMAN_UNIT, btsave_argv,
                          btsave_in_config, needs_a_password)
from .process import CALL_TIMEOUT, run_async
from .tools import (APP_ID, CONTRIB, DMNR, KILLSWITCH_SYSFS, PKEXEC, _tool,
                    _tool_maybe, phone_has_switches)
from .window import App, Window
from .words import PROFILE_WORDS, profile_in_words, server_in_words

__all__ = [
    "Adw", "GLib", "Gio", "Gtk", "os", "shutil",
    "APP_ID", "ASKPASS_HELPER", "App", "Askpass", "BATMAN_CONFIG",
    "BATMAN_UNIT", "BATTERY_UNIT",
    "CALL_TIMEOUT", "CLONE_HOME", "COMPONENTS", "CONTRIB", "DMNR",
    "KILLSWITCH_SYSFS", "OWN_CLONES", "PKEXEC", "PROFILE_WORDS", "SELF",
    "Window", "askpass", "behind_count", "clone_elsewhere", "clone_path",
    "btsave_argv", "btsave_in_config", "component_steps", "components",
    "installer_dir", "installer_env",
    "installer_said", "is_clone", "is_clone_of", "phone_has_switches",
    "needs_a_password", "process", "profile_in_words", "run_async",
    "server_in_words",
    "source_steps", "tools", "words", "_tool", "_tool_maybe",
]
