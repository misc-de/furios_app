# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Keep an Adw.ComboRow's chosen value readable.

Seen on the phone on 29.9.2026: with a long description under its title the
"Sound server" row showed "…" where "PipeWire" belongs. The row's title
column is given the width first; the small list that shows the chosen value
wanted 64 px and got 26, and no amount of re-measuring changed that. What
does change it is a minimum width on that list - as wide as its widest
entry, so switching to a longer one does not cut it either.
"""

from gi.repository import Gtk

# The list view draws its item with a little padding around the label.
PADDING = 4
# A row is a handful of widgets. The search stops after this many, whatever
# it is walking: on 29.9.2026 the tests' stand-in for GTK answered every
# "next sibling?" with a new object, the walk never ended, and the test run
# grew to 17 GB and took the phone's shell down with it.
MAX_WIDGETS = 64


def _value_list(row):
    """The Gtk.ListView inside the row that shows the chosen value - looked
    for breadth first, among at most MAX_WIDGETS widgets."""
    queue = [row]
    seen = 0
    while queue and seen < MAX_WIDGETS:
        widget = queue.pop(0)
        child = widget.get_first_child()
        while child is not None and seen < MAX_WIDGETS:
            seen += 1
            if isinstance(child, Gtk.ListView):
                return child
            queue.append(child)
            child = child.get_next_sibling()
    return None


def widest(strings):
    """The natural width of the widest of these, as a label would draw it."""
    best = 0
    for text in strings:
        best = max(best, Gtk.Label(label=text).measure(
            Gtk.Orientation.HORIZONTAL, -1)[1])
    return best


def model_strings(model):
    if model is None:
        return []
    if not isinstance(model, Gtk.StringList):
        return []
    n = model.get_n_items()
    if not isinstance(n, int):
        return []
    return [model.get_string(i) for i in range(min(n, MAX_WIDGETS))]


def keep_value_visible(row):
    """Size the row's value list for its widest entry, now and whenever the
    row gets a new list. Returns the list view, or None where there is none
    (a row that is not a real ComboRow - the tests' stand-in, for one)."""
    view = _value_list(row)
    if not isinstance(view, Gtk.ListView):
        return None

    def fit(*_args):
        width = widest(model_strings(row.get_model()))
        if width:
            view.set_size_request(width + PADDING, -1)

    fit()
    row.connect("notify::model", fit)
    return view
