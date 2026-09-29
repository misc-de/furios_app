# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""The Audio page: who owns the Android HAL.

The page itself is built in window.py with the rest of the window -
it is the one tab that exists before any tool is found. What lives
here is everything that happens after somebody touches it."""

from gi.repository import Adw, Gtk

from .. import askpass, components, process, tools
from ..tools import DMNR
from ..words import profile_in_words, server_in_words
from ..i18n import _


# batman, the battery manager that ships with the phone, keeps its settings
# here as plain KEY=value lines. BTSAVE is the one that decides whether the
# Bluetooth adapter is switched off along with the screen.
BATMAN_CONFIG = "/var/lib/batman/config"

# The two sound servers the page chooses between, by audioctl profile. pw-tunnel
# still exists in audioctl but is not offered: PulseAudio holds the HAL there
# too, so it reads as PulseAudio.
SERVERS = [
    ("standard", "PulseAudio"),
    ("pw-hal", "PipeWire"),
]

# The A2DP codecs "audioctl bt-codec" takes. Names only - the page does not
# rate them (decided 27.9.2026).
CODECS = [
    ("auto", _("Automatic"), _("the best one both ends know")),
    ("aac", "AAC", ""),
    ("sbc_xq", "SBC-XQ", ""),
    ("sbc", "SBC", ""),
    ("aptx", "aptX", ""),
    ("aptx_hd", "aptX HD", ""),
    ("ldac", "LDAC", ""),
]


def server_at(index):
    """The profile behind a position in the server list, or None for a
    position that is not in it (GTK answers INVALID_LIST_POSITION when
    nothing is selected)."""
    if isinstance(index, int) and 0 <= index < len(SERVERS):
        return SERVERS[index][0]
    return None


def codec_name(key):
    return next((name for k, name, __ in CODECS if k == key), key)


# The first entry for a single headset: no choice of its own, it plays what
# is set for all of them.
FOLLOW_ALL = ("default", _("Same as for all"), "")


def parse_codec_status(out):
    """ "audioctl bt-codec status" as a dict of its single values, plus the
    headsets it has seen - one "known=address|name|choice|codecs" line each,
    which a dict would squash into the last one."""
    values, known = {}, []
    for line in (out or "").splitlines():
        key, sep, value = line.partition("=")
        if not sep:
            continue
        if key == "known":
            parts = value.split("|")
            if len(parts) == 4 and parts[0]:
                known.append({"addr": parts[0], "name": parts[1] or parts[0],
                              "choice": parts[2] or "default",
                              "offered": [c for c in parts[3].split(",") if c]})
        else:
            values[key] = value
    return values, known


def device_codec_choices(offered, choice):
    """What one headset's list offers: following the rest, Automatic, and the
    codecs it said it has - in the order of CODECS. A choice made before it
    stopped offering it stays in the list, so the list does not lie about
    what is set."""
    keep = set(offered) | {choice}
    return [FOLLOW_ALL] + [c for c in CODECS
                           if c[0] == "auto" or c[0] in keep]


def codec_choices(values):
    """What the list for all headsets offers. Every codec under PipeWire;
    under PulseAudio only what audioctl says it can switch to ("choices="),
    plus whatever is set, so the list does not lie about it."""
    offered = values.get("choices")
    if offered is None:
        return CODECS
    keep = set(offered.split()) | {values.get("preference", "auto"), "auto"}
    return [c for c in CODECS if c[0] in keep]


def codec_words(values):
    """The row's subtitle from "audioctl bt-codec status" output, parsed into
    a dict. What is chosen, and what a connected headset really plays -
    which is not the same when the headset does not offer the choice."""
    pref = values.get("preference", "auto")
    what = next((note for k, __, note in CODECS if k == pref), "")
    # PulseAudio picks by itself on connect, and not "the best": SBC.
    if pref == "auto" and values.get("server") == "pulseaudio":
        what = _("PulseAudio's own choice")
    if not values.get("card"):
        return _("%s - no device connected") % what if what else _("no device connected")
    active = values.get("active")
    offered = values.get("offered", "").split()
    if not active:
        return _("The device is on hands-free right now")
    if pref != "auto" and pref not in offered:
        return _("This device does not offer %s - it plays %s") % (
            codec_name(pref), codec_name(active))
    if pref == "auto":
        return _("Playing %s · %s") % (codec_name(active), what)
    return _("Playing %s") % codec_name(active)
BATMAN_UNIT = "batman.service"

# Everything it works on comes in as an argument: the file as $1, the unit as
# $2, the value as $3. Not for quoting's sake - all three are ours - but so
# the script can be run against a scratch file in a test. A script that names
# /var/lib/batman/config in its own text can only ever be read, not checked.
# `sed` over the existing line, append when the key is missing; batman reads
# this file at startup only, hence the restart.
BTSAVE_SCRIPT = (
    'set -e\n'
    'if grep -q "^BTSAVE=" "$1"; then\n'
    '  sed -i "s/^BTSAVE=.*/BTSAVE=$3/" "$1"\n'
    'else\n'
    '  printf "BTSAVE=%s\\n" "$3" >> "$1"\n'
    'fi\n'
    'systemctl restart "$2"\n'
)


def btsave_in_config(text):
    """Whether batman is set to power the adapter down.

    None when the key is not in the file at all, which is a different thing
    from "off" and is shown as such: an unknown setting must not be drawn as
    a switch that is merely not on."""
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("BTSAVE="):
            return line.split("=", 1)[1].strip().lower() == "true"
    return None


def btsave_argv(wanted, secret=None):
    """The one command that changes it, with or without a password.

    Without a secret this is `sudo -n`: on a phone whose sudoers asks for
    nothing, the switch just works and nobody is shown a password box for a
    single config line. When sudo does want one, the caller asks and comes
    back through here with it - `-S` reads it from the pipe, `-p ""` keeps
    sudo's prompt out of the window's own output."""
    value = "true" if wanted else "false"
    front = (["sudo", "-S", "-p", ""] if secret is not None
             else ["sudo", "-n"])
    return front + ["sh", "-c", BTSAVE_SCRIPT, "sh",
                    BATMAN_CONFIG, BATMAN_UNIT, value]


def needs_a_password(out):
    """sudo -n turning the job down, told apart from the job failing.

    sudo says "a password is required" (or, in older versions, "no tty
    present and no askpass program specified"). Either way the answer is to
    ask, not to report a broken switch."""
    low = (out or "").lower()
    return "password is required" in low or "askpass" in low


class AudioPage:
    # The owner's descriptions (29.9.) - what the row is for, whatever state
    # it is in. What differs by state is added behind them.
    DMNR_WORDS = _("Suppresses the echo in speakerphone calls")
    PERSIST_WORDS = _("Saves the options above")

    def on_dmnr_status(self, ok, out):
        if not ok:
            self.dmnr_ok = False
            self.dmnr_row.set_sensitive(False)
            self.dmnr_row.set_subtitle(_("not available on this device"))
            return
        self.dmnr_ok = True
        on = "state=on" in out
        self._syncing = True
        self.dmnr_row.set_active(on)
        self._syncing = False
        # The tool reports both, because one cannot be read off the other:
        # switched on now and not remembered looks identical until the reboot.
        remembered = "persistent=yes" in out
        if on:
            self.dmnr_row.set_subtitle(
                self.DMNR_WORDS if remembered else
                self.DMNR_WORDS + _(" · until the next reboot"))
        else:
            self.dmnr_row.set_subtitle(
                self.DMNR_WORDS if not remembered else
                self.DMNR_WORDS + _(" · on again after the next reboot"))

    def on_status(self, ok, out):
        profile, persistent, server, sinks = "unknown", "unknown", "-", "-"
        warn = None
        fell_back = None
        testmode = False
        for line in out.splitlines():
            if line.startswith("Profile (active):"):
                profile = line.split(":", 1)[1].strip()
            elif line.startswith("Profile (persistent):"):
                persistent = line.split(":", 1)[1].strip()
            elif line.startswith("WARNING:"):
                warn = line.split(":", 1)[1].strip()
            elif line.startswith("Fell back:"):
                # "2026-09-28 17:50:01 pw-hal - that profile gave ..."
                fell_back = line.split(":", 1)[1].split(" - ")[0].strip()
            elif line.startswith("Test mode:"):
                testmode = line.split(":", 1)[1].strip().startswith("yes")
            elif line.startswith("Pulse server:"):
                server = line.split(":", 1)[1].strip()
            elif line.startswith("Sinks:"):
                sinks = line.split(":", 1)[1].strip()

        # What survives a reboot is not what is running: audioctl keeps both,
        # and "try" changes only the first of them. Showing one and calling it
        # the state is how this window claimed the shipped stack was set while
        # the phone had been on pw-hal permanently for two days.
        sticks = profile != "unknown" and persistent == profile and not testmode

        # Nothing came back that names a profile: say that, and leave both
        # switches where they are. Showing them off would be a statement about
        # a phone this window knows nothing about - and "off" happens to be
        # the shipped state, so it would be a plausible, wrong one.
        self.audio_ok = profile != "unknown"
        if not self.audio_ok:
            self.row_profile.set_subtitle(_("audioctl did not answer"))
            self.row_server.set_subtitle(server_in_words(server))
            self.row_sinks.set_subtitle(sinks.replace(",", ", ") or _("none"))
            self.persist_row.set_subtitle(_("audioctl did not answer"))
            self.set_busy(self.busy)
            return

        text = profile_in_words(profile)
        if persistent == "unknown":
            pass
        elif sticks:
            text += _(" - permanent")
        else:
            text += _(" - until the next reboot, then {profile}").format(
                profile=profile_in_words(persistent))
        if warn:
            text += f" | {warn}"
        if fell_back:
            # The boot check put the phone back on the shipped stack because
            # the chosen one gave no sound - most likely after an update. The
            # switch shows the result; this says why it moved by itself.
            when, _sp, was = fell_back.rpartition(" ")
            text += _(" | fell back by itself on {when}: {profile} gave "
                      "no sound at boot").format(
                when=when, profile=profile_in_words(was))
        self.row_profile.set_subtitle(text)
        self.row_server.set_subtitle(server_in_words(server))
        self.row_sinks.set_subtitle(sinks.replace(",", ", ") or _("none"))

        # Follow the switch without triggering a toggle while doing it.
        self._syncing = True
        self.switch_row.set_selected(1 if profile == "pw-hal" else 0)
        # This one is both a report and a choice: it says whether what is
        # running now is what the phone comes back to, and it decides between
        # "set" and "try" for the next switch.
        self.persist_row.set_active(sticks)
        self._syncing = False
        if sticks or persistent == "unknown":
            self.persist_row.set_subtitle(self.PERSIST_WORDS)
        else:
            self.persist_row.set_subtitle(
                self.PERSIST_WORDS + _(" · a reboot returns to {profile}").format(
                    profile=profile_in_words(persistent)))
        # Re-applied, not released. This answer arrives from every refresh,
        # and refreshes run while other things are in flight - a battery
        # change, the first one at start-up - so releasing here handed the
        # controls back in the middle of a modem switch or an install, and a
        # second tap started a second pkexec beside the first. And on a phone
        # without audioctl it never arrived at all, so every other page's
        # switch left the window grey for good. Whoever set busy releases it.
        self.set_busy(self.busy)


    def on_switch(self, row, _param):
        if self._syncing or self.busy:
            return
        want_pw = server_at(row.get_selected()) == "pw-hal"
        mode = "set" if self.persist_row.get_active() else "try"
        audioctl = self.live["audio"]
        argv = ([audioctl, mode, "pw-hal"] if want_pw
                else [audioctl, "set", "standard"])
        self.set_busy(True)
        self.pulse_start(_("Switching …"))
        process.run_async(argv, self.on_switched, on_line=self.on_progress_line)

    def on_switched(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
        if not ok:
            self.toast(_("Switching failed"))
            self.report(out or _("No output."))
        else:
            last = [l for l in out.splitlines() if l.strip()]
            self.toast(last[-1].strip() if last else _("Done"))
        self.refresh()

    def on_btx_status(self, ok, out):
        """audioctl bt-extras status: bt-extras=on|off, profile, and what
        actually runs (all, basic, none). An audioctl without the command
        answers with its usage - then there is no row."""
        values = dict(z.split("=", 1) for z in (out or "").splitlines()
                      if "=" in z)
        effective = values.get("effective")
        if not ok or effective not in ("all", "basic", "none"):
            self.btx_ok = False
            self.btx_row.set_visible(False)
            return
        self.btx_row.set_visible(True)
        self.btx_ok = True
        self._syncing = True
        self.btx_row.set_active(values.get("bt-extras") == "on")
        # The description is the owner's (29.9.). Under PulseAudio it says
        # what is missing there, because the row looks the same.
        words = _("Enables the helper that makes sure audio and microphone "
                  "are set correctly")
        if values.get("profile") != "pw-hal":
            words += _(" - with PulseAudio only reconnect, pause, and a "
                       "headset that connected as the wrong kind of device; "
                       "not tested there yet")
        self.btx_row.set_subtitle(words)
        self._syncing = False
        self.btx_row.set_sensitive(self.btx_ok and not self.busy)

    def on_btx(self, row, _param):
        if self._syncing or self.busy or not self.btx_ok \
                or not self.live.get("audio"):
            return
        self.set_busy(True)
        process.run_async([self.live["audio"], "bt-extras",
                           "on" if row.get_active() else "off"],
                          self.on_btx_done)

    def on_btx_done(self, ok, out):
        self.set_busy(False)
        if not ok:
            self.toast(_("Could not change the Bluetooth helpers"))
            self.report(out or _("No output."))
        else:
            last = [l for l in (out or "").splitlines() if l.strip()]
            self.toast(last[-1].strip() if last else _("Done"))
        self.refresh()

    def on_dmnr(self, row, _param):
        if self._syncing or self.busy:
            return
        # The same reading of the persist switch as the stack switch above:
        # "set" is now and after the next reboot, the bare word is now only.
        wanted = "on" if row.get_active() else "off"
        self._dmnr_args = (["set", wanted] if self.persist_row.get_active()
                           else [wanted])
        self.apply_dmnr()

    def apply_dmnr(self, secret=None):
        """Run the helper, and with a password when sudo wants one.

        The helper is a script with its own sudo lines - bind mounts, the
        modem's tuning memory - and it runs as this user, not under sudo: it
        restarts the user's audio stack at the end, which root cannot reach.
        So there is no "sudo -S" in front of it to pipe a password into. On
        a phone whose sudoers asks for nothing that never mattered; with a
        password its first sudo had no terminal to ask at, and the switch
        failed. Same answer as the installers: the password goes to sudo
        through the askpass socket, never through argv or a file."""
        argv = [tools._tool_maybe(DMNR) or DMNR] + list(self._dmnr_args)
        env = None
        if secret is not None:
            self._dmnr_askpass = askpass.Askpass(secret)
            helper = self._dmnr_askpass.start()
            if helper is None:
                self.toast(_("no password helper: {error}").format(
                    error=self._dmnr_askpass.error))
                self._dmnr_askpass = None
                self.refresh()
                return
            env = components.installer_env(helper)
        self.set_busy(True)
        self.pulse_start(_("Switching echo suppression …"))
        process.run_async(argv,
                          lambda ok, out: self.on_dmnr_done(
                              ok, out, asked=secret is not None),
                          on_line=self.on_progress_line, env=env)

    def on_dmnr_done(self, ok, out, asked=False):
        self.pulse_stop()
        self.set_busy(False)
        if getattr(self, "_dmnr_askpass", None) is not None:
            self._dmnr_askpass.stop()
            self._dmnr_askpass = None
        # The helper checks first whether sudo can be asked at all and stops
        # before changing anything, so this is a question, not a half-done
        # switch. Asked once: a wrong password is a failure to report.
        if not ok and not asked and needs_a_password(out):
            self.ask_dmnr_password()
            return
        if not ok:
            self.toast(_("Could not switch echo suppression"))
            self.report(out or _("No output."))
        else:
            self.toast(_("Echo suppression changed - try a call"))
        self.refresh()

    def ask_dmnr_password(self):
        entry = Adw.PasswordEntryRow(title=_("Your password (for sudo)"))
        group = Adw.PreferencesGroup()
        group.add(entry)
        dlg = Adw.AlertDialog(
            heading=_("Echo suppression"),
            body=_("This lays tuning files over the vendor's and opens the "
                 "modem's tuning memory to the audio group, so sudo asks for "
                 "a password. It goes to sudo and nowhere else."))
        dlg.set_extra_child(group)
        dlg.add_response("go", _("Switch"))
        dlg.add_response("cancel", _("Cancel"))
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        self._dmnr_pending = entry
        dlg.connect("response", self.on_dmnr_password)
        dlg.present(self)

    def on_dmnr_password(self, _dlg, response):
        entry, self._dmnr_pending = self._dmnr_pending, None
        secret = entry.get_text() if entry is not None else None
        if entry is not None:
            entry.set_text("")               # not kept a moment longer
        if response != "go" or secret is None:
            # Cancelled: the row goes back to what the helper reports.
            self.refresh()
            return
        self.apply_dmnr(secret)

    def on_rescue(self, _btn):
        if self.busy:
            return
        self.set_busy(True)
        self.pulse_start(_("Restoring …"))
        # The same recovery as on the command line - one truth, not two
        # versions that can drift apart.
        process.run_async([self.live["audio"], "rescue"], self.on_rescued,
                  on_line=self.on_progress_line)

    def on_rescued(self, ok, out):
        self.pulse_stop()
        self.set_busy(False)
        self.toast(
            _("Shipped state, speaker, 65 %")
            if ok
            else _("Restore failed")
        )
        if not ok:
            self.report(out or _("No output."))
        self.refresh()

    # --- Bluetooth powersave ---
    #
    # Not part of the audio stack and not ours: batman, the battery manager
    # the phone ships with, powers the Bluetooth adapter DOWN when the screen
    # goes off and nothing is connected. It is on this page because that is
    # where somebody looking for "why is my headset silent" arrives - and
    # because the symptom is entirely an audio one: take the earbuds out of
    # their case with the screen dark and they page a controller that is not
    # there. Nothing happens until the phone is woken, and then the headset
    # is back in under a second. Measured on 16.9.2026 with btmon.

    @staticmethod
    def btsave_words(state):
        """The owner's description (29.9.), and behind it what this state
        costs: on, a headset gets back only once the phone is woken - which
        is why somebody comes looking for this row at all."""
        words = _("Turns Bluetooth off when possible to save energy")
        if state is None:
            return words + _(" · batman is not installed, so nothing does")
        if state:
            return words + _(" · a headset reconnects only once the phone is woken")
        return words

    def sync_btsave(self):
        """Follow the config file, which is the only thing that decides this.

        Read here rather than through a helper: the file is world-readable
        and this is one line of it. It is also read again after every change,
        because a switch that reports what somebody just clicked, rather than
        what is in the file, is how this window once claimed a setting it had
        failed to write."""
        try:
            with open(BATMAN_CONFIG) as handle:
                state = btsave_in_config(handle.read())
        except OSError:
            state = None
        self.btsave_ok = state is not None
        self._syncing = True
        self.btsave_row.set_active(bool(state))
        self._syncing = False
        self.btsave_row.set_subtitle(self.btsave_words(state))
        self.btsave_row.set_sensitive(not self.busy and self.btsave_ok)

    def on_codec_status(self, ok, out):
        values, known = parse_codec_status(out)
        pref = values.get("preference")
        # Unsupported is its own answer: an older furios_audio, which knew
        # no codec under PulseAudio and no setting in WirePlumber.
        # "Automatic" would claim a choice nobody can make.
        if not ok or pref not in [k for k, __, __ in CODECS]:
            self.codec_ok = False
            self.codec_row.set_sensitive(False)
            self.codec_scope_row.set_visible(False)
            self.codec_row.set_subtitle(
                _("Needs a current furios_audio"))
            return
        self.codec_ok = True
        self._codec_values = values
        self._codec_known = {k["addr"]: k for k in known}

        # Which headsets there are to choose between. None stands for all of
        # them. Only headsets that were connected once are listed - before
        # that nobody knows which codecs they have.
        per_device = values.get("per_device") == "yes" and known
        scopes = [None] + ([k["addr"] for k in known] if per_device else [])
        device = values.get("device")
        labels = [_("All")] + [
            _("{name} · connected").format(name=k["name"])
            if k["addr"] == device else k["name"]
            for k in known if per_device]
        self._syncing = True
        if labels != self._codec_scope_labels:
            self.codec_scope_row.set_model(Gtk.StringList.new(labels))
            self._codec_scope_labels = labels
        # Until somebody picks one, the list follows the headset that is
        # connected - that is the one a change is most likely meant for.
        if self._codec_scope_auto or self._codec_scope not in scopes:
            self._codec_scope = device if device in scopes else None
        self._codec_scopes = scopes
        self.codec_scope_row.set_selected(scopes.index(self._codec_scope))
        self._syncing = False
        self.codec_scope_row.set_visible(bool(per_device))
        self.codec_scope_row.set_sensitive(not self.busy)
        self.show_codec_scope()

    def show_codec_scope(self):
        """Fill the codec list for what "Applies to" says: every codec for all
        headsets, only the ones it offers for a single one."""
        values = self._codec_values
        scope = self._codec_scope
        pref = values.get("preference", "auto")
        if scope is None:
            choices, chosen = codec_choices(values), pref
            words = codec_words(values)
        else:
            known = self._codec_known[scope]
            chosen = known["choice"]
            choices = device_codec_choices(known["offered"], chosen)
            if scope != values.get("device"):
                words = _("Not connected - applies when it connects")
            elif values.get("active"):
                words = _("Playing %s") % codec_name(values["active"])
            else:
                words = _("The device is on hands-free right now")
            if chosen == "default":
                words += _(" · all: %s") % codec_name(pref)
        keys = [k for k, __, __ in choices]
        self._syncing = True
        if keys != self._codec_keys:
            self.codec_row.set_model(Gtk.StringList.new(
                [name for _k, name, _n in choices]))
            self._codec_keys = keys
        if chosen in keys:
            self.codec_row.set_selected(keys.index(chosen))
        self._syncing = False
        self.codec_row.set_subtitle(words)
        self.codec_row.set_sensitive(not self.busy)

    def on_codec_scope(self, row, _param):
        if self._syncing or self.busy or not self.codec_ok:
            return
        index = row.get_selected()
        if not isinstance(index, int) or not 0 <= index < len(self._codec_scopes):
            return
        self._codec_scope_auto = False
        self._codec_scope = self._codec_scopes[index]
        self.show_codec_scope()

    def on_codec(self, row, _param):
        if self._syncing or self.busy or not self.live.get("audio"):
            return
        index = row.get_selected()
        if not isinstance(index, int) or not 0 <= index < len(self._codec_keys):
            return
        argv = [self.live["audio"], "bt-codec", self._codec_keys[index]]
        if self._codec_scope is not None:
            argv += ["--device", self._codec_scope]
        self.set_busy(True)
        process.run_async(argv, self.on_codec_done)

    def on_codec_done(self, ok, out):
        self.set_busy(False)
        if not ok:
            self.toast(_("Could not change the Bluetooth codec"))
            self.report(out or _("No output."))
        self.refresh()

    def on_btsave(self, row, _param):
        if self._syncing or self.busy:
            return
        self.apply_btsave(row.get_active())

    def apply_btsave(self, wanted, secret=None):
        self.set_busy(True)
        self.pulse_start(_("Changing Bluetooth powersave …"))
        process.run_async(
            btsave_argv(wanted, secret),
            lambda ok, out: self.on_btsave_done(ok, out, wanted),
            stdin=None if secret is None else (secret + "\n"))

    def on_btsave_done(self, ok, out, wanted):
        self.pulse_stop()
        self.set_busy(False)
        # A password being wanted is not a failure - it is the one answer
        # this switch can do something about, so it asks instead of reporting.
        if not ok and needs_a_password(out):
            self.ask_btsave_password(wanted)
            return
        if not ok:
            self.toast(_("Could not change Bluetooth powersave"))
            self.report(out or _("No output."))
        else:
            self.toast(_("Bluetooth powersave on") if wanted
                       else _("Bluetooth powersave off"))
        self.sync_btsave()

    def ask_btsave_password(self, wanted):
        entry = Adw.PasswordEntryRow(title=_("Your password (for sudo)"))
        group = Adw.PreferencesGroup()
        group.add(entry)
        dlg = Adw.AlertDialog(
            heading=_("Bluetooth powersave"),
            body=_("This changes one line in batman's config and restarts it, "
                 "so sudo asks for a password. It goes to sudo through a "
                 "pipe and nowhere else."))
        dlg.set_extra_child(group)
        dlg.add_response("go", _("Change it"))
        dlg.add_response("cancel", _("Cancel"))
        dlg.set_default_response("cancel")
        dlg.set_close_response("cancel")
        self._btsave_pending = (wanted, entry)
        dlg.connect("response", self.on_btsave_password)
        dlg.present(self)

    def on_btsave_password(self, _dlg, response):
        wanted, entry = self._btsave_pending
        self._btsave_pending = (None, None)
        secret = entry.get_text() if entry is not None else None
        if entry is not None:
            entry.set_text("")               # not kept a moment longer
        if response != "go" or wanted is None:
            # Cancelled: the switch goes back to what the file says, not to
            # what the finger left it at.
            self.sync_btsave()
            return
        self.apply_btsave(wanted, secret)

    def run_chain(self, commands, done):
        """Run several commands one after another, stopping at the first that
        fails. The last output seen is what `done` is handed, because that is
        the one worth showing."""
        rest = list(commands)

        def step(ok=True, out=""):
            if not ok or not rest:
                done(ok, out)
                return
            process.run_async(rest.pop(0), step)

        step()
