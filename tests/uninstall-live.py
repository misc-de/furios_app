#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""uninstall.sh leaves the phone as a new one - checked from the outside.

The rule: after uninstall.sh, a later install.sh behaves exactly as on a new
phone. Reading uninstall.sh against install.sh would only find what the
reader already expects, so this runs both for real - install.sh into a
staged root (DESTDIR) and a home of its own, with a sudo that refuses any
path outside the stage, the real gtk-update-icon-cache and
update-desktop-database making their real caches, then the window's own code
writing what it writes at runtime, then uninstall.sh - and compares the
stage and the home with what was there before. Whatever is left is the gap,
whether or not anybody thought of it.

Two things come from elsewhere than the current code, so that they are not
forgotten either: every file any earlier install.sh put in /usr/local (read
from git history, planted before the uninstall), and every place in miscde/
that writes to the file system (found by walking the source; a new one
fails here until uninstall.sh removes it and this test seeds it).

NEVER with sudo, and nothing here reaches the phone's own /usr/local, home
or dconf: gsettings, sudo, pgrep, systemctl and logger are stand-ins.
"""
import ast
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "uninstall.sh"

# Every function in miscde/ that writes to the file system or to dconf, and
# how the scenario below makes it write. A function that is not here fails
# ThereIsNoUnseenWriter: first make uninstall.sh remove what it writes, then
# add it here and to seed_runtime().
KNOWN_WRITERS = {
    ("askpass.py", "start"): "a password socket under $XDG_RUNTIME_DIR",
    ("i18n.py", "save"): "~/.config/misc-de/language",
    ("pages/install.py", "run_updates"): "clones under ~/.local/share/misc-de",
    ("pages/install.py", "run_component"): "clones under ~/.local/share/misc-de",
    ("pages/other.py", "set_search_hidden"): "~/.config/gtk-3.0/gtk.css",
    ("pages/other.py", "set_dock_enabled"): "phosh's status-icons list",
    ("pages/other.py", "set_dock_setting"): "~/.config/furios-folder-dock.conf",
    ("pages/other.py", "set_prompter_fixed"): "the keyring prompter shim",
    ("pages/other.py", "set_portals_fixed"):
        "~/.config/xdg-desktop-portal/phosh-portals.conf",
}
FS_CALLS = {"makedirs", "mkdir", "replace", "rename", "chmod", "mkdtemp",
            "mkstemp", "copy", "copy2", "copyfile", "copytree", "symlink",
            "link", "move"}
# On a Gio.Settings - a widget has set_value too, a slider for one.
SETTINGS_CALLS = {"set_strv", "set_boolean", "set_string", "set_int",
                  "set_uint", "set_double", "set_enum", "set_flags",
                  "set_value", "reset"}
PATH_CALLS = {"write_text", "write_bytes"}

# What a new phone has under /usr/local: base-files' directories. Neither
# share/icons nor share/applications is among them.
SKELETON = ["usr/local/bin", "usr/local/etc", "usr/local/include",
            "usr/local/lib", "usr/local/sbin", "usr/local/share",
            "usr/local/src"]

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t",
       "-c", "init.defaultBranch=main", "-c", "advice.detachedHead=false"]


def tree(base):
    base = Path(base)
    return sorted(str(p.relative_to(base)) for p in base.rglob("*"))


def git(*args, cwd=None):
    subprocess.run(GIT + list(args), cwd=cwd, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def pushed_clone(where, remote):
    """A clone with everything in it on its remote."""
    if not Path(remote).exists():
        git("init", "-q", "--bare", str(remote))
        seed = Path(str(remote) + ".seed")
        git("init", "-q", str(seed))
        (seed / "README").write_text("x\n")
        git("add", "README", cwd=seed)
        git("commit", "-q", "-m", "one", cwd=seed)
        git("push", "-q", str(remote), "HEAD:main", cwd=seed)
        shutil.rmtree(seed)
    git("clone", "-q", str(remote), str(where))


class Stage:
    """A staged root, a home and the stand-ins, in one temporary directory."""

    def __init__(self):
        self.work = Path(tempfile.mkdtemp(prefix="miscde-uninstall-"))
        self.root = self.work / "root"
        self.home = self.work / "home"
        self.bin = self.work / "bin"
        self.gs = self.work / "gs"
        self.runtime = self.work / "run"
        for d in (self.bin, self.gs, self.runtime, self.home):
            d.mkdir(parents=True)
        for d in SKELETON:
            (self.root / d).mkdir(parents=True)
        self.refused = self.work / "refused"
        self._stubs()

    def _stubs(self):
        w, r = shlex.quote(str(self.work)), shlex.quote(str(ROOT))
        (self.bin / "sudo").write_text(textwrap.dedent(f"""\
            #!/bin/bash
            # Runs the command as it is, but refuses any path outside the
            # stage: a system path the stage does not reach fails the test
            # instead of changing this phone.
            case "$1" in
            install|rm|rmdir|cp|find|chmod|mkdir|sed|gtk-update-icon-cache|update-desktop-database) ;;
            *) echo "sudo $1 is not stood in for: $*" >> {w}/refused; exit 97 ;;
            esac
            for a in "$@"; do
                case "$a" in
                /*) case "$a" in {w}/*|{r}/*) ;; *)
                        echo "system path: $*" >> {w}/refused; exit 97 ;;
                    esac ;;
                esac
            done
            exec "$@"
            """))
        (self.bin / "gsettings").write_text(textwrap.dedent(f"""\
            #!/bin/sh
            # One file per key; no file is no value in dconf, as on a new
            # phone. The memory backend answers the default, as the real one.
            f={w}/gs/"$3"
            [ "$2" = mobi.phosh.shell.plugins ] && [ "$3" = status-icons ] || exit 1
            case "$1" in
            get) if [ "${{GSETTINGS_BACKEND:-}}" = memory ] || [ ! -e "$f" ]; then
                     echo "@as []"
                 else cat "$f"; fi ;;
            set) printf '%s\\n' "$4" > "$f" ;;
            reset) rm -f "$f" ;;
            *) exit 1 ;;
            esac
            """))
        # No misc-de window open, and nothing reaches the user's units or
        # the journal.
        (self.bin / "pgrep").write_text("#!/bin/sh\nexit 1\n")
        for name in ("systemctl", "logger"):
            (self.bin / name).write_text("#!/bin/sh\nexit 0\n")
        for p in self.bin.iterdir():
            p.chmod(0o755)

    def env(self):
        env = {k: v for k, v in os.environ.items()
               if not k.startswith("XDG_") and k not in ("HOME", "DESTDIR")}
        env.update(HOME=str(self.home), DESTDIR=str(self.root),
                   XDG_RUNTIME_DIR=str(self.runtime),
                   PATH=str(self.bin) + ":" + os.environ.get("PATH", ""),
                   GIT_CONFIG_NOSYSTEM="1")
        return env

    def run(self, script):
        return subprocess.run(["bash", str(script)], env=self.env(), cwd=str(ROOT),
                              capture_output=True, text=True)

    @property
    def icons(self):
        return self.gs / "status-icons"

    def close(self):
        shutil.rmtree(self.work, ignore_errors=True)


def seed_runtime(stage):
    """What the window writes while it runs, written by its own code."""
    code = textwrap.dedent("""\
        import sys
        sys.path[:0] = [sys.argv[1] + "/tests", sys.argv[1]]
        import gi_stub
        gi_stub.install()
        from miscde import i18n
        from miscde.pages import other
        i18n.save("de")
        other.set_search_hidden(True)
        other.set_dock_setting(other.ONE_ROW, True)
        other.set_dock_setting(other.HIDE_LABELS, True)
        other.set_prompter_fixed(True)
        other.set_portals_fixed(True)
        """)
    subprocess.run([sys.executable, "-c", code, str(ROOT)], env=stage.env(),
                   check=True)
    # The dock switched on, as set_dock_enabled leaves the list.
    stage.icons.write_text("['wifi-hotspot', 'furios-folder-dock']\n")
    # The Audio tab's "Bluetooth powersave" switched off - by sudo sh -c, which
    # the walk over miscde/ cannot see, so it is planted here - and the copy
    # taken by hand before that switch existed.
    batman = stage.root / "var/lib/batman/config"
    (batman.parent / "config.bak-20260916-082123").write_text(batman.read_text())
    batman.write_text(batman.read_text().replace("BTSAVE=true", "BTSAVE=false"))
    # askpass.start: a window that crashed before it could clean up.
    (stage.runtime / "misc-de-abc123").mkdir()
    (stage.runtime / "misc-de-abc123" / "askpass").write_text("x\n")


def historical_files():
    """Every file under /usr/local that any install.sh ever installed.

    A path is a file when no other path lies beneath it. Empty without git
    history (a shallow checkout), and then the test says so."""
    try:
        commits = subprocess.run(
            ["git", "-C", str(ROOT), "log", "--format=%H", "--", "install.sh"],
            capture_output=True, text=True, check=True).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        return []
    paths = set()
    for c in commits:
        text = subprocess.run(["git", "-C", str(ROOT), "show", c + ":install.sh"],
                              capture_output=True, text=True).stdout
        for word in text.replace('"', " ").split():
            if word.startswith("/usr/local/"):
                paths.add(word.rstrip("/;"))
    return sorted(p for p in paths
                  if not any(o.startswith(p + "/") for o in paths))


def extract_clone_rule():
    text = SCRIPT.read_text()
    start = text.index("# --- clone rule")
    end = text.index("# --- end clone rule ---")
    return text[start:end]


def clone_table():
    """clone_tool from uninstall.sh as {dir: tool}, asked of bash itself."""
    script = extract_clone_rule() + textwrap.dedent("""
        for d in "$@"; do
            read -r tool sub <<<"$(clone_tool "$d")"
            if [ -n "$tool" ]; then echo "$d $tool ${sub:-}"; fi
        done
        """)
    out = subprocess.run(["bash", "-c", script, "-"] + list(COMPONENT_DIRS),
                         capture_output=True, text=True, check=True).stdout
    return {line.split()[0]: tuple(line.split()[1:]) for line in out.splitlines()}


def component_table():
    """{dir: (tool, sub)} from miscde/components.py, read without GTK."""
    tree_ = ast.parse((ROOT / "miscde" / "components.py").read_text())
    for node in tree_.body:
        if (isinstance(node, ast.Assign)
                and any(getattr(t, "id", None) == "COMPONENTS" for t in node.targets)):
            table = {}
            for entry in node.value.elts:
                fields = {k.value: v for k, v in zip(entry.keys, entry.values)
                          if isinstance(k, ast.Constant)}
                sub = fields.get("sub")
                table[fields["dir"].value] = (
                    (fields["tool"].value,) + ((sub.value,) if sub else ()))
            return table
    raise AssertionError("no COMPONENTS in miscde/components.py")


BATMAN_SHIPPED = ("OFFLINE=true\nPOWERSAVE=true\nMAX_CPU_USAGE=60\n"
                  "CHARGESAVE=true\nBUSSAVE=true\nGPUSAVE=true\n"
                  "BTSAVE=true\nWIFISAVE=false\n")
COMPONENT_TOOLS = component_table()
COMPONENT_DIRS = sorted(COMPONENT_TOOLS) + ["furios_app", "somebody_else"]


class ThereIsNoUnseenWriter(unittest.TestCase):
    """Walks miscde/ for every call that writes, and holds the list of
    functions making them against KNOWN_WRITERS."""

    def test_every_writer_is_known(self):
        found = set()
        base = ROOT / "miscde"
        for path in sorted(base.rglob("*.py")):
            rel = str(path.relative_to(base))
            for fn in ast.walk(ast.parse(path.read_text())):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for node in ast.walk(fn):
                    if not isinstance(node, ast.Call):
                        continue
                    f = node.func
                    name = getattr(f, "attr", None) or getattr(f, "id", None)
                    owner = getattr(getattr(f, "value", None), "id", None)
                    writes = (
                        (name in FS_CALLS and owner in ("os", "shutil", "tempfile"))
                        or name in PATH_CALLS
                        or (name in SETTINGS_CALLS and isinstance(f, ast.Attribute)
                            and "settings" in ast.unparse(f.value).lower())
                        or (name == "open" and len(node.args) > 1
                            and isinstance(node.args[1], ast.Constant)
                            and set(str(node.args[1].value)) & set("wax+")))
                    if writes:
                        found.add((rel, fn.name))
        unknown = found - set(KNOWN_WRITERS)
        self.assertFalse(unknown, "writes at runtime, and nothing says uninstall.sh "
                         "removes it: %s" % sorted(unknown))
        # And a list that only grows says nothing either.
        self.assertFalse(set(KNOWN_WRITERS) - found,
                         "no longer writes - take it out of KNOWN_WRITERS: %s"
                         % sorted(set(KNOWN_WRITERS) - found))


class LeavesThePhoneAsItShipped(unittest.TestCase):

    def setUp(self):
        self.s = Stage()
        self.addCleanup(self.s.close)
        s = self.s
        # Somebody's own: a gtk.css rule, a clone they keep in ~/Projekte.
        (s.home / ".config" / "gtk-3.0").mkdir(parents=True)
        (s.home / ".config" / "gtk-3.0" / "gtk.css").write_text("/* own */\n")
        (s.home / ".local" / "share").mkdir(parents=True)
        pushed_clone(s.home / "Projekte" / "furios_audio", s.work / "remote.git")
        s.icons.write_text("['wifi-hotspot']\n")
        # batman's config as FuriOS ships it.
        (s.root / "var/lib/batman").mkdir(parents=True)
        (s.root / "var/lib/batman/config").write_text(BATMAN_SHIPPED)
        self.root_before = tree(s.root)
        self.home_before = tree(s.home)

    def install(self):
        out = self.s.run(ROOT / "install.sh")
        if "libadwaita bindings missing" in out.stdout:
            self.skipTest("install.sh needs python3-gi and gir1.2-adw-1")
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)

    def uninstall(self):
        out = self.s.run(SCRIPT)
        self.assertEqual(0, out.returncode, out.stdout + out.stderr)
        return out.stdout

    def test_install_then_uninstall(self):
        s = self.s
        self.install()
        self.assertNotEqual(self.root_before, tree(s.root))
        old = historical_files()
        if not old:
            print("  (no git history - files of earlier versions not planted)")
        for p in old:
            target = s.root / p.lstrip("/")
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("left by an earlier version\n")
        seed_runtime(s)
        clones = s.home / ".local" / "share" / "misc-de"
        pushed_clone(clones / "furios_modem_fixes", s.work / "remote.git")
        pushed_clone(clones / "furios_gps", s.work / "remote.git")
        (clones / "furios_gps" / "notes.txt").write_text("mine\n")

        said = self.uninstall()

        self.assertEqual("", s.refused.read_text() if s.refused.exists() else "")
        self.assertEqual(self.root_before, tree(s.root),
                         "left in the staged root")
        kept = "furios_gps"
        left = [p for p in tree(s.home)
                if not p.startswith(".local/share/misc-de")]
        self.assertEqual(self.home_before, left, "left in the home")
        self.assertEqual([kept], sorted(os.listdir(clones)))
        self.assertIn("kept %s" % (clones / kept), said)
        self.assertEqual("/* own */\n",
                         (s.home / ".config/gtk-3.0/gtk.css").read_text())
        self.assertEqual("['wifi-hotspot']\n", s.icons.read_text())
        self.assertEqual([], os.listdir(s.runtime))
        self.assertEqual(BATMAN_SHIPPED,
                         (s.root / "var/lib/batman/config").read_text())

    def test_a_new_phone_keeps_no_value_in_dconf(self):
        s = self.s
        s.icons.unlink()
        self.install()
        s.icons.write_text("['furios-folder-dock']\n")
        self.uninstall()
        self.assertFalse(s.icons.exists(),
                         "a list back at its default was written, not reset")
        self.assertEqual(self.root_before, tree(s.root))

    def test_somebody_elses_icon_keeps_the_cache(self):
        s = self.s
        other = s.root / "usr/local/share/icons/hicolor/scalable/apps/other.svg"
        other.parent.mkdir(parents=True)
        other.write_text("<svg/>")
        self.install()
        self.uninstall()
        self.assertTrue(other.exists())
        self.assertTrue((other.parents[2] / "icon-theme.cache").exists(),
                        "the cache went although another icon needs it")


class TheCloneRule(unittest.TestCase):
    """remove_clones from uninstall.sh, run as bash runs it, on temp dirs.

    With a staged root of its own: whether a tool is still installed is
    asked of DESTDIR, so what this phone has installed decides nothing."""

    def setUp(self):
        self.work = Path(tempfile.mkdtemp(prefix="miscde-clones-"))
        self.addCleanup(shutil.rmtree, self.work, True)
        self.base = self.work / "misc-de"
        self.remote = self.work / "remote.git"
        self.root = self.work / "root"
        self.env = dict(os.environ, HOME=str(self.work), DESTDIR=str(self.root),
                        GIT_CONFIG_NOSYSTEM="1")

    def installed(self, where, name):
        """A tool in one of the places the app looks, as an executable."""
        path = Path(where) / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("#!/bin/sh\n")
        path.chmod(0o755)
        return path

    def clone(self, name):
        path = self.base / name
        pushed_clone(path, self.remote)
        return path

    def remove(self):
        script = extract_clone_rule() + "\nremove_clones " + shlex.quote(str(self.base))
        return subprocess.run(["bash", "-c", script], env=self.env,
                              capture_output=True, text=True).stdout

    def test_a_clone_with_everything_pushed_goes(self):
        self.clone("furios_audio")
        self.remove()
        self.assertFalse(self.base.exists(), "the empty directory stays behind")

    def test_uncommitted_changes_keep_it(self):
        path = self.clone("furios_audio")
        (path / "README").write_text("changed\n")
        said = self.remove()
        self.assertTrue(path.exists())
        self.assertIn("uncommitted changes", said)

    def test_an_untracked_file_keeps_it(self):
        path = self.clone("furios_audio")
        (path / "new.txt").write_text("mine\n")
        self.remove()
        self.assertTrue(path.exists())

    def test_a_commit_on_no_remote_keeps_it(self):
        path = self.clone("furios_audio")
        (path / "README").write_text("changed\n")
        git("commit", "-q", "-am", "local", cwd=path)
        said = self.remove()
        self.assertTrue(path.exists())
        self.assertIn("on no remote", said)

    def test_a_branch_never_pushed_keeps_it(self):
        path = self.clone("furios_audio")
        git("checkout", "-q", "-b", "idea", cwd=path)
        (path / "README").write_text("idea\n")
        git("commit", "-q", "-am", "idea", cwd=path)
        git("checkout", "-q", "main", cwd=path)
        self.remove()
        self.assertTrue(path.exists())

    def test_a_stash_keeps_it(self):
        path = self.clone("furios_audio")
        (path / "README").write_text("changed\n")
        git("stash", "-q", cwd=path)
        said = self.remove()
        self.assertTrue(path.exists())
        self.assertIn("stash", said)

    def test_something_that_is_not_a_clone_is_kept(self):
        (self.base / "furios_audio").mkdir(parents=True)
        (self.base / "furios_audio" / "file").write_text("x\n")
        said = self.remove()
        self.assertTrue((self.base / "furios_audio" / "file").exists())
        self.assertIn("not a git clone", said)

    def test_each_clone_on_its_own_merits(self):
        self.clone("furios_audio")
        dirty = self.clone("furios_gps")
        (dirty / "README").write_text("changed\n")
        self.remove()
        self.assertEqual(["furios_gps"], sorted(os.listdir(self.base)))

    def test_a_link_to_somebodys_own_clone_leaves_the_clone(self):
        own = self.work / "Projekte" / "furios_audio"
        pushed_clone(own, self.remote)
        self.base.mkdir()
        (self.base / "furios_audio").symlink_to(own)
        self.remove()
        self.assertTrue((own / "README").exists())
        self.assertFalse(self.base.exists())

    def test_a_clone_whose_tool_is_installed_keeps_it(self):
        """Its uninstall.sh is the only one on the phone - found on
        30.9.2026, the day the clones started to go with the app."""
        for where in ("usr/local/bin", "usr/bin"):
            with self.subTest(where=where):
                tool = self.installed(self.root / where, "audioctl")
                path = self.clone("furios_audio")
                said = self.remove()
                self.assertTrue(path.exists(), "the tool's uninstaller went")
                self.assertIn("audioctl is still installed", said)
                self.assertIn(str(path / "uninstall.sh"), said)
                # Once the tool is out, the next run takes the clone.
                tool.unlink()
                self.remove()
                self.assertFalse(self.base.exists())

    def test_a_tool_in_the_home_keeps_it_too(self):
        self.installed(self.work / ".local" / "bin", "killswitch-indicator")
        path = self.clone("furios_killswitch")
        self.remove()
        self.assertTrue(path.exists())

    def test_the_hint_names_the_installer_where_it_sits(self):
        """furios_misc collects several things; battctl's uninstaller is in
        battery/, not at the root of the clone."""
        self.installed(self.root / "usr/local/bin", "battctl")
        path = self.clone("furios_misc")
        said = self.remove()
        self.assertTrue(path.exists())
        self.assertIn(str(path / "battery" / "uninstall.sh"), said)

    def test_only_its_own_tool_keeps_a_clone(self):
        self.installed(self.root / "usr/local/bin", "modemctl")
        self.clone("furios_audio")
        kept = self.clone("furios_modem_fixes")
        self.remove()
        self.assertEqual([kept.name], sorted(os.listdir(self.base)))

    def test_without_a_stage_path_is_asked_as_well(self):
        """_tool_maybe's last resort. Without DESTDIR the real /usr/local/bin
        and /usr/bin are asked too, so this needs a tool the phone lacks."""
        missing = [(d, t[0]) for d, t in sorted(clone_table().items())
                   if not any(os.access(os.path.join(b, t[0]), os.X_OK)
                              for b in ("/usr/local/bin", "/usr/bin"))]
        if not missing:
            self.skipTest("every tool is installed here, so a hit on $PATH "
                          "could not be told from one in /usr")
        dirname, name = missing[0]
        own_bin = self.work / "elsewhere"
        self.installed(own_bin, name)
        self.env.pop("DESTDIR")
        self.env["PATH"] = str(own_bin) + ":" + os.environ.get("PATH", "")
        path = self.clone(dirname)
        self.remove()
        self.assertTrue(path.exists(), "a tool on $PATH was not seen")

    def test_the_table_is_the_components_list(self):
        """clone_tool in uninstall.sh, against what the app installs."""
        self.assertEqual(COMPONENT_TOOLS, clone_table())

    def test_a_linked_clone_directory_is_not_entered(self):
        own = self.work / "Projekte"
        pushed_clone(own / "furios_audio", self.remote)
        self.base.symlink_to(own)
        self.remove()
        self.assertTrue((own / "furios_audio" / "README").exists())


if __name__ == "__main__":
    if os.geteuid() == 0:
        sys.exit("never run this with sudo")
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for obj in list(globals().values()):
        if isinstance(obj, type) and issubclass(obj, unittest.TestCase):
            suite.addTests(loader.loadTestsFromTestCase(obj))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
