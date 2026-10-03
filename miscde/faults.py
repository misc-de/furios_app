# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Is the fault a switch repairs actually there on this phone?

A repair is offered only where the fault it repairs is present - or where
ours is already in place, because then the switch is the way back and has
to stay (3.10.2026, on request). These are the "is it there" halves: cheap,
read-only, no root, and each one a fact about the phone rather than about
this app. True: the fault is there. False: it is not. None: could not tell -
which counts as "not there", since a repair nobody can show is needed is
exactly what is not to be offered.

Every reader takes its path as an argument, so the tests can hand in a file
of their own instead of reading this phone.
"""

import os
import re

# --- automatic brightness: the sensor's unit ----------------------------------
#
# The fault is a disabled iio-sensor-proxy: nothing brings it back once it is
# off. FuriOS ships it enabled (FuriLabs #277), so on most phones there is
# nothing to repair - only the key, which the shell's own settings set.


def sensor_unit_off(state):
    """state is sensor_state()'s (enabled, active)."""
    return not all(state)


# --- keyring prompt -----------------------------------------------------------
#
# The fault: D-Bus starts the bare gcr-prompter when gnome-keyring asks before
# phosh has claimed the name. That is only possible while the shipped service
# file points at gcr-prompter.
SHIPPED_PROMPTER = ("/usr/share/dbus-1/services/"
                    "org.gnome.keyring.SystemPrompter.service")


def prompter_falls_back(path=SHIPPED_PROMPTER):
    text = _read(path)
    if text is None:
        return False
    return re.search(r"^Exec=\S*gcr-prompter\b", text, re.M) is not None


# --- portals ------------------------------------------------------------------
#
# The fault: xdg-desktop-portal waits a minute for a wlr backend that cannot
# start here. Without xdg-desktop-portal-wlr installed there is nothing to
# wait for.
WLR_PORTAL = "/usr/share/xdg-desktop-portal/portals/wlr.portal"


def wlr_portal_waits(path=WLR_PORTAL):
    return os.path.exists(path)


# --- network and camera sliders -----------------------------------------------
#
# The fault: a loose contact - the slider flaps with nobody touching it. The
# kernel counts every edge of the slider's line, readable by anyone. A hand
# moves it a few times a day; this phone's flapped 44 times in 12 hours and
# 65 times in one afternoon. Twelve edges and more than one an hour since
# boot is past anything a hand does, and well inside what a loose contact does.
FLAP_EDGES = 12
FLAP_PER_HOUR = 1.0


def switch_edges(interrupts, name):
    """The edge count of one slider's line, or None where it is not listed."""
    for line in (interrupts or "").splitlines():
        fields = line.split()
        if fields and fields[-1] == name:
            # One column per CPU after "NNN:", then the controller's name -
            # whose hardware number is digits too and must not be counted.
            counts = []
            for f in fields[1:]:
                if not f.isdigit():
                    break
                counts.append(int(f))
            return sum(counts) if counts else None
    return None


def switch_flaps(interrupts, uptime_s, names=("nwk_switch", "cam_switch")):
    if not uptime_s or uptime_s <= 0:
        return None
    hours = uptime_s / 3600.0
    for name in names:
        edges = switch_edges(interrupts, name)
        if edges is not None and edges >= FLAP_EDGES \
                and edges / hours > FLAP_PER_HOUR:
            return True
    return False


def sliders_flap(interrupts="/proc/interrupts", uptime="/proc/uptime"):
    text, up = _read(interrupts), _read(uptime)
    try:
        seconds = float((up or "").split()[0])
    except (IndexError, ValueError):
        return None
    return switch_flaps(text, seconds)


# --- echo suppression (DMNR) ----------------------------------------------------
#
# The fault: the vendor tuning switches handsfree DMNR off, or /dev/usip is
# closed to the audio HAL. furios-audio-dmnr's status names both.


def dmnr_missing(status):
    for line in (status or "").splitlines():
        text = line.strip()
        if text.startswith("usip:") and " closed" in text:
            return True
        key, sep, value = text.partition("=")
        if sep and key.strip().startswith("MTK_") and value.strip() == "no":
            return True
    return False


# --- Bluetooth power saving -----------------------------------------------------
#
# The fault: batman takes the adapter down with the screen. Only BTSAVE=true
# does that; with batman's file missing there is nothing to switch.


def btsave_bites(state):
    """state is btsave_in_config()'s answer: True, False or None."""
    return state is True


# --- modem ------------------------------------------------------------------
#
# The fault: a check of modemctl status failing - an ofono2mm file not
# patched, a route or a resolver missing. modemctl prints FAIL for each.


def modem_checks_fail(status):
    return any("FAIL" in line for line in (status or "").splitlines())


# --- Firefox and the satellite fix ---------------------------------------------
#
# The fault: Firefox gives up after 12 seconds. Without a Firefox profile
# there is no Firefox to give up.


def firefox_profiles(values):
    try:
        return int(values.get("profiles", "0")) > 0
    except ValueError:
        return False


# --- hardening ------------------------------------------------------------------


def sysctl_open(part):
    """A key whose value secctl reports as not what it wants."""
    keys = part.get("keys") or {}
    return any(isinstance(k, dict) and k.get("ok") is False
               for k in keys.values())


def loadable_modules(names, modules_dep):
    """Which of the names the running kernel can load as a module."""
    text = _read(modules_dep) or ""
    found = set()
    for line in text.splitlines():
        path = line.split(":", 1)[0]
        base = os.path.basename(path)
        for suffix in (".ko", ".ko.xz", ".ko.gz", ".ko.zst"):
            if base.endswith(suffix):
                found.add(base[:-len(suffix)].replace("-", "_"))
                break
    return [n for n in names if n.replace("-", "_") in found]


def modules_dep_path():
    try:
        release = os.uname().release
    except AttributeError:
        return None
    return os.path.join("/lib/modules", release, "modules.dep")


def modules_loadable(part, modules_dep=None):
    names = list((part.get("modules") or {}).keys())
    path = modules_dep or modules_dep_path()
    if not names or not path:
        return None
    return bool(loadable_modules(names, path))


PAM_AUTH = "/etc/pam.d/common-auth"


def pin_tries_unlimited(path=PAM_AUTH):
    """Nothing in the auth stack counts failures."""
    text = _read(path)
    if text is None:
        return None
    live = [l for l in text.splitlines() if not l.lstrip().startswith("#")]
    return not any(m in l for l in live
                   for m in ("pam_faillock", "pam_tally", "pam_furios_lockout"))


def _read(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read(1 << 20)
    except OSError:
        return None
