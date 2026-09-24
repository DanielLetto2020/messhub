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
        self.assertTrue(out.startswith("-a|Терминал|make build|ошибка (код 1)"), out)

    def test_ok_in_english(self):
        out = self.run_hook('__em_preexec "rsync -a x y"; true; __em_precmd', lang="en_US.UTF-8")
        self.assertTrue(out.startswith("-a|Terminal|rsync -a x y|done in"), out)

    def test_interactive_programs_skipped(self):
        self.assertEqual(self.run_hook('__em_preexec "vim notes.txt"; true; __em_precmd'), "")


if __name__ == "__main__":
    unittest.main()
