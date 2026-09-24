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
