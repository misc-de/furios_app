# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Other page: small things with no tool of their own.

Everything on the other tabs is a repository with an installer behind it.
What lives here is a line of configuration this window can write itself,
as the user, and take back the same way."""

import configparser
import os
import re
import subprocess

from gi.repository import Adw, Gio
from .. import faults, original, process
from ..components import PHOSH, folder_dock_plugin
from ..i18n import _

# key, title, icon - the same three a component carries for its tab.
TAB = ("other", "Phosh", "video-display-symbolic")

# The block goes between two markers, so taking it out again removes exactly
# what was put in and nothing somebody wrote around it.
BEGIN = "/* misc-de: hide phosh search - begin */"
END = "/* misc-de: hide phosh search - end */"

# GTK 3 has no display: none. What phosh's search bar can be made is nothing
# to see and nothing to measure: no height, no margin, no border, and text too
# small to push the entry open.
HIDE_SEARCH = """.phosh-search-bar-box,
.phosh-search-bar {
  min-height: 0; margin: 0; padding: 0;
  border: none; box-shadow: none; background: none;
  font-size: 1px; opacity: 0;
}"""

# The same rule written by hand before this switch existed, with a header
# line and no end marker. Recognised so that switching off removes it too,
# instead of reporting "off" over a search bar that stays hidden.
LEGACY = re.compile(
    r"/\* Hide phosh app grid search \(misc-de\) \*/\n"
    r"\.phosh-search-bar-box,\s*\.phosh-search-bar\s*\{[^}]*\}\n?")


def gtk_css_path():
    """Read at call time, not at import: the tests point XDG_CONFIG_HOME
    somewhere harmless, and they do it after the module is loaded."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "gtk-3.0", "gtk.css")


def _read(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""


def _strip(text):
    text = LEGACY.sub("", text)
    block = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END) + r"\n?",
                       re.S)
    return block.sub("", text)


def search_hidden(path=None):
    text = _read(path or gtk_css_path())
    return (BEGIN in text and END in text) or bool(LEGACY.search(text))


def set_search_hidden(hidden, path=None):
    """Write the block in or take it out; everything else stays as it was.

    Before the block goes in for the first time, the file as it was is
    recorded (miscde/original.py): its text, or that there was none, and
    which directories had to be made for it. Off puts exactly that back
    while the file, with our block out, is still that original - the
    newline added after a last line that had none goes too, and so does a
    gtk-3.0 directory we made. Changed by somebody since: only our block
    comes out, and the rest is theirs.

    Without a record (the block was written by a version before records,
    or by hand) off takes the block out as it always did, and a file that
    held nothing else is removed - somebody's own gtk.css never is.
    """
    path = path or gtk_css_path()
    old = _read(path)
    new = _strip(old)
    if hidden and not search_hidden(path):
        # block: uninstall.sh takes only this out of a file changed since.
        original.remember_file(path, block=[BEGIN, END])
    if not hidden:
        record = original.load(original.file_ident(path))
        if record is not None and original.block_back(record, new):
            original.put_back_file(record)
            return
    if hidden:
        if new and not new.endswith("\n"):
            new += "\n"
        new += BEGIN + "\n" + HIDE_SEARCH + "\n" + END + "\n"
    if new == old:
        return
    if not new.strip():
        if os.path.exists(path):
            os.remove(path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".misc-de.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(new)
    os.replace(tmp, path)


# --- folders at the bottom -------------------------------------------------
#
# A phosh plugin in furios_phosh/folder-dock does the work; this only
# puts its name into the list of status icons phosh loads, or takes it out.
# phosh follows that list while it runs, so both take effect at once - except
# right after the plugin was installed, because the plugin directory is only
# scanned when the shell starts.
DOCK_PLUGIN = "furios-folder-dock"
PLUGINS_SCHEMA = "mobi.phosh.shell.plugins"
PLUGINS_KEY = "status-icons"
# What the plugin leaves behind when the shell did not survive its last
# attempt; while it is there the plugin does nothing. Switching on removes it.
DOCK_GUARD = "furios-folder-dock.armed"


def dock_installed():
    return folder_dock_plugin() is not None


def plugin_settings():
    """None where the schema is missing: Gio.Settings on an unknown schema
    aborts the whole process instead of raising."""
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(PLUGINS_SCHEMA, True) is None:
        return None
    return Gio.Settings.new(PLUGINS_SCHEMA)


def dock_enabled(settings):
    return settings is not None and DOCK_PLUGIN in settings.get_strv(PLUGINS_KEY)


def dock_guard_path():
    base = os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache")
    return os.path.join(base, DOCK_GUARD)


def _user_value(settings):
    """The list in the user's dconf, or None while the key is unset and the
    schema's default applies."""
    get = getattr(settings, "get_user_value", None)
    value = get(PLUGINS_KEY) if get is not None else None
    return None if value is None else list(value.unpack())


def set_dock_enabled(on, settings):
    """Add or remove our name only; every other plugin in the list stays
    where it is.

    Before our name goes in for the first time, the key is recorded as it
    was - unset, or set to which list - unless furios_phosh's installer has
    recorded it already (original.phosh_plugin_record), which is older. Off with our name gone again and the
    list what it was then puts that back: reset where it was unset, so the
    key follows what a later phosh ships instead of being pinned to today's
    default. Another plugin that put itself in since makes the list a
    different one; then only our name comes out. Off with our name not in
    the list writes nothing at all.

    The crash mark is the plugin's own, and removing it is what "on" means
    (try again); it is not put back, because it would switch the plugin off.
    """
    current = settings.get_strv(PLUGINS_KEY)
    names = [n for n in current if n != DOCK_PLUGIN]
    if on:
        # furios_phosh's installer has usually written the list down
        # already, before the plugin existed; then that is the original.
        if DOCK_PLUGIN not in current and original.phosh_plugin_record() is None:
            original.remember_setting(PLUGINS_SCHEMA, PLUGINS_KEY,
                                      _user_value(settings), list(current))
        try:
            os.remove(dock_guard_path())
        except FileNotFoundError:
            pass
        names.append(DOCK_PLUGIN)
        settings.set_strv(PLUGINS_KEY, names)
        return
    if DOCK_PLUGIN not in current:
        return
    ident = original.setting_ident(PLUGINS_SCHEMA, PLUGINS_KEY)
    record = original.load(ident) or original.phosh_plugin_record()
    action, value = original.setting_back(record, names)
    if action == "reset":
        settings.reset(PLUGINS_KEY)
    else:
        settings.set_strv(PLUGINS_KEY, value)
    if record is not None and names == record.get("value"):
        original.forget(ident)


# The plugin's settings: every folder in a single row that scrolls sideways,
# and the apps in the overview without their names. A key file the plugin
# watches while the dock stands, so both take effect at once. Off is no key,
# and no key at all is no file - phosh's own look is the plugin's default.
DOCK_CONFIG = "furios-folder-dock.conf"
DOCK_GROUP = "dock"
ONE_ROW = "one-row"
HIDE_LABELS = "hide-labels"


def dock_config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, DOCK_CONFIG)


def _dock_settings(path):
    """The keys that are on, in the file's order; a broken file has none."""
    parser = configparser.ConfigParser()
    try:
        parser.read(path, encoding="utf-8")
        return [k for k in (ONE_ROW, HIDE_LABELS)
                if parser.getboolean(DOCK_GROUP, k, fallback=False)]
    except (configparser.Error, ValueError):
        return []


def dock_setting(key, path=None):
    return key in _dock_settings(path or dock_config_path())


def _dock_text(keys):
    """The whole file as this switch wrote it before 30.9.2026."""
    return "[%s]\n" % DOCK_GROUP + "".join("%s=true\n" % k for k in keys)


# Every file the switches ever wrote. One of these found without a record was
# made by an older version of this app, so it is not an original to keep.
DOCK_OWN_FORMS = {_dock_text(k) for k in
                  ([ONE_ROW], [HIDE_LABELS], [ONE_ROW, HIDE_LABELS])}


def _dock_edit(text, keys):
    """text with our two keys in [dock] set to exactly keys - every other
    line, group and comment kept where it was. None when nothing but an
    empty [dock] would be left: no key at all is no file."""
    out, group, seen = [], None, False
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("[") and s.endswith("]"):
            group = s[1:-1].strip()
            out.append(line)
            if group == DOCK_GROUP and not seen:
                seen = True
                out.extend("%s=true" % k for k in keys)
            continue
        if (group == DOCK_GROUP
                and s.split("=", 1)[0].strip() in (ONE_ROW, HIDE_LABELS)):
            continue
        out.append(line)
    if not seen and keys:
        out.append("[%s]" % DOCK_GROUP)
        out.extend("%s=true" % k for k in keys)
    if not any(l.strip() and l.strip() != "[%s]" % DOCK_GROUP for l in out):
        return None
    return "\n".join(out) + "\n"


def set_dock_setting(key, on, path=None):
    """One key on or off, the other left as it is, in the form GKeyFile
    reads - and nothing else in the file touched.

    The file is shared with the plugin (furios_phosh), so what was there
    before the first change is recorded first. Once both keys are back to
    what that original said, it is put back as it was, byte for byte, or
    taken away when there was none. A file found in exactly a form this
    switch used to write is ours from an older version: no record for that
    one, and off works as it did."""
    path = path or dock_config_path()
    text = original.read_text(path)
    keys = [k for k in _dock_settings(path) if k != key]
    if on:
        keys.append(key)
    keys = [k for k in (ONE_ROW, HIDE_LABELS) if k in keys]
    new = _dock_edit(text, keys)
    if new == text:
        return
    if text not in DOCK_OWN_FORMS:
        original.remember_file(path)
    record = original.load(original.file_ident(path))
    if record is not None and text in (record.get("content"),
                                       record.get("written", False)):
        before = [k for k in (ONE_ROW, HIDE_LABELS)
                  if k in _dock_keys_of(record.get("content"))]
        if keys == before:
            original.put_back_file(record)
            return
    if new is None:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".misc-de.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(new)
        os.replace(tmp, path)
    original.wrote_file(path)


def _dock_keys_of(text):
    """The keys that are on in a text rather than a file."""
    parser = configparser.ConfigParser()
    try:
        parser.read_string(text or "")
        return [k for k in (ONE_ROW, HIDE_LABELS)
                if parser.getboolean(DOCK_GROUP, k, fallback=False)]
    except (configparser.Error, ValueError):
        return []


def dock_one_row(path=None):
    return dock_setting(ONE_ROW, path)


def set_dock_one_row(on, path=None):
    set_dock_setting(ONE_ROW, on, path)


# --- keyring prompt ----------------------------------------------------------
#
# At boot gnome-keyring asks for a prompter before phosh has registered its
# own, so D-Bus activates the bare GTK3 gcr-prompter instead: light, whatever
# the theme, and unlike anything else on the phone. A service file of the same
# name in the user's data dir wins over the one in /usr and starts a shim that
# waits for phosh to take the name. The session bus watches that directory, so
# both directions count from the next prompt on.
PROMPTER_NAME = "org.gnome.keyring.SystemPrompter"
PROMPTER_MARK = "# misc-de: keyring prompter shim"
PROMPTER_SHIM = PROMPTER_MARK + """
# D-Bus activation shim for org.gnome.keyring.SystemPrompter.
# At boot gnome-keyring asks for a prompter before phosh has registered its
# own (themed, full-screen) one, so D-Bus started the bare GTK3 gcr-prompter.
# Wait for phosh to claim the name; dbus-daemon completes the activation as
# soon as anyone owns it. Only fall back to gcr-prompter, themed to match.
name=org.gnome.keyring.SystemPrompter
i=0
while [ $i -lt 90 ]; do
    busctl --user status "$name" >/dev/null 2>&1 && exit 0
    sleep 1
    i=$((i + 1))
done
case "$(gsettings get org.gnome.desktop.interface color-scheme 2>/dev/null)" in
    *dark*) export GTK_THEME=adw-gtk3-dark ;;
esac
exec /usr/libexec/gcr-prompter
"""
# The first line of the shim written by hand before this switch existed.
PROMPTER_LEGACY = "# D-Bus activation shim for org.gnome.keyring.SystemPrompter."


def _data_home():
    return (os.environ.get("XDG_DATA_HOME")
            or os.path.expanduser("~/.local/share"))


def prompter_service_path():
    return os.path.join(_data_home(), "dbus-1", "services",
                        PROMPTER_NAME + ".service")


def prompter_shim_path():
    """~/.local/libexec next to ~/.local/share, where the hand-made one went."""
    return os.path.join(os.path.dirname(_data_home()), "libexec",
                        "keyring-prompter-wait")


def _is_our_shim(path):
    text = _read(path)
    return PROMPTER_MARK in text or PROMPTER_LEGACY in text


def prompter_fixed(service=None, shim=None):
    """On only while the service file starts our shim: a service file of
    somebody else's is not this fix, and not ours to remove."""
    service = service or prompter_service_path()
    shim = shim or prompter_shim_path()
    return ("Exec=%s\n" % shim) in _read(service) and _is_our_shim(shim)


def set_prompter_fixed(on, service=None, shim=None):
    """On writes the shim and the service file that starts it; off takes
    both back.

    Both paths can hold something before we come: a service file of the
    same name somebody wrote, a shim of theirs. So each is recorded before
    the first write (unless it is ours already, from a version before
    records), and off puts back exactly what was there - their file, or no
    file, and the directories we made. A file changed after we wrote it is
    left as it is and named. Without a record, off removes what is ours by
    its content, as before."""
    service = service or prompter_service_path()
    shim = shim or prompter_shim_path()
    service_text = "[D-BUS Service]\nName=%s\nExec=%s\n" % (PROMPTER_NAME, shim)
    if on:
        if not _is_our_shim(shim):
            original.remember_file(shim)
        if ("Exec=%s\n" % shim) not in _read(service):
            original.remember_file(service)
        for path, text, mode in (
                (shim, "#!/bin/sh\n" + PROMPTER_SHIM, 0o755),
                (service, service_text, 0o644)):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".misc-de.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.chmod(tmp, mode)
            os.replace(tmp, path)
            original.wrote_file(path)
        return
    # The service file first: without it nothing starts the shim any more.
    changed = []
    state = original.restore_file(service)
    if state is None and ("Exec=%s\n" % shim) in _read(service):
        os.remove(service)
    elif state == "changed":
        changed.append(service)
    state = original.restore_file(shim)
    if state is None and _is_our_shim(shim):
        os.remove(shim)
    elif state == "changed":
        changed.append(shim)
    if changed:
        raise original.ChangedSince(changed)


# --- automatic brightness ------------------------------------------------------
#
# phosh dims and brightens by the light sensor when gsd's ambient-enabled is
# on and net.hadess.SensorProxy is on the system bus. The service behind
# that name (iio-sensor-proxy, which hadess-sensorfw-proxy's drop-in points
# at sensorfwd) is enabled by a symlink that package ships as a plain file;
# once anything disables it, nothing brings it back - no [Install] in the
# base unit, no D-Bus activation file, and the udev rule never matches
# (sensors come through sensorfw, not IIO). Found that way on this phone,
# 1.10.2026; the sensor itself is fine (400 lux indoors). FuriOS ships the
# key false. Two halves, then: the system unit, through sudo, and the key.
SENSOR_UNIT = "iio-sensor-proxy.service"
POWER_SCHEMA = "org.gnome.settings-daemon.plugins.power"
AMBIENT_KEY = "ambient-enabled"
BRIGHTNESS_IDENT = "auto-brightness"


def power_settings():
    """None where the schema is missing, as with plugin_settings."""
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(POWER_SCHEMA, True) is None:
        return None
    return Gio.Settings.new(POWER_SCHEMA)


def _systemctl_says(verb, unit=SENSOR_UNIT):
    try:
        return subprocess.run(["systemctl", verb, "--quiet", unit],
                              timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def sensor_state():
    """(enabled, active) of the system unit - readable without root."""
    return _systemctl_says("is-enabled"), _systemctl_says("is-active")


def _ambient_user_value(settings):
    value = settings.get_user_value(AMBIENT_KEY)
    return None if value is None else bool(value.unpack())


def brightness_on(settings, state):
    """On only while both halves are: the key alone moves nothing without a
    sensor on the bus, and the sensor alone is not automatic brightness."""
    return (settings is not None and settings.get_boolean(AMBIENT_KEY)
            and all(state))


def remember_brightness(settings, state):
    """The unit and the key as they were, before the first change."""
    if original.load(BRIGHTNESS_IDENT) is not None or brightness_on(settings, state):
        return
    original.save(BRIGHTNESS_IDENT, {
        "kind": BRIGHTNESS_IDENT, "unit": SENSOR_UNIT,
        "enabled": bool(state[0]), "active": bool(state[1]),
        "schema": POWER_SCHEMA, "key": AMBIENT_KEY,
        "user_value": _ambient_user_value(settings)})


def sensor_argv(on, state, record=None, secret=None):
    """The sudo command that brings the unit where it has to be, or None
    when it is there already - then nobody is asked for a password.

    Off goes back to what the record says; without one the unit is left
    as it is - FuriOS means it enabled, so "off" is no reason to guess."""
    enabled, active = state
    if on:
        if enabled and active:
            return None
        verb = ["enable", "--now"]
    else:
        if record is None:
            return None
        want_enabled = bool(record.get("enabled"))
        want_active = bool(record.get("active"))
        if enabled == want_enabled and active == want_active:
            return None
        if want_enabled:
            verb = ["enable", "--now"] if want_active else ["enable"]
        else:
            verb = ["disable"] + ([] if want_active else ["--now"])
    front = (["sudo", "-S", "-p", ""] if secret is not None
             else ["sudo", "-n"])
    return front + ["systemctl"] + verb + [SENSOR_UNIT]


def set_ambient(on, settings, record=None):
    """On sets the key; off puts back what the record holds - unset where
    it was unset, so a later FuriOS default applies again."""
    if on:
        settings.set_boolean(AMBIENT_KEY, True)
    elif record is not None and record.get("user_value") is None:
        settings.reset(AMBIENT_KEY)
    else:
        settings.set_boolean(AMBIENT_KEY, bool(record and record.get("user_value")))


# --- apps that start at once -------------------------------------------------
#
# FuriOS names xdg-desktop-portal-wlr for screenshots and screen casts, and on
# this phone it cannot start: phoc runs on hwcomposer without the screencopy
# protocols. It gives up at once, and xdg-desktop-portal then spends 55-60 s
# in D-Bus timeouts waiting for it - and every GTK4 app hangs at start on the
# portal's light/dark question in that time. Tapped apps do not open for a
# minute after boot.
#
# Naming "none" for those two takes wlr out; nothing is lost, because it was
# the only backend offering them and it never ran. "none" and not "gtk;": the
# UseIn= fallback only stops at "none", "gtk;" merely halves the wait.
#
# A file in the user's config dir is found before the one FuriOS ships, and
# replaces it whole - so it is the shipped file, as it is when switched on,
# with just those two lines changed. Read at the portal's start, which is at
# login.
PORTALS_SHIPPED = "/usr/share/xdg-desktop-portal/phosh-portals.conf"
PORTALS_MARK = "# misc-de: apps start without waiting for the wlr portal"
PORTALS_NONE = ("org.freedesktop.impl.portal.ScreenCast",
                "org.freedesktop.impl.portal.Screenshot")


def portals_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "xdg-desktop-portal", "phosh-portals.conf")


def portals_fixed(path=None):
    return PORTALS_MARK in _read(path or portals_path())


def portals_text(shipped):
    """The shipped file with our two keys at none - replaced where they are,
    added to [preferred] where a later FuriOS dropped them."""
    lines, seen = [], set()
    for line in shipped.splitlines():
        key = line.split("=", 1)[0].strip()
        if key in PORTALS_NONE:
            line = key + "=none;"
            seen.add(key)
        lines.append(line)
    missing = [k + "=none;" for k in PORTALS_NONE if k not in seen]
    if missing:
        if "[preferred]" not in lines:
            lines.append("[preferred]")
        at = lines.index("[preferred]") + 1
        lines[at:at] = missing
    return PORTALS_MARK + "\n" + "\n".join(lines) + "\n"


def set_portals_fixed(on, path=None, shipped=PORTALS_SHIPPED):
    """On writes the file, off removes it - but only ours: a portals.conf
    somebody wrote is neither overwritten nor taken away, not even an empty
    one.

    That there was no file, and which directories had to be made, is
    recorded before the first write; off puts exactly that back - an
    xdg-desktop-portal directory that was there before stays, even empty -
    unless the file was changed after we wrote it, which is then left
    alone and named. Without a record (written by an older version), off
    removes our file and the directory while it is empty, as before."""
    path = path or portals_path()
    current = original.read_text(path)
    if current is not None and PORTALS_MARK not in current:
        raise OSError("%s is not ours - left as it is" % path)
    if not on:
        state = original.restore_file(path)
        if state == "changed":
            raise original.ChangedSince([path])
        if state is None and current is not None:
            os.remove(path)
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
        return
    if current is None:
        original.remember_file(path)
    text = portals_text(_read(shipped))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".misc-de.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)
    original.wrote_file(path)


class OtherPage:
    def rebuild_other_page(self):
        """The folder dock was just installed: build the tab again, so its
        rows are live. It is the last tab, so it goes out and back in
        without disturbing the others."""
        self.comp_rows.pop(PHOSH["tool"], None)
        self.stack.remove(self.pages[TAB[0]])
        self.pages[TAB[0]] = self.build_other_page()
        self.stack.add_titled_with_icon(self.pages[TAB[0]], *TAB)
        self.stack.set_visible_child_name(TAB[0])
        # phosh scans its plugin directory only when it starts.
        self.dock_row.set_subtitle(_("Installed · takes effect after the "
                                     "next reboot"))

    def build_other_page(self):
        page = Adw.PreferencesPage()
        grp = Adw.PreferencesGroup(title=_("Home screen"))
        # The subtitle says when it takes effect, because nothing happens
        # when the switch moves: phosh reads gtk.css once, at start. Restarting
        # it from here is not an option - its unit takes the session down
        # with it when it fails.
        self.search_row = Adw.SwitchRow(
            title=_("Hide the search field"),
            subtitle=_("In the app overview · after the next login"))
        self._loading = True
        self.search_row.set_active(search_hidden())
        self._loading = False
        self.search_row.connect("notify::active", self.on_search_hidden)
        grp.add(self.search_row)
        page.add(grp)

        # Everything the folder-dock plugin does, in a box of its own: these
        # rows live or die with the plugin, the search field above does not.
        grp = Adw.PreferencesGroup(title=_("Folder dock"))
        # Off and closed without the plugin: a switch that only writes a
        # name phosh cannot find would look like it did something.
        self.dock_settings = plugin_settings()
        self.dock_row = Adw.SwitchRow(title=_("Folders at the bottom"))
        if not dock_installed() or self.dock_settings is None:
            self.dock_row.set_subtitle(
                _("Needs the folder-dock plugin from furios_phosh"))
            self.dock_row.set_sensitive(False)
        else:
            self.dock_row.set_subtitle(
                _("Held in a bar at the bottom edge of the app overview"))
            self._loading = True
            self.dock_row.set_active(dock_enabled(self.dock_settings))
            self._loading = False
        self.dock_row.connect("notify::active", self.on_dock_enabled)
        grp.add(self.dock_row)

        self.row_row = Adw.SwitchRow(
            title=_("Folders in one row"),
            subtitle=_("Scrolls sideways instead of growing upwards"))
        self._loading = True
        self.row_row.set_active(dock_one_row())
        self._loading = False
        self.row_row.set_sensitive(self.dock_row.get_active())
        self.row_row.connect("notify::active", self.on_dock_one_row)
        grp.add(self.row_row)

        # The plugin does this too - it is the one thing in the shell that
        # reaches the app buttons - so it needs the dock switched on.
        self.labels_row = Adw.SwitchRow(
            title=_("Hide app names"),
            subtitle=_("Icons only, like the favorites · folders keep theirs"))
        self._loading = True
        self.labels_row.set_active(dock_setting(HIDE_LABELS))
        self._loading = False
        self.labels_row.set_sensitive(self.dock_row.get_active())
        self.labels_row.connect("notify::active", self.on_hide_labels)
        grp.add(self.labels_row)
        if not dock_installed():
            # The offer, where the rows it brings to life are. The dock row
            # carries the progress, the way the "not installed" tabs' state
            # row does.
            btn = self.pill_button(_("Install the folder dock"))
            btn.connect("clicked",
                        lambda _b: self.ask_component(PHOSH, "install"))
            grp.add(btn)
            self.comp_rows[PHOSH["tool"]] = {"state": self.dock_row,
                                             "button": btn}
        page.add(grp)

        grp = Adw.PreferencesGroup(title=_("Display"))
        self.brightness_group = grp
        self.brightness_settings = power_settings()
        self.brightness_row = Adw.SwitchRow(
            title=_("Automatic brightness"),
            subtitle=_("Follows the light sensor · full brightness outdoors"))
        self.brightness_row.connect("notify::active", self.on_brightness)
        grp.add(self.brightness_row)
        page.add(grp)
        self.sync_brightness()

        grp = Adw.PreferencesGroup(title=_("Unlock"))
        self.offer("prompter", grp, prompter_fixed(),
                   faults.prompter_falls_back())
        self.prompter_row = Adw.SwitchRow(
            title=_("Keyring prompt in phosh style"),
            subtitle=_("Instead of the light window after a restart"))
        self._loading = True
        self.prompter_row.set_active(prompter_fixed())
        self._loading = False
        self.prompter_row.connect("notify::active", self.on_prompter_fixed)
        grp.add(self.prompter_row)
        page.add(grp)

        grp = Adw.PreferencesGroup(title=_("Apps"))
        self.offer("portals", grp, portals_fixed(), faults.wlr_portal_waits())
        self.portals_row = Adw.SwitchRow(
            title=_("Apps open right after boot"),
            subtitle=_("Otherwise apps wait up to a minute for the "
                       "light/dark theme · after the next restart"))
        self._loading = True
        self.portals_row.set_active(portals_fixed())
        self._loading = False
        self.portals_row.connect("notify::active", self.on_portals_fixed)
        grp.add(self.portals_row)
        page.add(grp)
        return page

    def sync_brightness(self):
        """Read back from the unit and the key - never what the finger left
        the switch at."""
        row = self.brightness_row
        self._loading = True
        if self.brightness_settings is None:
            row.set_active(False)
            row.set_sensitive(False)
            row.set_subtitle(_("not available on this device"))
            self.offer("brightness", self.brightness_group, False, False)
        else:
            state = sensor_state()
            on = brightness_on(self.brightness_settings, state)
            row.set_active(on)
            row.set_sensitive(True)
            # Ours: switched on here, over a unit that had to be brought
            # back. The fault: that unit off. With the unit as FuriOS ships
            # it, the key alone is the shell's own setting, not a repair.
            self.offer("brightness", self.brightness_group,
                       on and original.load(BRIGHTNESS_IDENT) is not None,
                       faults.sensor_unit_off(state))
        self._loading = False

    def on_brightness(self, row, _pspec):
        if self._loading or self.brightness_settings is None:
            return
        self.apply_brightness(row.get_active())

    def apply_brightness(self, wanted, secret=None):
        state = sensor_state()
        if wanted:
            try:
                remember_brightness(self.brightness_settings, state)
            except OSError:
                pass
        record = original.load(BRIGHTNESS_IDENT)
        argv = sensor_argv(wanted, state, record, secret)
        if argv is None:
            self.on_brightness_done(True, "", wanted, record)
            return
        self.brightness_row.set_sensitive(False)
        process.run_async(
            argv,
            lambda ok, out: self.on_brightness_done(ok, out, wanted, record),
            stdin=None if secret is None else (secret + "\n"))

    def on_brightness_done(self, ok, out, wanted, record):
        self.brightness_row.set_sensitive(True)
        low = (out or "").lower()
        if not ok and ("password is required" in low or "askpass" in low):
            self.ask_brightness_password(wanted)
            return
        if not ok:
            self.sync_brightness()
            self.report(out or _("No output."))
            return
        # The key only once the sensor is there (on), or is gone (off).
        set_ambient(wanted, self.brightness_settings, record)
        if not wanted and record is not None:
            original.forget(BRIGHTNESS_IDENT)
        self.sync_brightness()

    def ask_brightness_password(self, wanted):
        entry = Adw.PasswordEntryRow(title=_("Your password (for sudo)"))
        group = Adw.PreferencesGroup()
        group.add(entry)
        dlg = Adw.AlertDialog(
            heading=_("Automatic brightness"),
            body=_("This switches the light sensor service, so sudo asks "
                   "for a password. It goes to sudo through a pipe and "
                   "nowhere else."))
        dlg.set_extra_child(group)
        dlg.add_response("go", _("Change it"))
        dlg.add_response("cancel", _("Cancel"))
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        self._brightness_pending = (wanted, entry)
        dlg.connect("response", self.on_brightness_password)
        dlg.present(self)

    def on_brightness_password(self, _dlg, response):
        wanted, entry = self._brightness_pending
        self._brightness_pending = (None, None)
        secret = entry.get_text() if entry is not None else None
        if entry is not None:
            entry.set_text("")
        if response != "go" or wanted is None:
            self.sync_brightness()
            return
        self.apply_brightness(wanted, secret)

    def on_portals_fixed(self, row, _pspec):
        if self._loading:
            return
        want = row.get_active()
        try:
            set_portals_fixed(want)
        except original.ChangedSince as e:
            self._report_changed(row, want, e)
            return
        except OSError as e:
            self._loading = True
            row.set_active(not want)
            self._loading = False
            self.report(_("Could not write %s:\n%s") % (portals_path(), e))
            return
        self.toast(_("Takes effect after the next login"))

    def _report_changed(self, row, want, error):
        """Off found our file changed by somebody since: it stays, and so
        does the switch - it is still on, and saying otherwise would be the
        switch claiming what it did not do."""
        self._loading = True
        row.set_active(not want)
        self._loading = False
        self.report(_("Changed since misc-de wrote it, so left as it is:\n"
                      "{paths}").format(paths="\n".join(error.paths)))

    def on_prompter_fixed(self, row, _pspec):
        if self._loading:
            return
        want = row.get_active()
        try:
            set_prompter_fixed(want)
        except original.ChangedSince as e:
            self._report_changed(row, want, e)
        except OSError as e:
            self._loading = True
            row.set_active(not want)
            self._loading = False
            self.report(_("Could not write %s:\n%s")
                        % (prompter_service_path(), e))

    def on_dock_one_row(self, row, _pspec):
        self._set_dock_key(row, ONE_ROW)

    def on_hide_labels(self, row, _pspec):
        self._set_dock_key(row, HIDE_LABELS)

    def _set_dock_key(self, row, key):
        if self._loading:
            return
        want = row.get_active()
        try:
            set_dock_setting(key, want)
        except OSError as e:
            self._loading = True
            row.set_active(not want)
            self._loading = False
            self.report(_("Could not write %s:\n%s") % (dock_config_path(), e))

    def on_dock_enabled(self, row, _pspec):
        for name in ("row_row", "labels_row"):
            if hasattr(self, name):
                getattr(self, name).set_sensitive(row.get_active())
        if self._loading or self.dock_settings is None:
            return
        set_dock_enabled(row.get_active(), self.dock_settings)

    def on_search_hidden(self, row, _pspec):
        if self._loading:
            return
        want = row.get_active()
        try:
            set_search_hidden(want)
        except OSError as e:
            self._loading = True
            row.set_active(not want)
            self._loading = False
            self.report(_("Could not write %s:\n%s") % (gtk_css_path(), e))
            return
        self.toast(_("Takes effect after the next login"))
