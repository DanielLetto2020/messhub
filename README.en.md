# eXpress-msgs

**A board for your Linux desktop notifications.** The app reads the notifications your system
already shows on screen (messengers, mail, browser, your own scripts), stores them in a local
database and shows them in a translucent widget with a column per source — with mail-like rules,
search and statistics. Everything runs on your computer.

[Русская версия](README.md)

![Widget](docs/widget.png)

## Features

- **Collects** standard notifications (D-Bus `org.freedesktop.Notifications`): eXpress, Telegram,
  MAX and other websites in the browser (split per site), mail, calendar, your own events.
- **Widget**: a column per source, one card per chat, avatars, mentions of your name, clickable
  links, double-click to copy, click a name to jump to the app.
- **Triage**: mark a message, chat, column or everything read (with Undo), snooze for an hour, till
  evening or morning, pin; messages are auto-read after 24 hours.
- **Mail-like rules** by source, chat, sender and text (regex too): show, hide, highlight, mark read,
  pin, play a sound, forward to Telegram. **Profiles** (“Work”, “Home”) switched by schedule.
- **Search** across the whole history; optional **smart search (RAG)** by meaning and Q&A over your
  messages via a local Ollama.
- **Statistics**, weekly report, backups, CSV/JSON export, HTTP event intake, a “long terminal
  command finished” hook, self-diagnostics, Russian and English UI.

![Source settings](docs/settings-source.png)

## Install

Linux with GNOME (or another desktop with a notification service), Python 3.9+, GTK 3 and
WebKit2GTK 4.1 GObject introspection. Ubuntu/Debian:

```bash
sudo apt install python3-gi gir1.2-gtk-3.0 gir1.2-webkit2-4.1 gir1.2-wnck-3.0 dbus-bin libnotify-bin
git clone <repository url> express-msgs && cd express-msgs
./install.sh                    # checks dependencies, enables autostart and starts it
./install.sh --terminal-hook    # plus cards about long terminal commands
```

The installer sets up `systemd --user` units (no sudo): the collector and the widget start when you
log in. Page: <http://127.0.0.1:8765>, settings — the gear in the widget.

**Update:** `git pull && ./install.sh` — the widget reloads itself with the new version.
**Uninstall:** `./uninstall.sh` (keeps data) or `./uninstall.sh --purge`.

### Telegram Desktop

On Linux, Telegram shows its own pop-ups by default, bypassing the system — no app can see them.
In Telegram enable “Settings → Notifications and Sounds → System integration → **Use native
notifications**”. See Help inside the app.

### Wayland

The app fully works in an X11 session. On Wayland the widget can be moved and resized by mouse, but
its position isn't restored, it can't stay below other windows, and “go to app” uses the app's
launcher: these are Wayland's limits for applications.

## Privacy

Data never leaves your computer: the database lives in `~/.local/share/express-msgs`, settings in
`~/.config/express-msgs`, apart from the code. The app does not read other apps' data — only the
notifications you already see on screen. Only what you enable yourself goes out: rule-based
forwarding to Telegram and the weekly report. Smart search uses a local Ollama.

## Development

Python standard library only (plus GTK/WebKit via `gi` for the widget window).

```bash
python3 collect.py              # collector + page without installing (Ctrl+C to stop)
python3 widget.py               # the widget window
cd tests && python3 -m unittest discover -s . -t .    # tests
```

See [CONTRIBUTING.md](CONTRIBUTING.md) and [CHANGELOG.md](CHANGELOG.md).

## License

[Apache License 2.0](LICENSE). You may use, modify and redistribute it, including as part of other
software, **provided the attribution in the [NOTICE](NOTICE) file is kept** in all copies and
derivative works.
