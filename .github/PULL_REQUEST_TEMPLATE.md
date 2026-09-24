<!-- PR принимаются в ветку contrib. Pull requests go to the contrib branch. -->

**Что и зачем / What and why**


**Как проверял / How I tested**

- [ ] `python3 -m unittest discover -s tests -t tests`
- [ ] `python3 tools/i18n_check.py` (если менялся интерфейс / if the UI changed)
- [ ] `python3 tools/check_public.py --staged`
- [ ] строка в `CHANGELOG.md` → «Не выпущено» / a line under “Unreleased”

**Приватность / Privacy**

- [ ] В PR нет настоящих уведомлений, имён, путей, токенов; скриншоты — только `tools/screenshots.py`.
      No real notifications, names, paths or tokens; screenshots only from `tools/screenshots.py`.
