#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Swiping between the tabs, against the real GTK and libadwaita.

A touch cannot be faked from here, so the gesture itself is not driven. What
is checked is everything it relies on: the decision, the order of the tabs as
the real ViewStack reports it, hidden tabs left out, the ends not wrapping,
and a slider or a text field keeping its own drag. Needs a display; without
one it says so and skips.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

import gi
gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

RUN = FAILED = 0


def check(what, want, got):
    global RUN, FAILED
    RUN += 1
    if want == got:
        print("  \033[32mok\033[0m   %s" % what)
    else:
        FAILED += 1
        print("  \033[31mFAIL\033[0m %s\n       expected [%s], got [%s]" % (what, want, got))


if not Gtk.init_check():
    print("  \033[33mskipped\033[0m - no display")
    sys.exit(0)
Adw.init()

from miscde import swipe  # noqa: E402  (needs Gtk initialised first)

check("a fast sideways flick is a swipe", True, swipe.is_sideways_swipe(-900, 100))
check("a slow drag is not", False, swipe.is_sideways_swipe(-300, 0))
check("scrolling with a slanted thumb is not", False, swipe.is_sideways_swipe(-900, 700))

stack = Adw.ViewStack()
for name in ("audio", "modem", "gps", "other"):
    stack.add_titled(Gtk.Label(label=name), name, name.title())
stack.get_page(stack.get_child_by_name("gps")).set_visible(False)
check("the tabs in the switcher's order, hidden ones left out",
      ["audio", "modem", "other"], swipe.visible_page_names(stack))

stack.set_visible_child_name("audio")
check("finger to the left: the next tab", "modem", swipe.step(stack, -900, 0))
check("and the stack shows it", "modem", stack.get_visible_child_name())
check("a hidden tab is stepped over", "other", swipe.step(stack, -900, 0))
check("no wrapping at the last tab", None, swipe.step(stack, -900, 0))
check("and it stays there", "other", stack.get_visible_child_name())
check("finger to the right: back", "modem", swipe.step(stack, 900, 0))
check("a drag that began on a slider changes nothing", None,
      swipe.step(stack, 900, 0, own=True))

box = Gtk.Box()
scale = Gtk.Scale()
entry = Gtk.Entry()
label = Gtk.Label(label="x")
for w in (scale, entry, label):
    box.append(w)
check("a slider drags by itself", True, swipe.drags_by_itself(scale))
check("so does a text field", True, swipe.drags_by_itself(entry))
check("a label does not", False, swipe.drags_by_itself(label))
check("nothing picked is no own drag", False, swipe.drags_by_itself(None))

gesture = swipe.attach(stack)
check("the gesture only watches", Gtk.PropagationPhase.CAPTURE,
      gesture.get_propagation_phase())
check("and only touch", True, gesture.get_touch_only())

print("\n  %d checks, %d failed" % (RUN, FAILED))
sys.exit(1 if FAILED else 0)
