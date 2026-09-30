# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Other page: small things with no tool of their own.

Everything on the other tabs is a repository with an installer behind it.
What lives here is a line of configuration this window can write itself,
as the user, and take back the same way."""

import configparser
import os
import re

from gi.repository import Adw, Gio
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

    A file that ends up empty is removed rather than left behind, but only
    when it held nothing except our block - somebody's own gtk.css is never
    deleted.
    """
    path = path or gtk_css_path()
    old = _read(path)
    new = _strip(old)
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


def set_dock_enabled(on, settings):
    """Add or remove our name only; every other plugin in the list stays
    where it is."""
    names = [n for n in settings.get_strv(PLUGINS_KEY) if n != DOCK_PLUGIN]
    if on:
        try:
            os.remove(dock_guard_path())
        except FileNotFoundError:
            pass
        names.append(DOCK_PLUGIN)
    settings.set_strv(PLUGINS_KEY, names)


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


def set_dock_setting(key, on, path=None):
    """One key on or off, the other left as it is. Written by hand in the
    form GKeyFile reads, one line per key that is on."""
    path = path or dock_config_path()
    keys = [k for k in _dock_settings(path) if k != key]
    if on:
        keys.append(key)
    keys = [k for k in (ONE_ROW, HIDE_LABELS) if k in keys]
    if not keys:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".misc-de.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("[%s]\n" % DOCK_GROUP + "".join("%s=true\n" % k for k in keys))
    os.replace(tmp, path)


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
    service = service or prompter_service_path()
    shim = shim or prompter_shim_path()
    if on:
        for path, text, mode in (
                (shim, "#!/bin/sh\n" + PROMPTER_SHIM, 0o755),
                (service, "[D-BUS Service]\nName=%s\nExec=%s\n"
                 % (PROMPTER_NAME, shim), 0o644)):
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".misc-de.tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                f.write(text)
            os.chmod(tmp, mode)
            os.replace(tmp, path)
        return
    # The service file first: without it nothing starts the shim any more.
    if ("Exec=%s\n" % shim) in _read(service):
        os.remove(service)
    if _is_our_shim(shim):
        os.remove(shim)


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
    somebody wrote is neither overwritten nor taken away."""
    path = path or portals_path()
    current = _read(path)
    if current and PORTALS_MARK not in current:
        raise OSError("%s is not ours - left as it is" % path)
    if not on:
        if current:
            os.remove(path)
            try:
                os.rmdir(os.path.dirname(path))
            except OSError:
                pass
        return
    text = portals_text(_read(shipped))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".misc-de.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


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

        grp = Adw.PreferencesGroup(title=_("Unlock"))
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
        self.portals_row = Adw.SwitchRow(
            title=_("Apps open right after boot"),
            subtitle=_("Instead of a minute's wait for a screen-capture "
                       "service that cannot start here · after the next login"))
        self._loading = True
        self.portals_row.set_active(portals_fixed())
        self._loading = False
        self.portals_row.connect("notify::active", self.on_portals_fixed)
        grp.add(self.portals_row)
        page.add(grp)
        return page

    def on_portals_fixed(self, row, _pspec):
        if self._loading:
            return
        want = row.get_active()
        try:
            set_portals_fixed(want)
        except OSError as e:
            self._loading = True
            row.set_active(not want)
            self._loading = False
            self.report(_("Could not write %s:\n%s") % (portals_path(), e))
            return
        self.toast(_("Takes effect after the next login"))

    def on_prompter_fixed(self, row, _pspec):
        if self._loading:
            return
        want = row.get_active()
        try:
            set_prompter_fixed(want)
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
