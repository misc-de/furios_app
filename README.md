# misc-de

An app for the FuriPhone FLX1. It switches the fixes for audio, modem, GPS,
the hardware switches, security, battery icon, phosh and vibration on and
off - one tab each.

---
⚠️ **AI-assisted project**  
Large parts of this app's code and texts were written with the help of an AI
assistant (Claude) and reviewed, tested and shipped by a human maintainer.
If that matters to you, now you know.

---

The app repairs nothing itself; it drives the tools that do. A tab whose
tool is missing offers to install it. When an update is waiting, an icon
appears in the top left of the header bar.

<p>
  <img src="screenshots/overview.webp" alt="Overview" width="180">
  <img src="screenshots/audio.webp" alt="Audio" width="180">
  <img src="screenshots/modem.webp" alt="Modem" width="180">
  <img src="screenshots/switches.webp" alt="Switches" width="180">
</p>
<p>
  <img src="screenshots/battery.webp" alt="Battery" width="180">
  <img src="screenshots/phosh.webp" alt="Phosh" width="180">
  <img src="screenshots/vibration.webp" alt="Vibration" width="180">
</p>

## Install

    git clone https://github.com/misc-de/furios_app
    cd furios_app && ./install.sh

Run it without `sudo` - it asks for the password itself. Then start
**misc-de** from the app grid. Keep the folder: the app updates itself from it.

To remove it: `./uninstall.sh`. The tools behind the tabs stay installed;
each has its own uninstaller.

## The tabs

| Tab | What it does | Tool |
|---|---|---|
| Audio | Sound server, Bluetooth codec, echo suppression in calls | [furios_audio](https://github.com/misc-de/furios_audio) |
| Modem | Mobile data repairs, 5G, signal | [furios_modem_fixes](https://github.com/misc-de/furios_modem_fixes) |
| GPS | Share Wi-Fi networks with beaconDB (off until you switch it on) | [furios_gps](https://github.com/misc-de/furios_gps) |
| Switches | What the camera and network sliders take down | [furios_killswitch](https://github.com/misc-de/furios_killswitch) |
| Security | Kernel hardening, lock screen locks after wrong PINs | [furios_security](https://github.com/misc-de/furios_security) |
| Battery | Colour the battery icon, show time left | [furios_misc](https://github.com/misc-de/furios_misc) |
| Phosh | Folders at the bottom, hide search and app names, dark keyring prompt | [furios_phosh](https://github.com/misc-de/furios_phosh) |
| Vibration | Rhythm per event (calls, SMS, mail, keyboard) | built in |

The tool tabs have a **Restore shipped state** button that puts the phone back
exactly as it was, and asks first.

Requires `python3-gi` and `gir1.2-adw-1`.

## Tests

    tests/run-tests.sh

## Licence

MIT - see [LICENSE](LICENSE). The installed tools have their own licences
(audio LGPL-2.1, modem GPL-2.0); see [NOTICE](NOTICE). Design notes are in
[FINDINGS.md](FINDINGS.md).
