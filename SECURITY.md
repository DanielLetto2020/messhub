# Безопасность / Security

messhub хранит личные уведомления, пароли почтовых ящиков и ключи - к уязвимостям относимся серьёзно.

**Как сообщить.** Не открывай публичный issue. Используй «Report a vulnerability» на вкладке
Security этого репозитория (приватное сообщение владельцам) или напиши на адрес из [NOTICE](NOTICE).
Опиши, что и как можно сделать; настоящие данные не прикладывай. Ответим в течение недели.

**Что особенно важно:** всё, из-за чего данные могут уйти с компьютера или стать доступны другим
пользователям и сайтам: HTTP-сервер на 127.0.0.1 (API, приём событий), хранение паролей и ключей
(`~/.config/messhub`, права 600), подключение к почте (TLS), пересылка в Telegram.

---

messhub stores personal notifications, mailbox passwords and keys, so we take vulnerabilities
seriously. **Please don't open a public issue.** Use “Report a vulnerability” on the Security tab
(a private message to the maintainers) or email the address in [NOTICE](NOTICE). Describe what can
be done and how; don't attach real data. We'll reply within a week.
