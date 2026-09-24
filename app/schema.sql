-- Схема локальной БД перехваченных сообщений.
-- Одна строка = одно всплывающее уведомление, разобранное из D-Bus.

CREATE TABLE IF NOT EXISTS messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,  -- автоинкремент
    app             TEXT    NOT NULL,   -- источник: desktop-entry (express, yandex-browser…)
    chat            TEXT,               -- чат / имя собеседника (из summary уведомления)
    sender          TEXT,               -- кто написал (из префикса "Имя:" в body, иначе = chat)
    is_bot          INTEGER DEFAULT 0,  -- эвристика: 1 если отправитель похож на бота
    message         TEXT,               -- текст сообщения (body без префикса отправителя)
    notification_id INTEGER,            -- replaces_id уведомления (у eXpress один на чат)
    urgency         INTEGER,            -- 0 low / 1 normal / 2 critical
    has_media       INTEGER DEFAULT 0,  -- было ли вложение/аватар в уведомлении
    event_ts        REAL,               -- unix-время показа уведомления (из dbus)
    event_iso       TEXT,               -- то же в ISO (локальное время)
    received_at     TEXT DEFAULT (datetime('now','localtime')),  -- когда записали в БД (МСК: catcher пишет явно)
    raw_summary     TEXT,               -- исходный summary как есть
    raw_body        TEXT,               -- исходный body как есть (полный текст уведомления)
    processed       INTEGER DEFAULT 0,  -- флаг для LLM-слоя: 0 = ещё не обработано
    is_read         INTEGER DEFAULT 0,  -- 1 = прочитано: галочкой в виджете, правилом или само через 24 ч
    read_at         TEXT,               -- когда отмечено прочитанным (МСК)
    pinned          INTEGER DEFAULT 0,  -- 1 = закреплено: сверху колонки, само не прочитывается
    snooze_until    TEXT,               -- отложено до (МСК); до этого времени в виджете не видно
    site            TEXT,               -- для браузерных уведомлений — сайт (web.max.ru); '' = не сайт
    avatar          TEXT,               -- картинка из уведомления: имя файла в ~/.cache/<APP_ID>/avatars
    -- тематические колонки (events.py): одна «проблема» — один ключ; починилось — resolved_at
    event_key       TEXT,               -- container:podman:web, unit:system:backup.service, cmd:… ; NULL — обычное
    resolved_at     TEXT,               -- когда проблема ушла (МСК): карточка остаётся, но с «починилось»
    details         TEXT                -- хвост лога / вывода команды: в виджете свёрнут, в Telegram не пересылается
);
-- колонки после первой версии (is_read … details) в уже существующую БД досоздаёт catcher.migrate()

CREATE INDEX IF NOT EXISTS idx_messages_app         ON messages(app);
CREATE INDEX IF NOT EXISTS idx_messages_chat        ON messages(chat);
CREATE INDEX IF NOT EXISTS idx_messages_processed   ON messages(processed);
CREATE INDEX IF NOT EXISTS idx_messages_event_ts    ON messages(event_ts);
CREATE INDEX IF NOT EXISTS idx_messages_is_read     ON messages(is_read);
CREATE INDEX IF NOT EXISTS idx_messages_received_at ON messages(received_at);
CREATE INDEX IF NOT EXISTS idx_messages_event_key   ON messages(event_key);

-- Правила («фильтры как в почте»), логика — rules.py.
-- '' в chat/sender/text = «любой»; src = '*' — во всех источниках.
-- show/hide — видно ли в виджете (решает самое узкое правило); остальные действия
-- складываются: подсветить, сразу прочитано, закрепить, звук, переслать в Telegram.
-- Правило без chat/sender/text в конкретном источнике = режим всего источника.
-- profile — в каком профиле действует ('' — во всех), см. rules.active_profile.
CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    src         TEXT NOT NULL,              -- ключ rules.source_of (express, telegram, …) или '*'
    chat        TEXT NOT NULL DEFAULT '',   -- чат; '' = любой
    sender      TEXT NOT NULL DEFAULT '',   -- отправитель; '' = любой
    text        TEXT NOT NULL DEFAULT '',   -- текст сообщения; '' = любой
    text_mode   TEXT NOT NULL DEFAULT 'contains' CHECK (text_mode IN ('contains', 'regex')),
    action      TEXT NOT NULL CHECK (action IN
                  ('show', 'hide', 'highlight', 'read', 'pin', 'sound', 'forward')),
    param       TEXT NOT NULL DEFAULT '',   -- highlight: цвет (red, orange, yellow, green, blue, purple)
    profile     TEXT NOT NULL DEFAULT '',   -- id профиля; '' — во всех профилях
    created_at  TEXT,                       -- когда создано (МСК)
    UNIQUE (src, chat, sender, text, text_mode, action, profile)
);

-- Журнал: какие правила сработали при записи сообщения (сразу прочитано, закрепить,
-- звук, пересылка) — чтобы ответить «почему так». Решения о показе и подсветке
-- считаются на лету и здесь не хранятся.
CREATE TABLE IF NOT EXISTS rule_hits (
    message_id  INTEGER NOT NULL,
    rule_id     INTEGER,
    action      TEXT NOT NULL,
    at          TEXT                        -- МСК
);
CREATE INDEX IF NOT EXISTS idx_rule_hits_msg ON rule_hits(message_id);

-- Почта из ящиков (IMAP, mail.py): докуда дочитан каждый ящик.
CREATE TABLE IF NOT EXISTS mail_state (
    account     TEXT PRIMARY KEY,           -- id ящика из mail.json
    uidvalidity INTEGER,                    -- UIDVALIDITY папки: сменился — ящик пересоздан, начинаем заново
    last_uid    INTEGER,                    -- последнее забранное письмо
    checked_at  TEXT                        -- МСК
);

-- Умный поиск (RAG, необязательный, rag.py): вектор сообщения от модели Ollama.
-- vec — float32, нормированный (скалярное произведение = косинусная близость).
CREATE TABLE IF NOT EXISTS embeddings (
    message_id  INTEGER PRIMARY KEY,
    model       TEXT NOT NULL,
    vec         BLOB NOT NULL
);

-- Настройки виджета (внешний вид, упоминания, названия источников, хранение):
-- ключ → JSON-значение. Значения по умолчанию — rules.PREF_DEFAULTS.
CREATE TABLE IF NOT EXISTS prefs (
    key    TEXT PRIMARY KEY,
    value  TEXT NOT NULL
);

-- Напоминания по сообщениям (reminders.py): «⏰ 15:00» на плашке → в срок карточка в «Напоминания».
CREATE TABLE IF NOT EXISTS reminders (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id  INTEGER NOT NULL,
    at          TEXT NOT NULL,              -- когда напомнить, местное время ГГГГ-ММ-ДД ЧЧ:ММ
    event_at    TEXT,                       -- о чём речь: время из текста (для подписи)
    created     TEXT,
    fired       INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_reminders_due ON reminders(fired, at);

-- Ассистент (ai.py): беседы и их сообщения; настройки беседы — JSON (модель, контекст, выборка).
CREATE TABLE IF NOT EXISTS ai_sessions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL DEFAULT '',
    created     TEXT,
    updated     TEXT,
    settings    TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS ai_messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  INTEGER NOT NULL,
    role        TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content     TEXT NOT NULL,
    created     TEXT,
    meta        TEXT NOT NULL DEFAULT '{}'  -- на какие сообщения опирался ответ, модель, время, токены
);
CREATE INDEX IF NOT EXISTS idx_ai_messages_session ON ai_messages(session_id);
