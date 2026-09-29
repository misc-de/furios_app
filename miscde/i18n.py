# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The language the window speaks: English by default, German on request.

Every text on screen is written in English in the code and passed through
_(). German comes from miscde/lang_de.py, keyed by the English text itself,
so the English stays readable where it is used and a missing translation
falls back to it instead of to nothing. tests/test-app.py checks that every
_() in the code has its German entry - a new text without one fails the
suite, which is the point.

Chosen in the window (the icon at the top right), kept in
~/.config/misc-de/language, and read once at start: switching restarts the
window, the same way an update does, so nothing already built stays in the
old language.
"""

import os

LANGUAGES = (("en", "English"), ("de", "Deutsch"))
DEFAULT = "en"


def config_file():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "misc-de", "language")


def load():
    try:
        with open(config_file()) as f:
            code = f.read().strip()
    except OSError:
        return DEFAULT
    return code if code in dict(LANGUAGES) else DEFAULT


def save(code):
    """Returns True when the choice is on disk."""
    if code not in dict(LANGUAGES):
        return False
    path = config_file()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(code + "\n")
    except OSError:
        return False
    return True


_current = load()
_table = {}


def _load_table(code):
    if code == "de":
        from .lang_de import TRANSLATIONS
        return TRANSLATIONS
    return {}


_table = _load_table(_current)


def current():
    return _current


def use(code):
    """Switch for this process - the tests use it; the window restarts."""
    global _current, _table
    _current = code if code in dict(LANGUAGES) else DEFAULT
    _table = _load_table(_current)


def _(text):
    """The text in the chosen language. Placeholders are {name} and are
    filled in by the caller after translation, so the word order can differ
    between languages: _("Playing {codec}").format(codec=...)."""
    return _table.get(text, text)
