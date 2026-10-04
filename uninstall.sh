#!/bin/bash
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
#
# Removes the app and everything it left on the phone, so that a later
# install.sh behaves exactly as on a new one: the program, its icon and its
# launcher entry (and those of the names it had before), what the window
# wrote as the user - its language, the switches on the Phosh tab, the
# keyring prompter shim, batman's Bluetooth powersave - and its own clones
# in ~/.local/share/misc-de.
#
# Put back, not guessed: install.sh and every switch wrote down what was
# there before their first change (/usr/local/lib/misc-de/original-state,
# ~/.config/misc-de/original/ - see miscde/original.py), and this restores
# exactly that, while it is still as the app left it. Only where an older
# version left no record does it fall back to the app's markers, and it
# says so.
#
# What it deliberately does NOT remove: the tools behind the tabs. Each has
# its own uninstaller, each was a separate decision to install, and audio and
# modem hold the phone's sound and its data connection - taking those out
# because somebody removed a front end would be the app deciding something it
# was never asked about. One thing of theirs is the app's all the same: the
# colouring unit, which battctl's installer never enables and the Battery
# tab did - it goes back to how it stood before that, from the record.
#
# The clones are different: the app made them, in a directory of its own, to
# fetch and update those tools, so they are app state and go with it - except
# a clone with work in it that exists nowhere else (uncommitted changes, a
# stash, commits no remote has). That one is named and left alone. So is a
# clone whose tool is still installed: its uninstall.sh is the only one on
# the phone, and deleting it would leave a tool that nothing here can take
# out again. The clone is named with the uninstaller to run first; after
# that, a second run of this script removes it. Clones somebody keeps
# themselves, in ~/Projekte or anywhere else, are never looked at.
#
# DESTDIR, as in make: a staged root instead of /, for the tests.
set -uo pipefail

if [ "$(id -u)" = 0 ]; then
    echo "Please run WITHOUT sudo - it asks where it needs to." >&2
    exit 1
fi

PREFIX="${DESTDIR:-}/usr/local"
HERE=$(cd "$(dirname "$0")" && pwd)
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

# The tool each clone installs, and the subdirectory its installer sits in -
# "dir", "tool" and "sub" of COMPONENTS in miscde/components.py, which a test
# holds this table against. The app's own clone is not here: its uninstall.sh
# is this script, and step 1 has already removed the program.
clone_tool() {
    case "$1" in
    furios_audio) echo "audioctl" ;;
    furios_modem_fixes) echo "modemctl" ;;
    furios_gps) echo "furios-gps-contribute" ;;
    furios_killswitch) echo "killswitch-indicator" ;;
    furios_security) echo "secctl" ;;
    furios_misc) echo "battctl battery" ;;
    furios_phosh) echo "furios-folder-dock folder-dock" ;;
    esac
}

# Is this tool installed? Looked for where the app looks (_tool_maybe in
# miscde/tools.py): /usr/local/bin, /usr/bin, ~/.local/bin, then $PATH. With
# DESTDIR the first two are the staged ones and $PATH is not asked - it is
# this machine's, not the stage's.
tool_installed() {
    local name=$1 dir
    # The folder dock is a phosh plugin, not a program: installed is its
    # file where phosh looks (folder_dock_plugin in miscde/components.py).
    if [ "$name" = furios-folder-dock ]; then
        compgen -G "${DESTDIR:-}/usr/lib/*/phosh/plugins/$name.plugin" >/dev/null
        return
    fi
    for dir in "${DESTDIR:-}/usr/local/bin" "${DESTDIR:-}/usr/bin" \
            "$HOME/.local/bin"; do
        [ -x "$dir/$name" ] && return 0
    done
    [ -z "${DESTDIR:-}" ] && type -P "$name" >/dev/null
}

# Every clone in the app's own directory, each on its own merits, and the
# directory itself once it is empty. A link is taken out as a link: what it
# points to is somebody else's.
remove_clones() {
    local base=$1 dir why tool sub
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
        read -r tool sub <<<"$(clone_tool "$(basename "$dir")")"
        if [ -n "$tool" ] && tool_installed "$tool"; then
            echo "(kept $dir: $tool is still installed - run" \
                "$dir/${sub:+$sub/}uninstall.sh first, then this again)"
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

# What /usr/local looked like before install.sh first ran: which of the
# shared directories and caches were there. Read now, because step 1 takes
# the directory it lives in away.
ORIGINAL=$(cat "$PREFIX/lib/misc-de/original-state" 2>/dev/null) || ORIGINAL=""
# "present" or "absent" for a path under $PREFIX, nothing when not recorded.
was() {
    awk -v p="$1" '$2 == p { print $1 }' <<<"$ORIGINAL"
}

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
# Where somebody else's icon or entry is there as well, the cache is rebuilt.
# Otherwise the cache goes when it was not there before install.sh, and so
# does every directory install.sh made - but one that was there before, even
# empty, stays. That is read from what install.sh wrote down; only where it
# wrote nothing (an older version installed) does it fall back to "FuriOS
# ships neither directory", and says so.
if [ -n "$ORIGINAL" ]; then
    if find "$PREFIX/share/icons" -type f ! -name icon-theme.cache 2>/dev/null | grep -q .; then
        sudo gtk-update-icon-cache -qtf "$PREFIX/share/icons/hicolor" 2>/dev/null || true
    elif [ "$(was share/icons/hicolor/icon-theme.cache)" = present ]; then
        sudo gtk-update-icon-cache -qtf "$PREFIX/share/icons/hicolor" 2>/dev/null || true
    else
        sudo rm -f "$PREFIX/share/icons/hicolor/icon-theme.cache"
    fi
    if find "$PREFIX/share/applications" -type f ! -name mimeinfo.cache 2>/dev/null | grep -q .; then
        sudo update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
    elif [ "$(was share/applications/mimeinfo.cache)" = present ]; then
        sudo update-desktop-database -q "$PREFIX/share/applications" 2>/dev/null || true
    else
        sudo rm -f "$PREFIX/share/applications/mimeinfo.cache"
    fi
    for d in share/icons/hicolor/scalable/apps share/icons/hicolor/scalable \
            share/icons/hicolor share/icons share/applications lib/misc-de; do
        if [ "$(was "$d")" = absent ] && [ -d "$PREFIX/$d" ]; then
            sudo rmdir "$PREFIX/$d" 2>/dev/null || true
        elif [ "$(was "$d")" = present ] && [ ! -d "$PREFIX/$d" ]; then
            sudo install -d -m755 "$PREFIX/$d"
        fi
    done
else
    if [ -e "$PREFIX/share/icons" ] || [ -e "$PREFIX/share/applications" ]; then
        echo "(no record of /usr/local from before misc-de was installed - an" \
            "older version installed it; caches and directories go by what is" \
            "left in them)"
    fi
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
fi

echo "4) what the window wrote"
# The owner's rule (30.9.2026): every switch writes down what was there
# before its first change (miscde/original.py, records in
# ~/.config/misc-de/original/), and this puts exactly that back - a file's
# text or its absence, a dconf key set or unset, batman's BTSAVE lines as
# they were - but only while it is still as the app left it. Changed by
# somebody since: left alone, and said. Only where there is no record
# (switched by a version before records existed) does it fall back to what
# it did before, by our markers, and it says so rather than guessing
# quietly. The records are read from this clone's miscde/original.py, not
# from the program step 1 has just removed.
BATMAN_CONFIG="${DESTDIR:-}/var/lib/batman/config"
if python3 - "$HERE/miscde/original.py" "$CONFIG" "$DATA" "${DESTDIR:-}" <<'PY'
import ast, glob, importlib.util, os, re, subprocess, sys
module, config, data, destdir = sys.argv[1:5]
spec = importlib.util.spec_from_file_location("miscde_original", module)
original = importlib.util.module_from_spec(spec)
spec.loader.exec_module(original)

DOCK = "furios-folder-dock"
KEY = ["mobi.phosh.shell.plugins", "status-icons"]
NO_RECORD = "no record of %s from before misc-de changed it (an older version did)"


def say(text):
    print("(%s)" % text)


def read(path):
    return original.read_text(path) or ""


def remove(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass


def write(path, text):
    with open(path + ".misc-de.tmp", "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(path + ".misc-de.tmp", path)


def gsettings(*args, env=None):
    return subprocess.run(["gsettings"] + list(args), capture_output=True,
                          text=True, env=env)


def icons(env=None):
    out = gsettings("get", *KEY, env=env)
    text = out.stdout.strip()
    if out.returncode != 0:
        raise ValueError(out.stderr)
    if text.startswith("@as "):
        text = text[4:]
    return list(ast.literal_eval(text))


def restart_unit(record):
    return "" if destdir else (record.get("unit") or "")


# --- 1. everything with a record, put back from it -------------------------
seen = set()
for record in original.all_records():
    kind = record.get("kind")
    if kind == "file":
        path = record["path"]
        seen.add(path)
        if record.get("block"):
            # A block of ours in somebody else's file: the whole file goes
            # back while nothing but our block was added; otherwise only
            # the block comes out.
            begin, end = record["block"]
            current = read(path)
            stripped = original.strip_block(current, begin, end)
            if original.block_back(record, stripped):
                original.put_back_file(record)
            elif stripped != current:
                write(path, stripped)
                say("took the misc-de block out of %s; the rest was changed "
                    "since and stays" % path)
            continue
        state = original.restore_file(path)
        if state == "changed":
            say("kept %s: changed since misc-de wrote it - before, %s"
                % (path, "there was no such file" if record.get("content") is None
                   else "it held something else"))
    elif kind == "gsettings" and record.get("schema") == "org.sigxcpu.feedbackd":
        # The Vibration tab's theme key: back to what it was, while it still
        # names our theme - a theme somebody chose since stays theirs.
        fkey = ("org.sigxcpu.feedbackd", record.get("key", "theme"))
        if gsettings("get", *fkey).stdout.strip().strip("'") == "misc-de":
            if record.get("user_value") is None:
                gsettings("reset", *fkey)
            else:
                gsettings("set", *fkey, record["user_value"])
        original.forget(original.setting_ident(*fkey))
    elif kind == "gsettings":
        seen.add("gsettings")
        try:
            now = icons()
        except (ValueError, SyntaxError, OSError):
            say("could not read %s %s" % tuple(KEY))
            continue
        if DOCK not in now:
            continue
        names = [n for n in now if n != DOCK]
        action, value = original.setting_back(record, names)
        if action == "reset":
            gsettings("reset", *KEY)
        else:
            gsettings("set", *KEY, str(value))
    elif kind == "lines":
        path = destdir + record["path"]
        seen.add("lines:" + record["path"])
        state = original.lines_back(record, original.read_text(path))
        if state == "restore":
            done = subprocess.run(
                ["sudo", "sh", "-c", original.RESTORE_LINES_SCRIPT, "sh", path,
                 record["key"], "\n".join(record["lines"]), restart_unit(record)])
            if done.returncode != 0:
                say("could not put %s in %s back" % (record["key"], path))
        elif state == "changed":
            say("kept %s in %s: changed since misc-de wrote it" % (record["key"], path))
    elif kind == "unit":
        # Enabled from the Battery tab, and it was not before: battctl's
        # installer never enables it, so the enabling was this app's change
        # and goes with it - stopped too, unless it was running before.
        unit = record["unit"]
        if not record.get("enabled") and subprocess.run(
                ["systemctl", "--user", "is-enabled", "--quiet", unit]).returncode == 0:
            argv = ["systemctl", "--user", "disable"]
            if not record.get("active"):
                argv.append("--now")
            if subprocess.run(argv + [unit]).returncode == 0:
                say("%s disabled again, as it was before the Battery tab" % unit)
            else:
                say("could not disable %s again" % unit)

    elif kind == "auto-brightness":
        # The Phosh tab's automatic brightness: the light sensor service and
        # gsd's key, back to what they were - the key only while it is still
        # what the switch set.
        unit, key = record["unit"], [record["schema"], record["key"]]
        if not destdir and not record.get("enabled") and subprocess.run(
                ["systemctl", "is-enabled", "--quiet", unit]).returncode == 0:
            argv = ["sudo", "systemctl", "disable"]
            if not record.get("active"):
                argv.append("--now")
            if subprocess.run(argv + [unit]).returncode == 0:
                say("%s disabled again, as it was before the Phosh tab" % unit)
            else:
                say("could not disable %s again" % unit)
        if gsettings("get", *key).stdout.strip() == "true":
            if record.get("user_value") is None:
                gsettings("reset", *key)
            else:
                gsettings("set", *key, str(bool(record["user_value"])).lower())

# --- 2. no record: by our markers, as before, and said -----------------------

# The search field: our block out of gtk.css, and the file only when that
# block was all it held.
css = os.path.join(config, "gtk-3.0", "gtk.css")
if css not in seen:
    old = read(css)
    new = original.strip_block(old, "/* misc-de: hide phosh search - begin */",
                               "/* misc-de: hide phosh search - end */")
    new = re.sub(r"/\* Hide phosh app grid search \(misc-de\) \*/\n"
                 r"\.phosh-search-bar-box,\s*\.phosh-search-bar\s*\{[^}]*\}\n?",
                 "", new)
    if new != old:
        say(NO_RECORD % css + "; took out only the misc-de block")
        if new.strip():
            write(css, new)
        else:
            remove(css)
        try:
            os.rmdir(os.path.dirname(css))
        except OSError:
            pass
remove(css + ".misc-de.tmp")

# The dock's switches: removed only in exactly a form the switches wrote -
# anything else in that file is the plugin's or somebody's own.
dock = os.path.join(config, "furios-folder-dock.conf")
forms = {"[dock]\n" + "".join("%s=true\n" % k for k in keys)
         for keys in (["one-row"], ["hide-labels"], ["one-row", "hide-labels"])}
if dock not in seen and os.path.exists(dock):
    if read(dock) in forms:
        say(NO_RECORD % dock + "; removed it, it is in a form the switches wrote")
        remove(dock)
    else:
        say("kept %s: no record, and not in a form the switches wrote" % dock)
remove(dock + ".misc-de.tmp")

# The keyring prompter: the service file only while it starts our shim, the
# shim only while it is ours.
shim = os.path.join(os.path.dirname(data), "libexec", "keyring-prompter-wait")
service = os.path.join(data, "dbus-1", "services",
                       "org.gnome.keyring.SystemPrompter.service")
if service not in seen and ("Exec=%s\n" % shim) in read(service):
    say(NO_RECORD % service)
    remove(service)
text = read(shim)
if shim not in seen and (
        "# misc-de: keyring prompter shim" in text
        or "# D-Bus activation shim for org.gnome.keyring.SystemPrompter." in text):
    say(NO_RECORD % shim)
    remove(shim)
for path in (service, shim):
    remove(path + ".misc-de.tmp")

# "Apps open right after boot": our phosh-portals.conf, by its marker only -
# one somebody wrote stays.
portals = os.path.join(config, "xdg-desktop-portal", "phosh-portals.conf")
if portals not in seen and (
        "# misc-de: apps start without waiting for the wlr portal" in read(portals)):
    say(NO_RECORD % portals)
    remove(portals)
    try:
        os.rmdir(os.path.dirname(portals))
    except OSError:
        pass
remove(portals + ".misc-de.tmp")

# The directories the prompter switch made, while they are empty - only
# where no record said which ones it made.
if service not in seen and shim not in seen:
    for d in (os.path.dirname(service), os.path.dirname(os.path.dirname(service)),
              os.path.dirname(shim)):
        try:
            os.rmdir(d)
        except OSError:
            pass

# "Folders at the bottom": our name out of phosh's plugin list - back to
# what furios_phosh's installer recorded, where it did. Without any record,
# a list back at the default is reset rather than written - a value in
# dconf, even the default one, pins the key against a later phosh.
phosh = original.phosh_plugin_record()
# feedbackd ends with "Failed to load any theme" when its key names a theme
# file that is gone - whatever happened to the record, never leave that.
_ft = ("org.sigxcpu.feedbackd", "theme")
if (gsettings("get", *_ft).stdout.strip().strip("'") == "misc-de"
        and not os.path.exists(os.path.join(
            os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config"),
            "feedbackd", "themes", "misc-de.json"))):
    gsettings("reset", *_ft)
    say("feedbackd's theme was misc-de without the file - reset")

if "gsettings" not in seen and phosh is not None:
    seen.add("gsettings")
    try:
        now = icons()
    except (ValueError, SyntaxError, OSError):
        now = []
    if DOCK in now:
        action, value = original.setting_back(phosh, [n for n in now if n != DOCK])
        if action == "reset":
            gsettings("reset", *KEY)
        else:
            gsettings("set", *KEY, str(value))
if "gsettings" not in seen:
    try:
        now = icons()
    except (ValueError, SyntaxError, OSError):
        now = []
    if DOCK in now:
        names = [n for n in now if n != DOCK]
        try:
            default = icons(dict(os.environ, GSETTINGS_BACKEND="memory"))
        except (ValueError, SyntaxError, OSError):
            default = None
        say(NO_RECORD % " ".join(KEY) + "; compared with the default")
        if names == default:
            gsettings("reset", *KEY)
        else:
            gsettings("set", *KEY, str(names))

# "Bluetooth powersave": batman's own setting. Without a record the copy
# somebody took by hand before the switch existed (config.bak-YYYYMMDD-
# HHMMSS) says what it was; without that either, off - the only value the
# switch ever wrote that FuriOS does not ship - goes back to on, and this
# says it is a guess.
batman = destdir + "/var/lib/batman/config"
if "lines:/var/lib/batman/config" not in seen:
    now = original.key_lines(original.read_text(batman), "BTSAVE")
    baks = sorted(glob.glob(batman + ".bak-[0-9]*-[0-9]*"))
    before = original.key_lines(original.read_text(baks[0]), "BTSAVE") if baks else None
    if now == ["BTSAVE=false"] and before != now:
        lines = before if before else ["BTSAVE=true"]
        say(NO_RECORD % "BTSAVE in " + batman + "; "
            + ("put back as in %s" % baks[0] if before
               else "set back to true, as FuriOS ships it - a guess"))
        done = subprocess.run(
            ["sudo", "sh", "-c", original.RESTORE_LINES_SCRIPT, "sh", batman,
             "BTSAVE", "\n".join(lines), "" if destdir else "batman.service"])
        if done.returncode != 0:
            say("could not switch batman's Bluetooth powersave back")
PY
then
    # Read, and put back: the records have done their job, and with them
    # goes the language - nothing else lives in the app's config directory.
    rm -rf "$CONFIG/misc-de"
else
    # Not without them: they are the only memory of what was there before.
    echo "(could not undo what the window wrote - kept $CONFIG/misc-de/original" \
        "for the next run)"
    rm -f "$CONFIG/misc-de/language"
fi

# The copy taken by hand before the switch existed goes once it is the file
# as it now is - it held nothing else.
for bak in "$BATMAN_CONFIG".bak-[0-9]*-[0-9]*; do
    [ -f "$bak" ] || continue
    if cmp -s "$bak" "$BATMAN_CONFIG"; then
        sudo rm -f "$bak"
    else
        echo "(kept $bak: it is not the config as it is now)"
    fi
done

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
# way the app looks, with tool_installed above.
for tool in audioctl modemctl furios-gps-contribute killswitch-indicator secctl battctl \
        furios-folder-dock; do
    if tool_installed "$tool"; then
        echo "(still installed: $tool - its own repository has uninstall.sh)"
    fi
done
exit 0
