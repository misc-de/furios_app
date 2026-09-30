# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""What was there before this app changed anything, written down first.

The owner's rule (30.9.2026): every change this app makes to the phone
remembers the original state BEFORE the first change, and switching off and
uninstall.sh put back exactly that - instead of guessing what "as shipped"
probably was. The uninstaller used to set batman's BTSAVE to true because
FuriOS ships it that way, whatever the file had said before the switch was
first moved; that is the kind of guess this module is here to end.

One record per thing changed, a small JSON file each, in
$XDG_CONFIG_HOME/misc-de/original/ (~/.config/misc-de/original/) - next to
the language file, in the directory that is already the app's alone and
that uninstall.sh removes at the very end, after it has read what is in
here. The file name is a hash of what the record is about, so two paths can
never share a record; what it is about is written inside, readable.

Three rules hold for every kind of record:

  * Written once, before the first change, and never again: a second toggle,
    a reinstall or a newer version finds the record and leaves it. The first
    original is the one that counts.
  * Not written when our own change is already there without a record - an
    older version of the app made it, and what was there before that is not
    known. The caller then falls back to what it did before this module
    existed and says so, rather than writing down a guess as a fact.
  * Put back only while the thing is still as we left it ("written"). If
    somebody changed it after us, it is theirs now: left alone, and said.

This module imports nothing but the standard library: uninstall.sh loads it
by path, on a phone where the window's GTK stack may already be gone.
"""

import hashlib
import json
import os

VERSION = 1


class ChangedSince(OSError):
    """Switching off found a file changed by somebody after we wrote it.
    Nothing was put back; paths names what was left as it is."""

    def __init__(self, paths):
        self.paths = list(paths)
        super().__init__("changed since misc-de wrote it, left as it is: "
                         + ", ".join(self.paths))


def state_dir():
    """Read at call time: the tests point XDG_CONFIG_HOME elsewhere after
    import, and uninstall.sh sets it for a staged home."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "misc-de", "original")


def _record_path(ident):
    kind = ident.split(":", 1)[0]
    digest = hashlib.sha1(ident.encode("utf-8")).hexdigest()[:16]
    return os.path.join(state_dir(), "%s-%s.json" % (kind, digest))


def load(ident):
    """The record, or None when there is none - or when it cannot be read,
    which is treated the same: a record that is not believed is no record."""
    try:
        with open(_record_path(ident), encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(record, dict) or record.get("ident") != ident:
        return None
    return record


def save(ident, record):
    record = dict(record, ident=ident, version=VERSION)
    path = _record_path(ident)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(record, f, indent=1, sort_keys=True)
        f.write("\n")
    os.replace(tmp, path)


def forget(ident):
    try:
        os.remove(_record_path(ident))
    except FileNotFoundError:
        pass
    try:
        os.rmdir(state_dir())
    except OSError:
        pass


def all_records():
    """Every record there is, for uninstall.sh."""
    try:
        names = sorted(os.listdir(state_dir()))
    except OSError:
        return []
    found = []
    for name in names:
        if not name.endswith(".json"):
            continue
        try:
            with open(os.path.join(state_dir(), name), encoding="utf-8") as f:
                record = json.load(f)
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and "ident" in record:
            found.append(record)
    return found


def read_text(path):
    """The file's text, or None when there is no file - absent and empty are
    different originals, and both have to come back as they were."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return None


# --- files -------------------------------------------------------------------
#
# A whole file: its text or its absence, its mode, and which of the
# directories above it did not exist yet - those, and only those, go again
# when they are empty. A directory that was there before, even an empty one,
# was somebody's.

def file_ident(path):
    return "file:" + os.path.abspath(path)


def _missing_dirs(path):
    """The directories above path that do not exist, deepest first."""
    missing = []
    d = os.path.dirname(os.path.abspath(path))
    while d and not os.path.isdir(d):
        missing.append(d)
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return missing


def remember_file(path, content=None, **extra):
    """Record the file as it is now, unless a record exists already.

    content: what counts as the original when it is not simply the text on
    disk - gtk.css with a block of ours already taken out, for one. Returns
    True when a record was written now."""
    ident = file_ident(path)
    if load(ident) is not None:
        return False
    text = read_text(path)
    try:
        mode = os.stat(path).st_mode & 0o7777 if text is not None else None
    except OSError:
        mode = None
    record = {"kind": "file", "path": os.path.abspath(path),
              "content": text if content is None else content,
              "mode": mode, "created_dirs": _missing_dirs(path)}
    record.update(extra)
    save(ident, record)
    return True


def wrote_file(path):
    """After every write of ours: what the file looks like as we left it.
    That, and not the original, is what "still ours" is measured against."""
    ident = file_ident(path)
    record = load(ident)
    if record is not None:
        record["written"] = read_text(path)
        save(ident, record)


def put_back_file(record):
    """The file exactly as recorded - its text and mode, or no file - and the
    directories we made, while they are empty. Then the record goes."""
    path = record["path"]
    content = record.get("content")
    if content is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".misc-de.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(content)
        if record.get("mode") is not None:
            os.chmod(tmp, record["mode"])
        os.replace(tmp, path)
    for d in record.get("created_dirs") or ():
        try:
            os.rmdir(d)
        except OSError:
            break
    forget(record["ident"])


def restore_file(path):
    """For switch-off and uninstall: put the file back from its record.

    None      - there is no record; the caller does what it did before
    "restored" - the file is the original again (or already was)
    "changed" - somebody changed it after our last write: left as it is
    """
    record = load(file_ident(path))
    if record is None:
        return None
    current = read_text(path)
    if "written" in record and current == record["written"]:
        put_back_file(record)
        return "restored"
    if current == record.get("content"):
        put_back_file(record)
        return "restored"
    return "changed"


# --- a block between two markers, in somebody else's file --------------------

def strip_block(text, begin, end):
    """text without every begin...end block (and the newline after it)."""
    out, rest = [], text
    while True:
        at = rest.find(begin)
        stop = rest.find(end, at + len(begin)) if at >= 0 else -1
        if at < 0 or stop < 0:
            out.append(rest)
            return "".join(out)
        out.append(rest[:at])
        rest = rest[stop + len(end):]
        if rest.startswith("\n"):
            rest = rest[1:]


def block_back(record, stripped):
    """Whether the file, with our block out, is the original again - allowing
    for the one newline switching on added to a last line that had none.
    When it is, the caller writes the recorded original, byte for byte."""
    content = record.get("content")
    if content is None:
        return stripped == ""
    return stripped in (content, content + "\n")


# --- a list in dconf -----------------------------------------------------------
#
# A key can be unset (the schema's default applies, and follows what a later
# version ships) or set to a value - even to the default's value. Which of the
# two it was is recorded, so that off can reset it or set it, instead of
# guessing from "equals the default".

def setting_ident(schema, key):
    return "gsettings:%s:%s" % (schema, key)


def remember_setting(schema, key, user_value, value):
    """user_value: what the user's dconf holds, None when unset. value: what
    the key read as then, default included."""
    ident = setting_ident(schema, key)
    if load(ident) is not None:
        return False
    save(ident, {"kind": "gsettings", "schema": schema, "key": key,
                 "user_value": user_value, "value": value})
    return True


def setting_back(record, value):
    """What to do with the key once our part is out of value.

    ("reset", None) or ("set", original) when value is the original again -
    then the record has done its job and the caller forgets it; ("set",
    value) when something else changed the key after us (another plugin put
    itself into the same list): our part goes, theirs stays."""
    if record is not None and value == record.get("value"):
        if record.get("user_value") is None:
            return "reset", None
        return "set", record["user_value"]
    return "set", value


def phosh_plugin_record():
    """phosh's plugin list as furios_phosh's installer recorded it, in the
    form of a record of ours - or None.

    The folder dock is furios_phosh's plugin, and its installer writes down
    the list before its own first change, in
    ${XDG_STATE_HOME:-~/.local/state}/furios-phosh/original.json
    (lib/furios-phosh-original there). The app offers the switch only once
    the plugin is installed, so that record is always older than the app's
    first change, and the better original: it is used first, and the app
    writes its own only where there is none. Not believed when it says it
    was taken over an install from before records ("legacy") or over a
    list that already held our name."""
    base = (os.environ.get("XDG_STATE_HOME")
            or os.path.expanduser("~/.local/state"))
    try:
        with open(os.path.join(base, "furios-phosh", "original.json"),
                  encoding="utf-8") as f:
            record = json.load(f)
    except (OSError, ValueError):
        return None
    key = record.get("key") if isinstance(record, dict) else None
    if not isinstance(key, dict) or record.get("legacy") or key.get("had_ours"):
        return None
    if key.get("set"):
        value = key.get("value")
        user = value
    else:
        value, user = key.get("default"), None
    if not isinstance(value, list):
        return None
    return {"kind": "gsettings", "user_value": user, "value": value,
            "source": "furios_phosh"}


# --- KEY=value lines in another program's config -----------------------------
#
# batman's /var/lib/batman/config is root's, so it is changed through sudo;
# the record is only read and written here, as the user.

def lines_ident(path, key):
    return "lines:%s:%s" % (path, key)


def key_lines(text, key):
    """The lines that set key, as the switch's sed sees them: at the start
    of the line."""
    return [l for l in (text or "").splitlines() if l.startswith(key + "=")]


def remember_lines(path, key, text, source=None, unit=None):
    """Record which lines set key in text (none at all is a record too).

    source: where text came from when it is not the file itself - a copy
    somebody took by hand before the switch existed is a better original
    than the file that switch has already changed. unit: the service that
    reads the file only at its start, restarted after putting it back."""
    ident = lines_ident(path, key)
    if load(ident) is not None:
        return False
    save(ident, {"kind": "lines", "path": path, "key": key,
                 "lines": key_lines(text, key), "source": source or path,
                 "unit": unit})
    return True


def wrote_lines(path, key, lines):
    ident = lines_ident(path, key)
    record = load(ident)
    if record is not None:
        record["written"] = list(lines)
        save(ident, record)


def lines_back(record, text):
    """"restored" (already the original), "restore" (still ours: put the
    recorded lines back) or "changed" (somebody changed it after us)."""
    now = key_lines(text, record["key"])
    if now == record.get("lines"):
        return "restored"
    if "written" in record and now == record["written"]:
        return "restore"
    return "changed"


# Puts the recorded lines back, as root through sudo: $1 the file, $2 the
# key, $3 the lines (newline-separated; empty takes the key out altogether),
# $4 a unit to restart after, or empty. In the first line's place, so the
# order of the file is kept; through a temp file next to it and `cat >` over
# the original, so owner and mode stay what they were.
RESTORE_LINES_SCRIPT = (
    'set -e\n'
    'tmp=$(mktemp "$1.XXXXXX")\n'
    'awk -v key="$2" -v lines="$3" \'\n'
    '  index($0, key "=") == 1 { if (!done && lines != "") print lines; '
    'done = 1; next }\n'
    '  { print }\n'
    '  END { if (!done && lines != "") print lines }\' "$1" > "$tmp"\n'
    'cat "$tmp" > "$1"\n'
    'rm -f "$tmp"\n'
    '[ -z "$4" ] || systemctl try-restart "$4"\n'
)


# --- a user unit ----------------------------------------------------------------

def unit_ident(unit):
    return "unit:" + unit


def remember_unit(unit, enabled, active):
    ident = unit_ident(unit)
    if load(ident) is not None:
        return False
    save(ident, {"kind": "unit", "unit": unit, "enabled": bool(enabled),
                 "active": bool(active)})
    return True
