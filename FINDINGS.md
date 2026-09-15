# What came out of it

The README says what the app is and how to use it. This file says *why* it is
built the way it is: the decisions behind the interface, the mechanics of
installing, and the places that cost time.

Device: FuriPhone FLX1 (radon), FuriOS with phosh.

## From the README

The README was cut down to what is needed to use the thing. What follows stood
there until then: the reasons, the measurements and the trade-offs behind the
decisions.

## The app updates itself - without a tab

The app is a component like the tools (`misc-de`, this repo): the same clone,
the same installer. What it is not is something you *operate* on a page - it
IS the page. A fifth tab for it cost a fifth of the switcher bar on every
other page, to say which file the window runs from; and the one thing it was
there for - taking the next version - does not have to wait behind a tab
nobody opens.

So it sits in the header bar: **an icon at the top left that only appears when
there is a newer version.** What was found and where it would come from is in
its tooltip. Pressing it starts nothing yet, it asks back - the same question
every other component gets, with the steps that would run and the password
field for `sudo`. Afterwards the icon is gone again; it was the answer to a
question that has been answered.

(There used to be a "reload" button at the top right. It produced exactly the
state that was already on screen - the window asks by itself when it opens,
after every switch and after every install.)

What is asked is different from the tools: not only whether there are new
commits on the server, but whether the **running program is the same as the
`misc-de.py` in the clone**. On this phone the next version is written in
exactly that clone; so it is never behind the server, but regularly ahead of
what is installed. Then the offer reads "reinstall": nothing is fetched, only
`./install.sh` is run in that clone - a `git pull` would be the wrong
question, and its guard would refuse the install along with it if anything
were uncommitted.

Afterwards the old version is still running in this window, so it asks whether
it should restart itself. Restarting means `execv`: the same process is
replaced by the new program. A second instance would not be one - the
application ID makes it hand its activation to the running one, and that one
then presents the OLD window.

## When a tool is missing

Every tab is there, even when its tool is not. It then shows exactly three
things - what it would do, which repository that comes from, and what
installing will do - and an **Install** button. Nothing else: switches and
status rows with nothing behind them would be props, and a page full of greyed
out controls looks like a broken phone rather than a missing package.

It is fetched to `~/.local/share/misc-de/<repo>` and installed from there.
Three of the installers write to `/usr/local` and need root; this phone has no
polkit agent (`pkexec` answers "No authentication agent found"), so it is done
the way it is done in a terminal: `sudo` asks for the password once, the
script runs as you, and only its own sudo lines become root. Afterwards
`sudo -k` throws the ticket away.

The ticket alone cannot be relied on, and that is not theory: on 14.9.2026 a
sudoers rule fell away on this phone, and the GPS install stopped at its first
sudo line - cloned, nothing installed, `sudo: a terminal is required to read
the password`. Without a terminal sudo hangs its timestamp not on a TTY but on
the parent process, and the installer's bash is not the parent process that
`sudo -v` had. So the installer additionally gets `SUDO_ASKPASS`: a five-line
helper with no secret in it, which fetches the password over a socket in
`$XDG_RUNTIME_DIR` - directory 0700, and the other end checks the uid of the
caller. That way every sudo line of every installer may ask, as often as it
likes. (Plus `DISPLAY` if it is missing: sudo only reaches for `SUDO_ASKPASS`
when it believes somebody could see a graphical question - it is never
opened.)

The password goes through the pipe to `sudo` and through that socket and
nowhere else - not into `argv`, where every `ps` reads along, not into a file,
not into the environment, not into a log line - and it is gone from the entry
field as soon as the question has been answered. A wrong password is reported
by `sudo` in its own words; the chain stops there rather than starting an
installer that cannot finish. If everything goes through, the offer turns into
the real page immediately - in the same place in the switcher bar, and the app
stands on it afterwards. No restart: the tool is on the phone at that moment,
there is nothing left to wait for.

## When there is something new in the repo

At start the app looks once whether the installed tools still match the state
of their repository. If there is something new, a group "Update available"
appears at the **foot of the page concerned** with what is waiting there and
an **Update** button - for the app itself the icon at the top left of the
header bar. If there is nothing - or the question could not be answered
because the phone has no network at the moment - nothing appears at all. An
offer that is always there says nothing.

How it looks depends on who owns the clone:

- **Ours** (in `~/.local/share/misc-de`): `git fetch`, then count how many
  commits are waiting.
- **Yours** (found by the origin URL, not by the directory name - the same
  repository is called `furios_gps_fix` here and `furios_gps` upstream):
  `git ls-remote` asks the server for its HEAD, `git rev-parse` reads the
  clone's. **No fetch, no pull** - that would write into somebody else's
  `.git`.

An update in a clone that belongs to you says so in the question, and it
begins with a guard: if anything uncommitted is there, **nothing** is touched
and the reason stands there as a sentence. It pulls `--ff-only` - a merge is
not a decision an app makes for somebody else's working tree.

Once the update is through, the offer disappears: it was the answer to commits
that are here now.

## What each page does

**Audio** - who owns the Android HAL (PipeWire directly or PulseAudio as
shipped), whether that survives a reboot, and MediaTek's dual-microphone echo
cancellation for calls. Below it stands what is actually running.

**Modem** - the repairs to ofono2mm/ModemManager on or off, remembered or only
until the next boot, what the checks say and how good the signal is.

**GPS** - the filter that refuses geoclue a position derived from the IP
address. "Off" here does not mean "no position", it means: the position of the
carrier's exit node is published as though the phone had been seen there. That
is why every row of that page says what "off" means.

**Switches** - the three sliders on the case. Camera and network are software
shutdowns (Android stops the service), the microphone switch really cuts the
line - and is invisible to software for exactly that reason. The page does not
listen after it: that would mean opening the microphone, and the answer would
hold only for the seconds of the measurement. It says so.

**Battery** - three options, and nothing else on the page: colour while
charging (the bolt), colour by charge level (the filling), colour an unusual
drain (the frame). Under each option, revealed with it, the two sliders that
say when green, amber and red appear. No readings: a watt figure belongs
where somebody is measuring, and here the only question is which colour
appears when. A switch is on only when the setting AND the service behind it
are - an option left on in the file with the daemon stopped would be a switch
with nothing behind it.

## Rules the interface is built on

- **Rows instead of paragraphs.** What has to be said stands in the subtitle
  of the row it is about. On a phone nobody reads the essay above the switch.
- **One way back, the same everywhere.** Every page has the same group "Back
  to how it shipped" with the same plain button. No colours: blue would say
  "do this", red would say "careful", and which applies depends on the page -
  that is what the text beside it is for.
- **Ask first.** No way back acts on the bare tap. The question repeats
  exactly the text that stands next to the button; cancel is the default and
  also the meaning of tapping away.
- **Never claim more than is known.** A tool that does not answer greys out
  its switches and says so. A radio reporting `null` is "not reachable" and
  not "off".
- **Every helper call is capped** (90 s). systemctl can wait for a job that is
  itself waiting, and pkexec inherits that; without a cap the window stood
  grey with a pulsing bar.

## Origin

Until 14.9.2026 the app lived in
[furios_pipewire](https://github.com/misc-de/furios_pipewire) under `gui/`. It
moved here with its history, because it now drives five tools from five
repositories and none of them is its home.
