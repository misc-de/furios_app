#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The chosen value of a combo row, against the real GTK and libadwaita.

On the phone "Sound server" showed "…" where "PipeWire" belongs: its long
description took the width first. This builds the same row at the phone's
width and checks that the value gets the room of its widest entry. Needs a
display; without one it says so and skips.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

RUN = FAILED = 0


def check(what, ok, detail=""):
    global RUN, FAILED
    RUN += 1
    if ok:
        print("  \033[32mok\033[0m   %s" % what)
    else:
        FAILED += 1
        print("  \033[31mFAIL\033[0m %s %s" % (what, detail))


if not Gtk.init_check():
    print("  \033[33mskipped\033[0m - no display")
    sys.exit(0)
Adw.init()
from miscde import combo  # noqa: E402

# German on purpose: the translation from lang_de.py is the longest wording
# this row ever carries, and the width has to hold for that one.
row = Adw.ComboRow(
    title="Soundserver",
    subtitle="Wähle den primären Dienst für deine Audio-Ein- und -Ausgabe aus",
    model=Gtk.StringList.new(["PulseAudio", "PipeWire"]))
row.set_selected(1)
view = combo.keep_value_visible(row)
check("the value list is found", isinstance(view, Gtk.ListView))
need = combo.widest(["PulseAudio", "PipeWire"])
check("and is at least as wide as its widest entry", view.get_size_request()[0] >= need,
      "(%s < %s)" % (view.get_size_request()[0], need))
row.set_model(Gtk.StringList.new(["A much longer entry than before"]))
check("a new list is measured again",
      view.get_size_request()[0] >= combo.widest(["A much longer entry than before"]))
check("a row that is not a combo row is left alone",
      combo.keep_value_visible(Adw.ActionRow(title="x")) is None)

print("\n  %d checks, %d failed" % (RUN, FAILED))
sys.exit(1 if FAILED else 0)
