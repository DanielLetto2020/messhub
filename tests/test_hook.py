"""Хук терминала: долгая команда → notify-send с кодом выхода (notify-send подменён)."""
import os
import shutil
import stat
import subprocess
import unittest

import common

HOOK = os.path.join(common.ROOT, "app", "hooks", "long-command.sh")


@unittest.skipUnless(shutil.which("bash"), "нужен bash")
@unittest.skipIf(os.name == "nt" or not shutil.which("bash"), "хук терминала — для bash/zsh на Linux")
class HookTest(unittest.TestCase):
    def run_hook(self, script, lang="ru_RU.UTF-8"):
        bindir = os.path.join(common.TMP, "bin")
        os.makedirs(bindir, exist_ok=True)
        log = os.path.join(common.TMP, "notify.log")
        fake = os.path.join(bindir, "notify-send")
        with open(fake, "w") as f:
            f.write(f'#!/bin/sh\nprintf "%s|" "$@" > "{log}"\n')
        os.chmod(fake, os.stat(fake).st_mode | stat.S_IEXEC)
        if os.path.exists(log):
            os.remove(log)
        env = dict(os.environ, PATH=bindir + ":" + os.environ["PATH"], LANG=lang, MESSHUB_LONG_CMD="0")
        subprocess.run(["bash", "-c", f'source "{HOOK}"; {script}'], env=env, check=False)
        if not os.path.exists(log):
            return ""
        with open(log) as f:
            return f.read()

    def test_failed_command(self):
        out = self.run_hook('__em_preexec "make build"; false; __em_precmd')
        self.assertTrue(out.startswith("-a|Терминал|-h|string:desktop-entry:messhub-commands|make build|ошибка (код 1)"), out)

    def test_ok_in_english(self):
        out = self.run_hook('__em_preexec "rsync -a x y"; true; __em_precmd', lang="en_US.UTF-8")
        self.assertTrue(out.startswith("-a|Terminal|-h|string:desktop-entry:messhub-commands|rsync -a x y|done in"), out)

    def test_interactive_programs_skipped(self):
        self.assertEqual(self.run_hook('__em_preexec "vim notes.txt"; true; __em_precmd'), "")

    def test_interactive_with_prompt_command(self):
        """Настоящий интерактивный bash с чужим PROMPT_COMMAND (как у GNOME Terminal): отсчёт — от ввода
        команды, а не от показа приглашения; команды из PROMPT_COMMAND карточек не дают."""
        import pty
        import select
        import time
        log = os.path.join(common.TMP, "notify-i.log")
        open(log, "w").close()
        pid, fd = pty.fork()
        if pid == 0:
            os.execvp("bash", ["bash", "--norc", "--noprofile", "-i"])

        def send(text, wait=0.3):
            os.write(fd, text.encode())
            end = time.time() + wait
            while time.time() < end:
                if select.select([fd], [], [], 0.05)[0]:
                    try:
                        os.read(fd, 65536)
                    except OSError:
                        break
        send(f'notify-send(){{ echo "$5" >> "{log}"; }}\nother_prompt(){{ :; }}\nPROMPT_COMMAND="other_prompt;"\n')
        send(f'MESSHUB_LONG_CMD=1; LANG=ru_RU.UTF-8; source "{HOOK}"\n', 0.8)
        send("", 1.5)                              # простой у приглашения
        send("echo быстро\n", 0.8)
        send("sleep 1.3; true\n", 2.2)
        send("exit\n", 0.3)
        os.waitpid(pid, 0)
        with open(log, encoding="utf-8") as f:
            self.assertEqual(f.read().splitlines(), ["sleep 1.3"])


if __name__ == "__main__":
    unittest.main()
