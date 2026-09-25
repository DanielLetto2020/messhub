// Переводы страниц виджета и настроек.
// Ключ — сама русская фраза (как в gettext): на русском t() возвращает её же, на
// английском — перевод из EN; нет перевода — показывается русский текст.
// Подстановки — {имя}: t('Отложено до {t}', {t: '16:00'}).
// Язык: настройка «Язык» (prefs.language), при «авто» — язык системы; сервер
// присылает итог в prefs._lang. Статичная разметка переводится по data-t*
// (translateDom): data-t — текст, data-t-title — подсказка, data-t-ph — placeholder,
// data-t-aria — aria-label.

const EN = {
  // ── общее ──
  'Настройки': 'Settings', 'Сохранить': 'Save', 'Отмена': 'Cancel', 'Удалить': 'Delete',
  'Сохранено': 'Saved', 'Загружаю…': 'Loading…', 'Закрыть': 'Close', 'Вернуть': 'Undo',
  'сегодня в {hm}': 'today at {hm}', 'вчера в {hm}': 'yesterday at {hm}', '{d} в {hm}': '{d} at {hm}',
  'Сервер виджета не отвечает, поэтому настройки не загрузились.': 'The widget server is not responding, so settings could not load.',
  'Проверь, что работает сбор:': 'Check that the collector is running:',
  'Загрузить ещё раз': 'Try again',
  'Не удалось обновить — сервер не отвечает': 'Could not refresh — the server is not responding',
  'Сервер ответил {c}': 'The server replied {c}',

  // ── виджет ──
  'Ожидание сообщений…': 'Waiting for messages…', 'нет новых': 'nothing new', 'важного нет': 'nothing important',
  'Фокус: показывать только важное — закреплённое, подсвеченное, упоминания · клавиша F':
    'Focus: show only what matters — pinned, highlighted, mentions · key F',
  'Прочитать всё, кроме закреплённого': 'Mark all read, except pinned',
  'Нажми ещё раз — прочитать {n}': 'Click again to mark {n} read', 'ещё раз': 'again',
  'Скрыть содержимое (для показа экрана) · клавиша B': 'Hide contents (for screen sharing) · key B',
  'Показать содержимое · клавиша B': 'Show contents · key B',
  'Закрепить: не двигать, не менять размер, держать под всеми окнами': 'Lock: keep position and size, stay below all windows',
  'Открепить: снова можно двигать и менять размер': 'Unlock: move and resize again',
  'Прочитать всё в колонке, кроме закреплённого': 'Mark column read, except pinned',
  'Прочитать весь чат': 'Mark the whole chat read',
  'Перетащи, чтобы поменять порядок колонок': 'Drag to reorder columns',
  'Закрыть колонку': 'Close column', 'Закрыть колонку «{name}»?': 'Close the “{name}” column?',
  'Будет прочитано {n}.': '{n} will be marked read.',
  'Колонка вернётся, когда придёт новое сообщение.': 'The column comes back with the next new message.',
  'Скрыть насовсем': 'Hide for good', 'вернуть — в настройках': 'undo in Settings',
  'Колонку нельзя закрыть': 'This column can’t be closed', 'В колонке {what}.': 'The column has {what}.', ' и ': ' and ',
  'Открепи закреплённое и дождись отложенного — тогда колонку можно закрыть.':
    'Unpin the pinned ones and wait for the snoozed ones to return, then close the column.',
  'Открепи закреплённое — тогда колонку можно закрыть.': 'Unpin them first, then close the column.',
  'Дождись, пока отложенное вернётся, — тогда колонку можно закрыть.': 'Wait for the snoozed ones to return, then close the column.',
  'Понятно': 'OK', 'Не удалось закрыть — сервер не отвечает': 'Could not close — the server is not responding',
  'Колонка «{name}» закрыта, прочитано: {n}': 'Column “{name}” closed, {n} marked read',
  'Колонка «{name}» закрыта': 'Column “{name}” closed',
  'Не удалось открыть {site}: {e}': 'Could not open {site}: {e}', 'Не удалось запустить: {e}': 'Could not launch: {e}',
  'Не нашёл окно «{app}» — приложение закрыто?': 'No “{app}” window found — is the app closed?',
  'Колонка «{name}» скрыта. Вернуть — в настройках, «Внешний вид»': 'Column “{name}” hidden. Bring it back in Settings → Appearance',
  'Закреплено': 'Pinned', 'Упоминание': 'Mention', 'Есть упоминание': 'Has a mention', 'бот': 'bot',
  'Отложить': 'Snooze', 'Открепить': 'Unpin', 'Закрепить — не прочитается само через 24 ч': 'Pin — won’t be auto-read after 24 h',
  'Прочитано — скрыть': 'Read — hide', 'Почему так?': 'Why is this here?',
  'Двойной клик — скопировать текст': 'Double-click to copy the text',
  'Скопировано': 'Copied', 'Не скопировалось': 'Copy failed',
  'Открыть {site}': 'Open {site}', 'Перейти в {app}': 'Go to {app}',
  'Переходить в приложение умеет только окно виджета': 'Only the widget window can switch to the app',
  'Не удалось отметить прочитанным — сервер не отвечает': 'Could not mark as read — the server is not responding',
  'Не удалось закрепить — сервер не отвечает': 'Could not pin — the server is not responding',
  'Не удалось отложить — сервер не отвечает': 'Could not snooze — the server is not responding',
  'Не удалось вернуть — сервер не отвечает': 'Could not undo — the server is not responding',
  'Закреплено: не прочитается само': 'Pinned: won’t be auto-read', 'Откреплено': 'Unpinned',
  'Прочитано: {n}': 'Marked read: {n}', 'Прочитано': 'Marked read', 'Возвращено': 'Restored', 'Читать нечего': 'Nothing to read',
  'Отложить до': 'Snooze until', 'Через час': 'In an hour', 'Через 3 часа': 'In 3 hours',
  'Вечером': 'This evening', 'Завтра утром': 'Tomorrow morning', 'Отложено до {t}': 'Snoozed until {t}',
  'Показать отправителей': 'Show senders',
  'Профиль': 'Profile', 'Без профиля': 'No profile', 'Авто — по расписанию': 'Auto — by schedule',
  'Авто: {name}': 'Auto: {name}', 'Авто: без профиля': 'Auto: no profile', 'Настроить профили…': 'Set up profiles…',
  'Профиль: {name}': 'Profile: {name}', 'Не удалось сменить профиль': 'Could not switch the profile',
  'фокус': 'focus', '{n} ист.': '{n} src.', 'только: {names}': 'only: {names}',
  'Видно в виджете': 'Shown in the widget', 'Скрыто в виджете': 'Hidden in the widget',
  'по умолчанию': 'by default', 'режимом источника': 'by the source mode', 'правилом: {r}': 'by rule: {r}',
  'Подсвечено правилом: {r}': 'Highlighted by rule: {r}', 'Закреплено вручную или правилом': 'Pinned manually or by a rule',
  'При записи: {a} — правилом {r}': 'On arrival: {a} — by rule {r}', 'правило уже удалено': 'the rule was deleted',
  'Отложено до {t}.': 'Snoozed until {t}.', 'Действует профиль «{name}».': 'Profile “{name}” is active.',

  // ── настройки: меню ──
  'Источники': 'Sources', 'Правила для всех': 'Rules for all', 'Профили': 'Profiles', 'Упоминания': 'Mentions',
  'Поиск': 'Search', 'Внешний вид': 'Appearance', 'Статистика': 'Statistics', 'Данные': 'Data',
  'Пересылка в Telegram': 'Telegram forwarding', 'Приём событий': 'Event intake', 'Система': 'System', 'Справка': 'Help',
  'Разделы настроек': 'Settings sections',
  'Правила меняют то, что видно в виджете, и что делать с новыми сообщениями. Сами сообщения сохраняются всегда, а если удалить правило, скрытое снова появится.':
    'Rules change what the widget shows and what happens to new messages. Messages are always kept, and deleting a rule brings hidden ones back.',

  // ── правила ──
  'показывать в виджете': 'show in the widget', 'не показывать в виджете': 'hide from the widget',
  'подсвечивать': 'highlight', 'сразу отмечать прочитанным': 'mark read at once', 'закреплять': 'pin',
  'играть звук': 'play a sound', 'пересылать в Telegram': 'forward to Telegram',
  'красным': 'red', 'оранжевым': 'orange', 'жёлтым': 'yellow', 'зелёным': 'green', 'синим': 'blue', 'фиолетовым': 'purple',
  'Сообщения {c} — {a}': 'Messages {c} — {a}', 'все': 'all',
  'в чате {x}': 'in chat {x}', 'от {x}': 'from {x}', 'по выражению {x}': 'matching {x}', 'с текстом {x}': 'containing {x}',
  'в профиле «{p}»': 'in profile “{p}”',
  'Показывать': 'Show', 'Не показывать': 'Hide', 'Подсветить': 'Highlight', 'Сразу прочитано': 'Mark read',
  'Закрепить': 'Pin', 'Звук': 'Sound', 'Переслать в Telegram': 'Forward to Telegram',
  'Сообщения': 'Messages', 'с текстом': 'with text', 'Что делать': 'Action', 'Цвет': 'Colour', 'Цвет подсветки': 'Highlight colour',
  'любым (необязательно)': 'any (optional)', 'любым': 'any', 'регулярное выражение': 'regular expression',
  'из чата — любого': 'from chat — any', 'от кого — от любого': 'from sender — any', 'Чат': 'Chat', 'Отправитель': 'Sender', 'Текст': 'Text',
  'Во всех профилях': 'In all profiles', 'Только в профиле «{p}»': 'Only in profile “{p}”',
  'Сохранить правило': 'Save rule', 'Правило сохранено': 'Rule saved', 'Правило изменено': 'Rule changed', 'Правило удалено': 'Rule deleted',
  'Сначала настрой раздел «Пересылка в Telegram»': 'Set up “Telegram forwarding” first',
  'Пересылка станет доступна, когда настроишь бота в разделе «Пересылка в Telegram».': 'Forwarding becomes available once a bot is set up in “Telegram forwarding”.',
  'Показывать в виджете, даже если чат или весь источник скрыт.': 'Show in the widget even if the chat or the whole source is hidden.',
  'Не показывать в виджете. Само сообщение всё равно сохранится.': 'Hide from the widget. The message is still kept.',
  'Цветная полоска и фон на плашке. В режиме фокуса такие сообщения видны.': 'A coloured stripe and tint on the card. Such messages stay visible in focus mode.',
  'Считать прочитанным сразу, в виджете не появится. Действует на новые сообщения.': 'Mark read at once, it won’t appear in the widget. Applies to new messages.',
  'Закрепить сверху колонки, само через 24 ч не прочитается. Действует на новые сообщения.': 'Pin to the top of the column; won’t be auto-read after 24 h. Applies to new messages.',
  'Проиграть системный звук, когда придёт. Действует на новые сообщения.': 'Play the system sound when it arrives. Applies to new messages.',
  'Переслать текст в твой Telegram через бота. Это единственное, что уходит с компьютера.': 'Forward the text to your Telegram via a bot. This is the only thing that leaves the computer.',
  'режим источника': 'source mode', 'правило: {r}': 'rule: {r}', '(для всех источников)': '(for all sources)',
  'чат {x}': 'chat {x}', 'от {x} ': 'from {x} ',
  'Так решает режим источника': 'Decided by the source mode', 'Так решает правило': 'Decided by a rule',
  'По умолчанию всё показывается': 'Everything is shown by default',
  'Показывается в виджете. {why}': 'Shown in the widget. {why}', 'Не показывается в виджете. {why}': 'Hidden from the widget. {why}',
  'в виджете': 'shown', 'скрыто': 'hidden', 'скрыт в виджете': 'hidden in widget',

  // ── источники ──
  'Загружаю источники…': 'Loading sources…',
  'Источников пока нет. Они появятся здесь сами, как только придёт первое уведомление от приложения.': 'No sources yet. They appear here by themselves once the first notification arrives.',
  'Приложения и сайты, от которых приходят уведомления. Открой источник, чтобы решить, чьи сообщения показывать в виджете, переименовать его или задать правила.':
    'Apps and websites that send notifications. Open a source to decide whose messages the widget shows, rename it or set rules.',
  'в {n}': 'in {n}', 'показываются только разрешённые': 'only allowed ones are shown', 'показываются все': 'all are shown',
  'Переименовать': 'Rename', 'Название колонки': 'Column name', 'Значок (эмодзи)': 'Icon (emoji)', 'Вернуть как было': 'Reset',
  'Название сохранено': 'Name saved', 'Название возвращено': 'Name reset',
  'Реши, что из этого источника показывать в виджете и что делать с новыми сообщениями. Правило с текстом главнее правила для отправителя, отправитель главнее чата, а всё это главнее режима источника.':
    'Decide what the widget shows from this source and what to do with new messages. A text rule beats a sender rule, a sender beats a chat, and all of them beat the source mode.',
  'Что показывать в виджете': 'What the widget shows', 'Все сообщения': 'All messages', 'кроме тех, что скрыты правилами': 'except those hidden by rules',
  'Только разрешённые': 'Only allowed', 'остальное скрыто, пока правило не разрешит': 'everything else is hidden until a rule allows it',
  'Режим источника сохранён': 'Source mode saved', 'Правила': 'Rules', 'Новое правило': 'New rule',
  'Правил пока нет. Создай первое кнопкой «Новое правило» или из списка «Кто писал».': 'No rules yet. Create one with “New rule” or from “Who wrote”.',
  'Ещё действуют {n} для всех источников —': 'Also in effect: {n} for all sources —', 'посмотреть': 'view',
  'Кто писал': 'Who wrote', 'Все чаты и отправители, от которых были уведомления. Нажми «Создать правило» у нужной строки.':
    'All chats and senders that sent notifications. Click “Create rule” on a row.',
  'Найти чат или отправителя': 'Find a chat or sender', 'Создать правило': 'Create rule',
  'Из этого источника ещё не было уведомлений.': 'No notifications from this source yet.', 'Никого не нашлось по запросу {q}.': 'Nobody matches {q}.',
  'личный чат': 'direct chat', 'группа': 'group', 'без названия': 'untitled', 'последнее {w}': 'last {w}',
  'из личного чата с {x}': 'from the direct chat with {x}', 'от {x} в любом чате': 'from {x} in any chat',
  'из чата {x}': 'from chat {x}', 'от {x} только в чате {y}': 'from {x} only in chat {y}',
  'Сейчас действует профиль «{p}» — строки ниже учитывают его правила.': 'Profile “{p}” is active now — the rows below account for its rules.',

  // ── правила для всех ──
  'Правила для всех источников': 'Rules for all sources',
  'Срабатывают в любом приложении и на любом сайте. Удобно для слов и фраз: скрывать всё про обед, подсвечивать «срочно», закреплять «дедлайн». Правило конкретного источника с тем же условием главнее.':
    'They work in any app and on any site. Handy for words and phrases: hide everything about lunch, highlight “urgent”, pin “deadline”. A rule of a specific source with the same condition wins.',
  'Правил для всех источников пока нет.': 'No rules for all sources yet.',

  // ── профили ──
  'Профили — это наборы правил: «Работа», «Дом», «Созвон». Правило можно привязать к профилю — тогда оно действует, только пока профиль включён. Включить профиль можно вручную (в шапке виджета) или «авто» — по расписанию.':
    'Profiles are sets of rules: “Work”, “Home”, “Call”. A rule tied to a profile works only while that profile is on. Switch profiles by hand (in the widget header) or “auto” — by schedule.',
  'Сейчас': 'Now', 'Новый профиль': 'New profile', 'Название': 'Name', 'Расписание': 'Schedule',
  'Добавить время': 'Add a time slot', 'без расписания — только вручную': 'no schedule — manual only',
  'с': 'from', 'до': 'to', 'Профиль сохранён': 'Profile saved', 'Профиль удалён': 'Profile deleted',
  'Удалить профиль и его правила?': 'Delete the profile and its rules?',
  'Профилей пока нет.': 'No profiles yet.', 'Например: Работа': 'For example: Work',
  'Пн': 'Mon', 'Вт': 'Tue', 'Ср': 'Wed', 'Чт': 'Thu', 'Пт': 'Fri', 'Сб': 'Sat', 'Вс': 'Sun',
  'правил: {n}': 'rules: {n}', 'Правила профиля создаются в редакторе правила: поле «Профиль».': 'Profile rules are created in the rule editor: the “Profile” field.',
  'Нажми ещё раз — удалить': 'Click again to delete',

  // ── упоминания ──
  'Твоё имя, ник и слова, которые касаются тебя. Сообщение с таким словом получает значок @, слово подсвечивается, а в режиме фокуса такое сообщение видно всегда.':
    'Your name, nickname and words that concern you. A message with such a word gets an @ badge, the word is highlighted, and it stays visible in focus mode.',
  'Например: Иван': 'For example: Ivan', 'Добавить': 'Add', 'Добавлено': 'Added', 'Убрано': 'Removed', 'Убрать {x}': 'Remove {x}',
  'Пока ничего не добавлено.': 'Nothing added yet.', 'Новое слово': 'New word',
  'Совпадает начало слова без учёта регистра: «Иван» найдёт и «Ивану», и «ивана», но не «Диван». Короткое «Ив» найдёт и «ива» — лучше вписывать полные формы.':
    'Matches the start of a word, ignoring case: “Ivan” finds “Ivan’s” and “ivan”, but not “Divan”. A short “Iv” also finds “ivy” — better to add full forms.',

  // ── поиск ──
  'Поиск по всем сохранённым сообщениям, в том числе прочитанным и скрытым. Найденное можно вернуть в виджет.':
    'Search all saved messages, including read and hidden ones. Anything found can be sent back to the widget.',
  'Что ищем?': 'What are you looking for?', 'Найти': 'Search', 'Обычный': 'Plain', 'По смыслу': 'By meaning',
  'Все источники': 'All sources', 'Любой статус': 'Any status', 'Непрочитанные': 'Unread', 'Прочитанные': 'Read', 'Закреплённые': 'Pinned',
  'с даты': 'from date', 'по дату': 'to date', 'Найдено: {n}': 'Found: {n}', 'Ничего не нашлось.': 'Nothing found.',
  'Показать ещё': 'Show more', 'Вернуть в виджет': 'Back to the widget', 'Возвращено в виджет': 'Sent back to the widget',
  'прочитано': 'read', 'не прочитано': 'unread', 'близость {s}': 'similarity {s}',
  'Спросить по переписке': 'Ask about your messages', 'Например: когда переносили релиз?': 'For example: when was the release moved?',
  'Спросить': 'Ask', 'Думаю…': 'Thinking…', 'Ответ модели {m} по найденным сообщениям:': 'Answer by {m} from the messages found:',
  'Умный поиск (RAG)': 'Smart search (RAG)',
  'Ищет по смыслу, а не по буквам, и отвечает на вопросы по переписке. Работает целиком на компьютере через Ollama: скачивает модель векторов и считает их для всех сообщений. Без него работает обычный поиск.':
    'Searches by meaning, not letters, and answers questions about your messages. Runs fully on the computer via Ollama: it downloads an embedding model and indexes all messages. Plain search works without it.',
  'Ollama не отвечает на {h}. Установи её (см. «Справка → Умный поиск») и запусти.': 'Ollama does not respond at {h}. Install it (see “Help → Smart search”) and start it.',
  'Включён: модель {m}, посчитано {a} из {b} сообщений.': 'On: model {m}, indexed {a} of {b} messages.',
  'Выключен.': 'Off.', 'Модель векторов': 'Embedding model', 'Модель для ответов': 'Answer model', 'первая доступная': 'first available',
  'Установить и включить': 'Install and enable', 'Выключить': 'Disable', 'Выключить и удалить векторы': 'Disable and delete the index',
  'Удалить модель из Ollama': 'Remove the model from Ollama',
  'Скачивание — один раз, около 1,2 ГБ для bge-m3; дальше векторы считаются в фоне.': 'One-time download, about 1.2 GB for bge-m3; then indexing runs in the background.',
  'Умный поиск выключен.': 'Smart search is off.', 'Модель удалена из Ollama': 'Model removed from Ollama',
  'Установка: {p}': 'Installing: {p}', 'Ошибка: {e}': 'Error: {e}',
  'Для поиска по смыслу включи умный поиск ниже.': 'Enable smart search below to search by meaning.',

  // ── внешний вид ──
  'Виджет применяет изменения сам, примерно за секунду — можно смотреть на него и подбирать.': 'The widget applies changes itself in about a second — watch it while you adjust.',
  'Язык': 'Language', 'Как в системе': 'System', 'Русский': 'Русский', 'Непрозрачность': 'Opacity', 'Размер текста': 'Text size',
  'Тема': 'Theme', 'Тёмная': 'Dark', 'Светлая': 'Light', 'Плотность': 'Density', 'Обычная': 'Normal', 'Компактная': 'Compact',
  'Сообщения одного чата': 'Messages from one chat', 'Сворачивать в одну плашку': 'Collapse into one card', 'Показывать по отдельности': 'Show separately',
  'Аватары': 'Avatars',
  'Колонки': 'Columns', 'Порядок колонок меняется перетаскиванием прямо в виджете. Скрытые колонки:': 'Reorder columns by dragging them in the widget. Hidden columns:',
  'скрытых нет': 'none hidden', 'Показать': 'Show', 'Сбросить порядок': 'Reset the order', 'Порядок сброшен': 'Order reset',

  // ── статистика ──
  'Кто пишет больше всех, какие чаты самые шумные и когда приходят сообщения. Шумный чат можно сразу скрыть из виджета.':
    'Who writes most, which chats are the noisiest and when messages arrive. A noisy chat can be hidden from the widget right away.',
  '7 дней': '7 days', '30 дней': '30 days', 'Всё время': 'All time', 'Источник': 'Source', 'Считаю…': 'Counting…',
  'Сервер виджета не отвечает — статистику не посчитать.': 'The widget server is not responding — statistics unavailable.',
  'За этот период сообщений нет. Выбери период побольше.': 'No messages in this period. Pick a longer one.',
  'самый активный час, {n}': 'busiest hour, {n}', 'Кто пишет больше всех': 'Who writes most', 'Самые шумные чаты': 'Noisiest chats',
  'Скрыть в виджете': 'Hide in widget', 'Когда приходят сообщения': 'When messages arrive',
  'Показать картой': 'Show as a map', 'Показать таблицей': 'Show as a table',
  'Сообщения по дням недели и часам; числа — в виде таблицы': 'Messages by weekday and hour; numbers — in the table view',
  'меньше': 'fewer', 'больше': 'more', 'тусклые клетки — ни одного сообщения': 'dim cells — no messages',
  'Чат «{c}» скрыт в виджете': 'Chat “{c}” hidden in the widget', '{w}, {h}: {n}': '{w}, {h}: {n}',

  // ── данные ──
  'В базе {n}, {mb} МБ вместе с журналом.': 'The database holds {n}, {mb} MB with the journal.',
  'Первое записано {a}, последнее — {b}.': 'First saved {a}, last {b}.', 'Закреплено: {n}.': 'Pinned: {n}.',
  'Сколько хранить': 'Keep for', 'Раз в час удаляются записи старше срока. Закреплённые не удаляются никогда.': 'Every hour older records are deleted. Pinned ones are never deleted.',
  'Хранить всё': 'Keep everything', '90 дней': '90 days', '180 дней': '180 days', '1 год': '1 year', '{n} дней': '{n} days',
  'Срок хранения сохранён': 'Retention saved', 'Удалить старое сейчас': 'Delete old records now', 'старше': 'older than',
  '1 года': '1 year', 'Точно удалить? Нажми ещё раз': 'Sure? Click again', 'Удалено: {n}': 'Deleted: {n}',
  'Выгрузить': 'Export', 'Файл сохранится в папку «Загрузки». CSV открывается в LibreOffice и Excel.': 'The file goes to your Downloads folder. CSV opens in LibreOffice and Excel.',
  'Выгрузить CSV': 'Export CSV', 'Выгрузить JSON': 'Export JSON', 'Сохранено {n}:': 'Saved {n}:',
  'Резервные копии': 'Backups',
  'Раз в сутки делается копия базы. Хранятся последние {k} ежедневных; ручные остаются, пока не удалишь сам.':
    'The database is copied once a day. The last {k} daily copies are kept; manual ones stay until you delete them.',
  'Делать ежедневные копии': 'Make daily copies', 'хранить': 'keep', 'Сделать копию сейчас': 'Back up now', 'Копия сделана': 'Backup made',
  'Восстановить': 'Restore', 'Восстановить эту копию? Нажми ещё раз': 'Restore this copy? Click again',
  'Восстановлено. Текущая база сохранена как {n}.': 'Restored. The current database was saved as {n}.',
  'ежедневная': 'daily', 'ручная': 'manual', 'перед восстановлением': 'before restore', 'старая': 'legacy', 'Копий пока нет.': 'No backups yet.',
  'Правила и настройки': 'Rules and settings',
  'Выгрузка в файл — чтобы перенести на другой компьютер или поделиться набором правил. Токены и ключи в файл не попадают.':
    'Export to a file to move to another computer or share a rule set. Tokens and keys are never included.',
  'Выгрузить правила и настройки': 'Export rules and settings', 'Загрузить из файла…': 'Import from file…',
  'Заменить мои правила': 'Replace my rules', 'Добавить к моим правилам': 'Add to my rules',
  'Загружено правил: {n}.': 'Rules imported: {n}.', 'Пропущено: {n}': 'Skipped: {n}', 'Это не файл настроек': 'Not a settings file',
  'Где лежат данные': 'Where data lives',

  // ── пересылка ──
  'Бот пересылает в твой чат или группу сообщения, попавшие под правило «Переслать в Telegram». Удобно, когда ты не за компьютером.':
    'A bot forwards messages matching a “Forward to Telegram” rule to your chat or group. Handy when you are away from the computer.',
  'Это единственное, что уходит с компьютера: текст таких сообщений идёт через серверы Telegram. Всё остальное остаётся локально.':
    'This is the only thing that leaves the computer: the text of such messages goes through Telegram servers. Everything else stays local.',
  'Настроено: бот с токеном {t}, чат {c}': 'Set up: bot with token {t}, chat {c}', ', тема {n}': ', topic {n}', 'Пока не настроено.': 'Not set up yet.',
  'Токен бота': 'Bot token', 'оставь пустым, чтобы не менять': 'leave empty to keep it', 'ID чата или группы': 'Chat or group ID',
  'Токен выдаёт @BotFather.': 'Get the token from @BotFather.',
  'Номер темы': 'Topic id', 'необязательно': 'optional', 'Отправить проверку': 'Send a test',
  'Проверка отправлена — загляни в Telegram.': 'Test sent — check Telegram.',
  'Недельный отчёт': 'Weekly report',
  'Раз в неделю бот присылает сводку цифр: сколько и откуда пришло, самые шумные чаты, кто больше писал, упоминания, что осталось непрочитанным.':
    'Once a week the bot sends a summary: how much came from where, noisiest chats, most active senders, mentions, what is still unread.',
  'Присылать отчёт': 'Send the report', 'в {t}': 'at {t}', 'Показать, что придёт': 'Preview', 'Отправить сейчас': 'Send now',
  'Отчёт отправлен': 'Report sent', 'понедельник': 'Monday', 'вторник': 'Tuesday', 'среда': 'Wednesday', 'четверг': 'Thursday',
  'пятница': 'Friday', 'суббота': 'Saturday', 'воскресенье': 'Sunday',

  // ── приём событий ──
  'Скрипты, CI, Home Assistant или другой компьютер могут класть события в виджет напрямую — HTTP-запросом с ключом. Дальше на них работают обычные правила.':
    'Scripts, CI, Home Assistant or another computer can post events straight into the widget with a keyed HTTP request. Regular rules then apply.',
  'Ключ': 'Key', 'Ключа ещё нет.': 'No key yet.', 'Создать ключ': 'Create a key', 'Заменить ключ': 'Replace the key',
  'Показать ключ': 'Show the key', 'Скрыть ключ': 'Hide the key', 'Ключ создан': 'Key created',
  'Старый ключ перестанет работать. Нажми ещё раз': 'The old key will stop working. Click again',
  'Пример': 'Example', 'Приём из сети': 'Intake from the network',
  'По умолчанию события принимаются только с этого компьютера. Чтобы присылать с других машин, укажи адрес и порт — поднимется отдельный сервер, который умеет только приём событий.':
    'By default events are accepted from this computer only. To accept them from other machines, set an address and port — a separate server that only accepts events will start.',
  'выключен': 'off', 'Применится после перезапуска сбора.': 'Takes effect after restarting the collector.',
  'Перезапустить сбор': 'Restart the collector', 'Сбор перезапускается…': 'Restarting the collector…',
  'Поля: source — колонка (обязательно), text — текст (обязательно), chat, sender, urgency (0–2).':
    'Fields: source — the column (required), text (required), chat, sender, urgency (0–2).',

  // ── система ──
  'Проверка системы и автозапуск.': 'System check and autostart.', 'Проверить ещё раз': 'Check again',
  'Автозапуск': 'Autostart', 'Сбор уведомлений': 'Notification collector', 'Виджет на рабочем столе': 'Desktop widget',
  'запускать при входе в систему': 'start when you log in', 'работает': 'running', 'остановлен': 'stopped',
  'не установлен — запусти ./install.sh': 'not installed — run ./install.sh', 'Автозапуск включён': 'Autostart enabled',
  'Автозапуск выключен': 'Autostart disabled', 'Перезапустить': 'Restart', 'Версия': 'Version', 'Папки': 'Folders',
  'код': 'code', 'данные': 'data', 'настройки': 'settings', 'кэш': 'cache', 'база': 'database',

  'Виджет перезапускается…': 'Widget is restarting…',
  'messhub на GitHub': 'messhub on GitHub', 'автор': 'author', 'Проверять новые версии': 'Check for new versions',
  'Раз в 12 часов программа спрашивает у GitHub номер последнего выпуска. Ничего о тебе и твоих сообщениях при этом не отправляется. Выключишь — запросов не будет.':
    'Every 12 hours the app asks GitHub for the latest release number. Nothing about you or your messages is sent. Turn it off and there are no requests at all.',
  'есть новая версия {v}': 'version {v} is out', 'установлена последняя версия': 'you have the latest version',
  'GitHub не ответил': 'GitHub did not answer', 'проверяю…': 'checking…', 'Установлена последняя версия': 'You have the latest version',
  'Есть новая версия {v} — открыть страницу выпуска': 'Version {v} is out — open the release page', 'Запускать вместе с Windows': 'Start with Windows',

  // ── почта ──
  'Почта': 'Mail', 'Ящики': 'Mailboxes', 'Откуда брать почту': 'Where mail comes from',
  'Письма попадают в колонку «Почта» одним из двух способов. Работает только один, чтобы письма не приходили дважды.':
    'Mail reaches the Mail column in one of two ways. Only one works at a time, so no message arrives twice.',
  'Уведомления почтовых программ': 'Mail app notifications',
  'Thunderbird, Evolution, Geary и почта в браузере: что они показывают уведомлением, то и попадает в колонку. Настраивать ничего не нужно.':
    'Thunderbird, Evolution, Geary and webmail: whatever they show as a notification lands in the column. Nothing to set up.',
  'Напрямую из ящиков (IMAP)': 'Straight from mailboxes (IMAP)',
  'Программа сама проверяет подключённые ящики, даже когда почтовая программа закрыта. Уведомления почтовых программ тогда не записываются.':
    'The app checks the connected mailboxes itself, even when no mail app is open. Mail app notifications are not recorded then.',
  'Ящики проверяются, только когда выбран способ «Напрямую из ящиков».': 'Mailboxes are only checked when “Straight from mailboxes” is selected.',
  'Ящиков пока нет.': 'No mailboxes yet.', 'Подключи хотя бы один, иначе почта в виджет не попадёт.': 'Connect at least one, or no mail reaches the widget.',
  'Подключить ящик': 'Connect a mailbox', 'Подключить': 'Connect', 'Изменить': 'Edit', 'Проверить сейчас': 'Check now',
  'Письма забираются по IMAP; SMTP нужен только для отправки, и здесь он не используется. На сервере письмо не становится прочитанным. Когда ящик подключён, старые письма не подтягиваются — приходят только новые. Пароли лежат в mail.json с правами 600, на страницу они не отдаются.':
    'Mail is fetched over IMAP; SMTP is only for sending and isn’t used here. Messages stay unread on the server. Old mail isn’t pulled in when a mailbox is connected — only new mail arrives. Passwords are kept in mail.json (mode 600) and never sent to the page.',
  'Почта берётся из ящиков': 'Mail now comes from mailboxes', 'Почта берётся из уведомлений': 'Mail now comes from notifications',
  'проверено {w}': 'checked {w}', 'новых: {n}': '{n} new', 'ещё не проверялся': 'not checked yet',
  'Новых писем: {n}': 'New messages: {n}', 'Новых писем нет': 'No new messages',
  'Удалить? Нажми ещё раз': 'Delete? Click again', 'Ящик удалён; письма, что уже пришли, остались': 'Mailbox removed; messages already received are kept',
  'Почтовая служба': 'Mail provider', 'Яндекс Почта': 'Yandex Mail', 'Почта Mail.ru': 'Mail.ru', 'Другой сервер': 'Other server',
  'Адрес или логин': 'Address or login', 'Пароль': 'Password',
  'Яндекс, Gmail, Mail.ru и iCloud пускают сторонние программы только по паролю приложения. Его создают в настройках безопасности почты; обычный пароль не подойдёт.':
    'Yandex, Gmail, Mail.ru and iCloud only let third-party apps in with an app password, created in the account’s security settings; the regular password won’t work.',
  'например, Работа': 'e.g. Work', 'так ящик подписан в колонке «Почта»': 'how the mailbox is labelled in the Mail column',
  'Сервер IMAP': 'IMAP server', 'Порт': 'Port', 'Защита': 'Security', 'без шифрования': 'no encryption',
  'Не проверять сертификат — для локальных мостов вроде Proton Bridge': 'Skip certificate check — for local bridges such as Proton Bridge',
  'Папка': 'Folder', 'Проверять каждые': 'Check every', 'мин': 'min', 'Проверять этот ящик': 'Check this mailbox',
  'Проверить подключение': 'Test connection', 'Подключаюсь…': 'Connecting…', 'Подключение есть: в папке {n}.': 'Connected: {n} in the folder.',
  'Ящик сохранён': 'Mailbox saved',
  'Ящик сохранён. Чтобы письма шли из него, выбери «Напрямую из ящиков».': 'Mailbox saved. To get mail from it, choose “Straight from mailboxes”.',

  // ── тематические колонки ──
  'Тематические колонки': 'Themed columns', 'Контейнеры': 'Containers', 'Службы': 'Services', 'Команды': 'Commands',
  'Колонки для тех, кто работает с кодом и серверами. Каждая включается отдельно, а выключенная ничего не собирает. Всё остаётся на этом компьютере.':
    'Columns for people who work with code and servers. Each one is turned on separately, and one that is off collects nothing. Everything stays on this computer.',
  'Docker и Podman: контейнер упал, его убило по памяти, healthcheck стал «нездоров», контейнер перезапускается по кругу. Когда контейнер снова работает, карточка отмечается «починилось».':
    'Docker and Podman: a container crashed, was killed for running out of memory, its healthcheck turned unhealthy, or it keeps restarting. When the container works again, the card is marked “fixed”.',
  'Службы systemd, которые упали: не запустился сервис, не прошёл таймер бэкапа. Когда служба снова работает, карточка отмечается «починилось».':
    'systemd services that failed: a service did not start, a backup timer did not run. When the service works again, the card is marked “fixed”.',
  'Службы Windows, которые завершились с ошибкой или не запустились (по журналу событий). Если служба снова работает, карточка отмечается «починилось».':
    'Windows services that stopped with an error or failed to start (from the event log). If the service runs again, the card is marked “fixed”.',
  'Итог команды: код выхода, сколько шла и хвост вывода, если она упала. Удачный повторный запуск той же команды в той же папке отмечает прошлую ошибку «починилось».':
    'The result of a command: exit code, how long it ran and the tail of its output if it failed. A successful rerun of the same command in the same folder marks the previous failure “fixed”.',
  'включена': 'on', 'выключена': 'off',
  '{e}: не найден': '{e}: not found', '{e}: найден': '{e}: found', '{e}: слушаю события': '{e}: listening to events',
  '{e}: запускается…': '{e}: starting…', 'запускается…': 'starting…',
  'systemctl не найден': 'systemctl not found', 'Журнал событий Windows недоступен': 'The Windows event log is not available',
  'проверяю раз в 30 секунд': 'checking every 30 seconds', 'проверяю раз в минуту': 'checking every minute',
  'сейчас упавших: {n}': 'failed right now: {n}',
  'Показывать и обычный запуск и остановку': 'Also show normal starts and stops',
  'Хвост лога': 'Log tail', 'Хвост журнала': 'Journal tail', 'Хвост вывода': 'Output tail', 'не сохранять': 'do not keep',
  'Не следить за': 'Ignore', 'имена через запятую, можно test-*': 'names separated by commas, test-* works',
  'Программа только слушает события движка: ничего не запускает, не останавливает и не удаляет. Rootless Podman видит только твои контейнеры, Docker — если у пользователя есть доступ к нему.':
    'The app only listens to engine events: it never starts, stops or removes anything. Rootless Podman sees only your containers; Docker works if your user has access to it.',
  'Системные службы': 'System services', 'Службы пользователя': 'User services',
  'Обёртка': 'Wrapper', 'Без обёртки': 'Without the wrapper',
  'Например: сборка, тесты, выгрузка. Вывод идёт в терминал как обычно, код выхода сохраняется — обёртку можно ставить и в скрипты.':
    'For example a build, tests or an export. Output goes to the terminal as usual and the exit code is kept, so the wrapper works in scripts too.',
  'Хук терминала: о любой команде дольше минуты — всплывашка и карточка (строка в ~/.bashrc или ~/.zshrc, либо ./install.sh --terminal-hook).':
    'Terminal hook: any command longer than a minute gives a pop-up and a card (a line in ~/.bashrc or ~/.zshrc, or ./install.sh --terminal-hook).',
  'Хвосты логов и вывода хранятся только в базе на этом компьютере: в виджете они свёрнуты, а правило «Переслать в Telegram» отправляет только текст карточки. Колонка появится на доске с первым событием.':
    'Log and output tails are kept only in the database on this computer: they are collapsed in the widget, and the “Forward to Telegram” rule sends only the card text. A column appears on the board with its first event.',
  'Лог': 'Log', 'Двойной клик — скопировать лог': 'Double-click to copy the log', '✓ Починилось в {hm}': '✓ Fixed at {hm}',
  // окно «целиком»
  'Открыть целиком': 'Open in full', 'Показать целиком': 'Show in full', 'целиком': 'in full',
  'Скопировать текст': 'Copy text', 'Скопировать лог': 'Copy log', 'Отметить прочитанным': 'Mark read',
  'Важное': 'Important', 'Содержимое скрыто для показа экрана.': 'Contents are hidden for screen sharing.',
  'Сообщения нет: его удалили по сроку хранения или вручную.': 'The message is gone: it was removed by the retention period or by hand.',
  'Сервер виджета не отвечает — сообщение не загрузилось.': 'The widget server is not responding, so the message could not load.',

  // ── доска: напоминания, тихие часы, ассистент, показ экрана ──
  'Ассистент: вопросы по сообщениям на модели на этом компьютере': 'Assistant: ask about your messages, on a model on this computer',
  'В {hm}': 'At {hm}', 'За 10 минут': '10 minutes before', 'За 30 минут': '30 minutes before', 'За час': 'An hour before',
  'Утром в {hm}': 'In the morning at {hm}', 'Накануне в 18:00': 'The day before at 18:00',
  'Напоминание {w}': 'Reminder {w}', 'Напомнить: {w}': 'Remind: {w}', 'Напомню {w}': 'Will remind {w}', 'напомню {w}': 'reminder {w}',
  'Напомнить об этом': 'Remind me about this', 'Напоминание заведено — нажми, чтобы отменить': 'Reminder set — click to cancel',
  'Отменить напоминание': 'Cancel the reminder', 'Напоминание отменено': 'Reminder cancelled', 'Это время уже прошло': 'That time has passed',
  'Не удалось завести напоминание — сервер не отвечает': 'Could not set the reminder — the server is not responding',
  'Не удалось отменить — сервер не отвечает': 'Could not cancel — the server is not responding',
  'сегодня': 'today', 'завтра': 'tomorrow', 'пн': 'Mon', 'вт': 'Tue', 'ср': 'Wed', 'чт': 'Thu', 'пт': 'Fri', 'сб': 'Sat', 'вс': 'Sun',
  'Тихие часы': 'Quiet hours', 'Тихие часы: звуки правил выключены': 'Quiet hours: rule sounds are off',
  'Сейчас тихо': 'Quiet now', 'Сейчас не тихо': 'Not quiet now', 'до {hm}': 'until {hm}', 'тихо': 'quiet',
  'по расписанию': 'by schedule', 'включено вручную': 'turned on by hand', 'включено «Не беспокоить» в системе': '“Do Not Disturb” is on in the system',
  '«Выключить сейчас» — до того, как «Не беспокоить» выключат. Не связывать их совсем — в настройках тихих часов.': '“Turn off now” lasts until “Do Not Disturb” is switched off. To unlink them for good — quiet hours settings.',
  'Тихие часы идут вместе с «Не беспокоить» в системе. «Выключить сейчас» — до того, как «Не беспокоить» выключат; чтобы не связывать их совсем, сними галочку «Считать тихими часами…» ниже.': 'Quiet hours follow the system “Do Not Disturb”. “Turn off now” lasts until “Do Not Disturb” is switched off; to unlink them for good, clear “Treat…” below.',
  'Сейчас в системе включено «Не беспокоить»: всплывающие уведомления скрыты, а доска собирает и показывает всё как обычно.': '“Do Not Disturb” is on in the system: pop-ups are hidden, while the board collects and shows everything as usual.',
  'Можно включить «Не беспокоить» в системе: всплывающие уведомления пропадут, а сообщения будут собираться и показываться на доске как обычно.': 'You can turn on “Do Not Disturb” in the system: pop-ups disappear, while messages keep being collected and shown on the board as usual.',
  'обычно не нужно: тогда и здесь станет тихо — луна в шапке, звуки правил молчат': 'usually not needed: then it gets quiet here too — the moon in the header, rule sounds are muted',
  'Тихо на час': 'Quiet for an hour', 'До утра': 'Until morning', 'Выключить сейчас': 'Turn off now',
  'Расписание и настройки…': 'Schedule and settings…', 'Тихо до {hm}': 'Quiet until {hm}', 'Тихие часы выключены': 'Quiet hours are off',
  'Идёт показ экрана — доска размыта': 'Screen sharing is on — the board is blurred', 'Показ экрана кончился': 'Screen sharing ended',

  // ── настройки: ресурсы, журналы, календарь, тихие часы, скрипты ──
  'Ресурсы': 'Resources', 'Журналы': 'Log watch', 'Календарь': 'Calendar',
  'Диск заполнен, память или swap на пределе, перегрелись процессор или видеокарта NVIDIA. Проверка раз в минуту; когда отпустило — «починилось». К карточке о диске прикладывается, сколько занимают образы и контейнеры.':
    'A disk is full, memory or swap is nearly exhausted, the CPU or an NVIDIA GPU is overheating. Checked every minute; when it eases — “fixed”. A full-disk card also shows how much images and containers take.',
  'Диск, % занято': 'Disk, % used', 'Память, %': 'Memory, %', 'Swap, %': 'Swap, %', 'Процессор, °C': 'CPU, °C', 'Видеокарта, °C': 'GPU, °C',
  'Ещё папки': 'More folders', 'другие диски, через запятую: /mnt/data': 'other disks, separated by commas: /mnt/data', 'проверяю': 'checking',
  'Строки логов по своему шаблону: файл (как tail -F) или служба journald. Совпадения за час собираются в одну карточку со счётчиком, последние строки — в логе под ней.':
    'Log lines matching your pattern: a file (like tail -F) or a journald unit. Matches within an hour go into one card with a counter; the latest lines are in its log.',
  'служба': 'unit', 'совпадений: {n}, последнее в {t}': 'matches: {n}, last at {t}', 'Наблюдений пока нет.': 'No watches yet.',
  'Добавить наблюдение': 'Add a watch', 'например: nginx ошибки': 'e.g. nginx errors', 'Откуда': 'Source', 'файл': 'file',
  'служба journald': 'journald unit', '/var/log/nginx/error.log или имя службы': '/var/log/nginx/error.log or a unit name',
  'служба пользователя': 'user unit', 'Шаблон': 'Pattern', 'без учёта регистра': 'ignore case',
  'Регулярное выражение Python. Проверка берёт последние 500 строк и показывает, что совпало бы.':
    'A Python regular expression. The check takes the last 500 lines and shows what would match.',
  'Проверить на последних строках': 'Test on the latest lines', 'Проверено строк: {c}, совпало: {m}': 'Lines checked: {c}, matched: {m}',
  'События из календарей на этом компьютере: GNOME Календарь и Evolution (в том числе подключённые аккаунты) и свои файлы .ics. За несколько минут до начала — карточка, утром — план на день.':
    'Events from calendars on this computer: GNOME Calendar and Evolution (including connected accounts) and your own .ics files. A card a few minutes before the start, and a plan for the day in the morning.',
  'Напоминать за': 'Remind', 'минут': 'minutes before', 'План на день в': 'Plan for the day at', 'Свои .ics': 'Own .ics',
  'файлы или папки с .ics, через запятую': '.ics files or folders, separated by commas', 'Нашёл календари:': 'Calendars found:',
  'календарей: {n}, событий на ближайшие сутки: {e}': 'calendars: {n}, events in the next day: {e}',
  'Время в тексте': 'Time in text', 'Предлагать напомнить ⏰': 'Offer a reminder ⏰', 'Показ экрана': 'Screen sharing',
  'Размывать доску сама': 'Blur the board automatically', 'Не трогать': 'Leave as is',
  '«Время в тексте»: если в сообщении есть «в 15:00», «завтра в 10» или «к пятнице», на плашке появится ⏰ — по клику можно завести напоминание.':
    '“Time in text”: if a message says “at 3 pm”, “tomorrow at 10” or “by Friday”, the card gets ⏰ — click it to set a reminder.',
  '«Показ экрана»: пока идёт демонстрация (Zoom, Meet и другие сайты в Chrome, Firefox, портал PipeWire), доска размывается, а потом возвращается. Свои признаки — части заголовков окон через запятую:':
    '“Screen sharing”: while you share your screen (Zoom, Meet and other sites in Chrome, Firefox, the PipeWire portal), the board blurs and comes back afterwards. Your own signs — parts of window titles, separated by commas:',
  'например: Screen sharing, Демонстрация': 'e.g. Screen sharing, Presenting',
  'Пока тихо, сообщения копятся как обычно, но правила не играют звук, а в шапке доски горит луна. Когда тихие часы кончатся, в колонку «Сводки» придёт одна карточка: сколько пришло, откуда, сколько упоминаний.':
    'While it is quiet, messages pile up as usual, but rules play no sound and a moon shows in the board header. When quiet hours end, one card lands in the Digests column: how much arrived, from where, how many mentions.',
  'По расписанию': 'By schedule', 'Что делать, пока тихо': 'While it is quiet', '«Не беспокоить» GNOME': 'GNOME “Do Not Disturb”',
  'Всё равно играть звук правил': 'Play rule sounds anyway', 'Пересылать в Telegram по правилам': 'Forward to Telegram by rules',
  'обычно полезно, если тебя нет за компьютером': 'usually useful when you are away from the computer',
  'Сводка, когда тихие часы кончились': 'A digest when quiet hours end',
  'Считать тихими часами, когда включено «Не беспокоить»': 'Treat “Do Not Disturb” as quiet hours',
  'Включать «Не беспокоить» на время тихих часов': 'Turn on “Do Not Disturb” during quiet hours',
  'тогда и всплывающие уведомления системы молчат': 'then system pop-ups stay silent too',
  'Не нашёл настройку «Не беспокоить» — это не GNOME или Windows.': 'Could not find “Do Not Disturb” — this is not GNOME, or it is Windows.',
  'Интервала ещё нет. Например: будни с 22:00 до 08:00 — интервал может идти через полночь.': 'No interval yet. For example, weekdays 22:00 to 08:00 — an interval may cross midnight.',
  'Свои источники: скрипты': 'Your own sources: scripts',
  'Положи скрипт в папку — программа будет запускать его по расписанию, а каждую напечатанную им строку-JSON (те же поля, что выше, плюс key и status) превращать в карточку. Колонки можно добавлять без правки программы.':
    'Put a script into the folder: the app runs it on a schedule and turns every JSON line it prints (the same fields as above, plus key and status) into a card. New columns without touching the app.',
  'Открыть папку': 'Open folder', 'Создать пример': 'Create an example', 'запускать скрипты': 'run scripts',
  'раз в {n} с': 'every {n}s', 'запускался {w}': 'ran {w}', 'карточек: {n}': 'cards: {n}', 'ещё не запускался': 'has not run yet',
  'Интервал, секунд': 'Interval, seconds', 'Запустить': 'Run', 'В папке пока нет скриптов.': 'No scripts in the folder yet.',
  'Папки ещё нет — «Создать пример» создаст её и файл-образец.': 'The folder does not exist yet — “Create an example” makes it and a sample file.',
  'Годятся .bat, .cmd, .ps1 и .py. Интервал можно задать и строкой «# messhub: interval=60» в начале файла.':
    '.bat, .cmd, .ps1 and .py work. The interval can also be set with a “# messhub: interval=60” line at the top of the file.',
  'Годятся исполняемые файлы (chmod +x) и .py. Интервал можно задать и строкой «# messhub: interval=60» в начале файла. Пример выключен (.off в конце имени): переименуй и сделай исполняемым.':
    'Executable files (chmod +x) and .py work. The interval can also be set with a “# messhub: interval=60” line at the top of the file. The example is off (.off at the end of its name): rename it and make it executable.',
  'Создан пример: {p}': 'Example created: {p}', 'Карточек: {n}': 'Cards: {n}',

  // ── ассистент ──
  'Ассистент': 'Assistant', 'на модели на этом компьютере': 'on a model on this computer', 'Новая беседа': 'New conversation',
  'Найти беседу': 'Find a conversation', 'Модели': 'Models', 'Настроить заново': 'Set up again',
  'Модель работает на этом компьютере — сообщения никуда не отправляются.': 'The model runs on this computer — messages are not sent anywhere.',
  'Нажми, чтобы переименовать': 'Click to rename', 'Модель и настройки беседы': 'Model and conversation settings',
  'Скопировать беседу (Markdown)': 'Copy the conversation (Markdown)', 'Настройки беседы': 'Conversation settings',
  'Сегодня': 'Today', 'Раньше': 'Earlier', 'Бесед пока нет': 'No conversations yet', 'Ничего не нашлось': 'Nothing found',
  'Беседа удалена': 'Conversation deleted', 'Дождись ответа или останови его': 'Wait for the answer or stop it',
  'Беседа скопирована (Markdown)': 'Conversation copied (Markdown)', 'модель не выбрана': 'no model selected',
  '{p} не отвечает — запусти или выбери другую модель': '{p} is not responding — start it or pick another model', 'Модель': 'Model',
  'Что я пропустил?': 'What did I miss?', 'Коротко о главном за сутки': 'The gist of the last day',
  'Кратко перескажи, что было в сообщениях за период: по каждому активному чату 1–2 пункта, отдельно — что адресовано мне и что ждёт моего ответа.':
    'Briefly summarize the messages for the period: 1–2 points per active chat, and separately what is addressed to me and waits for my reply.',
  'Упоминания и вопросы ко мне': 'Mentions and questions to me', 'Где меня звали или спрашивали': 'Where I was mentioned or asked',
  'Найди сообщения, где упоминают меня или задают мне вопрос, и перечисли их с номерами и кратко — что от меня хотят.':
    'Find messages that mention me or ask me something, and list them with numbers and briefly what is wanted from me.',
  'Сроки и договорённости': 'Deadlines and agreements', 'Встречи, дедлайны, обещания': 'Meetings, deadlines, promises',
  'Выпиши все сроки, встречи и договорённости со временем, кто и что обещал — с номерами сообщений. Сначала ближайшие.':
    'List all deadlines, meetings and agreements with times, who promised what — with message numbers. Nearest first.',
  'Отчёт по серверам': 'Server report', 'Контейнеры, службы, команды': 'Containers, services, commands',
  'Сделай отчёт по контейнерам, службам и командам: что падало, что починилось, что до сих пор не работает. С номерами сообщений.':
    'Make a report on containers, services and commands: what failed, what got fixed, what still does not work. With message numbers.',
  'Сводка по чату…': 'Chat summary…', 'Подставь название чата': 'Fill in the chat name',
  'Сделай сводку по чату «»: о чём говорили, что решили, что осталось открытым.': 'Summarize the chat “”: what was discussed, what was decided, what is still open.',
  'Найти…': 'Find…', 'Поиск своими словами': 'Search in your own words', 'Найди сообщения про ': 'Find messages about ',
  'Спроси о своих сообщениях…': 'Ask about your messages…', 'Отправить · Enter': 'Send · Enter', 'Остановить': 'Stop',
  'Слова «сегодня», «вчера», «за неделю» в вопросе сами сузят выборку.': 'Words like “today”, “yesterday”, “this week” in the question narrow the selection.',
  'Enter — отправить, Shift+Enter — новая строка': 'Enter — send, Shift+Enter — new line', 'Выборка: {p}': 'Selection: {p}',
  'за сутки': 'last day', 'за 2 дня': 'last 2 days', 'за неделю': 'last week', 'за месяц': 'last month', 'за всё время': 'all time',
  'опирался на {n}': 'based on {n}', 'сообщений в выборке не было': 'no messages in the selection', '{n} токенов': '{n} tokens',
  'остановлено': 'stopped', 'О чём спросить?': 'What to ask?',
  'Ассистент читает твои сообщения из базы — выборку за период — и отвечает моделью на этом компьютере. Номера вида #123 в ответе открывают само сообщение.':
    'The assistant reads your messages from the database — a selection for the period — and answers with a model on this computer. Numbers like #123 in the answer open the message itself.',
  '{p} не отвечает. Запусти его или выбери другую модель в настройках беседы.': '{p} is not responding. Start it or pick another model in the conversation settings.',
  'Модель не выбрана — открой «Модели» или настройки беседы.': 'No model selected — open “Models” or the conversation settings.',
  'Выбери модель в настройках беседы': 'Pick a model in the conversation settings', 'Собираю сообщения…': 'Collecting messages…',
  'Выборка: {s}': 'Selection: {s}', 'Остановлено': 'Stopped', 'Открыть сообщение': 'Open the message',
  'моделей нет — открой «Модели»': 'no models — open “Models”', 'недоступна': 'unavailable',
  'Модель умеет контекст до {n} токенов.': 'The model supports a context of up to {n} tokens.', 'Температура': 'Temperature',
  'Ниже — точнее и повторяемее (для сводок и поиска), выше — свободнее.': 'Lower — more precise and repeatable (summaries, search), higher — freer.',
  'Размер контекста': 'Context size', 'токенов': 'tokens',
  'У LM Studio размер контекста задаётся при загрузке модели в самой программе; здесь он лишь решает, сколько сообщений отдать.':
    'In LM Studio the context size is set when the model is loaded in the app; here it only decides how many messages to pass.',
  'Больше — больше сообщений влезет в выборку, но нужно больше видеопамяти и ответ медленнее.': 'Bigger — more messages fit into the selection, but it needs more VRAM and answers slower.',
  'Длина ответа, не больше': 'Answer length, at most', 'Какие сообщения давать модели': 'Which messages to give the model', 'Период': 'Period',
  'Ничего не выбрано — все источники.': 'Nothing selected — all sources.', 'Сообщений в выборке, не больше': 'Messages in the selection, at most',
  'Брать и прочитанные': 'Include read ones', 'Брать хвосты логов (тематические колонки)': 'Include log tails (themed columns)',
  'Системный промпт': 'System prompt', 'Пусто — стандартный (виден подсказкой). Здесь можно задать тон, язык ответа, формат отчётов.':
    'Empty — the standard one (shown as a hint). Set the tone, answer language or report format here.',
  'Сделать по умолчанию': 'Make default', 'Стандартный промпт': 'Standard prompt', 'Сохранено как настройки новых бесед': 'Saved as settings for new conversations',
  'ГБ': 'GB', 'ошибка: {e}': 'error: {e}', 'скачана': 'downloaded', 'Отменить': 'Cancel', 'Отменяю…': 'Cancelling…',
  'поместится в видеокарту': 'fits the graphics card', 'на процессоре — медленнее': 'on the CPU — slower', 'может не хватить памяти': 'may run out of memory',
  'Установленные': 'Installed', 'Скачать': 'Download', 'Найти в каталоге или ввести своё имя модели…': 'Search the catalog or type a model name…',
  'Найти среди установленных…': 'Search installed…', 'загружена': 'loaded', 'контекст до {n}': 'context up to {n}',
  'По умолчанию': 'Make default', 'Среди установленных такой нет.': 'No such model installed.', 'Посмотри во вкладке «Скачать».': 'Look in the Download tab.',
  'В LM Studio нет моделей для чата — скачай модель в самой программе (вкладка Discover) и нажми «Проверить ещё раз».':
    'LM Studio has no chat models — download one in the app (Discover tab) and click “Check again”.',
  'Моделей для чата ещё нет — открой вкладку «Скачать».': 'No chat models yet — open the Download tab.',
  'Видеопамять: {v}, оперативная: {r}. Размеры — примерно. Модель скачивается один раз и дальше работает без интернета.':
    'VRAM: {v}, RAM: {r}. Sizes are approximate. A model is downloaded once and then works offline.',
  'нет NVIDIA': 'no NVIDIA', 'своё имя: из ollama.com/library (qwen3:30b) или с Hugging Face (hf.co/автор/модель:Q4_K_M)':
    'your own name: from ollama.com/library (qwen3:30b) or Hugging Face (hf.co/author/model:Q4_K_M)',
  'В каталоге такой нет — впиши точное имя модели, и появится кнопка «Скачать».': 'Not in the catalog — type the exact model name and a Download button appears.',
  'Всё из каталога уже установлено.': 'Everything from the catalog is installed.',
  'Полный список моделей — на ollama.com/library; любое имя оттуда можно вписать в поиск.': 'The full list is at ollama.com/library; type any name from there into the search.',
  'Точно удалить?': 'Delete for sure?', 'Модель удалена': 'Model deleted', 'Модель по умолчанию: {m}': 'Default model: {m}',
  'Не скачалось: {e}': 'Download failed: {e}', 'Модель {m} скачана': 'Model {m} downloaded', 'Скачивание остановлено': 'Download stopped',
  'Модели, которые можно использовать в беседах. Всё работает на этом компьютере.': 'Models you can use in conversations. Everything runs on this computer.',
  '← К беседе': '← Back to the conversation', 'Ollama не отвечает': 'Ollama is not responding',
  'Установи Ollama (ollama.com) — на Linux одной командой, потом она работает сама:': 'Install Ollama (ollama.com) — on Linux with one command, then it runs by itself:',
  'На Windows — установщик с ollama.com/download. Уже стоит, но не запущена: ollama serve.': 'On Windows use the installer from ollama.com/download. Installed but not running: ollama serve.',
  'LM Studio не отвечает': 'LM Studio is not responding',
  'Скачай LM Studio (lmstudio.ai), скачай в ней модель и включи сервер: вкладка Developer → Start Server.': 'Get LM Studio (lmstudio.ai), download a model in it and start the server: Developer tab → Start Server.',
  'Запустить сервер LM Studio': 'Start the LM Studio server', 'Запускаю…': 'Starting…', 'Сервер LM Studio запущен': 'LM Studio server started',
  'Не получилось': 'Did not work', 'Знакомство': 'Welcome', 'Где модель': 'Where', 'Какая модель': 'Which model', 'Готово': 'Done',
  'Привет! Это ассистент по твоим сообщениям': 'Hi! This is an assistant for your messages',
  'Можно спросить своими словами: «что я пропустил за утро?», «кто спрашивал про отчёт?», «что падало на серверах за неделю?», «сделай сводку по чату…». Ассистент соберёт подходящие сообщения из базы и ответит, а номера #123 в ответе откроют сами сообщения.':
    'Ask in your own words: “what did I miss this morning?”, “who asked about the report?”, “what failed on the servers this week?”, “summarize the chat…”. The assistant gathers matching messages from the database and answers; numbers like #123 open the messages.',
  'Отвечает модель на этом компьютере — через Ollama или LM Studio. Сообщения никуда не уходят, интернет нужен только чтобы один раз скачать модель.':
    'A model on this computer answers — via Ollama or LM Studio. Messages go nowhere; the internet is only needed once, to download a model.',
  'Начать настройку': 'Start setup', 'Где будет работать модель': 'Where the model will run',
  'Обе программы бесплатные и работают на этом компьютере. Если ни одной нет — проще начать с Ollama: модели скачиваются прямо отсюда.':
    'Both are free and run on this computer. If you have neither, start with Ollama: models download right from here.',
  'Простая, модели скачиваются одной кнопкой прямо в этом окне.': 'Simple: models download with one button right in this window.',
  'Программа с окном: модели ищутся и скачиваются в ней самой.': 'An app with a window: models are found and downloaded in the app itself.',
  'найдена · моделей для чата: {n}': 'found · chat models: {n}', 'не отвечает — {e}': 'not responding — {e}', '← Назад': '← Back', 'Дальше': 'Next',
  'Выбери установленную модель или скачай новую. Для сводок и поиска по русским сообщениям хороши модели с флажком 🇷🇺.':
    'Pick an installed model or download a new one. Models with the 🇷🇺 flag are good for Russian messages.',
  'Выбери установленную модель (или скачай и выбери)': 'Pick an installed model (or download one and pick it)',
  'Модель: {m} ({p}). Её и другие настройки — температуру, размер контекста, какие сообщения брать — можно поменять в любой беседе кнопкой настроек вверху.':
    'Model: {m} ({p}). It and other settings — temperature, context size, which messages to use — can be changed in any conversation with the settings button at the top.',
  'Начать беседу': 'Start a conversation', 'Сервер виджета не отвечает — ассистент не загрузился.': 'The widget server is not responding — the assistant could not load.',

  // ── ассистент: размышления моделей ──
  'Думает…': 'Thinking…', 'Размышления модели': 'Model thinking', '{n} символов': '{n} characters',
  'Скрывать — свёрнуты над ответом': 'Hide — collapsed above the answer', 'Показывать сразу': 'Show right away',
  'Не просить размышлять — быстрее': 'Do not ask it to think — faster',
  'Модель «думающая» (qwen3, deepseek-r1 и подобные): сначала рассуждает, потом отвечает. «Не просить» ускоряет гибридные модели, но модели, которые думают всегда, будут рассуждать прямо в ответе.':
    'A “thinking” model (qwen3, deepseek-r1 and similar) reasons first and answers after. “Do not ask” speeds up hybrid models, but always-thinking models will reason right in the answer.',
  'Эта модель не размышляет — настройка на неё не влияет.': 'This model does not think — the setting has no effect.',

  // ── поиск в шапке доски ──
  'Поиск…': 'Search…', 'Поиск по всем сообщениям · клавиша /': 'Search all messages · key /', 'Найдено': 'Found',
  'Все результаты в «Поиске»': 'All results in Search', 'Ничего не нашлось по «{q}»': 'Nothing found for “{q}”',
  'Сервер виджета не отвечает': 'The widget server is not responding', 'на доске': 'on the board',

  // ── логи ──
  'Логи': 'Logs',
  'Журнал работы самой программы: запуск, ошибки, фоновые задачи, что сделали правила. Тексты твоих сообщений сюда не пишутся. Журнал лежит только на этом компьютере.':
    'The log of the app itself: start-up, errors, background jobs, what rules did. The text of your messages is never written here. The log stays on this computer.',
  'Все': 'All', 'Внимание и ошибки': 'Warnings and errors', 'Только ошибки': 'Errors only',
  'инфо': 'info', 'внимание': 'warning', 'ошибка': 'error',
  'сбор': 'collector', 'доска': 'board', 'страница': 'page', 'просмотр': 'viewer',
  'Поиск по журналу': 'Search the log', 'Обновлять само': 'Auto-refresh', 'Скопировать': 'Copy', 'Очистить': 'Clear',
  'Записей: {n}': 'Entries: {n}', 'показаны последние {n}': 'showing the latest {n}', 'ошибок за сутки: {n}': 'errors in the last day: {n}',
  'папка': 'folder', 'из {m} — старые записи удаляются сами': 'of {m}; old entries are removed automatically',
  '{n} Б': '{n} B', '{n} КБ': '{n} KB', '{n} МБ': '{n} MB',
  'Журнал пуст.': 'The log is empty.', 'Журнал очищен': 'Log cleared', 'Удалить все записи? Нажми ещё раз': 'Delete all entries? Click again',
  'Сохранено: {p}': 'Saved: {p}',
  'Чтобы сообщить об ошибке, выгрузи журнал: домашняя папка в выгрузке заменится на «~», имя пользователя — на <user>. Всё равно просмотри файл перед отправкой.':
    'To report a bug, export the log: your home folder becomes “~” and your user name becomes <user>. Still, look through the file before sending it.',

  // ── ассистент: OpenRouter, картинки, код, графики ──
  'Ollama и LM Studio бесплатные и работают на этом компьютере. Если ни одной нет — проще начать с Ollama: модели скачиваются прямо отсюда. OpenRouter — облачные модели, по желанию.':
    'Ollama and LM Studio are free and run on this computer. If you have neither, Ollama is the easiest start: models download right from here. OpenRouter is cloud models, optional.',
  'OpenRouter выключен — включи его в «Моделях» или выбери локальную модель': 'OpenRouter is off — turn it on under “Models” or pick a local model',
  'OpenRouter даёт доступ к сотням облачных моделей по твоему ключу. В беседе с такой моделью к каждому вопросу уйдут выборка твоих сообщений (тексты, имена, названия чатов, хвосты логов, если они включены) и приложенные картинки — на серверы OpenRouter и компании, чья это модель. Что с ними будет дальше, решают их правила, а не messhub.':
    'OpenRouter gives access to hundreds of cloud models with your key. In a conversation with such a model every question sends a selection of your messages (texts, names, chat titles, log tails if enabled) and attached pictures to the servers of OpenRouter and of the company behind the model. What happens next is up to their rules, not messhub.',
  'OpenRouter отключён — облачные модели недоступны': 'OpenRouter is off — cloud models are unavailable',
  'OpenRouter подключён': 'OpenRouter connected',
  'OpenRouter подключён — облачные модели': 'OpenRouter connected — cloud models',
  'SVG скопирован — можно вставить в документ': 'SVG copied — paste it into a document',
  '{i} / {o} за 1 млн токенов': '{i} / {o} per 1M tokens',
  '{n} не посчитались — модель сбоит на этих текстах. Умный поиск их не найдёт, обычный — найдёт. Попробую снова при перезапуске и раз в сутки.':
    '{n} could not be indexed — the model fails on these texts. Smart search will not find them, plain search will. I will retry on restart and once a day.',
  'В беседах с этими моделями выборка сообщений, вопросы и картинки уходят в OpenRouter и к провайдеру модели. Такие беседы помечены ☁.':
    'Conversations with these models send the message selection, questions and pictures to OpenRouter and the model provider. They are marked ☁.',
  'Видит картинки.': 'Sees pictures.',
  'Выборка сообщений (тексты, имена, названия чатов), вопрос и картинки уйдут в OpenRouter и к провайдеру модели. Для личного и рабочего лучше локальная модель.':
    'The message selection (texts, names, chat titles), the question and pictures will go to OpenRouter and the model provider. For personal and work chats a local model is better.',
  'Выборка сообщений, вопрос и картинки уходят в OpenRouter и к провайдеру модели. Локальную модель можно выбрать в настройках беседы.':
    'The message selection, the question and pictures go to OpenRouter and the model provider. You can pick a local model in the conversation settings.',
  'Годятся PNG, JPEG, GIF и WebP': 'PNG, JPEG, GIF and WebP work',
  'График': 'Chart', 'Таблица': 'Table', 'Другое': 'Other', 'Значение': 'Value', 'всего': 'total', 'Ряд {n}': 'Series {n}',
  'График не нарисовался: данные не похожи на JSON.': 'The chart was not drawn: the data does not look like JSON.',
  'График не нарисовался: нужны labels и series с числами.': 'The chart was not drawn: it needs labels and series with numbers.',
  'Картинка не открылась': 'The picture did not open',
  'Ключ {k} хранится только на этом компьютере. Согласие дано {d}.': 'The key {k} is stored only on this computer. Consent given {d}.',
  'Ключ создаётся на openrouter.ai в разделе Keys. Он хранится только на этом компьютере (файл с доступом только для тебя) и странице обратно не показывается.':
    'Create a key on openrouter.ai under Keys. It is stored only on this computer (a file only you can read) and is never shown back on the page.',
  'Ключ сохранён': 'Key saved', 'Ключ удалён': 'Key deleted', 'Код скопирован': 'Code copied',
  'Локальные модели работают на этом компьютере. Беседы с облачными моделями OpenRouter помечены ☁ — их сообщения уходят наружу.':
    'Local models run on this computer. Conversations with OpenRouter cloud models are marked ☁ — their messages leave the computer.',
  'Модели, которые можно использовать в беседах. Ollama и LM Studio работают на этом компьютере; OpenRouter — облако, подключается по желанию.':
    'Models you can use in conversations. Ollama and LM Studio run on this computer; OpenRouter is the cloud, connected only if you want.',
  'Найти модель…': 'Find a model…', 'Найти среди {n} моделей: gemini, qwen, deepseek…': 'Search {n} models: gemini, qwen, deepseek…',
  'Не больше {n} картинок к одному вопросу': 'No more than {n} pictures per question',
  'Ничего не нашлось — поменяй поиск или сними фильтры.': 'Nothing found — change the search or clear the filters.',
  'Облачная модель': 'Cloud model', 'Облачная модель.': 'Cloud model.', 'Обновить список': 'Refresh list',
  'Отключить': 'Disconnect', 'Отключить и удалить ключ': 'Disconnect and delete the key',
  'Подключаешь на свой страх и риск. Для рабочих и личных переписок лучше оставить локальные модели. Локальные беседы работают как раньше, облачные помечены ☁.':
    'You connect it at your own risk. For work and personal chats keep local models. Local conversations work as before, cloud ones are marked ☁.',
  'Подключить OpenRouter': 'Connect OpenRouter', 'Показаны {a} из {b} — уточни поиск.': 'Showing {a} of {b} — refine the search.',
  'Понимаю: выборка сообщений и вопросы будут уходить в OpenRouter': 'I understand: message selections and questions will be sent to OpenRouter',
  'Попробовать сейчас': 'Retry now', 'Приложить картинку (можно вставить из буфера или перетащить)': 'Attach a picture (paste or drag it in too)',
  'Рисую график…': 'Drawing the chart…', 'Скопировать SVG': 'Copy SVG', 'Сменить ключ': 'Change key', 'Снова в очереди: {n}': 'Queued again: {n}',
  'Сотни облачных моделей по твоему ключу, часть бесплатно. Сообщения уходят наружу — на твой страх и риск.':
    'Hundreds of cloud models with your key, some free. Messages leave the computer — at your own risk.',
  'Сохранить ключ': 'Save key', 'Список моделей не загрузился: {e}': 'The model list did not load: {e}',
  'Список моделей пуст — проверь интернет и нажми «Проверить ещё раз».': 'The model list is empty — check the internet and press “Check again”.',
  'Точно удалить ключ?': 'Delete the key?', 'Убрать': 'Remove',
  'Цена: {i} / {o} за 1 млн токенов (вход / ответ).': 'Price: {i} / {o} per 1M tokens (input / answer).',
  'Цены — за 1 млн токенов, их берёт OpenRouter со счёта твоего ключа. Бесплатные модели обычно с ограничением запросов в минуту.':
    'Prices are per 1M tokens, charged by OpenRouter to your key’s balance. Free models are usually rate-limited per minute.',
  'Что на картинке?': 'What is in the picture?', 'Эта модель, похоже, не видит картинки': 'This model probably cannot see pictures',
  'Это облако, а не этот компьютер': 'This is the cloud, not this computer',
  'бесплатно': 'free', 'видит картинки': 'sees pictures', 'размышляет': 'reasons', 'облако': 'cloud', 'пишет…': 'writing…',
  'Бесплатные': 'Free', 'Видят картинки': 'See pictures', 'Размышляют': 'Reason',
  'локальные модели и облачные (OpenRouter)': 'local and cloud models (OpenRouter)',
  'не подключён': 'not connected', 'подключён · моделей: {n}': 'connected · models: {n}', 'повторю сам через {n} с': 'retrying by itself in {n} s',
  // ── справка ──
  'Инструкции по настройке. Если что-то не ловится — начни с раздела «Система»: он сам подскажет известные случаи.':
    'Setup instructions. If something is not captured, start with “System”: it points out known issues.',
};

let LANG = 'ru';
function setLang(l) { LANG = l === 'en' ? 'en' : 'ru'; document.documentElement.lang = LANG; }
function t(s, p) {
  let r = (LANG === 'en' && EN[s]) || s;
  if (p) r = r.replace(/\{(\w+)\}/g, (m, k) => (p[k] != null ? p[k] : m));
  return r;
}
// число со словом: tp(5, ['сообщение','сообщения','сообщений'], ['message','messages'])
function tpw(n, ru, en) {
  if (LANG === 'en') return n === 1 ? en[0] : en[1];
  const a = n % 10, b = n % 100;
  return a === 1 && b !== 11 ? ru[0] : (a >= 2 && a <= 4 && (b < 12 || b > 14) ? ru[1] : ru[2]);
}
function tp(n, ru, en) { return n + ' ' + tpw(n, ru, en); }
// словари для частых слов
const W = {
  msg: [['сообщение', 'сообщения', 'сообщений'], ['message', 'messages']],
  chat: [['чат', 'чата', 'чатов'], ['chat', 'chats']],
  chatIn: [['чате', 'чатах', 'чатах'], ['chat', 'chats']],
  sender: [['отправитель', 'отправителя', 'отправителей'], ['sender', 'senders']],
  senderFrom: [['отправителя', 'отправителей', 'отправителей'], ['sender', 'senders']],
  rule: [['правило', 'правила', 'правил'], ['rule', 'rules']],
  row: [['строка', 'строки', 'строк'], ['row', 'rows']],
  line: [['строка', 'строки', 'строк'], ['line', 'lines']],
  entry: [['запись', 'записи', 'записей'], ['entry', 'entries']],
  letter: [['письмо', 'письма', 'писем'], ['message', 'messages']],
  newMsg: [['новое сообщение', 'новых сообщения', 'новых сообщений'], ['new message', 'new messages']],
  pinnedMsg: [['закреплённое сообщение', 'закреплённых сообщения', 'закреплённых сообщений'], ['pinned message', 'pinned messages']],
  snoozedMsg: [['отложенное сообщение', 'отложенных сообщения', 'отложенных сообщений'], ['snoozed message', 'snoozed messages']],
};
function translateDom(root) {
  (root || document).querySelectorAll('[data-t]').forEach(el => { el.textContent = t(el.dataset.t); });
  (root || document).querySelectorAll('[data-t-title]').forEach(el => { el.title = t(el.dataset.tTitle); });
  (root || document).querySelectorAll('[data-t-ph]').forEach(el => { el.placeholder = t(el.dataset.tPh); });
  (root || document).querySelectorAll('[data-t-aria]').forEach(el => { el.setAttribute('aria-label', t(el.dataset.tAria)); });
}
