# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Swiping left and right between the tabs.

Adw.ViewStack has no gesture of its own, so the window watches for one: a
Gtk.GestureSwipe in the capture phase that never claims the touch. Every
widget underneath still gets it whole - a row still takes its tap, a page
still scrolls - and only at the end, from the speed the finger left with,
is it decided whether that was a swipe to the next tab.

Two things decide it, and both are here as plain functions so they can be
tested without a display: whether the speed says "sideways, and meant", and
whether the touch began on something that is dragged sideways by itself - a
slider on the battery page, a text field - where a fast drag is that
widget's, not the window's.
"""

from gi.repository import Gtk

# Pixels per second. A deliberate flick is well above this; a slow drag while
# reading, or a tap that slid, stays below it.
MIN_SPEED = 600

# Widgets a sideways drag belongs to. Checked up the tree from where the touch
# began, so a slider's trough and knob count as the slider.
OWN_DRAG = (Gtk.Scale, Gtk.Editable, Gtk.SpinButton)


def is_sideways_swipe(vx, vy, min_speed=MIN_SPEED):
    """Fast enough, and clearly more sideways than up or down - scrolling a
    page with a thumb that is not quite vertical must not change the tab."""
    return abs(vx) >= min_speed and abs(vx) > 2 * abs(vy)


def neighbour(names, current, vx):
    """The tab a swipe leads to, or None at either end - no wrapping round,
    because a swipe that lands on the far side reads as a jump, not a step.
    The finger moving left (vx < 0) brings the next tab in from the right."""
    if current not in names:
        return None
    i = names.index(current) + (1 if vx < 0 else -1)
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


def step(stack, vx, vy, own=False):
    """What a finished swipe does to the stack: move one tab, or nothing.
    Returns the tab it moved to, or None."""
    if own or not is_sideways_swipe(vx, vy):
        return None
    target = neighbour(visible_page_names(stack),
                       stack.get_visible_child_name(), vx)
    if target:
        stack.set_visible_child_name(target)
    return target


def attach(stack):
    """Watch the stack for sideways swipes. Returns the gesture."""
    gesture = Gtk.GestureSwipe()
    # Touch only: with a mouse, a fast drag is selecting text.
    gesture.set_touch_only(True)
    gesture.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    state = {"own": False}

    def begin(g, sequence):
        ok, x, y = g.get_point(sequence)
        target = stack.pick(x, y, Gtk.PickFlags.DEFAULT) if ok else None
        state["own"] = drags_by_itself(target)

    def swipe(_g, vx, vy):
        step(stack, vx, vy, state["own"])

    gesture.connect("begin", begin)
    gesture.connect("swipe", swipe)
    stack.add_controller(gesture)
    return gesture
