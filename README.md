# misc-de

A GTK4/libadwaita app for the FuriPhone FLX1 that shows and switches what has
been repaired on this phone by hand: audio, modem, location and the three
hardware switches on the case.

It repairs nothing itself. It drives the tools that do, reads their state, and
says what a decision costs.

| Tab | Tool | Repository |
|---|---|---|
| Audio | `audioctl` | [furios_pipewire](https://github.com/misc-de/furios_pipewire) |
| Modem | `modemctl` | [furios_modem_fixes](https://github.com/misc-de/furios_modem_fixes) |
| GPS | `gpsctl` | [furios_gps](https://github.com/misc-de/furios_gps) |
| Switches | `killswitch-indicator` | [furios_killswitch](https://github.com/misc-de/furios_killswitch) |

None of them has to be installed. A tab whose tool is missing is still there
and offers to fetch and install it for you; once that finishes, the tab becomes
the real one without a restart.

When a newer version of a tool is available, the page offers an update. For the
app itself, that offer is an icon in the top left of the header bar, and it
only appears when there is something to take.

## Install

Fetch the repository, then run the installer from inside it:

    git clone https://github.com/misc-de/furios_app
    cd furios_app && ./install.sh

Not with `sudo` in front - the installer asks for it where it needs it, which
is only the three lines that write to `/usr/local`.

Puts `misc-de` in `/usr/local/bin` along with its icon and launcher entry. It
then appears in the app grid, or starts with `misc-de`. Remove it again with
`./uninstall.sh`.

Keep the clone: the app updates itself out of it, and the icon in the header
bar offers the next version when there is one. The four tools behind the tabs
are fetched the same way, into `~/.local/share/misc-de/`.

Requires `python3-gi` and `gir1.2-adw-1`, and nothing else.

## What each tab does

**Audio** — who owns the Android audio HAL, whether that survives a reboot, and
the dual-microphone echo cancellation for calls.

**Modem** — the repairs to ofono2mm and ModemManager on or off, remembered or
only until the next boot, what the checks say, and how good the signal is.

**GPS** — the filter that refuses geoclue a position derived from the phone's
IP address. "Off" here does not mean "no position": it means the carrier's exit
node is published as though the phone had been seen there, and every line on
the page says so.

**Switches** — the three sliders on the case. Camera and cellular are software
shutdowns; the microphone switch physically cuts the line and is therefore
invisible to software, which the page states rather than guessing at.

Every page has the same plainly labelled way back to how the phone shipped, and
asks before it does anything.

## Tests

    tests/run-tests.sh      # no display, no root, no phone in hand
    tests/coverage.sh       # line coverage

The window is built, filled and clicked against a stand-in for PyGObject, so
this runs over ssh. What it cannot check is what a person sees — whether the
text fits 360 logical pixels, whether a tap lands where it looks. That is read
off the phone.

## Licence

MIT — see [LICENSE](LICENSE). **What the app installs is not MIT:** the audio
package is LGPL-2.1 and the modem package GPL-2.0, because of what they build
on. [NOTICE](NOTICE) lists every component with its licence.

Why the app is built this way is in [FINDINGS.md](FINDINGS.md).
