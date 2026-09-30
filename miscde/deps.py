# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""What the window needs before it can open at all.

Checked by the launcher BEFORE the package is imported, because the package
imports GTK 4 and libadwaita on its first lines - with one of them missing,
the window died with a traceback nobody sees when it is started from the
app grid. So this file imports nothing of the package: the launcher loads it
by path, and it reads the language and the German table the same way.

What it cannot open, it says in whatever is left: a GTK 4 window without
libadwaita, a GTK 3 dialog, a notification, and stderr always.
"""

import importlib.util
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))

# (what is imported, its version, the package that brings it)
NEEDED = (("Gtk", "4.0", "gir1.2-gtk-4.0"),
          ("Adw", "1", "gir1.2-adw-1"))


def _can_import(namespace, version):
    import gi
    try:
        gi.require_version(namespace, version)
        importlib.import_module("gi.repository." + namespace)
    except (ValueError, ImportError):
        return False
    return True


def missing(can_import=None):
    """The Debian packages the window needs and this phone does not have."""
    try:
        import gi  # noqa: F401
    except ImportError:
        return ["python3-gi"] + [pkg for _n, _v, pkg in NEEDED]
    can_import = can_import or _can_import
    return [pkg for name, version, pkg in NEEDED if not can_import(name, version)]


def _language():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    try:
        with open(os.path.join(base, "misc-de", "language")) as f:
            return f.read().strip()
    except OSError:
        return "en"


def _(text):
    """i18n._ without the package: lang_de.py loaded by path."""
    if _language() != "de":
        return text
    try:
        spec = importlib.util.spec_from_file_location(
            "miscde_lang_de", os.path.join(HERE, "lang_de.py"))
        table = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(table)
        return table.TRANSLATIONS.get(text, text)
    except Exception:
        return text


def message(packages):
    """Heading and text of the dialog."""
    return (_("misc-de cannot start"),
            _("These packages are missing:\n\n{packages}\n\nInstall them in a "
              "terminal with:\n\n{command}").format(
                  packages="\n".join("  " + p for p in packages),
                  command="sudo apt install " + " ".join(packages)))


def _show_gtk4(heading, text):
    import gi
    gi.require_version("Gtk", "4.0")
    from gi.repository import GLib, Gtk
    loop = GLib.MainLoop()
    win = Gtk.Window(title=heading, default_width=360)
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18,
                  margin_top=24, margin_bottom=24, margin_start=24,
                  margin_end=24)
    box.append(Gtk.Label(label=heading, xalign=0, css_classes=["title-2"]))
    box.append(Gtk.Label(label=text, xalign=0, wrap=True, selectable=True))
    btn = Gtk.Button(label=_("Got it"), halign=Gtk.Align.CENTER)
    btn.connect("clicked", lambda _b: win.close())
    box.append(btn)
    win.set_child(box)
    win.connect("close-request", lambda _w: loop.quit() or False)
    win.present()
    loop.run()


def _show_gtk3(heading, text):
    import gi
    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk
    dlg = Gtk.MessageDialog(message_type=Gtk.MessageType.ERROR,
                            buttons=Gtk.ButtonsType.CLOSE, text=heading,
                            secondary_text=text)
    dlg.run()
    dlg.destroy()


def tell(packages):
    """Say it on whatever can still show something."""
    heading, text = message(packages)
    print(heading + "\n\n" + text, file=sys.stderr)
    if "gir1.2-gtk-4.0" not in packages and "python3-gi" not in packages:
        shows = (_show_gtk4,)
    elif "python3-gi" not in packages:
        shows = (_show_gtk3,)
    else:
        shows = ()
    for show in shows:
        try:
            show(heading, text)
            return
        except Exception:
            pass
    if shutil.which("notify-send"):
        subprocess.run(["notify-send", "-i", "dialog-error", heading, text],
                       check=False)


def check():
    """True when the window can start; otherwise says why and returns False."""
    packages = missing()
    if packages:
        tell(packages)
        return False
    return True
