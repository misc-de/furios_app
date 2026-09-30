#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Removes the app and everything it left on the phone, so that a later
# install.sh behaves exactly as on a new one: the program, its icon and its
# launcher entry (and those of the names it had before), what the window
# wrote as the user - its language, the switches on the Phosh tab, the
# keyring prompter shim - and its own clones in ~/.local/share/misc-de.
#
# What it deliberately does NOT remove: the tools behind the tabs. Each has
# its own uninstaller, each was a separate decision to install, and audio and
# modem hold the phone's sound and its data connection - taking those out
# because somebody removed a front end would be the app deciding something it
# was never asked about.
#
# The clones are different: the app made them, in a directory of its own, to
# fetch and update those tools, so they are app state and go with it - except
# a clone with work in it that exists nowhere else (uncommitted changes, a
# stash, commits no remote has). That one is named and left alone. Clones
# somebody keeps themselves, in ~/Projekte or anywhere else, are never
# looked at. A tool installed from a clone that is gone now can still be
# removed: its repository on GitHub has the same uninstall.sh.
#
# DESTDIR, as in make: a staged root instead of /, for the tests.
set -uo pipefail

if [ "$(id -u)" = 0 ]; then
    echo "Please run WITHOUT sudo - it asks where it needs to." >&2
    exit 1
fi

PREFIX="${DESTDIR:-}/usr/local"
CONFIG="${XDG_CONFIG_HOME:-$HOME/.config}"
DATA="${XDG_DATA_HOME:-$HOME/.local/share}"
CLONES="$DATA/misc-de"

# --- clone rule (the tests extract everything down to the end marker) ---
# Why a clone holds work that exists nowhere else, or nothing when it holds
# none. Anything git cannot answer counts as work: a clone is only deleted
# when git has said that everything in it is on a remote.
unsaved_work() {
    local dir=$1 ahead
    [ -e "$dir/.git" ] || { echo "not a git clone"; return; }
    [ -z "$(git -C "$dir" status --porcelain 2>&1)" ] \
        || { echo "uncommitted changes"; return; }
    [ -z "$(git -C "$dir" stash list 2>&1)" ] || { echo "a stash"; return; }
    ahead=$(git -C "$dir" rev-list --branches --tags HEAD --not --remotes 2>&1) \
        || { echo "git could not say what was pushed"; return; }
    [ -z "$ahead" ] || { echo "commits that are on no remote"; return; }
}

# Every clone in the app's own directory, each on its own merits, and the
# directory itself once it is empty. A link is taken out as a link: what it
# points to is somebody else's.
remove_clones() {
    local base=$1 dir why
    [ -e "$base" ] || return 0
    if [ -L "$base" ]; then
        echo "(kept $base: it is a link, and what it points to is not the app's)"
        return 0
    fi
    for dir in "$base"/* "$base"/.[!.]*; do
        [ -e "$dir" ] || [ -L "$dir" ] || continue
        if [ -L "$dir" ]; then
            rm -f "$dir"
            continue
        fi
        why=$(unsaved_work "$dir")
        if [ -n "$why" ]; then
            echo "(kept $dir: $why)"
        else
            rm -rf "$dir"
        fi
    done
    rmdir "$base" 2>/dev/null || true
}
# --- end clone rule ---

echo "1) program"
# furios-audio-switch is what the app was called until 13.9.2026.
sudo rm -f "$PREFIX/bin/misc-de" "$PREFIX/bin/furios-audio-switch"
sudo rm -rf "$PREFIX/lib/misc-de"

echo "2) icon"
sudo rm -f "$PREFIX/share/icons/hicolor/scalable/apps/de.misc-de.tools.svg" \
    "$PREFIX/share/icons/hicolor/scalable/apps/de.furios.audioswitch.svg"

echo "3) launcher entry"
sudo rm -f "$PREFIX/share/applications/de.misc-de.tools.desktop" \
    "$PREFIX/share/applications/de.furios.audioswitch.desktop"

# So the app grid drops the entry right away instead of at the next login.
# The two caches are the installer's too: FuriOS ships neither directory, so
# where nothing but the cache is left, cache and directories go; where
# somebody else's icon or entry is there as well, the cache is rebuilt.
if find "$PREFIX/share/icons" -type f ! -name icon-theme.cache 2>/dev/null | grep -q .; then
    sudo gtk-update-icon-cache -qtf "$PREFIX/share/icons/hicolor" 2>/dev/null || true
elif [ -d "$PREFIX/share/icons" ]; then
    sudo rm -f "$PREFIX/share/icons/hicolor/icon-theme.cache"
    sudo find "$PREFIX/share/icons" -depth -type d -empty -delete
fi
if find "$PREFIX/share/applications" -type f ! -name mimeinfo.cache 2>/dev/null | grep -q .; then
    sudo update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
elif [ -d "$PREFIX/share/applications" ]; then
    sudo rm -f "$PREFIX/share/applications/mimeinfo.cache"
    sudo rmdir "$PREFIX/share/applications" 2>/dev/null || true
fi

echo "4) what the window wrote"
# The language, and nothing else lives there.
rm -rf "$CONFIG/misc-de"

# The Phosh tab, switch by switch, the way the tab itself switches off (see
# miscde/pages/other.py) - only what carries our marker, so somebody's own
# gtk.css or prompter service is never touched. Including the forms written
# by hand before the switches existed, which the tab counts as its own too.
python3 - "$CONFIG" "$DATA" <<'PY' || echo "(could not undo the Phosh tab's switches)"
import os, re, sys
config, data = sys.argv[1], sys.argv[2]


def read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


# The search field: our block out of gtk.css, and the file only when that
# block was all it held.
css = os.path.join(config, "gtk-3.0", "gtk.css")
old = read(css)
new = re.sub(r"/\* misc-de: hide phosh search - begin \*/.*?"
             r"/\* misc-de: hide phosh search - end \*/\n?", "", old, flags=re.S)
new = re.sub(r"/\* Hide phosh app grid search \(misc-de\) \*/\n"
             r"\.phosh-search-bar-box,\s*\.phosh-search-bar\s*\{[^}]*\}\n?", "", new)
if new != old:
    if new.strip():
        with open(css + ".misc-de.tmp", "w", encoding="utf-8") as f:
            f.write(new)
        os.replace(css + ".misc-de.tmp", css)
    else:
        remove(css)
    try:
        os.rmdir(os.path.dirname(css))
    except OSError:
        pass
remove(css + ".misc-de.tmp")

# The dock's switches, a file that is ours by name.
for name in ("furios-folder-dock.conf", "furios-folder-dock.conf.misc-de.tmp"):
    remove(os.path.join(config, name))

# The keyring prompter: the service file only while it starts our shim, the
# shim only while it is ours.
shim = os.path.join(os.path.dirname(data), "libexec", "keyring-prompter-wait")
service = os.path.join(data, "dbus-1", "services",
                       "org.gnome.keyring.SystemPrompter.service")
if ("Exec=%s\n" % shim) in read(service):
    remove(service)
text = read(shim)
if ("# misc-de: keyring prompter shim" in text
        or "# D-Bus activation shim for org.gnome.keyring.SystemPrompter." in text):
    remove(shim)
for path in (service, shim):
    remove(path + ".misc-de.tmp")
# The directories the switch made, while they are empty.
for d in (os.path.dirname(service), os.path.dirname(os.path.dirname(service)),
          os.path.dirname(shim)):
    try:
        os.rmdir(d)
    except OSError:
        pass
PY

# "Folders at the bottom": our name out of phosh's plugin list, and a list
# back at its default reset rather than written - a value in the user's
# dconf, even the default one, pins the key against whatever a later phosh
# ships. The plugin itself is furios_phosh's, and stays.
if command -v gsettings >/dev/null; then
    python3 - <<'PY' || true
import ast, os, subprocess, sys
key = ["mobi.phosh.shell.plugins", "status-icons"]


def read(env=None):
    out = subprocess.run(["gsettings", "get"] + key, capture_output=True,
                         text=True, env=env)
    text = out.stdout.strip()
    if text.startswith("@as "):
        text = text[4:]
    return list(ast.literal_eval(text))


try:
    now = read()
except (ValueError, SyntaxError):
    sys.exit(0)
if "furios-folder-dock" not in now:
    sys.exit(0)
names = [n for n in now if n != "furios-folder-dock"]
try:
    default = read(dict(os.environ, GSETTINGS_BACKEND="memory"))
except (ValueError, SyntaxError):
    default = None
if names == default:
    subprocess.run(["gsettings", "reset"] + key, check=False)
else:
    subprocess.run(["gsettings", "set"] + key + [str(names)], check=False)
PY
fi

# The password socket of a window that did not get to close it. It lives on
# tmpfs and would go at the next boot anyway; not while a window is open.
if [ -n "${XDG_RUNTIME_DIR:-}" ] && ! pgrep -u "$(id -u)" -f 'bin/misc-de|misc-de\.py' >/dev/null; then
    rm -rf "$XDG_RUNTIME_DIR"/misc-de-*
fi

echo "5) the app's own clones"
remove_clones "$CLONES"

echo
echo "Removed."
# Said rather than done: somebody who wants these gone should see where they
# are, and each tool's own uninstaller knows what it changed. Looked for the
# way install.sh and the app look, ~/.local/bin included.
for tool in audioctl modemctl furios-gps-contribute killswitch-indicator secctl battctl; do
    for dir in /usr/local/bin /usr/bin "$HOME/.local/bin"; do
        if [ -x "$dir/$tool" ]; then
            echo "(still installed: $tool - its own repository has uninstall.sh)"
            break
        fi
    done
done
exit 0
