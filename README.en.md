# messhub

**One window for all the notifications on your Linux computer.**

Messages from your work messenger, Telegram, MAX, WhatsApp, mail and your own scripts land on one
tidy board on your desktop. The pop-up is gone - the message stays. And nothing leaves your computer.

> 🔒 **Everything stays on your computer.** messhub sends your messages nowhere: not to its own servers
> (there are none), not to a cloud, not to analytics. The database lives in your user folder; processing
> and search happen right there. Only what you turn on yourself in the settings goes out.

[Русская версия](README.md)

![The messhub board on the desktop](docs/screens/en/widget.png)

*All people and messages in the pictures are made up.*

## Where the idea came from

When you work at a computer, notifications come from everywhere: the work chat, family Telegram,
the building chat, mail, build results. Each pop-up stays for a couple of seconds and is gone. You
step out for lunch, sit through a call, get busy in another window - and you no longer know what you
missed. So you open every app one by one and scroll.

messhub grew out of a simple thought: my computer already shows me all these notifications - let
it remember them too. Put them in one place, sort them by app, and keep the important ones from
drowning in the stream. No cloud and no access to the conversations themselves - only what was on
the screen anyway.

## What problems it solves

- **"What did I miss?"** Everything that arrived while you were away stays on the board until you
  mark it read. After a day, old messages clear themselves.
- **Ten apps instead of one window.** No need to open each one to check for news: one board, one
  column per app.
- **The important stuff drowns in noise.** Mail-like rules: hide the chatty chat, pin messages
  from your manager, highlight mentions of your name, play a sound for urgent ones.
- **Sharing your screen on a call.** One button blurs every message so colleagues don't read too much.
- **You'd rather not hand your messages to a service.** Everything is stored and processed on your
  computer. Only what you turn on yourself goes out (for example, forwarding important messages to
  Telegram).

## What it looks like

### The board on your desktop

A translucent window at the bottom of the screen. Move and resize it with the mouse, or lock it in
place and keep it below other windows. On every card: ✓ - read, ⏰ - snooze, 📌 - pin,
ⓘ - "why is this here?". Click a name to open the app, double-click the text to copy it, links
open in the browser.

**Snooze** - the message disappears and comes back in an hour, in the evening or tomorrow morning.

![Snooze a message](docs/screens/en/widget-snooze.png)

**"Why is this here?"** - see which rule highlighted, pinned or hid a message.

![Why a message is highlighted](docs/screens/en/widget-why.png)

**Close a column** - its messages are marked read, and the column comes back with the next new
message. You can also hide it for good.

![Close a column](docs/screens/en/widget-close.png)

**Focus mode** (key F) - only what matters: pinned, highlighted and mentions.

![Focus mode](docs/screens/en/widget-focus.png)

**Blur for screen sharing** (key B).

![Blur](docs/screens/en/widget-privacy.png)

**Light theme**, opacity and text size - in the settings.

![Light theme](docs/screens/en/widget-light.png)

### Settings

Open them with the gear in the corner of the board.

**Sources** - every app that has sent notifications. Rename any of them and give it your own icon.

![Sources](docs/screens/en/settings-sources.png)

**A source** - who wrote and what to show. For every chat and sender you see whether it reaches the
board, and one click creates a rule for it.

![Source settings](docs/screens/en/settings-source.png)

**Mail-like rules** - a condition (chat, sender, words in the text) and an action: show, hide,
highlight with a color, mark read right away, pin, play a sound, forward to Telegram.

![Rule editor](docs/screens/en/settings-rule-editor.png)

**Rules for all** - apply to every app at once: for example, a sound for the word "urgent".

![Rules for all](docs/screens/en/settings-rules.png)

**Profiles** - sets of rules: "Work" on weekdays, "Home" in the evenings and at weekends. Switch
them by hand or let a schedule do it.

![Profiles](docs/screens/en/settings-profiles.png)

**Mentions** - your name and nicknames: such messages are highlighted and shown in focus mode.

![Mentions](docs/screens/en/settings-mentions.png)

**Search** across the whole history, including read and hidden messages. Bring anything you find
back to the board. Optionally - smart search by meaning and answers to questions ("when was the
call moved?") through an AI model that runs on your own computer.

![Search](docs/screens/en/settings-search.png)

**Appearance** - language, opacity, text size, theme, density, avatars.

![Appearance](docs/screens/en/settings-look.png)

**Statistics** - who writes the most, which chats are the noisiest (with a "hide" button right
there), at what hours most messages arrive.

![Statistics](docs/screens/en/settings-stats.png)

**Data** - how long to keep history, daily backups with one-click restore, export to a spreadsheet
(CSV) or JSON.

![Data](docs/screens/en/settings-data.png)

**Mail** - two ways to choose from: take mail app notifications, or check mailboxes directly
(Yandex, Mail.ru, Gmail, Outlook, iCloud or your own server). Connect as many mailboxes as you like;
messages stay unread on the server.

![Mail](docs/screens/en/settings-mail.png)

**Telegram forwarding** - important messages go to your Telegram by rule when you're away from the
computer. Also a weekly report: how much came from where, the noisiest chats.

![Telegram forwarding](docs/screens/en/settings-forward.png)

**Event intake** - scripts, builds, a smart home or another computer can post cards to the board
over the network, with a key.

![Event intake](docs/screens/en/settings-ingest.png)

**System** - the app checks itself and tells you what to fix. Autostart at login is here too.

![System](docs/screens/en/settings-system.png)

**Help** - instructions: getting Telegram to cooperate, sending your own events, Wayland notes.

![Help](docs/screens/en/settings-help.png)

## Install

All files are on the [releases page](https://github.com/DanielLetto2020/messhub/releases/latest). Pick your
system. Admin rights are needed only for the Linux packages (the package manager installs them).

| system | file | in short |
|---|---|---|
| Ubuntu, Debian, Mint and other Debian-based | `messhub_<version>_all.deb` | `sudo apt install ./messhub_*_all.deb` |
| Fedora, openSUSE, RHEL-like | `messhub-<version>-1.noarch.rpm` | `sudo dnf install ./messhub-*.noarch.rpm` |
| any other Linux | `messhub-<version>.tar.gz` | unpack and run `./install.sh` |
| Windows 10 / 11 (beta) | `messhub-<version>-windows-x64.msi` | double-click - regular install |
| Windows 10 / 11 (beta) | `messhub-<version>-windows-setup.bat` | install without an installer |
| Windows 10 / 11 (beta) | `messhub-<version>-windows-portable.zip` | portable, no install |
| to verify | `SHA256SUMS.txt` | checksums of all files |

### Linux

You need the GNOME desktop (Ubuntu, Fedora, Debian, Mint and others); a "GNOME on Xorg" session works best.

**Ubuntu, Debian, Mint - `.deb` package**

```bash
sudo apt install ./messhub_*_all.deb        # in the folder you downloaded it to; dependencies come along
```

**Fedora, openSUSE - `.rpm` package**

```bash
sudo dnf install ./messhub-*.noarch.rpm     # Fedora
sudo zypper install ./messhub-*.noarch.rpm  # openSUSE
```

Then start **messhub** from the app menu (or run `messhub`): the board appears at the bottom of the screen
and starts by itself when you log in. Settings - the gear in its corner. Update - install the new package
over the old one; uninstall - `sudo apt remove messhub` / `sudo dnf remove messhub` (the history stays in
`~/.local/share/messhub`).

**Any other Linux - `.tar.gz` archive**

```bash
tar -xzf messhub-*.tar.gz
cd messhub-*/
./install.sh            # checks what's missing and tells you the command for your distro
```

It installs just for you, without sudo, and starts by itself when you log in. Uninstall - `./uninstall.sh`
(keeps the history) or `./uninstall.sh --purge` (deletes it too).

**From source (for the latest code)**

```bash
sudo apt install git python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-wnck-3.0 dbus-bin libnotify-bin
git clone https://github.com/DanielLetto2020/messhub.git
cd messhub
./install.sh            # to update later: git pull && ./install.sh
```

### Windows 10 and 11 (beta)

**`.msi` installer** - download and double-click. No admin rights needed: it installs just for you into
`%LOCALAPPDATA%\Programs\messhub`, adds a Start menu shortcut and starts with Windows. Uninstall -
Settings → Apps → messhub → Uninstall.

**`.bat` setup** - download `messhub-…-windows-setup.bat` and double-click it: it downloads the portable
version, installs it to the same place and creates a shortcut. Uninstall - run the same file with
`/uninstall` (from a command prompt: `messhub-…-windows-setup.bat /uninstall`).

**Portable `.zip`** - unpack anywhere (even a USB stick) and run `messhub.exe`. The database and settings
stay next to it, in the `data` folder. Uninstall - delete the folder.

On first start Windows asks whether messhub may read notifications - allow it (if you declined:
Settings → Privacy & security → Notifications). It needs the WebView2 engine - already in Windows 11 and
updated Windows 10. The app isn't code-signed yet, so Windows may warn about an "unknown publisher":
More info → Run anyway. Windows 7 is not supported: it has no system notification center. The Windows
version is new - if something is off, open an [issue](https://github.com/DanielLetto2020/messhub/issues/new/choose).

### Verify the download

```bash
sha256sum -c SHA256SUMS.txt --ignore-missing      # Linux: next to the downloaded files
certutil -hashfile messhub-…-windows-x64.msi SHA256   # Windows: compare with SHA256SUMS.txt
```

### If Telegram messages don't show up

On Linux, Telegram Desktop shows its own pop-ups by default, bypassing the system, so nobody can see
them. In Telegram turn on **Settings → Notifications and Sounds → Use native notifications**, and
keep the sender name and message preview on.

## Privacy in plain words

- messhub sees **only the notifications** your computer has already shown you. It doesn't look into
  the apps, their databases or conversations.
- The history is kept **only on your computer** (`~/.local/share/messhub`). No servers, accounts or
  analytics.
- Only what you turn on leaves the computer: forwarding to Telegram, the weekly report and checking
  your own mailboxes (read-only). Smart search uses an AI model on your own computer.
- Passwords and keys are stored in files only you can read and are never sent anywhere.
- Every 12 hours the app asks GitHub for the latest version number to show "a new version is out".
  Nothing about you is sent; turn it off under Settings → System.

## FAQ

**Will I see messages that arrived while the computer was off?** No. messhub remembers what was
shown as a notification. The exception is mail from connected mailboxes: new mail comes in at the
next check.

**Why are there no messages from the chat I have open?** Apps don't show notifications for the chat
you're already looking at, so there's nothing to remember.

**Sometimes only the beginning of a long message arrives.** That's how the app itself showed it:
notifications often carry just the start of the text and "photo" or "file" instead of attachments.

**Does it work on Windows or macOS?** Linux - yes, Windows 10 and 11 - yes (beta). Not Windows 7: it has no
system notification center an app could read. No macOS.

**And on Wayland?** Yes, with Wayland's own limits: the board can't remember its position on screen
or stay below other windows. See Help inside the app.

**Do I need an AI model?** No. Everything except smart search works without one. Turn smart search
on in the settings if you want it.

## For developers

The app is written in Python with no external dependencies (GTK and WebKit for the window come from
the system). The program is in `app/`, packaging in `packaging/` and `tools/`, tests in `tests/`.
How the code is organized and how to run the tests - see [CONTRIBUTING.md](CONTRIBUTING.md); version
history - [CHANGELOG.md](CHANGELOG.md).

**Pull requests are accepted only into the [`contrib`](https://github.com/DanielLetto2020/messhub/tree/contrib)
branch**: fork, branch off `contrib` and open the PR against `contrib`. Only releases go to `main`.
Bugs and ideas - [issues](https://github.com/DanielLetto2020/messhub/issues/new/choose), with ready-made forms.

## License

[Apache License 2.0](LICENSE). You may use, modify and redistribute it, including as part of other
software, on one mandatory condition: **keep the [NOTICE](NOTICE) file and credit the author exactly
as "Кузьминский Максим i@m-letto.ru"** in all copies and derivative works.
