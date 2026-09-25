# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Other page: small things with no tool of their own.

Everything on the other tabs is a repository with an installer behind it.
What lives here is a line of configuration this window can write itself,
as the user, and take back the same way."""

import configparser
import glob
import os
import re

from gi.repository import Adw, Gio

# key, title, icon - the same three a component carries for its tab.
TAB = ("other", "Other", "preferences-other-symbolic")

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
# A phosh plugin in furios_misc/phosh-folder-dock does the work; this only
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
    return bool(glob.glob("/usr/lib/*/phosh/plugins/%s.plugin" % DOCK_PLUGIN))


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


# The plugin's one setting: every folder in a single row that scrolls
# sideways. A key file the plugin watches while the dock stands, so it takes
# effect at once. Off is no file at all - rows are the plugin's default.
DOCK_CONFIG = "furios-folder-dock.conf"


def dock_config_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, DOCK_CONFIG)


def dock_one_row(path=None):
    parser = configparser.ConfigParser()
    try:
        parser.read(path or dock_config_path(), encoding="utf-8")
        return parser.getboolean("dock", "one-row", fallback=False)
    except (configparser.Error, ValueError):
        return False


def set_dock_one_row(on, path=None):
    path = path or dock_config_path()
    if not on:
        try:
            os.remove(path)
        except FileNotFoundError:
            pass
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".misc-de.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("[dock]\none-row=true\n")
    os.replace(tmp, path)


class OtherPage:
    def build_other_page(self):
        page = Adw.PreferencesPage()
        grp = Adw.PreferencesGroup(title="Home screen")
        # The subtitle says when it takes effect, because nothing happens
        # when the switch moves: phosh reads gtk.css once, at start. Restarting
        # it from here is not an option - its unit takes the session down
        # with it when it fails.
        self.search_row = Adw.SwitchRow(
            title="Hide the search field",
            subtitle="In the app overview · after the next login")
        self._loading = True
        self.search_row.set_active(search_hidden())
        self._loading = False
        self.search_row.connect("notify::active", self.on_search_hidden)
        grp.add(self.search_row)

        # Off and closed without the plugin: a switch that only writes a
        # name phosh cannot find would look like it did something.
        self.dock_settings = plugin_settings()
        self.dock_row = Adw.SwitchRow(title="Folders at the bottom")
        if not dock_installed() or self.dock_settings is None:
            self.dock_row.set_subtitle(
                "Needs the phosh-folder-dock plugin from furios_misc")
            self.dock_row.set_sensitive(False)
        else:
            self.dock_row.set_subtitle(
                "Held in a bar at the bottom edge of the app overview")
            self._loading = True
            self.dock_row.set_active(dock_enabled(self.dock_settings))
            self._loading = False
        self.dock_row.connect("notify::active", self.on_dock_enabled)
        grp.add(self.dock_row)

        self.row_row = Adw.SwitchRow(
            title="Folders in one row",
            subtitle="Scrolls sideways instead of growing upwards")
        self._loading = True
        self.row_row.set_active(dock_one_row())
        self._loading = False
        self.row_row.set_sensitive(self.dock_row.get_active())
        self.row_row.connect("notify::active", self.on_dock_one_row)
        grp.add(self.row_row)
        page.add(grp)
        return page

    def on_dock_one_row(self, row, _pspec):
        if self._loading:
            return
        want = row.get_active()
        try:
            set_dock_one_row(want)
        except OSError as e:
            self._loading = True
            row.set_active(not want)
            self._loading = False
            self.report("Could not write %s:\n%s" % (dock_config_path(), e))

    def on_dock_enabled(self, row, _pspec):
        if hasattr(self, "row_row"):
            self.row_row.set_sensitive(row.get_active())
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
            self.report("Could not write %s:\n%s" % (gtk_css_path(), e))
            return
        self.toast("Takes effect after the next login")
