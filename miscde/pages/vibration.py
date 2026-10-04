# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Vibration page: which rhythm the phone vibrates in, per kind of event.

Measured on the FLX1 (4.10.2026): the motor is driven through
/sys/class/leds/vibrator (mtk_vibrator) with nothing but "on for N ms" -
duration, then activate. There is no amplitude: feedbackd's sysfs backend
receives the magnitude and never writes it, so max-haptic-strength and every
magnitude in a theme change nothing here. The rhythm is free, though: a
pattern step with magnitude 0 is a real pause, any other step runs the motor
for exactly its duration (checked against activate: 500 -> 502 ms, 1500 ->
1500 ms). So this page offers rhythms and says plainly that strength is not
one of the things it can set.

How: a feedbackd theme of our own, ~/.config/feedbackd/themes/misc-de.json,
chained to the default one with "parent-name" and holding only the events
somebody changed - so everything else, and whatever a later feedbackd adds,
stays as shipped. The vibrations live in the theme's "quiet" profile (the
"full" one adds the sounds on top), and an entry for an event there replaces
the default's. feedbackd is told to use the theme through its "theme" key,
which it watches; a rewrite of the file under an unchanged key is picked up
with SIGHUP. After an installation nothing is written: every event starts on
"Standard", and with all of them back on "Standard" the key and the file go
back to what was there before the first change (miscde/original.py).
"""

import json
import os
import subprocess

from gi.repository import Adw, GLib, Gio, Gtk

from .. import original, process
from ..i18n import _


def N_(text):
    """Marks a text that is translated where it is shown, through _()."""
    return text


def _words():
    """The marked texts once more as literal _() calls: tests/test-app.py
    finds what needs German by reading the code for exactly those."""
    return [_("Vibration"), _("Incoming call"), _("SMS"), _("Messenger"),
            _("E-mail"), _("Other notifications"), _("Keyboard"),
            _("Standard"), _("Off"), _("Tap"), _("Short"), _("Double"),
            _("Triple"), _("Long"), _("Heartbeat"), _("Staccato"), _("SOS")]

# key, title, icon - the same three a component carries for its tab.
TAB = ("vibration", "Vibration", "phone-symbolic")

# FuriOS has feedbackd write every duration times ten to the driver
# (adaptation-radon-configs), and feedbackd only switches the motor off at
# the end of a feedback, not between its steps - so with the multiplier a
# pattern's pauses vanish: "triple" measured as one buzz of ~650 ms, and
# FuriOS' own notification pattern (50/250/50) is one buzz too. Without it
# every step runs exactly as long as written: three pulses of 118 ms with
# 120 ms between them (4.10.2026). So a rhythm of ours moves the file aside
# with dpkg-divert - kept, and an update of the package lands beside it -
# and the very short haptics FuriOS relies on it for get a firm tap instead.
MULTIPLIER = "/usr/lib/furios/device/vibrator-sysfs-multiplier"
MULTIPLIER_ASIDE = MULTIPLIER + ".misc-de-off"

THEME = "misc-de"
SCHEMA = "org.sigxcpu.feedbackd"
KEY = "theme"
SYSFS = "/sys/class/leds/vibrator"

# The events a person tells apart by feel. The alarm is not here: its entry
# in the quiet profile is the alarm sound, and a pattern would replace it.
EVENTS = (
    ("phone-incoming-call", N_("Incoming call")),
    ("message-new-sms", N_("SMS")),
    ("message-new-instant", N_("Messenger")),
    ("message-new-email", N_("E-mail")),
    ("notification-new-generic", N_("Other notifications")),
    ("key-pressed", N_("Keyboard")),
)


def _pattern(*steps):
    """steps: on, off, on, off ... in ms."""
    return {"type": "VibraPattern",
            "magnitudes": [1.0 if i % 2 == 0 else 0.0 for i in range(len(steps))],
            "durations": list(steps)}


# id, title, the feedback (None: the default theme's own).
PATTERNS = (
    ("default", N_("Standard"), None),
    ("off", N_("Off"), {"type": "VibraPattern", "magnitudes": [0.0],
                        "durations": [1]}),
    ("tap", N_("Tap"), _pattern(40)),
    ("short", N_("Short"), _pattern(150)),
    ("double", N_("Double"), _pattern(150, 150, 150)),
    ("triple", N_("Triple"), _pattern(120, 120, 120, 120, 120)),
    ("long", N_("Long"), _pattern(800)),
    ("heartbeat", N_("Heartbeat"), _pattern(90, 110, 90, 700)),
    ("staccato", N_("Staccato"), _pattern(60, 60, 60, 60, 60, 60, 60, 400)),
    ("sos", N_("SOS"), _pattern(100, 100, 100, 100, 100, 300, 350, 100, 350,
                                100, 350, 300, 100, 100, 100, 100, 100)),
)
PATTERN = {pid: feedback for pid, _title, feedback in PATTERNS}

# Without the multiplier these defaults (7, 12 and 25 ms) are too short to
# feel. What they get instead while it is aside - one firm tap per key or
# button, its release silent. key-released follows the keyboard row: one
# feedback per key, whatever was chosen for the press.
COMPENSATION = {
    "button-pressed": _pattern(50),
    "button-released": PATTERN["off"],
    "window-close": _pattern(40),
}
FIRM_TAP = _pattern(50)


def multiplier_aside():
    """True while the multiplier is moved aside by us."""
    return not os.path.exists(MULTIPLIER) and os.path.exists(MULTIPLIER_ASIDE)


def multiplier_argv(aside, secret=None):
    """The sudo command that moves the multiplier aside or back, or None when
    it is where it has to be already (then nobody is asked anything)."""
    if aside == multiplier_aside() or (aside and not os.path.exists(MULTIPLIER)):
        return None
    front = (["sudo", "-S", "-p", ""] if secret is not None
             else ["sudo", "-n"])
    return front + ["dpkg-divert", "--local", "--rename", "--divert",
                    MULTIPLIER_ASIDE, "--remove" if not aside else "--add",
                    MULTIPLIER]


def theme_path():
    """Read at call time: the tests point XDG_CONFIG_HOME somewhere harmless
    after this module is loaded."""
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "feedbackd", "themes", THEME + ".json")


def read_choices(path=None):
    """{event: pattern id} for every event of ours in the theme file. An entry
    that matches none of the patterns - written by hand - reads as "custom"
    and is kept as it is."""
    try:
        with open(path or theme_path(), encoding="utf-8") as f:
            theme = json.load(f)
    except (OSError, ValueError):
        return {}
    choices = {}
    for profile in theme.get("profiles") or ():
        if profile.get("name") != "quiet":
            continue
        for fb in profile.get("feedbacks") or ():
            event = fb.get("event-name")
            body = {k: v for k, v in fb.items() if k != "event-name"}
            pid = next((p for p, f in PATTERN.items() if f == body), "custom")
            if event == "key-pressed" and body == FIRM_TAP:
                pid = "default"           # the stand-in, not a choice
            choices[event] = pid
    return choices


def theme_text(choices, keep=None, exact=False):
    """The theme for these choices. keep: entries from the file that this
    page does not manage (other events, "custom" ones) and carries over.
    exact: the multiplier is aside, so the too-short defaults get theirs."""
    feedbacks = []
    for event, pid in sorted(choices.items()):
        if pid in ("default", "custom"):
            continue
        feedbacks.append(dict({"event-name": event}, **PATTERN[pid]))
    if exact:
        chosen = {f["event-name"] for f in feedbacks}
        kept = {f.get("event-name") for f in keep or ()}
        extra = dict(COMPENSATION)
        if choices.get("key-pressed", "default") == "default":
            extra["key-pressed"] = FIRM_TAP
        extra["key-released"] = PATTERN["off"]
        for event, fb in sorted(extra.items()):
            if event not in chosen and event not in kept:
                feedbacks.append(dict({"event-name": event}, **fb))
    feedbacks.extend(keep or ())
    theme = {"name": THEME, "parent-name": "default",
             "profiles": [{"name": "quiet", "feedbacks": feedbacks}]}
    return json.dumps(theme, indent=2) + "\n"


def foreign_entries(path=None):
    """Entries in the theme file that are not one of our patterns for one of
    our events - left exactly as they are."""
    try:
        with open(path or theme_path(), encoding="utf-8") as f:
            theme = json.load(f)
    except (OSError, ValueError):
        return []
    ours = {e for e, _t in EVENTS} | set(COMPENSATION) | {"key-released"}
    keep = []
    for profile in theme.get("profiles") or ():
        if profile.get("name") != "quiet":
            continue
        for fb in profile.get("feedbacks") or ():
            body = {k: v for k, v in fb.items() if k != "event-name"}
            known = list(PATTERN.values()) + list(COMPENSATION.values()) + [FIRM_TAP]
            if fb.get("event-name") not in ours or body not in known:
                keep.append(fb)
    return keep


def _settings():
    source = Gio.SettingsSchemaSource.get_default()
    if source is None or source.lookup(SCHEMA, True) is None:
        return None
    return Gio.Settings.new(SCHEMA)


def _user_value(settings):
    v = settings.get_user_value(KEY)
    return None if v is None else v.get_string()


def reload_feedbackd():
    """feedbackd reads its theme again on SIGHUP. Only ours, the user's."""
    subprocess.run(["pkill", "-HUP", "-x", "-u", str(os.getuid()), "feedbackd"],
                   capture_output=True)


def apply(choices, settings=None, exact=None):
    """Write what the choices say, or put everything back once none is left.

    Returns "on" (our theme in use), "off" (back to what was there) or
    "changed" (somebody changed key or file after us - left alone)."""
    settings = settings if settings is not None else _settings()
    exact = multiplier_aside() if exact is None else exact
    path = theme_path()
    keep = foreign_entries(path)
    wanted = {e: p for e, p in choices.items() if p not in ("default",)}
    if not wanted and not keep:
        state = "off"
        if settings is not None and settings.get_string(KEY) == THEME:
            ident = original.setting_ident(SCHEMA, KEY)
            record = original.load(ident)
            if record is None or record.get("user_value") is None:
                settings.reset(KEY)
            else:
                settings.set_string(KEY, record["user_value"])
            original.forget(ident)
        if original.restore_file(path) == "changed":
            state = "changed"
        elif os.path.exists(path) and original.load(original.file_ident(path)) is None:
            os.remove(path)
        reload_feedbackd()
        return state

    original.remember_file(path)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".misc-de.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(theme_text(choices, keep, exact))
    os.replace(tmp, path)
    original.wrote_file(path)
    if settings is not None and settings.get_string(KEY) != THEME:
        original.remember_setting(SCHEMA, KEY, _user_value(settings),
                                  settings.get_string(KEY))
        settings.set_string(KEY, THEME)       # feedbackd reloads on its own
    else:
        reload_feedbackd()
    return "on"


class Player:
    """Plays a pattern on the motor directly, for the try button: feedbackd
    would add the event's sound on top, and the test is about the feel. The
    same steps feedbackd runs - on for N ms, or a pause."""

    def __init__(self, sysfs=SYSFS):
        self.sysfs = sysfs
        self.timer = 0

    def available(self):
        return all(os.access(os.path.join(self.sysfs, a), os.W_OK)
                   for a in ("duration", "activate"))

    def _write(self, attr, value):
        with open(os.path.join(self.sysfs, attr), "w") as f:
            f.write("%s\n" % value)

    def stop(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        try:
            self._write("activate", 0)
        except OSError:
            pass

    def play(self, feedback):
        self.stop()
        if not feedback:
            return
        steps = list(zip(feedback["magnitudes"], feedback["durations"]))
        self._step(steps)

    def _step(self, steps):
        self.timer = 0
        if not steps:
            return GLib.SOURCE_REMOVE
        magnitude, duration = steps[0]
        try:
            if magnitude > 0:
                self._write("duration", duration)
                self._write("activate", 1)
        except OSError:
            return GLib.SOURCE_REMOVE
        self.timer = GLib.timeout_add(duration, self._step, steps[1:])
        return GLib.SOURCE_REMOVE


class VibrationPage:
    """Mixed into the window, like the other pages."""

    def build_vibration_page(self):
        page = Adw.PreferencesPage()
        self.vibra_player = Player()
        self.vibra_settings = _settings()
        choices = read_choices()

        grp = Adw.PreferencesGroup(title=_("Rhythm"))
        self.vibra_rows = {}
        titles = [_(t) for _pid, t, _fb in PATTERNS]
        ids = [pid for pid, _t, _fb in PATTERNS]
        self._vibra_loading = True
        for event, title in EVENTS:
            row = Adw.ComboRow(title=_(title),
                               model=Gtk.StringList.new(titles))
            pid = choices.get(event, "default")
            if pid == "custom":
                row.set_subtitle(_("Written by hand - kept until changed here"))
                pid = "default"
            row.set_selected(ids.index(pid))
            row.connect("notify::selected", self.on_vibra_changed)
            play = Gtk.Button(icon_name="media-playback-start-symbolic",
                              valign=Gtk.Align.CENTER,
                              tooltip_text=_("Try"),
                              sensitive=self.vibra_player.available())
            play.add_css_class("flat")
            play.connect("clicked", self.on_vibra_try, row)
            row.add_suffix(play)
            grp.add(row)
            self.vibra_rows[event] = row
        self._vibra_loading = False
        page.add(grp)

        info = Adw.PreferencesGroup(title=_("Strength"))
        info.add(Adw.ActionRow(
            title=_("Not adjustable on this phone"),
            subtitle=_("The motor only knows on and off - strength values "
                       "are ignored by the driver. Short pulses with pauses "
                       "feel lighter."),
            subtitle_lines=4))
        page.add(info)
        return page

    def vibra_choices(self):
        ids = [pid for pid, _t, _fb in PATTERNS]
        return {event: ids[row.get_selected()]
                for event, row in self.vibra_rows.items()}

    def on_vibra_changed(self, row, _pspec):
        if self._vibra_loading:
            return
        row.set_subtitle("")
        choices = self.vibra_choices()
        state = apply(choices, self.vibra_settings)
        if state == "changed":
            self.toast(_("The theme file was changed by someone else - "
                         "left as it is"))
        self.vibra_multiplier(state == "on")

    def vibra_multiplier(self, aside, secret=None):
        """Rhythms need the multiplier aside; Standard everywhere puts it back."""
        argv = multiplier_argv(aside, secret)
        if argv is None:
            return
        process.run_async(argv, lambda ok, out: self.on_vibra_multiplier(ok, out, aside),
                          stdin=secret)

    def on_vibra_multiplier(self, ok, out, aside):
        low = (out or "").lower()
        if not ok and ("password is required" in low or "askpass" in low):
            self.ask_vibra_password(aside)
            return
        if not ok:
            self.report(out or _("No output."))
            return
        # The theme again, now with or without the stand-ins for the short
        # defaults - they belong to the multiplier being aside.
        apply(self.vibra_choices(), self.vibra_settings, exact=aside)

    def ask_vibra_password(self, aside):
        entry = Adw.PasswordEntryRow(title=_("Your password (for sudo)"))
        group = Adw.PreferencesGroup()
        group.add(entry)
        dlg = Adw.AlertDialog(
            heading=_("Exact rhythms"),
            body=_("FuriOS stretches every vibration tenfold, which melts the "
                   "pauses of a rhythm into one buzz. Switching that off needs "
                   "sudo; the password goes to sudo through a pipe and nowhere "
                   "else."))
        dlg.set_extra_child(group)
        dlg.add_response("cancel", _("Cancel"))
        dlg.add_response("go", _("Change it"))
        dlg.set_response_appearance("go", Adw.ResponseAppearance.SUGGESTED)
        dlg.set_default_response("go")
        dlg.set_close_response("cancel")

        def done(_d, response):
            secret = entry.get_text()
            entry.set_text("")
            if response == "go":
                self.vibra_multiplier(aside, secret)
        dlg.connect("response", done)
        dlg.present(self)

    def on_vibra_try(self, _btn, row):
        pid = [p for p, _t, _fb in PATTERNS][row.get_selected()]
        event = next(e for e, r in self.vibra_rows.items() if r is row)
        feedback = PATTERN.get(pid)
        if feedback is None:
            feedback = default_feedback(event)
        self.vibra_player.play(_as_pattern(feedback))


def default_feedback(event):
    """The default theme's vibration for an event, from feedbackd's own file."""
    for base in GLib.get_system_data_dirs():
        path = os.path.join(base, "feedbackd", "themes", "default.json")
        try:
            with open(path, encoding="utf-8") as f:
                theme = json.load(f)
        except (OSError, ValueError):
            continue
        for profile in theme.get("profiles") or ():
            if profile.get("name") != "quiet":
                continue
            for fb in profile.get("feedbacks") or ():
                if fb.get("event-name") == event:
                    return fb
    return None


def _as_pattern(fb):
    """Any of feedbackd's vibra types as on/off steps."""
    if not fb:
        return None
    kind = fb.get("type")
    if kind == "VibraPattern":
        return {"magnitudes": fb["magnitudes"], "durations": fb["durations"]}
    if kind == "VibraRumble":
        count = max(1, int(fb.get("count", 1)))
        duration = int(fb.get("duration", 0))
        pause = int(fb.get("pause", 0))
        rumble = max(1, duration // count - pause) if count > 1 else duration
        mags, durs = [], []
        for i in range(count):
            mags.append(1.0); durs.append(rumble)
            if i < count - 1:
                mags.append(0.0); durs.append(pause)
        return {"magnitudes": mags, "durations": durs}
    if kind == "VibraPeriodic":
        return {"magnitudes": [1.0], "durations": [int(fb.get("duration", 0))]}
    return None
