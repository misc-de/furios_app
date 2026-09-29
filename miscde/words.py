# SPDX-FileCopyrightText: Copyright (c) 2026 misc-de
# SPDX-License-Identifier: MIT
"""Turning what a tool prints into what a row says."""

from .i18n import _




def server_in_words(raw):
    """PipeWire's PulseAudio interface announces itself as
    "PulseAudio (on PipeWire 1.6.6)". Reading that underneath a switch which
    says "PipeWire holds the HAL" rightly looks like a contradiction. So
    translate it."""
    if not raw or raw == "-":
        return _("not reachable")
    if "PipeWire" in raw:
        ver = ""
        for token in raw.replace(")", " ").split():
            if token[:1].isdigit():
                ver = " " + token
                break
        return _('PipeWire{0} - also speaks PulseAudio for older apps').format(ver)
    if raw.lower().startswith("pulseaudio"):
        return _("PulseAudio - the shipped setup")
    return raw


PROFILE_WORDS = {
    "pw-hal": _("PipeWire owns the HAL"),
    "standard": _("PulseAudio owns the HAL (as shipped)"),
    "pw-tunnel": _("PulseAudio owns the HAL, PipeWire gets a sink"),
}


def profile_in_words(p):
    return PROFILE_WORDS.get(p, p)
