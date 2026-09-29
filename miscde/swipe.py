# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Swiping left and right between the tabs.

Adw.ViewStack has no gesture of its own, so the window watches for one.

Not with a Gtk.GestureSwipe. That was the first version, and on the phone it
only worked on the empty background between the groups: every row has a
click gesture of its own, it claims the touch the moment the finger lands,
and a claimed touch cancels every other gesture on the way to it - the
window's included, capture phase or not. So a swipe that started on a row,
which is nearly every swipe on a page made of rows, did nothing.

What is used instead is an event controller that sees the raw touch events
in the capture phase and never takes part in claiming: it is told where the
finger went down and where it came up, whoever else acted on the touch in
between. The row under the finger sees the movement too and does not count
it as a tap once the finger has moved, so nothing is switched by accident.

Whether that was a swipe is decided from distance, direction and time - here
as plain functions so they can be tested without a touchscreen - and whether
it began on something that drags sideways by itself: a slider on the battery
page, a text field. A drag there is that widget's, not the window's.
"""

import os
import sys

from gi.repository import Gdk, Gtk

# MISCDE_SWIPE_DEBUG=1: every touch event and every decision on stderr - the
# only way to see what the phone really delivers, since a touch cannot be
# produced from a test.
DEBUG = bool(os.environ.get("MISCDE_SWIPE_DEBUG"))


def debug(*parts):
    if DEBUG:
        print("swipe:", *parts, file=sys.stderr, flush=True)

# Far enough that a tap that slid a little, or a thumb resting while reading,
# is not a swipe; short enough for a flick. In logical pixels.
MIN_DISTANCE = 80
# A swipe is quick. Longer than this, the finger was dragging something, or
# reading along a line.
MAX_DURATION_MS = 700

# Widgets a sideways drag belongs to. Checked up the tree from where the touch
# began, so a slider's trough and knob count as the slider.
OWN_DRAG = (Gtk.Scale, Gtk.Editable, Gtk.SpinButton)


def is_sideways_swipe(dx, dy, duration_ms,
                      min_distance=MIN_DISTANCE, max_ms=MAX_DURATION_MS):
    """Far enough, quick enough, and clearly more sideways than up or down -
    scrolling a page with a thumb that is not quite vertical must not change
    the tab."""
    return (abs(dx) >= min_distance and abs(dx) > 2 * abs(dy)
            and 0 <= duration_ms <= max_ms)


def neighbour(names, current, dx):
    """The tab a swipe leads to, or None at either end - no wrapping round,
    because a swipe that lands on the far side reads as a jump, not a step.
    The finger moving left (dx < 0) brings the next tab in from the right."""
    if current not in names:
        return None
    i = names.index(current) + (1 if dx < 0 else -1)
    return names[i] if 0 <= i < len(names) else None


def drags_by_itself(widget):
    """Did the touch begin on something with a sideways drag of its own?"""
    while widget is not None:
        if isinstance(widget, OWN_DRAG):
            return True
        widget = widget.get_parent()
    return False


def visible_page_names(stack):
    """The tab names in the order the switcher shows them, hidden ones left
    out."""
    pages = stack.get_pages()
    names = []
    for i in range(pages.get_n_items()):
        page = pages.get_item(i)
        if page.get_visible() and page.get_name():
            names.append(page.get_name())
    return names


def step(stack, dx, dy, duration_ms, own=False):
    """What a finished touch does to the stack: move one tab, or nothing.
    Returns the tab it moved to, or None."""
    if own or not is_sideways_swipe(dx, dy, duration_ms):
        return None
    target = neighbour(visible_page_names(stack),
                       stack.get_visible_child_name(), dx)
    if target:
        stack.set_visible_child_name(target)
    return target


class Tracker:
    """One finger, from down to up. A second finger makes it not a swipe:
    two fingers are a zoom or a mistake, and neither is a tab change."""

    def __init__(self):
        self.start = None     # (sequence, x, y, time_ms, own)
        self.spoiled = False

    def down(self, sequence, x, y, time_ms, own):
        if self.start is not None:
            self.spoiled = True
            return
        self.start = (sequence, x, y, time_ms, own)
        self.spoiled = False

    def up(self, sequence, x, y, time_ms):
        """The movement as (dx, dy, duration_ms, own), or None when this was
        not the finger being followed, or the touch does not count."""
        if self.start is None or self.start[0] != sequence:
            return None
        _seq, x0, y0, t0, own = self.start
        self.start = None
        if self.spoiled:
            return None
        return (x - x0, y - y0, time_ms - t0, own)

    def cancel(self, sequence):
        if self.start is not None and self.start[0] == sequence:
            self.start = None


def attach(stack):
    """Watch the stack's touches for sideways swipes. Returns the controller."""
    controller = Gtk.EventControllerLegacy()
    controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    tracker = Tracker()

    def widget_at(event):
        """What the finger landed on, for the own-drag question. Surface
        coordinates, so through the window's own surface offset."""
        root = stack.get_root()
        ok, x, y = event.get_position()
        if root is None or not ok:
            return None
        tx, ty = root.get_surface_transform()
        return root.pick(x - tx, y - ty, Gtk.PickFlags.DEFAULT)

    def on_event(ctl, event):
        # PyGObject hands this signal's GdkEvent over as None (seen on the
        # phone 29.9.: every touch arrived, every one as None). The
        # controller still knows the event it is handling.
        if event is None:
            event = ctl.get_current_event()
        if event is None:
            debug("no event")
            return False
        try:
            return handle(event)
        except Exception as err:  # never let a watcher take input down
            debug("error", repr(err))
            return False

    def handle(event):
        kind = event.get_event_type()
        debug("event", kind.value_nick if hasattr(kind, "value_nick") else kind)
        if kind not in (Gdk.EventType.TOUCH_BEGIN, Gdk.EventType.TOUCH_END,
                        Gdk.EventType.TOUCH_CANCEL):
            return False
        sequence = event.get_event_sequence()
        ok, x, y = event.get_position()
        debug("  at", ok, x, y, "time", event.get_time())
        if not ok:
            return False
        t = event.get_time()
        if kind == Gdk.EventType.TOUCH_BEGIN:
            tracker.down(sequence, x, y, t, drags_by_itself(widget_at(event)))
        elif kind == Gdk.EventType.TOUCH_END:
            moved = tracker.up(sequence, x, y, t)
            debug("  moved", moved)
            if moved:
                dx, dy, ms, own = moved
                debug("  step ->", step(stack, dx, dy, ms, own))
        else:
            tracker.cancel(sequence)
        # Never stop the event: whatever is under the finger gets it as if
        # nothing were watching.
        return False

    controller.connect("event", on_event)
    stack.add_controller(controller)
    return controller
