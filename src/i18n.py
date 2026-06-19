from __future__ import annotations


SUPPORTED_LANGS = {"ru", "uk", "en", "fr", "de", "es", "ka", "hy", "it"}


TEXTS = {
    "ru": {
        "pay": "Оплатить {stars} Stars",
        "status": "Статус доступа",
        "open_app": "Открыть Mini App",
        "share": "Поделиться",
        "rename": "Переименовать",
        "video_help": "Про видео",
        "language": "Язык",
        "quick_actions": "Быстрые действия:",
        "help_button": "Помощь",
        "resume_button": "Резюме",
        "next_steps": "Что дальше:",
        "done": "Готово",
        "now": "Сейчас",
        "next": "Далее",
        "details": "Детали",
        "stage": "этап",
        "cancelled": "Ок, отменил текущее действие.",
        "language_prompt": (
            "Выбери язык интерфейса для этого чата.\n"
            "Можешь оставить авто-язык Telegram или вручную переключить здесь."
        ),
        "unknown_language": "Неизвестный язык. Выбери язык кнопкой из меню.",
        "language_saved": "Готово. Язык этого чата: {language}.\n\nТеперь отправь изображение, видео или YouTube-ссылку.",
        "help_menu": (
            "Навигация по боту\n\n"
            "Главная идея простая: отправьте файл или ссылку, а бот сам покажет подходящие кнопки.\n\n"
            "Что умею:\n"
            "- конвертация картинок и видео;\n"
            "- YouTube Shorts/Preview;\n"
            "- субтитры разными стилями;\n"
            "- PNG-обложки и пакеты публикации;\n"
            "- PDF-резюме с шаблонами и фото.\n\n"
            "Выберите раздел ниже."
        ),
        "help_files": (
            "Файлы и конвертация\n\n"
            "1. Отправьте картинку или видео прямо в чат.\n"
            "2. Бот проверит размер и формат.\n"
            "3. Появятся кнопки форматов: PNG/JPG/WEBP/PDF или MP4/WEBM/GIF.\n"
            "4. Для изображений можно выбрать режим веса: легко, баланс, качество.\n\n"
            "Лимиты: изображения до {image_mb} MB, видео до {video_mb} MB."
        ),
        "help_youtube": (
            "YouTube-монтаж\n\n"
            "Отправьте ссылку YouTube. Бот предложит:\n"
            "- Shorts: вертикальные клипы по сильным моментам;\n"
            "- Preview: один широкий 16:9 ролик;\n"
            "- PNG-обложку;\n"
            "- пакет публикации ZIP.\n\n"
            "Для интервью работает face-focus: стараюсь держать лицо в кадре."
        ),
        "help_resume": (
            "PDF-резюме\n\n"
            "Команда: /resume\n"
            "Бот проведет по шагам, даст пропуск необязательных полей кнопками, примет фото, покажет превью шаблонов и даст отредактировать блоки перед PDF."
        ),
        "help_subtitles": (
            "Субтитры\n\n"
            "После MP4 нажмите кнопку Subtitles. Можно выбрать стиль, посмотреть картинку-примеры стилей и выбрать язык речи: Auto, RU, UK, EN.\n\n"
            "Есть стили Pop, Neon, Clean, Typewriter, Luxury, Mono и другие."
        ),
        "help_pro": (
            "Pro и Telegram Stars\n\n"
            "Free подходит для пробы. Pro открывает больше обработок, YouTube, субтитры, обложки, пакеты публикации и приоритетные сценарии.\n\n"
            "Оплата идет через Telegram Stars. Нажмите кнопку оплаты, Telegram покажет официальный счет, после оплаты доступ активируется автоматически на {days} дней."
        ),
        "pay_intro": (
            "Pro-доступ через Telegram Stars\n\n"
            "Что получите:\n"
            "- больше конвертаций;\n"
            "- YouTube Shorts/Preview;\n"
            "- автосубтитры и стили;\n"
            "- PNG-обложки;\n"
            "- пакеты публикации ZIP;\n"
            "- PDF-резюме без лишних ограничений.\n\n"
            "Стоимость: {stars} Stars на {days} дней. Сейчас отправлю официальный счет Telegram."
        ),
        "resume_start": "Соберем сильное PDF-резюме. Начнем с имени и фамилии.\n\nМожно отвечать обычным текстом, списки и переносы строк я сохраню.",
        "resume_position": "Укажите желаемую должность или роль: например, Product Manager, Python Developer, Sales Lead.",
        "resume_contact": "Контакты: телефон, email, Telegram, LinkedIn или город. Можно в одну строку.",
        "resume_summary": "Напишите краткую профессиональную цель или короткое резюме о себе. Это может быть один-два предложения о том, в чем вы сильны.",
        "resume_experience": "Опыт работы. Лучше форматировать так:\nКомпания / роль / годы\n- что делали\n- какой результат получили",
        "resume_education": "Укажите ваше образование (например: 'Высшее, СПбГУ, информатика').",
        "resume_skills": "Перечислите ключевые навыки и инструменты через запятую: Python, SQL, Git, продажи, аналитика.",
        "resume_achievements": "Добавьте ваши достижения, сертификаты или проекты. Если пока нет, напишите 'нет'.",
        "resume_additional": "Дополнительно: языки, сертификаты, курсы, хобби, инструменты. Напишите все, что хотите добавить в резюме.",
        "resume_photo": "Хотите добавить фото в резюме? Отправьте портрет как фото или картинку-файл.\nЕсли фото не нужно, нажмите кнопку ниже.",
        "resume_skip_photo": "Пропустить фото",
        "resume_photo_added": "Фото добавлено. Давайте проверим резюме перед генерацией.",
        "resume_photo_wrong": "Отправьте фото/картинку-файл или нажмите «Пропустить фото».",
        "resume_template_prompt": "Выберите профессиональный шаблон для PDF:",
        "resume_skip_achievements": "Пропустить достижения",
        "resume_skip_additional": "Пропустить дополнительно",
        "start": (
            "Привет! Я конвертирую изображения и видео прямо в чате.\n\n"
            "Изображения: PNG, JPG, WEBP, PDF, BMP, TIFF, GIF.\n"
            "Видео: MP4, WEBM, GIF.\n"
            "YouTube: отправь ссылку, и я предложу Shorts или Preview wide-ролик до 30 сек.\n\n"
            "Для интервью включен face-focus: клипы стараются держать лицо в кадре.\n"
            "Подписка: {stars} Telegram Stars на {days} дней."
        ),
        "help": (
            "Как пользоваться:\n"
            "1. Отправь изображение, видео или YouTube-ссылку.\n"
            "2. Для файлов выбери формат кнопкой.\n"
            "3. Для YouTube выбери режим: вертикальные Shorts или один широкий Preview-ролик.\n\n"
            "Лимиты: изображения до {image_mb} MB, видео до {video_mb} MB.\n"
            "YouTube: до {yt_minutes} минут, до {shorts} клипов по {short_seconds} сек.\n"
            "Команды: /subscribe, /status, /language, /id, /help, /resume."
        ),
        "id": "Твой Telegram ID: {user_id}\nБесплатный доступ задается в FREE_USER_IDS в .env.",
        "free_access": "Доступ активен: бесплатный пользователь из FREE_USER_IDS.",
        "sub_active": "Подписка активна до {date}.",
        "sub_inactive": "Подписка пока не активна.",
        "need_sub_youtube": "Для нарезки YouTube-видео нужна подписка.",
        "youtube_start": (
            "Принял YouTube-ссылку. Скачаю видео и обработаю выбранный режим.\n"
            "Если это интервью или разговорный ролик, попробую держать лицо в кадре через face-focus."
        ),
    },
    "uk": {
        "pay": "Оплатити {stars} Stars",
        "status": "Статус доступу",
        "open_app": "Відкрити Mini App",
        "share": "Поділитися",
        "rename": "Перейменувати",
        "video_help": "Про відео",
        "language": "Мова",
        "quick_actions": "Швидкі дії:",
        "help_button": "Допомога",
        "resume_button": "Резюме",
        "next_steps": "Що далі:",
        "done": "Готово",
        "now": "Зараз",
        "next": "Далі",
        "details": "Деталі",
        "stage": "етап",
        "cancelled": "Ок, скасував поточну дію.",
        "language_prompt": (
            "Оберіть мову інтерфейсу для цього чату.\n"
            "Можна залишити авто-мову Telegram або перемкнути вручну тут."
        ),
        "unknown_language": "Невідома мова. Оберіть мову кнопкою з меню.",
        "language_saved": "Готово. Мова цього чату: {language}.\n\nТепер надішліть зображення, відео або YouTube-посилання.",
        "help_menu": "Навігація по боту\n\nНадішліть файл або посилання, а бот покаже потрібні кнопки.\n\nОберіть розділ нижче.",
        "help_files": "Файли та конвертація\n\nНадішліть зображення або відео, потім оберіть формат кнопкою.\n\nЛіміти: зображення до {image_mb} MB, відео до {video_mb} MB.",
        "help_youtube": "YouTube-монтаж\n\nНадішліть YouTube-посилання. Бот запропонує Shorts, Preview, PNG-обкладинку або ZIP-пакет публікації.",
        "help_resume": "PDF-резюме\n\nКоманда: /resume\nБот проведе по кроках, прийме фото, покаже прев'ю шаблонів і дасть редагувати блоки.",
        "help_subtitles": "Субтитри\n\nПісля MP4 натисніть Subtitles. Можна обрати стиль, подивитися приклади стилів і вибрати мову мовлення.",
        "help_pro": "Pro і Telegram Stars\n\nPro відкриває більше обробок, YouTube, субтитри, обкладинки та ZIP-пакети.\n\nОплата через Telegram Stars на {days} днів.",
        "pay_intro": "Pro-доступ через Telegram Stars\n\nВартість: {stars} Stars на {days} днів. Зараз надішлю офіційний рахунок Telegram.",
        "resume_start": "Зберемо сильне PDF-резюме. Почнемо з імені та прізвища.\n\nМожна відповідати звичайним текстом, списки й переноси рядків я збережу.",
        "resume_position": "Вкажіть бажану посаду або роль: наприклад, Product Manager, Python Developer, Sales Lead.",
        "resume_contact": "Контакти: телефон, email, Telegram, LinkedIn або місто. Можна в один рядок.",
        "resume_summary": "Напишіть коротку професійну ціль або резюме про себе. Достатньо одного-двох речень про ваші сильні сторони.",
        "resume_experience": "Досвід роботи. Краще форматувати так:\nКомпанія / роль / роки\n- що робили\n- який результат отримали",
        "resume_education": "Вкажіть освіту, наприклад: вища, університет, спеціальність.",
        "resume_skills": "Перелічіть ключові навички та інструменти через кому: Python, SQL, Git, продажі, аналітика.",
        "resume_achievements": "Додайте досягнення, сертифікати або проєкти. Якщо поки немає, напишіть 'ні'.",
        "resume_additional": "Додатково: мови, сертифікати, курси, хобі, інструменти. Напишіть усе, що хочете додати.",
        "resume_photo": "Хочете додати фото в резюме? Надішліть портрет як фото або файл-картинку.\nЯкщо фото не потрібне, натисніть кнопку нижче.",
        "resume_skip_photo": "Пропустити фото",
        "resume_photo_added": "Фото додано. Перевірмо резюме перед генерацією.",
        "resume_photo_wrong": "Надішліть фото/картинку-файл або натисніть «Пропустити фото».",
        "resume_template_prompt": "Оберіть професійний шаблон для PDF:",
        "resume_skip_achievements": "Пропустити досягнення",
        "resume_skip_additional": "Пропустити додаткове",
        "start": (
            "Привіт! Я конвертую зображення та відео прямо в чаті.\n\n"
            "Зображення: PNG, JPG, WEBP, PDF, BMP, TIFF, GIF.\n"
            "Відео: MP4, WEBM, GIF.\n"
            "YouTube: надішли посилання, і я запропоную Shorts або Preview wide-ролик до 30 сек.\n\n"
            "Для інтерв'ю увімкнено face-focus: кліпи намагаються тримати обличчя в кадрі.\n"
            "Підписка: {stars} Telegram Stars на {days} днів."
        ),
        "help": (
            "Як користуватися:\n"
            "1. Надішли зображення, відео або YouTube-посилання.\n"
            "2. Для файлів обери формат кнопкою.\n"
            "3. Для YouTube обери режим: вертикальні Shorts або один широкий Preview-ролик.\n\n"
            "Ліміти: зображення до {image_mb} MB, відео до {video_mb} MB.\n"
            "YouTube: до {yt_minutes} хвилин, до {shorts} кліпів по {short_seconds} сек.\n"
            "Команди: /subscribe, /status, /language, /id, /help, /resume."
        ),
        "id": "Твій Telegram ID: {user_id}\nБезкоштовний доступ задається у FREE_USER_IDS в .env.",
        "free_access": "Доступ активний: безкоштовний користувач із FREE_USER_IDS.",
        "sub_active": "Підписка активна до {date}.",
        "sub_inactive": "Підписка поки не активна.",
        "need_sub_youtube": "Для нарізки YouTube-відео потрібна підписка.",
        "youtube_start": (
            "Прийняв YouTube-посилання. Завантажу відео та оброблю вибраний режим.\n"
            "Якщо це інтерв'ю або розмовний ролик, спробую тримати обличчя в кадрі через face-focus."
        ),
    },
    "en": {
        "pay": "Pay {stars} Stars",
        "status": "Access Status",
        "open_app": "Open Mini App",
        "share": "Share",
        "rename": "Rename",
        "video_help": "Video Help",
        "language": "Language",
        "quick_actions": "Quick actions:",
        "help_button": "Help",
        "resume_button": "Resume",
        "next_steps": "Next steps:",
        "done": "Done",
        "now": "Now",
        "next": "Next",
        "details": "Details",
        "stage": "step",
        "cancelled": "Okay, I cancelled the current action.",
        "language_prompt": (
            "Choose the interface language for this chat.\n"
            "You can keep Telegram auto-language or switch it manually here."
        ),
        "unknown_language": "Unknown language. Choose a language using the menu button.",
        "language_saved": "Done. This chat language is {language}.\n\nNow send an image, video, or YouTube link.",
        "help_menu": "Bot navigation\n\nSend a file or link, and the bot will show the right buttons.\n\nChoose a section below.",
        "help_files": "Files and conversion\n\nSend an image or video, then choose the output format with a button.\n\nLimits: images up to {image_mb} MB, videos up to {video_mb} MB.",
        "help_youtube": "YouTube editing\n\nSend a YouTube link. The bot can offer Shorts, Preview, PNG cover, or a publication ZIP package.",
        "help_resume": "PDF resume\n\nCommand: /resume\nThe bot walks you through fields, accepts a photo, shows template previews, and lets you edit blocks before PDF generation.",
        "help_subtitles": "Subtitles\n\nAfter an MP4 is ready, tap Subtitles. You can choose a style, see style previews, and select speech language.",
        "help_pro": "Pro and Telegram Stars\n\nPro unlocks more processing, YouTube, subtitles, covers, and ZIP publication packages.\n\nPayment is via Telegram Stars for {days} days.",
        "pay_intro": "Pro access via Telegram Stars\n\nPrice: {stars} Stars for {days} days. I will send the official Telegram invoice now.",
        "resume_start": "Let's build a strong PDF resume. Start with your first and last name.\n\nYou can answer with normal text; I will keep lists and line breaks.",
        "resume_position": "Enter the target job title or role, for example: Product Manager, Python Developer, Sales Lead.",
        "resume_contact": "Contacts: phone, email, Telegram, LinkedIn, or city. One line is fine.",
        "resume_summary": "Write a short professional summary or career goal. One or two sentences about your strengths is enough.",
        "resume_experience": "Work experience. A good format is:\nCompany / role / years\n- what you did\n- what result you achieved",
        "resume_education": "Enter your education, for example: university, degree, field.",
        "resume_skills": "List key skills and tools separated by commas: Python, SQL, Git, sales, analytics.",
        "resume_achievements": "Add achievements, certificates, or projects. If there are none yet, write 'none'.",
        "resume_additional": "Additional info: languages, certificates, courses, hobbies, tools. Add anything you want included.",
        "resume_photo": "Would you like to add a photo? Send a portrait as a photo or image file.\nIf you do not need a photo, tap the button below.",
        "resume_skip_photo": "Skip photo",
        "resume_photo_added": "Photo added. Let's review the resume before generating it.",
        "resume_photo_wrong": "Send a photo/image file or tap “Skip photo”.",
        "resume_template_prompt": "Choose a professional PDF template:",
        "resume_skip_achievements": "Skip achievements",
        "resume_skip_additional": "Skip additional info",
        "start": (
            "Hi! I convert images and videos right in chat.\n\n"
            "Images: PNG, JPG, WEBP, PDF, BMP, TIFF, GIF.\n"
            "Video: MP4, WEBM, GIF.\n"
            "YouTube: send a link and I will offer Shorts or a Preview wide cut up to 30s.\n\n"
            "For interviews, face-focus is enabled: clips try to keep faces framed.\n"
            "Subscription: {stars} Telegram Stars for {days} days."
        ),
        "help": (
            "How to use:\n"
            "1. Send an image, video, or YouTube link.\n"
            "2. For files, choose the output format with buttons.\n"
            "3. For YouTube, choose vertical Shorts or one wide Preview cut.\n\n"
            "Limits: images up to {image_mb} MB, videos up to {video_mb} MB.\n"
            "YouTube: up to {yt_minutes} minutes, up to {shorts} clips of {short_seconds}s.\n"
            "Commands: /subscribe, /status, /language, /id, /help, /resume."
        ),
        "id": "Your Telegram ID: {user_id}\nFree access is configured in FREE_USER_IDS in .env.",
        "free_access": "Access is active: free user from FREE_USER_IDS.",
        "sub_active": "Subscription is active until {date}.",
        "sub_inactive": "Subscription is not active yet.",
        "need_sub_youtube": "A subscription is required for YouTube Shorts cutting.",
        "youtube_start": (
            "Got the YouTube link. I will download the video and process the selected mode.\n"
            "If it is an interview or talking-head video, I will try to keep faces framed with face-focus."
        ),
    },
}


def lang_from_code(language_code: str | None) -> str:
    code = (language_code or "").lower()
    for supported in SUPPORTED_LANGS:
        if code.startswith(supported):
            return supported
    if code.startswith("uk"):
        return "uk"
    if code.startswith("ru"):
        return "ru"
    return "en"


TEXTS.update({
    "ru": {
        **TEXTS["en"],
        **TEXTS.get("ru", {}),
        "pay": "Оплатить Stars",
        "status": "Статус",
        "wallet": "Баланс",
        "support": "Поддержка",
        "language": "Язык",
        "open_app": "Открыть CherryX",
        "quick_actions": "Быстрые действия:",
        "cancelled": "Ок, отменил текущее действие.",
        "language_prompt": "Выберите язык интерфейса для этого чата.",
        "unknown_language": "Неизвестный язык. Выберите язык кнопкой из меню.",
        "language_saved": "Готово. Язык этого чата: {language}.",
    },
    "uk": {
        **TEXTS["en"],
        **TEXTS.get("uk", {}),
        "pay": "Оплатити Stars",
        "status": "Статус",
        "wallet": "Баланс",
        "support": "Підтримка",
        "language": "Мова",
        "open_app": "Відкрити CherryX",
        "quick_actions": "Швидкі дії:",
        "cancelled": "Ок, скасував поточну дію.",
        "language_prompt": "Оберіть мову інтерфейсу для цього чату.",
        "unknown_language": "Невідома мова. Оберіть мову кнопкою з меню.",
        "language_saved": "Готово. Мова цього чату: {language}.",
    },
    "en": {
        **TEXTS["en"],
        "pay": "Pay Stars",
        "status": "Status",
        "wallet": "Wallet",
        "support": "Support",
        "language": "Language",
        "open_app": "Open CherryX",
    },
    "fr": {
        **TEXTS["en"],
        "pay": "Payer Stars",
        "status": "Statut",
        "wallet": "Solde",
        "support": "Support",
        "language": "Langue",
        "open_app": "Ouvrir CherryX",
        "quick_actions": "Actions rapides :",
        "cancelled": "D'accord, action annulée.",
        "language_prompt": "Choisissez la langue de ce chat.",
        "unknown_language": "Langue inconnue. Choisissez une langue avec le bouton du menu.",
        "language_saved": "C'est fait. Langue de ce chat : {language}.",
    },
    "de": {
        **TEXTS["en"],
        "pay": "Stars zahlen",
        "status": "Status",
        "wallet": "Guthaben",
        "support": "Support",
        "language": "Sprache",
        "open_app": "CherryX öffnen",
        "quick_actions": "Schnellaktionen:",
        "cancelled": "Okay, die aktuelle Aktion wurde abgebrochen.",
        "language_prompt": "Wählen Sie die Sprache für diesen Chat.",
        "unknown_language": "Unbekannte Sprache. Wählen Sie eine Sprache über die Menüschaltfläche.",
        "language_saved": "Fertig. Sprache dieses Chats: {language}.",
    },
    "es": {
        **TEXTS["en"],
        "pay": "Pagar Stars",
        "status": "Estado",
        "wallet": "Saldo",
        "support": "Soporte",
        "language": "Idioma",
        "open_app": "Abrir CherryX",
        "quick_actions": "Acciones rápidas:",
        "cancelled": "Listo, cancelé la acción actual.",
        "language_prompt": "Elige el idioma de este chat.",
        "unknown_language": "Idioma desconocido. Elige un idioma con el botón del menú.",
        "language_saved": "Listo. Idioma de este chat: {language}.",
    },
    "it": {
        **TEXTS["en"],
        "pay": "Paga Stars",
        "status": "Stato",
        "wallet": "Saldo",
        "support": "Supporto",
        "language": "Lingua",
        "open_app": "Apri CherryX",
        "quick_actions": "Azioni rapide:",
        "cancelled": "Ok, azione corrente annullata.",
        "language_prompt": "Scegli la lingua per questa chat.",
        "unknown_language": "Lingua sconosciuta. Scegli una lingua dal menu.",
        "language_saved": "Fatto. Lingua di questa chat: {language}.",
    },
    "ka": {
        **TEXTS["en"],
        "pay": "Stars გადახდა",
        "status": "სტატუსი",
        "wallet": "ბალანსი",
        "support": "მხარდაჭერა",
        "language": "ენა",
        "open_app": "CherryX-ის გახსნა",
        "quick_actions": "სწრაფი მოქმედებები:",
        "cancelled": "კარგი, მიმდინარე მოქმედება გაუქმდა.",
        "language_prompt": "აირჩიეთ ამ ჩატის ენა.",
        "unknown_language": "უცნობი ენა. აირჩიეთ ენა მენიუს ღილაკით.",
        "language_saved": "მზადაა. ამ ჩატის ენაა: {language}.",
    },
    "hy": {
        **TEXTS["en"],
        "pay": "Վճարել Stars",
        "status": "Կարգավիճակ",
        "wallet": "Բալանս",
        "support": "Աջակցություն",
        "language": "Լեզու",
        "open_app": "Բացել CherryX-ը",
        "quick_actions": "Արագ գործողություններ.",
        "cancelled": "Լավ, ընթացիկ գործողությունը չեղարկվեց։",
        "language_prompt": "Ընտրեք այս չատի լեզուն։",
        "unknown_language": "Անհայտ լեզու։ Ընտրեք լեզուն մենյուի կոճակով։",
        "language_saved": "Պատրաստ է։ Այս չատի լեզուն՝ {language}։",
    },
})


TEXTS.update({
    "ru": {
        **TEXTS["ru"],
        "pay": "Оплатить Stars",
        "status": "Статус",
        "wallet": "Баланс",
        "support": "Поддержка",
        "language": "Язык",
        "open_app": "Открыть CherryX",
        "quick_actions": "Быстрые действия:",
        "cancelled": "Ок, отменил текущее действие.",
        "language_prompt": "Выберите язык интерфейса для этого чата.",
        "unknown_language": "Неизвестный язык. Выберите язык кнопкой из меню.",
        "language_saved": "Готово. Язык этого чата: {language}.",
    },
    "uk": {
        **TEXTS["uk"],
        "pay": "Оплатити Stars",
        "status": "Статус",
        "wallet": "Баланс",
        "support": "Підтримка",
        "language": "Мова",
        "open_app": "Відкрити CherryX",
        "quick_actions": "Швидкі дії:",
        "cancelled": "Ок, скасував поточну дію.",
        "language_prompt": "Оберіть мову інтерфейсу для цього чату.",
        "unknown_language": "Невідома мова. Оберіть мову кнопкою з меню.",
        "language_saved": "Готово. Мова цього чату: {language}.",
    },
    "en": {
        **TEXTS["en"],
        "pay": "Pay Stars",
        "status": "Status",
        "wallet": "Wallet",
        "support": "Support",
        "language": "Language",
        "open_app": "Open CherryX",
    },
    "fr": {
        **TEXTS["en"],
        "pay": "Payer Stars",
        "status": "Statut",
        "wallet": "Solde",
        "support": "Support",
        "language": "Langue",
        "open_app": "Ouvrir CherryX",
        "quick_actions": "Actions rapides :",
        "cancelled": "D'accord, action annulée.",
        "language_prompt": "Choisissez la langue de ce chat.",
        "unknown_language": "Langue inconnue. Choisissez une langue avec le bouton du menu.",
        "language_saved": "C'est fait. Langue de ce chat : {language}.",
    },
    "de": {
        **TEXTS["en"],
        "pay": "Stars zahlen",
        "status": "Status",
        "wallet": "Guthaben",
        "support": "Support",
        "language": "Sprache",
        "open_app": "CherryX öffnen",
        "quick_actions": "Schnellaktionen:",
        "cancelled": "Okay, die aktuelle Aktion wurde abgebrochen.",
        "language_prompt": "Wählen Sie die Sprache für diesen Chat.",
        "unknown_language": "Unbekannte Sprache. Wählen Sie eine Sprache über die Menüschaltfläche.",
        "language_saved": "Fertig. Sprache dieses Chats: {language}.",
    },
    "es": {
        **TEXTS["en"],
        "pay": "Pagar Stars",
        "status": "Estado",
        "wallet": "Saldo",
        "support": "Soporte",
        "language": "Idioma",
        "open_app": "Abrir CherryX",
        "quick_actions": "Acciones rápidas:",
        "cancelled": "Listo, cancelé la acción actual.",
        "language_prompt": "Elige el idioma de este chat.",
        "unknown_language": "Idioma desconocido. Elige un idioma con el botón del menú.",
        "language_saved": "Listo. Idioma de este chat: {language}.",
    },
    "it": {
        **TEXTS["en"],
        "pay": "Paga Stars",
        "status": "Stato",
        "wallet": "Saldo",
        "support": "Supporto",
        "language": "Lingua",
        "open_app": "Apri CherryX",
        "quick_actions": "Azioni rapide:",
        "cancelled": "Ok, azione corrente annullata.",
        "language_prompt": "Scegli la lingua per questa chat.",
        "unknown_language": "Lingua sconosciuta. Scegli una lingua dal menu.",
        "language_saved": "Fatto. Lingua di questa chat: {language}.",
    },
    "ka": {
        **TEXTS["en"],
        "pay": "Stars გადახდა",
        "status": "სტატუსი",
        "wallet": "ბალანსი",
        "support": "მხარდაჭერა",
        "language": "ენა",
        "open_app": "CherryX-ის გახსნა",
        "quick_actions": "სწრაფი მოქმედებები:",
        "cancelled": "კარგი, მიმდინარე მოქმედება გაუქმდა.",
        "language_prompt": "აირჩიეთ ამ ჩატის ენა.",
        "unknown_language": "უცნობი ენა. აირჩიეთ ენა მენიუს ღილაკით.",
        "language_saved": "მზადაა. ამ ჩატის ენაა: {language}.",
    },
    "hy": {
        **TEXTS["en"],
        "pay": "Վճարել Stars",
        "status": "Կարգավիճակ",
        "wallet": "Բալանս",
        "support": "Աջակցություն",
        "language": "Լեզու",
        "open_app": "Բացել CherryX-ը",
        "quick_actions": "Արագ գործողություններ.",
        "cancelled": "Լավ, ընթացիկ գործողությունը չեղարկվեց։",
        "language_prompt": "Ընտրեք այս չատի լեզուն։",
        "unknown_language": "Անհայտ լեզու։ Ընտրեք լեզուն մենյուի կոճակով։",
        "language_saved": "Պատրաստ է։ Այս չատի լեզուն՝ {language}։",
    },
})


def tr(lang: str, key: str, **kwargs: object) -> str:
    template = TEXTS.get(lang, TEXTS["en"]).get(key, TEXTS["en"].get(key, key))
    return template.format(**kwargs)
