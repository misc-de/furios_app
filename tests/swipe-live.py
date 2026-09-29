#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Swiping between the tabs, against the real GTK and libadwaita.

A touch cannot be faked from here, so the controller itself is not driven. What
is checked is everything it relies on: the decision, the order of the tabs as
the real ViewStack reports it, hidden tabs left out, the ends wrapping round,
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

check("a quick sideways flick is a swipe", True, swipe.is_sideways_swipe(-150, 20, 250))
check("a short slide is not", False, swipe.is_sideways_swipe(-40, 0, 150))
check("a slow drag is not", False, swipe.is_sideways_swipe(-300, 0, 1500))
check("scrolling with a slanted thumb is not", False, swipe.is_sideways_swipe(-150, 120, 250))

# One finger, followed from down to up - whatever else claimed the touch.
t = swipe.Tracker()
t.down("a", 300, 400, 1000, False)
check("the finger that went down is measured", (-200, 10, 200, False), t.up("a", 100, 410, 1200))
t.down("a", 300, 400, 1000, False)
check("another finger's end is not this one's", None, t.up("b", 100, 400, 1200))
check("and this one still counts", (-200, 0, 200, False), t.up("a", 100, 400, 1200))
t.down("a", 300, 400, 1000, False)
t.down("b", 350, 400, 1010, False)
check("two fingers are not a swipe", None, t.up("a", 100, 400, 1200))
t.down("a", 300, 400, 1000, True)
check("where it began is carried through", True, t.up("a", 100, 400, 1200)[3])
t.down("a", 300, 400, 1000, False)
t.cancel("a")
check("a cancelled touch is forgotten", None, t.up("a", 100, 400, 1200))

stack = Adw.ViewStack()
for name in ("audio", "modem", "gps", "other"):
    stack.add_titled(Gtk.Label(label=name), name, name.title())
stack.get_page(stack.get_child_by_name("gps")).set_visible(False)
check("the tabs in the switcher's order, hidden ones left out",
      ["audio", "modem", "other"], swipe.visible_page_names(stack))

stack.set_visible_child_name("audio")
check("finger to the left: the next tab", "modem", swipe.step(stack, -200, 0, 200))
check("and the stack shows it", "modem", stack.get_visible_child_name())
check("a hidden tab is stepped over", "other", swipe.step(stack, -200, 0, 200))
check("past the last tab comes the first", "audio", swipe.step(stack, -200, 0, 200))
check("and before the first the last", "other", swipe.step(stack, 200, 0, 200))
check("finger to the right: back", "modem", swipe.step(stack, 200, 0, 200))
one = Adw.ViewStack()
one.add_titled(Gtk.Label(label="x"), "only", "Only")
check("a single tab has nowhere to go", None, swipe.step(one, -200, 0, 200))
check("a drag that began on a slider changes nothing", None,
      swipe.step(stack, 200, 0, 200, own=True))

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

controller = swipe.attach(stack)
check("it sees touches before anything under the finger", Gtk.PropagationPhase.CAPTURE,
      controller.get_propagation_phase())
check("and is not a gesture a row's click could cancel", True,
      isinstance(controller, Gtk.EventControllerLegacy))

print("\n  %d checks, %d failed" % (RUN, FAILED))
sys.exit(1 if FAILED else 0)
