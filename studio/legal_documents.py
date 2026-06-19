from __future__ import annotations

from .localization import clean_language


LEGAL_DOCUMENTS: dict[str, dict[str, dict[str, object]]] = {
    "terms": {
        "en": {
            "meta_service_type": "Digital services",
            "sections": [
                {
                    "title": "1. General provisions",
                    "paragraphs": [
                        "These Terms and conditions govern the use of CherryX Creator Studio, a remote digital service operated by the service provider.",
                    ],
                    "items": [
                        "CherryX Creator Studio provides digital services only. No physical goods are sold or shipped.",
                        "By choosing a plan, submitting files, starting generation or making a payment, the customer confirms acceptance of these Terms.",
                        "The service is provided remotely through the website interface, user workspace and related digital tools.",
                    ],
                },
                {
                    "title": "2. Definitions",
                    "items": [
                        "Service means access to CherryX Creator Studio and digital processing, creation, preparation or export of files.",
                        "Customer means a person who uses the website, uploads materials, selects a plan or pays for access.",
                        "Digital result means generated, processed or prepared files available in the workspace, including previews, downloads, ZIP packages, PDF files, videos, covers, subtitles or design layouts.",
                        "Plan means a paid access package with a defined price, period, storage amount, limits or available tools.",
                    ],
                },
                {
                    "title": "3. Service scope",
                    "paragraphs": [
                        "CherryX Creator Studio provides digital services for creating, processing and preparing downloadable files. The available tools may include:",
                    ],
                    "items": [
                        "video processing, short video preparation, previews and export files;",
                        "covers, PNG/JPG/WEBP images, design layouts and visual assets;",
                        "subtitles, SRT/VTT files and subtitle styling;",
                        "PDF resume generation and resume template exports;",
                        "publication packages, ZIP archives, texts and related digital assets;",
                        "additional AI-assisted preparation, formatting or conversion tools available in the workspace.",
                    ],
                    "after": [
                        "The exact list of available features depends on the selected plan, technical availability and the current version of the service.",
                    ],
                },
                {
                    "title": "4. Order process",
                    "items": [
                        "The customer selects a digital plan or starts using a paid tool in CherryX Creator Studio.",
                        "Before payment, the interface may show the plan name, price, access duration, storage amount, available tools or other relevant limits.",
                        "The order is considered placed when the customer confirms payment through the payment interface.",
                        "The service may require a user account, temporary workspace or session data to attach paid access and digital results.",
                    ],
                },
                {
                    "title": "5. Price and payment",
                    "items": [
                        "Payment is made online through WayForPay or another payment method displayed on the website.",
                        "The final amount is shown before payment confirmation. Additional bank, card issuer, currency conversion or payment provider fees may be applied by third parties and are outside the provider's control.",
                        "The provider receives confirmation of successful payment from the payment provider and activates the selected digital access after such confirmation.",
                        "If the payment is declined, interrupted or not confirmed, paid access may not be activated.",
                    ],
                },
                {
                    "title": "6. Activation, access and digital delivery",
                    "items": [
                        "Access to the paid plan is activated immediately after successful payment confirmation.",
                        "Digital results are delivered inside the customer workspace and may be downloaded from the service interface after processing is complete.",
                        "Because the service is digital and starts immediately after payment, no postal delivery, courier delivery or physical pickup is provided.",
                        "Processing time may depend on file size, queue load, selected tool, network availability and third-party infrastructure.",
                        "The provider may temporarily limit access for maintenance, security updates or technical repairs.",
                    ],
                },
                {
                    "title": "7. Customer materials and rights",
                    "items": [
                        "The customer is responsible for uploaded source files, text, images, video, audio and any other materials submitted to the service.",
                        "The customer confirms that they have the rights, permissions or lawful basis to upload and process submitted materials.",
                        "The customer remains the owner of their source materials and generated digital results, subject to third-party rights and applicable law.",
                        "The customer grants the provider a limited technical right to process submitted materials only for providing the requested digital service, generating previews, preparing downloads and maintaining the workspace.",
                    ],
                },
                {
                    "title": "8. Prohibited use",
                    "paragraphs": ["The customer must not use CherryX Creator Studio to create, upload, process or distribute materials that:"],
                    "items": [
                        "violate intellectual property rights, privacy rights or applicable law;",
                        "contain malicious code, phishing materials, fraud, spam or attempts to bypass security;",
                        "include unlawful, defamatory, abusive or harmful content;",
                        "attempt to overload, scrape, reverse engineer, resell or misuse the service infrastructure;",
                        "misrepresent the origin, authorship or legal status of generated materials.",
                    ],
                    "after": ["The provider may suspend or restrict access if prohibited use, payment abuse, technical abuse or security risk is detected."],
                },
                {
                    "title": "9. Storage, files and availability",
                    "items": [
                        "Plans may include storage limits, file limits, access periods or download availability periods.",
                        "The customer should download and keep copies of important digital results. The service is not intended to be the only long-term archive of customer files.",
                        "Files may be removed after plan expiration, account inactivity, technical cleanup, abuse prevention or storage limit enforcement.",
                        "The provider may change storage rules, technical limits and supported formats to improve stability or security.",
                    ],
                },
                {
                    "title": "10. Refunds and cancellation",
                    "paragraphs": [
                        "Refunds are governed by the separate Refund policy. In general, refunds are not provided because the services are digital and access to the service and results is provided immediately after successful payment.",
                    ],
                },
                {
                    "title": "11. Service quality and limitations",
                    "items": [
                        "The provider makes reasonable efforts to keep the service available, functional and secure.",
                        "Digital output quality may depend on the quality of uploaded source materials, selected settings, file format and technical limitations of automated processing.",
                        "The service may use automated or AI-assisted tools. The customer is responsible for reviewing the final result before publication or professional use.",
                        "The provider does not guarantee that every generated result will match a subjective expectation, platform rule, editorial standard or third-party requirement.",
                    ],
                },
                {
                    "title": "12. Liability",
                    "items": [
                        "The provider is not liable for losses caused by incorrect customer materials, unlawful uploads, third-party platform changes, payment provider issues, internet failures or force majeure events.",
                        "The provider is not responsible for how the customer uses, publishes, edits, distributes or monetizes generated digital results.",
                        "To the maximum extent permitted by applicable law, the provider's liability is limited to the amount paid by the customer for the relevant digital plan or service.",
                    ],
                },
                {
                    "title": "13. Support and communication",
                    "paragraphs": [
                        "Support requests, payment status questions and technical issues can be sent to the contacts listed on this website.",
                        "When contacting support, the customer should provide the payment date, email, plan name, task name or any other information that helps identify the order.",
                    ],
                },
                {
                    "title": "14. Changes to these Terms",
                    "items": [
                        "The provider may update these Terms to reflect service changes, legal requirements, payment provider requirements or technical changes.",
                        "The current version is published on this page and applies from the moment it becomes available on the website.",
                        "Continued use of the service after updates means acceptance of the updated Terms.",
                    ],
                },
            ],
        },
        "ru": {
            "meta_service_type": "Цифровые услуги",
            "sections": [
                {"title": "1. Общие положения", "paragraphs": ["Настоящие Правила и условия регулируют использование CherryX Creator Studio - дистанционного цифрового сервиса, предоставляемого поставщиком услуг."], "items": ["CherryX Creator Studio предоставляет только цифровые услуги. Физические товары не продаются и не доставляются.", "Выбирая план, загружая файлы, запуская генерацию или выполняя оплату, клиент подтверждает согласие с этими условиями.", "Услуга предоставляется дистанционно через сайт, рабочее пространство пользователя и связанные цифровые инструменты."]},
                {"title": "2. Термины", "items": ["Услуга - доступ к CherryX Creator Studio и цифровая обработка, создание, подготовка или экспорт файлов.", "Клиент - лицо, которое использует сайт, загружает материалы, выбирает план или оплачивает доступ.", "Цифровой результат - созданные, обработанные или подготовленные файлы в рабочем пространстве: предпросмотры, скачивания, ZIP, PDF, видео, обложки, субтитры или дизайн-макеты.", "План - платный пакет доступа с указанной ценой, сроком, объёмом хранилища, лимитами или доступными инструментами."]},
                {"title": "3. Состав услуг", "paragraphs": ["CherryX Creator Studio предоставляет цифровые услуги для создания, обработки и подготовки файлов к скачиванию. Доступные инструменты могут включать:"], "items": ["обработку видео, подготовку коротких роликов, предпросмотры и файлы экспорта;", "обложки, PNG/JPG/WEBP изображения, дизайн-макеты и визуальные материалы;", "субтитры, SRT/VTT файлы и оформление субтитров;", "генерацию PDF-резюме и экспорт по шаблонам;", "пакеты публикаций, ZIP-архивы, тексты и связанные цифровые материалы;", "дополнительные инструменты с поддержкой AI для подготовки, форматирования или конвертации."], "after": ["Точный список возможностей зависит от выбранного плана, технической доступности и текущей версии сервиса."]},
                {"title": "4. Порядок заказа", "items": ["Клиент выбирает цифровой план или запускает платный инструмент в CherryX Creator Studio.", "До оплаты интерфейс может показывать название плана, цену, срок доступа, объём хранилища, доступные инструменты и другие лимиты.", "Заказ считается оформленным после подтверждения оплаты через платёжный интерфейс.", "Для привязки оплаченного доступа и цифровых результатов может использоваться аккаунт, временное рабочее пространство или session data."]},
                {"title": "5. Цена и оплата", "items": ["Оплата выполняется онлайн через WayForPay или другой способ оплаты, отображённый на сайте.", "Итоговая сумма показывается до подтверждения платежа. Комиссии банка, эмитента карты, конвертации валют или платёжного провайдера могут применяться третьими лицами и не контролируются поставщиком.", "Поставщик получает подтверждение успешной оплаты от платёжного провайдера и после этого активирует выбранный цифровой доступ.", "Если платёж отклонён, прерван или не подтверждён, платный доступ может не активироваться."]},
                {"title": "6. Активация, доступ и цифровая доставка", "items": ["Доступ к оплаченному плану активируется сразу после успешного подтверждения оплаты.", "Цифровые результаты предоставляются в рабочем пространстве клиента и могут скачиваться из интерфейса после завершения обработки.", "Поскольку услуга цифровая и начинается сразу после оплаты, почтовая доставка, курьерская доставка и самовывоз не предусмотрены.", "Время обработки зависит от размера файлов, очереди, выбранного инструмента, сети и сторонней инфраструктуры.", "Поставщик может временно ограничивать доступ для обслуживания, обновлений безопасности или технического ремонта."]},
                {"title": "7. Материалы клиента и права", "items": ["Клиент отвечает за загруженные исходные файлы, текст, изображения, видео, аудио и другие материалы.", "Клиент подтверждает наличие прав, разрешений или законного основания для загрузки и обработки материалов.", "Клиент остаётся владельцем своих исходных материалов и цифровых результатов с учётом прав третьих лиц и применимого законодательства.", "Клиент предоставляет поставщику ограниченное техническое право обрабатывать материалы только для оказания заказанной цифровой услуги, создания предпросмотров, подготовки файлов к скачиванию и обслуживания рабочего пространства."]},
                {"title": "8. Запрещённое использование", "paragraphs": ["Клиент не должен использовать CherryX Creator Studio для создания, загрузки, обработки или распространения материалов, которые:"], "items": ["нарушают права интеллектуальной собственности, приватность или закон;", "содержат вредоносный код, phishing, fraud, spam или попытки обхода безопасности;", "являются незаконными, клеветническими, оскорбительными или вредоносными;", "направлены на перегрузку, scraping, reverse engineering, перепродажу или злоупотребление инфраструктурой сервиса;", "искажают происхождение, авторство или правовой статус созданных материалов."], "after": ["Поставщик может приостановить или ограничить доступ при запрещённом использовании, платёжных злоупотреблениях, техническом abuse или риске безопасности."]},
                {"title": "9. Хранение, файлы и доступность", "items": ["Планы могут включать лимиты хранилища, лимиты файлов, периоды доступа или сроки доступности скачивания.", "Клиент должен самостоятельно скачивать и хранить копии важных цифровых результатов. Сервис не предназначен быть единственным долгосрочным архивом файлов.", "Файлы могут удаляться после окончания плана, неактивности аккаунта, технической очистки, предотвращения abuse или применения лимитов хранилища.", "Поставщик может изменять правила хранения, технические лимиты и поддерживаемые форматы для стабильности и безопасности."]},
                {"title": "10. Возвраты и отмена", "paragraphs": ["Возвраты регулируются отдельной политикой возврата средств. В целом возврат средств не предусмотрен, поскольку услуги являются цифровыми, а доступ к сервису и результатам предоставляется сразу после успешной оплаты."]},
                {"title": "11. Качество услуги и ограничения", "items": ["Поставщик предпринимает разумные усилия для доступности, работоспособности и безопасности сервиса.", "Качество цифрового результата зависит от качества исходных материалов, настроек, формата файла и технических ограничений автоматизированной обработки.", "Сервис может использовать автоматические или AI-assisted инструменты. Клиент отвечает за проверку результата перед публикацией или профессиональным использованием.", "Поставщик не гарантирует, что каждый результат будет соответствовать субъективным ожиданиям, правилам платформы, редакционному стандарту или требованиям третьих лиц."]},
                {"title": "12. Ответственность", "items": ["Поставщик не отвечает за убытки, вызванные некорректными материалами клиента, незаконными загрузками, изменениями сторонних платформ, проблемами платёжного провайдера, сбоями интернета или форс-мажором.", "Поставщик не отвечает за то, как клиент использует, публикует, редактирует, распространяет или монетизирует цифровые результаты.", "В максимально допустимой законом мере ответственность поставщика ограничена суммой, оплаченной клиентом за соответствующий цифровой план или услугу."]},
                {"title": "13. Поддержка и коммуникация", "paragraphs": ["Запросы поддержки, вопросы по статусу оплаты и технические обращения можно направлять по контактам, указанным на сайте.", "При обращении клиенту желательно указать дату оплаты, email, название плана, название задачи или другую информацию для идентификации заказа."]},
                {"title": "14. Изменение условий", "items": ["Поставщик может обновлять условия из-за изменений сервиса, требований законодательства, требований платёжного провайдера или технических изменений.", "Актуальная версия публикуется на этой странице и действует с момента размещения на сайте.", "Продолжение использования сервиса после обновления означает согласие с обновлёнными условиями."]},
            ],
        },
        "uk": {
            "meta_service_type": "Цифрові послуги",
            "sections": [
                {"title": "1. Загальні положення", "paragraphs": ["Ці Правила і умови регулюють використання CherryX Creator Studio - дистанційного цифрового сервісу, який надається постачальником послуг."], "items": ["CherryX Creator Studio надає лише цифрові послуги. Фізичні товари не продаються і не доставляються.", "Обираючи план, завантажуючи файли, запускаючи генерацію або здійснюючи оплату, клієнт підтверджує згоду з цими умовами.", "Послуга надається дистанційно через сайт, робочий простір користувача та пов'язані цифрові інструменти."]},
                {"title": "2. Терміни", "items": ["Послуга - доступ до CherryX Creator Studio та цифрова обробка, створення, підготовка або експорт файлів.", "Клієнт - особа, яка використовує сайт, завантажує матеріали, обирає план або оплачує доступ.", "Цифровий результат - створені, оброблені або підготовлені файли у робочому просторі: попередні перегляди, завантаження, ZIP, PDF, відео, обкладинки, субтитри або дизайн-макети.", "План - платний пакет доступу із зазначеною ціною, строком, обсягом сховища, лімітами або доступними інструментами."]},
                {"title": "3. Склад послуг", "paragraphs": ["CherryX Creator Studio надає цифрові послуги для створення, обробки та підготовки файлів до завантаження. Доступні інструменти можуть включати:"], "items": ["обробку відео, підготовку коротких роликів, попередні перегляди та файли експорту;", "обкладинки, PNG/JPG/WEBP зображення, дизайн-макети та візуальні матеріали;", "субтитри, SRT/VTT файли та оформлення субтитрів;", "генерацію PDF-резюме та експорт за шаблонами;", "пакети публікацій, ZIP-архіви, тексти та пов'язані цифрові матеріали;", "додаткові інструменти з підтримкою AI для підготовки, форматування або конвертації."], "after": ["Точний перелік можливостей залежить від обраного плану, технічної доступності та поточної версії сервісу."]},
                {"title": "4. Порядок замовлення", "items": ["Клієнт обирає цифровий план або запускає платний інструмент у CherryX Creator Studio.", "До оплати інтерфейс може показувати назву плану, ціну, строк доступу, обсяг сховища, доступні інструменти та інші ліміти.", "Замовлення вважається оформленим після підтвердження оплати через платіжний інтерфейс.", "Для прив'язки оплаченого доступу та цифрових результатів може використовуватися акаунт, тимчасовий робочий простір або session data."]},
                {"title": "5. Ціна та оплата", "items": ["Оплата здійснюється онлайн через WayForPay або інший спосіб оплати, показаний на сайті.", "Підсумкова сума показується до підтвердження платежу. Комісії банку, емітента картки, конвертації валюти або платіжного провайдера можуть застосовуватися третіми особами і не контролюються постачальником.", "Постачальник отримує підтвердження успішної оплати від платіжного провайдера і після цього активує обраний цифровий доступ.", "Якщо платіж відхилений, перерваний або не підтверджений, платний доступ може не активуватися."]},
                {"title": "6. Активація, доступ і цифрова доставка", "items": ["Доступ до оплаченого плану активується одразу після успішного підтвердження оплати.", "Цифрові результати надаються у робочому просторі клієнта і можуть завантажуватися з інтерфейсу після завершення обробки.", "Оскільки послуга цифрова і починається одразу після оплати, поштова доставка, кур'єрська доставка та самовивіз не передбачені.", "Час обробки залежить від розміру файлів, черги, обраного інструменту, мережі та сторонньої інфраструктури.", "Постачальник може тимчасово обмежувати доступ для обслуговування, оновлень безпеки або технічного ремонту."]},
                {"title": "7. Матеріали клієнта та права", "items": ["Клієнт відповідає за завантажені вихідні файли, текст, зображення, відео, аудіо та інші матеріали.", "Клієнт підтверджує наявність прав, дозволів або законної підстави для завантаження й обробки матеріалів.", "Клієнт залишається власником своїх вихідних матеріалів і цифрових результатів з урахуванням прав третіх осіб і застосовного законодавства.", "Клієнт надає постачальнику обмежене технічне право обробляти матеріали лише для надання замовленої цифрової послуги, створення попередніх переглядів, підготовки файлів до завантаження і підтримки робочого простору."]},
                {"title": "8. Заборонене використання", "paragraphs": ["Клієнт не повинен використовувати CherryX Creator Studio для створення, завантаження, обробки або поширення матеріалів, які:"], "items": ["порушують права інтелектуальної власності, приватність або закон;", "містять шкідливий код, phishing, fraud, spam або спроби обходу безпеки;", "є незаконними, наклепницькими, образливими або шкідливими;", "спрямовані на перевантаження, scraping, reverse engineering, перепродаж або зловживання інфраструктурою сервісу;", "спотворюють походження, авторство або правовий статус створених матеріалів."], "after": ["Постачальник може призупинити або обмежити доступ у разі забороненого використання, платіжних зловживань, технічного abuse або ризику безпеки."]},
                {"title": "9. Зберігання, файли і доступність", "items": ["Плани можуть включати ліміти сховища, ліміти файлів, періоди доступу або строки доступності завантаження.", "Клієнт повинен самостійно завантажувати і зберігати копії важливих цифрових результатів. Сервіс не призначений бути єдиним довгостроковим архівом файлів.", "Файли можуть видалятися після завершення плану, неактивності акаунта, технічного очищення, запобігання abuse або застосування лімітів сховища.", "Постачальник може змінювати правила зберігання, технічні ліміти і підтримувані формати для стабільності та безпеки."]},
                {"title": "10. Повернення коштів і скасування", "paragraphs": ["Повернення коштів регулюється окремою політикою повернення коштів. Загалом повернення коштів не передбачене, оскільки послуги є цифровими, а доступ до сервісу та результатів надається одразу після успішної оплати."]},
                {"title": "11. Якість послуги та обмеження", "items": ["Постачальник вживає розумних заходів для доступності, працездатності та безпеки сервісу.", "Якість цифрового результату залежить від якості вихідних матеріалів, налаштувань, формату файлу та технічних обмежень автоматизованої обробки.", "Сервіс може використовувати автоматичні або AI-assisted інструменти. Клієнт відповідає за перевірку результату перед публікацією або професійним використанням.", "Постачальник не гарантує, що кожен результат відповідатиме суб'єктивним очікуванням, правилам платформи, редакційному стандарту або вимогам третіх осіб."]},
                {"title": "12. Відповідальність", "items": ["Постачальник не відповідає за збитки, спричинені некоректними матеріалами клієнта, незаконними завантаженнями, змінами сторонніх платформ, проблемами платіжного провайдера, збоями інтернету або форс-мажором.", "Постачальник не відповідає за те, як клієнт використовує, публікує, редагує, поширює або монетизує цифрові результати.", "У максимально допустимій законом мірі відповідальність постачальника обмежується сумою, сплаченою клієнтом за відповідний цифровий план або послугу."]},
                {"title": "13. Підтримка і комунікація", "paragraphs": ["Запити підтримки, питання щодо статусу оплати і технічні звернення можна надсилати за контактами, зазначеними на сайті.", "Під час звернення клієнту бажано вказати дату оплати, email, назву плану, назву задачі або іншу інформацію для ідентифікації замовлення."]},
                {"title": "14. Зміна умов", "items": ["Постачальник може оновлювати умови через зміни сервісу, вимоги законодавства, вимоги платіжного провайдера або технічні зміни.", "Актуальна версія публікується на цій сторінці і діє з моменту розміщення на сайті.", "Подальше використання сервісу після оновлення означає згоду з оновленими умовами."]},
            ],
        },
    },
    "refund": {
        "en": {
            "meta_service_type": "Digital services",
            "sections": [
                {"title": "1. General refund rule", "paragraphs": ["This Refund policy applies to payments for CherryX Creator Studio digital services."], "items": ["CherryX Creator Studio provides digital services only. The service does not sell or deliver physical goods.", "Access to the paid plan, workspace tools and digital processing starts immediately after successful payment confirmation.", "Because the digital service is activated immediately, refunds are generally not provided after payment confirmation and access activation."]},
                {"title": "2. Why refunds are not provided", "paragraphs": ["Refunds are not provided because the customer receives immediate digital value after payment. This may include access to paid tools, storage, generation capacity, previews, exports, processing queues or downloadable results."], "items": ["The service begins before any physical delivery could take place, because delivery is digital and remote.", "The customer may start using paid functionality immediately after the payment is confirmed.", "Generated previews, files, exports or workspace access cannot be technically returned in the same way as unused physical goods."]},
                {"title": "3. Transaction cancellation", "items": ["A transaction cannot be cancelled after successful payment confirmation and activation of paid digital access.", "If the payment was not completed, was declined, or was interrupted before confirmation, paid access is not activated and no refund procedure is required.", "If the customer made a mistake when choosing a plan, the customer should contact support as soon as possible before using the paid access or generating digital results.", "The provider may review exceptional situations individually, but such review does not create an obligation to refund an activated digital service."]},
                {"title": "4. Cases that may be reviewed", "paragraphs": ["The following cases may be reviewed by support if the customer provides enough payment and account information:"], "items": ["a duplicated payment for the same plan caused by a technical or payment processing issue;", "a confirmed payment that did not activate paid access due to a technical error;", "an incorrect charge where the payment provider confirms an error;", "unauthorized payment claims supported by bank, card issuer or payment provider evidence;", "other technical incidents where the customer did not receive access to the paid digital service."], "after": ["If support confirms that paid access was not provided due to a technical issue, the provider may restore access, extend access, provide equivalent service capacity or assist with refund processing through the payment provider where required."]},
                {"title": "5. Cases that are not refundable", "paragraphs": ["The following cases are not grounds for refund after successful activation of the digital service:"], "items": ["the customer changed their mind after payment;", "the customer did not use the plan during the active access period;", "the customer uploaded low-quality, incorrect, incomplete or unlawful source materials;", "the generated result does not match a subjective expectation, creative preference or third-party platform requirement;", "the customer lost access because of violation of the Terms and conditions, abuse, prohibited content or security risk;", "technical limitations caused by the customer's device, browser, internet connection or unsupported file format."]},
                {"title": "6. How to request review", "paragraphs": ["To request review of a payment issue, the customer must contact support and include:"], "items": ["payment date and approximate time;", "paid plan or service name;", "email, account, workspace or task name used in CherryX Creator Studio;", "payment amount and payment method, if available;", "screenshots or payment provider confirmation if the issue relates to duplicated, failed or incorrect charge."]},
                {"title": "7. Review period and decision", "items": ["Support will make reasonable efforts to review payment issues within 5 business days after receiving enough information.", "Complex cases involving WayForPay, bank, card issuer or other third-party verification may take longer.", "The decision may include confirmation of normal activation, restoration of access, technical correction, access extension, equivalent service capacity or refund assistance where applicable.", "Any refund, if approved or required, is processed through the original payment provider and may be subject to the provider's banking and processing timelines."]},
                {"title": "8. Chargebacks and payment disputes", "items": ["If the customer initiates a bank dispute or chargeback, access to the disputed digital service may be suspended while the dispute is reviewed.", "The provider may submit service activation logs, payment confirmation, workspace activity and download records to the payment provider or bank to verify delivery of the digital service.", "Chargeback abuse, fraudulent payment activity or repeated disputed payments may result in account restriction."]},
                {"title": "9. Relation to Terms and conditions", "paragraphs": ["This Refund policy is part of the CherryX Creator Studio legal documents and should be read together with the Terms and conditions. If there is a conflict, this Refund policy governs refund-related questions, while the Terms govern general service use."]},
            ],
        },
        "ru": {
            "meta_service_type": "Цифровые услуги",
            "sections": [
                {"title": "1. Общее правило возврата", "paragraphs": ["Настоящая политика возврата применяется к оплатам цифровых услуг CherryX Creator Studio."], "items": ["CherryX Creator Studio предоставляет только цифровые услуги и не продаёт физические товары.", "Доступ к платному плану, инструментам рабочего пространства и цифровой обработке начинается сразу после успешного подтверждения оплаты.", "Поскольку цифровая услуга активируется немедленно, возврат средств после подтверждения оплаты и активации доступа обычно не предоставляется."]},
                {"title": "2. Почему возврат не предусмотрен", "paragraphs": ["Возврат не предусмотрен, потому что клиент сразу получает цифровую ценность после оплаты: доступ к платным инструментам, хранилищу, генерации, предпросмотрам, экспортам, очередям обработки или файлам для скачивания."], "items": ["Услуга начинается до какой-либо физической доставки, потому что доставка является цифровой и дистанционной.", "Клиент может начать использовать платный функционал сразу после подтверждения оплаты.", "Сгенерированные предпросмотры, файлы, экспорты или доступ к рабочему пространству нельзя технически вернуть как неиспользованный физический товар."]},
                {"title": "3. Отмена транзакции", "items": ["Транзакция не может быть отменена после успешного подтверждения оплаты и активации платного цифрового доступа.", "Если платёж не завершён, отклонён или прерван до подтверждения, платный доступ не активируется и процедура возврата не требуется.", "Если клиент ошибся при выборе плана, он должен как можно быстрее обратиться в поддержку до использования платного доступа или генерации результатов.", "Поставщик может индивидуально рассмотреть исключительные ситуации, но такое рассмотрение не создаёт обязанности вернуть оплату за активированную цифровую услугу."]},
                {"title": "4. Случаи, которые могут быть рассмотрены", "paragraphs": ["Поддержка может рассмотреть следующие случаи при наличии достаточной информации об оплате и аккаунте:"], "items": ["двойная оплата одного и того же плана из-за технической или платёжной ошибки;", "подтверждённая оплата, после которой доступ не активировался из-за технической ошибки;", "некорректное списание, подтверждённое платёжным провайдером;", "заявление о несанкционированной оплате с подтверждением банка, эмитента карты или платёжного провайдера;", "другой технический инцидент, при котором клиент не получил доступ к оплаченной цифровой услуге."], "after": ["Если поддержка подтвердит, что доступ не был предоставлен из-за технической ошибки, поставщик может восстановить доступ, продлить доступ, предоставить эквивалентный объём услуги или помочь с обработкой возврата через платёжного провайдера, если это требуется."]},
                {"title": "5. Случаи без возврата", "paragraphs": ["Следующие случаи не являются основанием для возврата после успешной активации цифровой услуги:"], "items": ["клиент передумал после оплаты;", "клиент не использовал план в течение активного периода доступа;", "клиент загрузил низкокачественные, неверные, неполные или незаконные исходные материалы;", "результат не совпал с субъективным ожиданием, творческим предпочтением или требованием сторонней платформы;", "клиент потерял доступ из-за нарушения условий, abuse, запрещённого контента или риска безопасности;", "технические ограничения вызваны устройством, браузером, интернет-соединением клиента или неподдерживаемым форматом файла."]},
                {"title": "6. Как подать запрос на проверку", "paragraphs": ["Для проверки платёжной ситуации клиент должен обратиться в поддержку и указать:"], "items": ["дату и примерное время оплаты;", "название оплаченного плана или услуги;", "email, аккаунт, рабочее пространство или название задачи в CherryX Creator Studio;", "сумму и способ оплаты, если доступны;", "скриншоты или подтверждение платёжного провайдера, если вопрос связан с дублем, ошибкой или некорректным списанием."]},
                {"title": "7. Срок рассмотрения и решение", "items": ["Поддержка приложит разумные усилия, чтобы рассмотреть вопрос в течение 5 рабочих дней после получения достаточной информации.", "Сложные случаи с участием WayForPay, банка, эмитента карты или другой проверки могут занимать больше времени.", "Решение может включать подтверждение нормальной активации, восстановление доступа, техническую коррекцию, продление доступа, эквивалентный объём услуги или помощь с возвратом, если применимо.", "Любой возврат, если он одобрен или обязателен, обрабатывается через исходного платёжного провайдера и зависит от банковских сроков обработки."]},
                {"title": "8. Банковские споры и chargeback", "items": ["Если клиент инициирует банковский спор или chargeback, доступ к спорной цифровой услуге может быть приостановлен на время проверки.", "Поставщик может передать логи активации, подтверждение оплаты, активность рабочего пространства и записи скачиваний платёжному провайдеру или банку для подтверждения оказания цифровой услуги.", "Злоупотребление chargeback, мошенничество или повторные спорные платежи могут привести к ограничению аккаунта."]},
                {"title": "9. Связь с Правилами и условиями", "paragraphs": ["Эта политика возврата является частью юридических документов CherryX Creator Studio и применяется вместе с Правилами и условиями. По вопросам возврата приоритет имеет политика возврата, а общие правила использования регулируются Правилами и условиями."]},
            ],
        },
        "uk": {
            "meta_service_type": "Цифрові послуги",
            "sections": [
                {"title": "1. Загальне правило повернення", "paragraphs": ["Ця політика повернення застосовується до оплат цифрових послуг CherryX Creator Studio."], "items": ["CherryX Creator Studio надає лише цифрові послуги і не продає фізичні товари.", "Доступ до платного плану, інструментів робочого простору та цифрової обробки починається одразу після успішного підтвердження оплати.", "Оскільки цифрова послуга активується негайно, повернення коштів після підтвердження оплати та активації доступу зазвичай не надається."]},
                {"title": "2. Чому повернення не передбачене", "paragraphs": ["Повернення не передбачене, тому що клієнт одразу отримує цифрову цінність після оплати: доступ до платних інструментів, сховища, генерації, попередніх переглядів, експортів, черг обробки або файлів для завантаження."], "items": ["Послуга починається до будь-якої фізичної доставки, тому що доставка є цифровою та дистанційною.", "Клієнт може почати використовувати платний функціонал одразу після підтвердження оплати.", "Згенеровані попередні перегляди, файли, експорти або доступ до робочого простору неможливо технічно повернути як невикористаний фізичний товар."]},
                {"title": "3. Скасування транзакції", "items": ["Транзакція не може бути скасована після успішного підтвердження оплати та активації платного цифрового доступу.", "Якщо платіж не завершений, відхилений або перерваний до підтвердження, платний доступ не активується і процедура повернення не потрібна.", "Якщо клієнт помилився під час вибору плану, він має якнайшвидше звернутися до підтримки до використання платного доступу або генерації результатів.", "Постачальник може індивідуально розглянути виняткові ситуації, але такий розгляд не створює обов'язку повернути оплату за активовану цифрову послугу."]},
                {"title": "4. Випадки, які можуть бути розглянуті", "paragraphs": ["Підтримка може розглянути такі випадки за наявності достатньої інформації про оплату та акаунт:"], "items": ["подвійна оплата одного й того самого плану через технічну або платіжну помилку;", "підтверджена оплата, після якої доступ не активувався через технічну помилку;", "некоректне списання, підтверджене платіжним провайдером;", "заява про несанкціоновану оплату з підтвердженням банку, емітента картки або платіжного провайдера;", "інший технічний інцидент, коли клієнт не отримав доступ до оплаченої цифрової послуги."], "after": ["Якщо підтримка підтвердить, що доступ не був наданий через технічну помилку, постачальник може відновити доступ, продовжити доступ, надати еквівалентний обсяг послуги або допомогти з обробкою повернення через платіжного провайдера, якщо це потрібно."]},
                {"title": "5. Випадки без повернення", "paragraphs": ["Такі випадки не є підставою для повернення після успішної активації цифрової послуги:"], "items": ["клієнт передумав після оплати;", "клієнт не використовував план протягом активного періоду доступу;", "клієнт завантажив низькоякісні, неправильні, неповні або незаконні вихідні матеріали;", "результат не збігся із суб'єктивним очікуванням, творчою перевагою або вимогою сторонньої платформи;", "клієнт втратив доступ через порушення умов, abuse, заборонений контент або ризик безпеки;", "технічні обмеження спричинені пристроєм, браузером, інтернет-з'єднанням клієнта або непідтримуваним форматом файлу."]},
                {"title": "6. Як подати запит на перевірку", "paragraphs": ["Для перевірки платіжної ситуації клієнт має звернутися до підтримки та вказати:"], "items": ["дату і приблизний час оплати;", "назву оплаченого плану або послуги;", "email, акаунт, робочий простір або назву задачі в CherryX Creator Studio;", "суму та спосіб оплати, якщо доступні;", "скриншоти або підтвердження платіжного провайдера, якщо питання пов'язане з дублем, помилкою або некоректним списанням."]},
                {"title": "7. Строк розгляду і рішення", "items": ["Підтримка докладе розумних зусиль, щоб розглянути питання протягом 5 робочих днів після отримання достатньої інформації.", "Складні випадки за участю WayForPay, банку, емітента картки або іншої перевірки можуть тривати довше.", "Рішення може включати підтвердження нормальної активації, відновлення доступу, технічну корекцію, продовження доступу, еквівалентний обсяг послуги або допомогу з поверненням, якщо застосовно.", "Будь-яке повернення, якщо воно схвалене або обов'язкове, обробляється через початкового платіжного провайдера і залежить від банківських строків обробки."]},
                {"title": "8. Банківські спори і chargeback", "items": ["Якщо клієнт ініціює банківський спір або chargeback, доступ до спірної цифрової послуги може бути призупинений на час перевірки.", "Постачальник може передати логи активації, підтвердження оплати, активність робочого простору і записи завантажень платіжному провайдеру або банку для підтвердження надання цифрової послуги.", "Зловживання chargeback, шахрайство або повторні спірні платежі можуть призвести до обмеження акаунта."]},
                {"title": "9. Зв'язок із Правилами і умовами", "paragraphs": ["Ця політика повернення є частиною юридичних документів CherryX Creator Studio і застосовується разом із Правилами і умовами. З питань повернення пріоритет має політика повернення, а загальні правила використання регулюються Правилами і умовами."]},
            ],
        },
    },
    "contacts": {
        "en": {"meta_service_type": "Remote digital services", "sections": [{"title": "Provider details", "items": ["Individual entrepreneur Petrusenko Maksym Denysovych.", "Tax ID: 3795908055.", "Email: cherryxdigital@gmail.com.", "Phone: +380 (96) 363-59-05.", "Services are provided remotely; there is no physical service location."]}, {"title": "Service format", "paragraphs": ["Services are provided remotely through CherryX Creator Studio. There is no physical service location or offline customer service point."]}, {"title": "Payment provider", "paragraphs": ["Online payments are processed through WayForPay. After successful payment, the selected digital access is activated in the service account or workspace."]}]},
        "ru": {"meta_service_type": "Дистанционные цифровые услуги", "sections": [{"title": "Данные поставщика", "items": ["ФОП Петрусенко Максим Денисович.", "РНОКПП/ИНН: 3795908055.", "Email: cherryxdigital@gmail.com.", "Телефон: +380 (96) 363-59-05.", "Услуги предоставляются дистанционно, физическая точка обслуживания отсутствует."]}, {"title": "Формат услуг", "paragraphs": ["Услуги предоставляются дистанционно через CherryX Creator Studio. Физическая точка обслуживания и офлайн-приём клиентов отсутствуют."]}, {"title": "Платёжный провайдер", "paragraphs": ["Онлайн-оплаты обрабатываются через WayForPay. После успешной оплаты выбранный цифровой доступ активируется в аккаунте или рабочем пространстве."]}]},
        "uk": {"meta_service_type": "Дистанційні цифрові послуги", "sections": [{"title": "Дані постачальника", "items": ["ФОП Петрусенко Максим Денисович.", "РНОКПП/ІПН: 3795908055.", "Email: cherryxdigital@gmail.com.", "Телефон: +380 (96) 363-59-05.", "Послуги надаються дистанційно, фізична точка обслуговування відсутня."]}, {"title": "Формат послуг", "paragraphs": ["Послуги надаються дистанційно через CherryX Creator Studio. Фізична точка обслуговування та офлайн-прийом клієнтів відсутні."]}, {"title": "Платіжний провайдер", "paragraphs": ["Онлайн-оплати обробляються через WayForPay. Після успішної оплати обраний цифровий доступ активується в акаунті або робочому просторі."]}]},
    },
}


LEGAL_DOCUMENTS["terms"].update(
    {
        "fr": {
            "meta_service_type": "Services numériques",
            "sections": [
                {"title": "1. Dispositions générales", "paragraphs": ["Les présentes conditions régissent l'utilisation de CherryX Creator Studio, un service numérique fourni à distance."], "items": ["CherryX Creator Studio fournit uniquement des services numériques; aucun bien physique n'est vendu ou expédié.", "En choisissant un plan, en téléversant des fichiers, en lançant une génération ou en payant, le client accepte ces conditions.", "Le service est fourni via le site, l'espace de travail utilisateur et les outils numériques associés."]},
                {"title": "2. Objet des services", "items": ["création, traitement et export de vidéos, images, couvertures et fichiers de design;", "préparation de sous-titres, fichiers SRT/VTT et exports associés;", "génération de CV PDF, archives ZIP, textes et packages de publication;", "outils automatisés ou assistés par IA disponibles dans l'espace de travail."]},
                {"title": "3. Commande et paiement", "items": ["Le client choisit un plan ou un outil payant avant la confirmation du paiement.", "Le paiement est effectué en ligne via WayForPay ou un autre moyen affiché sur le site.", "Le prix final, la durée d'accès, les limites et les outils disponibles peuvent être affichés avant confirmation.", "Si le paiement est refusé, interrompu ou non confirmé, l'accès payant peut ne pas être activé."]},
                {"title": "4. Activation et livraison numérique", "items": ["L'accès payant est activé immédiatement après confirmation du paiement.", "Les résultats numériques sont fournis dans l'espace de travail et peuvent être téléchargés après traitement.", "Aucune livraison postale, livraison par coursier ou retrait physique n'est prévu.", "Le délai de traitement dépend de la taille des fichiers, de la file d'attente, du réseau et des limites techniques."]},
                {"title": "5. Responsabilité du client", "items": ["Le client est responsable des fichiers, textes, images, vidéos et autres contenus téléversés.", "Le client confirme disposer des droits nécessaires pour utiliser et traiter les matériaux envoyés.", "Le prestataire peut traiter ces matériaux uniquement pour fournir le service numérique demandé.", "Toute utilisation illicite, abusive, frauduleuse ou portant atteinte aux droits de tiers est interdite."]},
                {"title": "6. Remboursements, limitations et support", "items": ["Les remboursements sont régis par la politique de remboursement séparée.", "Le service peut utiliser des outils automatisés ou assistés par IA; le client doit vérifier le résultat final avant publication.", "Le prestataire ne garantit pas que chaque résultat corresponde à une attente subjective ou aux règles d'une plateforme tierce.", "Les demandes de support peuvent être envoyées aux contacts publiés sur le site."]},
            ],
        },
        "de": {
            "meta_service_type": "Digitale Dienstleistungen",
            "sections": [
                {"title": "1. Allgemeine Bestimmungen", "paragraphs": ["Diese Bedingungen regeln die Nutzung von CherryX Creator Studio, einem remote bereitgestellten digitalen Dienst."], "items": ["CherryX Creator Studio erbringt ausschließlich digitale Dienstleistungen; physische Waren werden nicht verkauft oder versendet.", "Mit Auswahl eines Plans, Upload von Dateien, Start einer Generierung oder Zahlung akzeptiert der Kunde diese Bedingungen.", "Der Dienst wird über die Website, den Benutzerarbeitsbereich und verbundene digitale Werkzeuge erbracht."]},
                {"title": "2. Leistungsumfang", "items": ["Erstellung, Verarbeitung und Export von Videos, Bildern, Covern und Design-Dateien;", "Vorbereitung von Untertiteln, SRT/VTT-Dateien und zugehörigen Exporten;", "Erstellung von PDF-Lebensläufen, ZIP-Archiven, Texten und Veröffentlichungspaketen;", "automatisierte oder KI-unterstützte Werkzeuge im Arbeitsbereich."]},
                {"title": "3. Bestellung und Zahlung", "items": ["Der Kunde wählt vor der Zahlungsbestätigung einen Plan oder ein kostenpflichtiges Werkzeug aus.", "Die Zahlung erfolgt online über WayForPay oder eine andere auf der Website angezeigte Zahlungsmethode.", "Endpreis, Zugriffsdauer, Limits und verfügbare Werkzeuge können vor der Bestätigung angezeigt werden.", "Wenn die Zahlung abgelehnt, unterbrochen oder nicht bestätigt wird, kann der kostenpflichtige Zugriff nicht aktiviert werden."]},
                {"title": "4. Aktivierung und digitale Lieferung", "items": ["Der kostenpflichtige Zugriff wird unmittelbar nach erfolgreicher Zahlungsbestätigung aktiviert.", "Digitale Ergebnisse werden im Arbeitsbereich bereitgestellt und können nach Abschluss der Verarbeitung heruntergeladen werden.", "Postversand, Kurierlieferung oder physische Abholung sind nicht vorgesehen.", "Die Bearbeitungszeit hängt von Dateigröße, Warteschlange, Netzwerk und technischen Grenzen ab."]},
                {"title": "5. Verantwortung des Kunden", "items": ["Der Kunde ist für hochgeladene Dateien, Texte, Bilder, Videos und sonstige Inhalte verantwortlich.", "Der Kunde bestätigt, über die erforderlichen Rechte zur Nutzung und Verarbeitung der übermittelten Materialien zu verfügen.", "Der Anbieter darf diese Materialien nur zur Erbringung der angeforderten digitalen Dienstleistung verarbeiten.", "Rechtswidrige, missbräuchliche, betrügerische oder Rechte Dritter verletzende Nutzung ist untersagt."]},
                {"title": "6. Rückerstattung, Einschränkungen und Support", "items": ["Rückerstattungen richten sich nach der separaten Rückerstattungsrichtlinie.", "Der Dienst kann automatisierte oder KI-unterstützte Werkzeuge verwenden; der Kunde muss das Endergebnis vor Veröffentlichung prüfen.", "Der Anbieter garantiert nicht, dass jedes Ergebnis subjektiven Erwartungen oder Regeln Dritter entspricht.", "Supportanfragen können an die auf der Website angegebenen Kontakte gesendet werden."]},
            ],
        },
        "es": {
            "meta_service_type": "Servicios digitales",
            "sections": [
                {"title": "1. Disposiciones generales", "paragraphs": ["Estos términos regulan el uso de CherryX Creator Studio, un servicio digital prestado de forma remota."], "items": ["CherryX Creator Studio presta únicamente servicios digitales; no se venden ni envían bienes físicos.", "Al elegir un plan, subir archivos, iniciar una generación o pagar, el cliente acepta estos términos.", "El servicio se presta a través del sitio web, el espacio de trabajo del usuario y las herramientas digitales relacionadas."]},
                {"title": "2. Alcance del servicio", "items": ["creación, procesamiento y exportación de vídeos, imágenes, portadas y archivos de diseño;", "preparación de subtítulos, archivos SRT/VTT y exportaciones relacionadas;", "generación de CV en PDF, archivos ZIP, textos y paquetes de publicación;", "herramientas automatizadas o asistidas por IA disponibles en el espacio de trabajo."]},
                {"title": "3. Pedido y pago", "items": ["El cliente elige un plan o herramienta de pago antes de confirmar el pago.", "El pago se realiza en línea mediante WayForPay u otro método mostrado en el sitio.", "Antes de confirmar, pueden mostrarse el precio final, duración de acceso, límites y herramientas disponibles.", "Si el pago se rechaza, se interrumpe o no se confirma, el acceso pagado puede no activarse."]},
                {"title": "4. Activación y entrega digital", "items": ["El acceso pagado se activa inmediatamente después de la confirmación correcta del pago.", "Los resultados digitales se entregan en el espacio de trabajo y pueden descargarse tras finalizar el procesamiento.", "No existe entrega postal, mensajería ni recogida física.", "El tiempo de procesamiento depende del tamaño de los archivos, la cola, la red y los límites técnicos."]},
                {"title": "5. Responsabilidad del cliente", "items": ["El cliente es responsable de los archivos, textos, imágenes, vídeos y otros contenidos subidos.", "El cliente confirma que tiene los derechos necesarios para usar y procesar los materiales enviados.", "El proveedor puede procesar dichos materiales solo para prestar el servicio digital solicitado.", "Está prohibido el uso ilegal, abusivo, fraudulento o que vulnere derechos de terceros."]},
                {"title": "6. Reembolsos, limitaciones y soporte", "items": ["Los reembolsos se regulan por la política de reembolso separada.", "El servicio puede usar herramientas automatizadas o asistidas por IA; el cliente debe revisar el resultado final antes de publicarlo.", "El proveedor no garantiza que cada resultado coincida con expectativas subjetivas o normas de terceros.", "Las solicitudes de soporte pueden enviarse a los contactos publicados en el sitio."]},
            ],
        },
        "ka": {
            "meta_service_type": "ციფრული სერვისები",
            "sections": [
                {"title": "1. ზოგადი დებულებები", "paragraphs": ["ეს პირობები არეგულირებს CherryX Creator Studio-ს გამოყენებას, რომელიც დისტანციურად მიწოდებული ციფრული სერვისია."], "items": ["CherryX Creator Studio უზრუნველყოფს მხოლოდ ციფრულ სერვისებს; ფიზიკური საქონელი არ იყიდება და არ იგზავნება.", "გეგმის არჩევით, ფაილების ატვირთვით, გენერაციის დაწყებით ან გადახდით მომხმარებელი ეთანხმება ამ პირობებს.", "სერვისი მიეწოდება ვებსაიტის, მომხმარებლის სამუშაო სივრცისა და დაკავშირებული ციფრული ინსტრუმენტების მეშვეობით."]},
                {"title": "2. სერვისის მოცულობა", "items": ["ვიდეოების, სურათების, ქავერებისა და დიზაინის ფაილების შექმნა, დამუშავება და ექსპორტი;", "სუბტიტრების, SRT/VTT ფაილებისა და შესაბამისი ექსპორტების მომზადება;", "PDF რეზიუმეების, ZIP არქივების, ტექსტებისა და პუბლიკაციის პაკეტების გენერაცია;", "სამუშაო სივრცეში არსებული ავტომატიზებული ან AI-ით მხარდაჭერილი ინსტრუმენტები."]},
                {"title": "3. შეკვეთა და გადახდა", "items": ["მომხმარებელი გადახდის დადასტურებამდე ირჩევს გეგმას ან ფასიან ინსტრუმენტს.", "გადახდა ხორციელდება ონლაინ WayForPay-ის ან საიტზე ნაჩვენები სხვა მეთოდის მეშვეობით.", "დადასტურებამდე შეიძლება გამოჩნდეს საბოლოო ფასი, წვდომის ვადა, ლიმიტები და ხელმისაწვდომი ინსტრუმენტები.", "თუ გადახდა უარყოფილია, შეწყვეტილია ან არ დადასტურდა, ფასიანი წვდომა შეიძლება არ გააქტიურდეს."]},
                {"title": "4. აქტივაცია და ციფრული მიწოდება", "items": ["ფასიანი წვდომა აქტიურდება წარმატებული გადახდის დადასტურებისთანავე.", "ციფრული შედეგები მიეწოდება სამუშაო სივრცეში და დამუშავების დასრულების შემდეგ შესაძლებელია მათი ჩამოტვირთვა.", "საფოსტო, საკურიერო ან ფიზიკური მიღება არ არის გათვალისწინებული.", "დამუშავების დრო დამოკიდებულია ფაილის ზომაზე, რიგზე, ქსელსა და ტექნიკურ შეზღუდვებზე."]},
                {"title": "5. მომხმარებლის პასუხისმგებლობა", "items": ["მომხმარებელი პასუხისმგებელია ატვირთულ ფაილებზე, ტექსტებზე, სურათებზე, ვიდეოებსა და სხვა მასალებზე.", "მომხმარებელი ადასტურებს, რომ აქვს საჭირო უფლებები გაგზავნილი მასალების გამოსაყენებლად და დასამუშავებლად.", "მომწოდებელს შეუძლია მასალების დამუშავება მხოლოდ მოთხოვნილი ციფრული სერვისის გასაწევად.", "აკრძალულია უკანონო, ბოროტად გამოყენებითი, თაღლითური ან მესამე პირთა უფლებების დამრღვევი გამოყენება."]},
                {"title": "6. დაბრუნება, შეზღუდვები და მხარდაჭერა", "items": ["თანხის დაბრუნება რეგულირდება ცალკე დაბრუნების პოლიტიკით.", "სერვისმა შეიძლება გამოიყენოს ავტომატიზებული ან AI-ით მხარდაჭერილი ინსტრუმენტები; მომხმარებელმა საბოლოო შედეგი გამოქვეყნებამდე უნდა შეამოწმოს.", "მომწოდებელი არ იძლევა გარანტიას, რომ ყოველი შედეგი დაემთხვევა სუბიექტურ მოლოდინს ან მესამე მხარის წესებს.", "მხარდაჭერის მოთხოვნები შეიძლება გაიგზავნოს საიტზე გამოქვეყნებულ საკონტაქტო მისამართებზე."]},
            ],
        },
        "hy": {
            "meta_service_type": "Թվային ծառայություններ",
            "sections": [
                {"title": "1. Ընդհանուր դրույթներ", "paragraphs": ["Այս պայմանները կարգավորում են CherryX Creator Studio-ի օգտագործումը՝ որպես հեռավար մատուցվող թվային ծառայություն։"], "items": ["CherryX Creator Studio-ն տրամադրում է միայն թվային ծառայություններ․ ֆիզիկական ապրանքներ չեն վաճառվում և չեն առաքվում։", "Պլան ընտրելով, ֆայլեր վերբեռնելով, գեներացում սկսելով կամ վճարում կատարելով՝ հաճախորդը համաձայնում է այս պայմաններին։", "Ծառայությունը մատուցվում է կայքի, օգտատիրոջ աշխատանքային տարածքի և հարակից թվային գործիքների միջոցով։"]},
                {"title": "2. Ծառայության շրջանակը", "items": ["տեսանյութերի, պատկերների, շապիկների և դիզայն ֆայլերի ստեղծում, մշակում և արտահանում;", "ենթագրերի, SRT/VTT ֆայլերի և հարակից արտահանումների պատրաստում;", "PDF ռեզյումեների, ZIP արխիվների, տեքստերի և հրապարակման փաթեթների գեներացում;", "աշխատանքային տարածքում հասանելի ավտոմատացված կամ AI-ով աջակցվող գործիքներ։"]},
                {"title": "3. Պատվեր և վճարում", "items": ["Հաճախորդը վճարման հաստատումից առաջ ընտրում է պլան կամ վճարովի գործիք։", "Վճարումը կատարվում է առցանց WayForPay-ի կամ կայքում ցուցադրված այլ եղանակով։", "Հաստատումից առաջ կարող են ցուցադրվել վերջնական գինը, մուտքի ժամկետը, սահմանափակումները և հասանելի գործիքները։", "Եթե վճարումը մերժվել է, ընդհատվել է կամ չի հաստատվել, վճարովի մուտքը կարող է չակտիվացվել։"]},
                {"title": "4. Ակտիվացում և թվային տրամադրում", "items": ["Վճարովի մուտքը ակտիվանում է հաջող վճարման հաստատումից անմիջապես հետո։", "Թվային արդյունքները տրամադրվում են աշխատանքային տարածքում և մշակման ավարտից հետո կարող են ներբեռնվել։", "Փոստային, սուրհանդակային կամ ֆիզիկական ստացում նախատեսված չէ։", "Մշակման ժամանակը կախված է ֆայլերի չափից, հերթից, ցանցից և տեխնիկական սահմանափակումներից։"]},
                {"title": "5. Հաճախորդի պատասխանատվությունը", "items": ["Հաճախորդը պատասխանատու է վերբեռնված ֆայլերի, տեքստերի, պատկերների, տեսանյութերի և այլ նյութերի համար։", "Հաճախորդը հաստատում է, որ ունի անհրաժեշտ իրավունքներ ներկայացված նյութերը օգտագործելու և մշակելու համար։", "Մատակարարը կարող է մշակել այդ նյութերը միայն պահանջված թվային ծառայությունը մատուցելու նպատակով։", "Արգելվում է անօրինական, չարաշահող, խարդախ կամ երրորդ անձանց իրավունքները խախտող օգտագործումը։"]},
                {"title": "6. Վերադարձներ, սահմանափակումներ և աջակցություն", "items": ["Վճարումների վերադարձը կարգավորվում է առանձին վերադարձի քաղաքականությամբ։", "Ծառայությունը կարող է օգտագործել ավտոմատացված կամ AI-ով աջակցվող գործիքներ․ հաճախորդը պետք է ստուգի վերջնական արդյունքը հրապարակումից առաջ։", "Մատակարարը չի երաշխավորում, որ յուրաքանչյուր արդյունք կհամապատասխանի սուբյեկտիվ ակնկալիքներին կամ երրորդ կողմի կանոններին։", "Աջակցության հարցումները կարող են ուղարկվել կայքում հրապարակված կոնտակտներով։"]},
            ],
        },
        "it": {
            "meta_service_type": "Servizi digitali",
            "sections": [
                {"title": "1. Disposizioni generali", "paragraphs": ["Questi termini regolano l'uso di CherryX Creator Studio, un servizio digitale fornito da remoto."], "items": ["CherryX Creator Studio fornisce solo servizi digitali; non vengono venduti o spediti beni fisici.", "Scegliendo un piano, caricando file, avviando una generazione o pagando, il cliente accetta questi termini.", "Il servizio è fornito tramite il sito, lo spazio di lavoro dell'utente e gli strumenti digitali collegati."]},
                {"title": "2. Ambito del servizio", "items": ["creazione, elaborazione ed esportazione di video, immagini, copertine e file di design;", "preparazione di sottotitoli, file SRT/VTT ed esportazioni correlate;", "generazione di CV PDF, archivi ZIP, testi e pacchetti di pubblicazione;", "strumenti automatizzati o assistiti da IA disponibili nello spazio di lavoro."]},
                {"title": "3. Ordine e pagamento", "items": ["Il cliente sceglie un piano o uno strumento a pagamento prima della conferma del pagamento.", "Il pagamento viene effettuato online tramite WayForPay o un altro metodo mostrato sul sito.", "Prima della conferma possono essere mostrati prezzo finale, durata dell'accesso, limiti e strumenti disponibili.", "Se il pagamento viene rifiutato, interrotto o non confermato, l'accesso a pagamento potrebbe non essere attivato."]},
                {"title": "4. Attivazione e consegna digitale", "items": ["L'accesso a pagamento viene attivato immediatamente dopo la conferma del pagamento riuscito.", "I risultati digitali sono forniti nello spazio di lavoro e possono essere scaricati al termine dell'elaborazione.", "Non sono previste consegna postale, corriere o ritiro fisico.", "Il tempo di elaborazione dipende da dimensione dei file, coda, rete e limiti tecnici."]},
                {"title": "5. Responsabilità del cliente", "items": ["Il cliente è responsabile dei file, testi, immagini, video e altri contenuti caricati.", "Il cliente conferma di avere i diritti necessari per usare e trattare i materiali inviati.", "Il fornitore può trattare tali materiali solo per fornire il servizio digitale richiesto.", "È vietato l'uso illecito, abusivo, fraudolento o lesivo di diritti di terzi."]},
                {"title": "6. Rimborsi, limitazioni e supporto", "items": ["I rimborsi sono regolati dalla politica di rimborso separata.", "Il servizio può usare strumenti automatizzati o assistiti da IA; il cliente deve verificare il risultato finale prima della pubblicazione.", "Il fornitore non garantisce che ogni risultato corrisponda ad aspettative soggettive o regole di terzi.", "Le richieste di supporto possono essere inviate ai contatti pubblicati sul sito."]},
            ],
        },
    }
)


LEGAL_DOCUMENTS["refund"].update(
    {
        "fr": {
            "meta_service_type": "Services numériques",
            "sections": [
                {"title": "1. Règle générale de remboursement", "paragraphs": ["Cette politique s'applique aux paiements des services numériques CherryX Creator Studio."], "items": ["Les services sont numériques et commencent immédiatement après la confirmation du paiement.", "Après activation de l'accès payant, le remboursement n'est généralement pas prévu.", "Aucun bien physique n'est vendu, livré ou retourné."]},
                {"title": "2. Cas pouvant être examinés", "items": ["paiement dupliqué pour le même plan;", "paiement confirmé sans activation de l'accès à cause d'une erreur technique;", "débit incorrect confirmé par le prestataire de paiement;", "incident technique empêchant l'accès au service numérique payé."]},
                {"title": "3. Cas non remboursables", "items": ["changement d'avis après paiement;", "non-utilisation du plan pendant la période active;", "fichiers source de mauvaise qualité, incorrects ou incomplets;", "résultat ne correspondant pas à une préférence subjective ou aux règles d'une plateforme tierce;", "restriction d'accès due à une violation des conditions ou à un abus."]},
                {"title": "4. Demande d'examen", "paragraphs": ["Pour demander un examen, le client doit contacter le support et fournir la date de paiement, le plan payé, l'email ou le compte, le montant et toute confirmation utile du paiement."], "items": ["Le support fera des efforts raisonnables pour examiner la demande sous 5 jours ouvrables après réception des informations suffisantes.", "Les cas impliquant WayForPay, une banque ou l'émetteur de carte peuvent prendre plus de temps.", "Si nécessaire, l'accès peut être restauré, prolongé ou une assistance au remboursement peut être fournie via le prestataire de paiement."]},
            ],
        },
        "de": {
            "meta_service_type": "Digitale Dienstleistungen",
            "sections": [
                {"title": "1. Allgemeine Rückerstattungsregel", "paragraphs": ["Diese Richtlinie gilt für Zahlungen für digitale Dienstleistungen von CherryX Creator Studio."], "items": ["Die Dienstleistungen sind digital und beginnen unmittelbar nach Zahlungsbestätigung.", "Nach Aktivierung des kostenpflichtigen Zugangs ist eine Rückerstattung grundsätzlich nicht vorgesehen.", "Es werden keine physischen Waren verkauft, geliefert oder zurückgegeben."]},
                {"title": "2. Fälle, die geprüft werden können", "items": ["doppelte Zahlung für denselben Plan;", "bestätigte Zahlung ohne Aktivierung des Zugangs aufgrund eines technischen Fehlers;", "fehlerhafte Abbuchung, die vom Zahlungsanbieter bestätigt wurde;", "technischer Vorfall, durch den der Kunde keinen Zugang zur bezahlten digitalen Dienstleistung erhalten hat."]},
                {"title": "3. Nicht erstattungsfähige Fälle", "items": ["Meinungsänderung nach Zahlung;", "Nichtnutzung des Plans während der aktiven Zugriffszeit;", "minderwertige, falsche oder unvollständige Quelldateien;", "Ergebnis entspricht nicht subjektiven Erwartungen oder Regeln Dritter;", "Zugriffsbeschränkung wegen Verstoßes gegen Bedingungen oder Missbrauch."]},
                {"title": "4. Prüfungsanfrage", "paragraphs": ["Für eine Prüfung muss der Kunde den Support kontaktieren und Zahlungsdatum, bezahlten Plan, E-Mail oder Konto, Betrag und verfügbare Zahlungsbestätigungen angeben."], "items": ["Der Support bemüht sich, die Anfrage innerhalb von 5 Werktagen nach Erhalt ausreichender Informationen zu prüfen.", "Fälle mit WayForPay, Bank oder Kartenherausgeber können länger dauern.", "Falls erforderlich, kann der Zugang wiederhergestellt, verlängert oder Unterstützung bei einer Rückerstattung über den Zahlungsanbieter geleistet werden."]},
            ],
        },
        "es": {
            "meta_service_type": "Servicios digitales",
            "sections": [
                {"title": "1. Regla general de reembolso", "paragraphs": ["Esta política se aplica a pagos por servicios digitales de CherryX Creator Studio."], "items": ["Los servicios son digitales y comienzan inmediatamente después de la confirmación del pago.", "Después de activar el acceso pagado, generalmente no se prevén reembolsos.", "No se venden, entregan ni devuelven bienes físicos."]},
                {"title": "2. Casos que pueden revisarse", "items": ["pago duplicado por el mismo plan;", "pago confirmado sin activación del acceso por un error técnico;", "cargo incorrecto confirmado por el proveedor de pago;", "incidente técnico que impidió el acceso al servicio digital pagado."]},
                {"title": "3. Casos no reembolsables", "items": ["cambio de opinión después del pago;", "no uso del plan durante el período activo;", "archivos fuente de baja calidad, incorrectos o incompletos;", "resultado que no coincide con una preferencia subjetiva o reglas de terceros;", "restricción de acceso por incumplimiento de los términos o abuso."]},
                {"title": "4. Solicitud de revisión", "paragraphs": ["Para solicitar revisión, el cliente debe contactar soporte e indicar fecha de pago, plan pagado, email o cuenta, importe y cualquier confirmación útil del pago."], "items": ["Soporte hará esfuerzos razonables para revisar la solicitud dentro de 5 días hábiles tras recibir información suficiente.", "Los casos con WayForPay, banco o emisor de tarjeta pueden tardar más.", "Si corresponde, el acceso puede restaurarse, extenderse o puede brindarse ayuda para un reembolso mediante el proveedor de pago."]},
            ],
        },
        "ka": {
            "meta_service_type": "ციფრული სერვისები",
            "sections": [
                {"title": "1. დაბრუნების ზოგადი წესი", "paragraphs": ["ეს პოლიტიკა ვრცელდება CherryX Creator Studio-ს ციფრული სერვისების გადახდებზე."], "items": ["სერვისები ციფრულია და იწყება გადახდის დადასტურებისთანავე.", "ფასიანი წვდომის აქტივაციის შემდეგ თანხის დაბრუნება, როგორც წესი, არ არის გათვალისწინებული.", "ფიზიკური საქონელი არ იყიდება, არ იგზავნება და არ ბრუნდება."]},
                {"title": "2. შემთხვევები, რომლებიც შეიძლება განიხილოს მხარდაჭერამ", "items": ["ერთი და იმავე გეგმის ორმაგი გადახდა;", "დადასტურებული გადახდა, მაგრამ წვდომა არ გააქტიურდა ტექნიკური შეცდომის გამო;", "არასწორი ჩამოჭრა, რომელიც დადასტურებულია გადახდის პროვაიდერის მიერ;", "ტექნიკური ინციდენტი, რომელმაც მომხმარებელს არ მისცა ფასიან ციფრულ სერვისზე წვდომა."]},
                {"title": "3. დაუბრუნებელი შემთხვევები", "items": ["მომხმარებელმა გადაიფიქრა გადახდის შემდეგ;", "გეგმა არ გამოიყენებოდა აქტიური პერიოდის განმავლობაში;", "ატვირთული წყარო ფაილები დაბალი ხარისხის, არასწორი ან არასრული იყო;", "შედეგი არ ემთხვევა სუბიექტურ მოლოდინს ან მესამე მხარის წესებს;", "წვდომა შეიზღუდა პირობების დარღვევის ან ბოროტად გამოყენების გამო."]},
                {"title": "4. განხილვის მოთხოვნა", "paragraphs": ["განხილვისთვის მომხმარებელმა უნდა დაუკავშირდეს მხარდაჭერას და მიუთითოს გადახდის თარიღი, გადახდილი გეგმა, email ან ანგარიში, თანხა და გადახდის დადასტურება, თუ ხელმისაწვდომია."], "items": ["მხარდაჭერა შეეცდება მოთხოვნის განხილვას 5 სამუშაო დღეში საკმარისი ინფორმაციის მიღების შემდეგ.", "WayForPay-ს, ბანკის ან ბარათის გამომცემლის მონაწილე შემთხვევებს შეიძლება მეტი დრო დასჭირდეს.", "საჭიროების შემთხვევაში წვდომა შეიძლება აღდგეს, გაგრძელდეს ან დაბრუნების პროცესში დახმარება გაეწიოს გადახდის პროვაიდერის მეშვეობით."]},
            ],
        },
        "hy": {
            "meta_service_type": "Թվային ծառայություններ",
            "sections": [
                {"title": "1. Վերադարձի ընդհանուր կանոն", "paragraphs": ["Այս քաղաքականությունը կիրառվում է CherryX Creator Studio-ի թվային ծառայությունների վճարումների նկատմամբ։"], "items": ["Ծառայությունները թվային են և սկսվում են վճարման հաստատումից անմիջապես հետո։", "Վճարովի մուտքի ակտիվացումից հետո վերադարձը, որպես կանոն, չի նախատեսվում։", "Ֆիզիկական ապրանքներ չեն վաճառվում, չեն առաքվում և չեն վերադարձվում։"]},
                {"title": "2. Դեպքեր, որոնք կարող են վերանայվել", "items": ["նույն պլանի կրկնակի վճարում;", "հաստատված վճարում, բայց մուտքը չի ակտիվացվել տեխնիկական սխալի պատճառով;", "սխալ գանձում, որը հաստատվել է վճարային մատակարարի կողմից;", "տեխնիկական միջադեպ, որի պատճառով հաճախորդը չի ստացել վճարված թվային ծառայության հասանելիություն։"]},
                {"title": "3. Չվերադարձվող դեպքեր", "items": ["հաճախորդը փոխել է որոշումը վճարումից հետո;", "պլանը չի օգտագործվել ակտիվ ժամանակահատվածում;", "վերբեռնված սկզբնաղբյուր ֆայլերը ցածրորակ, սխալ կամ թերի էին;", "արդյունքը չի համապատասխանում սուբյեկտիվ ակնկալիքին կամ երրորդ կողմի կանոններին;", "մուտքը սահմանափակվել է պայմանների խախտման կամ չարաշահման պատճառով։"]},
                {"title": "4. Վերանայման հարցում", "paragraphs": ["Վերանայման համար հաճախորդը պետք է կապվի աջակցության հետ և նշի վճարման ամսաթիվը, վճարված պլանը, email-ը կամ հաշիվը, գումարը և վճարման հաստատումը, եթե առկա է։"], "items": ["Աջակցությունը կփորձի հարցումը դիտարկել 5 աշխատանքային օրվա ընթացքում՝ բավարար տեղեկատվություն ստանալուց հետո։", "WayForPay-ի, բանկի կամ քարտ թողարկողի մասնակցությամբ դեպքերը կարող են ավելի երկար տևել։", "Անհրաժեշտության դեպքում մուտքը կարող է վերականգնվել, երկարաձգվել կամ վերադարձի գործընթացում օգնություն տրամադրվել վճարային մատակարարի միջոցով։"]},
            ],
        },
        "it": {
            "meta_service_type": "Servizi digitali",
            "sections": [
                {"title": "1. Regola generale di rimborso", "paragraphs": ["Questa politica si applica ai pagamenti per i servizi digitali di CherryX Creator Studio."], "items": ["I servizi sono digitali e iniziano subito dopo la conferma del pagamento.", "Dopo l'attivazione dell'accesso a pagamento, il rimborso generalmente non è previsto.", "Non vengono venduti, consegnati o restituiti beni fisici."]},
                {"title": "2. Casi che possono essere esaminati", "items": ["pagamento duplicato per lo stesso piano;", "pagamento confermato senza attivazione dell'accesso a causa di un errore tecnico;", "addebito errato confermato dal provider di pagamento;", "incidente tecnico che ha impedito l'accesso al servizio digitale pagato."]},
                {"title": "3. Casi non rimborsabili", "items": ["ripensamento dopo il pagamento;", "mancato utilizzo del piano durante il periodo attivo;", "file sorgente di bassa qualità, errati o incompleti;", "risultato non conforme a preferenze soggettive o regole di terzi;", "restrizione dell'accesso per violazione dei termini o abuso."]},
                {"title": "4. Richiesta di verifica", "paragraphs": ["Per richiedere una verifica, il cliente deve contattare il supporto indicando data del pagamento, piano pagato, email o account, importo e conferme disponibili del pagamento."], "items": ["Il supporto farà ragionevoli sforzi per esaminare la richiesta entro 5 giorni lavorativi dopo aver ricevuto informazioni sufficienti.", "I casi con WayForPay, banca o emittente della carta possono richiedere più tempo.", "Se necessario, l'accesso può essere ripristinato, esteso o può essere fornita assistenza per il rimborso tramite il provider di pagamento."]},
            ],
        },
    }
)


LEGAL_DOCUMENTS["contacts"].update(
    {
        "fr": {"meta_service_type": "Services numériques à distance", "sections": [{"title": "Coordonnées du prestataire", "items": ["Entrepreneur individuel Petrusenko Maksym Denysovych.", "Identifiant fiscal: 3795908055.", "Email: cherryxdigital@gmail.com.", "Téléphone: +380 (96) 363-59-05.", "Les services sont fournis à distance; il n'existe pas de point de service physique."]}, {"title": "Format du service", "paragraphs": ["Les services sont fournis à distance via CherryX Creator Studio. Aucun accueil hors ligne n'est prévu."]}, {"title": "Prestataire de paiement", "paragraphs": ["Les paiements en ligne sont traités via WayForPay. Après paiement réussi, l'accès numérique choisi est activé dans le compte ou l'espace de travail."]}]},
        "de": {"meta_service_type": "Remote digitale Dienstleistungen", "sections": [{"title": "Anbieterdaten", "items": ["Einzelunternehmer Petrusenko Maksym Denysovych.", "Steuernummer: 3795908055.", "E-Mail: cherryxdigital@gmail.com.", "Telefon: +380 (96) 363-59-05.", "Die Dienstleistungen werden remote erbracht; es gibt keinen physischen Service-Standort."]}, {"title": "Serviceformat", "paragraphs": ["Die Dienstleistungen werden remote über CherryX Creator Studio erbracht. Ein Offline-Kundenservicepunkt ist nicht vorhanden."]}, {"title": "Zahlungsanbieter", "paragraphs": ["Online-Zahlungen werden über WayForPay verarbeitet. Nach erfolgreicher Zahlung wird der gewählte digitale Zugang im Konto oder Arbeitsbereich aktiviert."]}]},
        "es": {"meta_service_type": "Servicios digitales remotos", "sections": [{"title": "Datos del proveedor", "items": ["Empresario individual Petrusenko Maksym Denysovych.", "ID fiscal: 3795908055.", "Email: cherryxdigital@gmail.com.", "Teléfono: +380 (96) 363-59-05.", "Los servicios se prestan a distancia; no existe punto físico de atención."]}, {"title": "Formato del servicio", "paragraphs": ["Los servicios se prestan de forma remota a través de CherryX Creator Studio. No hay atención offline."]}, {"title": "Proveedor de pago", "paragraphs": ["Los pagos en línea se procesan mediante WayForPay. Tras el pago correcto, el acceso digital elegido se activa en la cuenta o espacio de trabajo."]}]},
        "ka": {"meta_service_type": "დისტანციური ციფრული სერვისები", "sections": [{"title": "მომწოდებლის ინფორმაცია", "items": ["ინდივიდუალური მეწარმე Petrusenko Maksym Denysovych.", "საგადასახადო ID: 3795908055.", "Email: cherryxdigital@gmail.com.", "ტელეფონი: +380 (96) 363-59-05.", "სერვისები მიეწოდება დისტანციურად; ფიზიკური მომსახურების პუნქტი არ არსებობს."]}, {"title": "სერვისის ფორმატი", "paragraphs": ["სერვისები მიეწოდება დისტანციურად CherryX Creator Studio-ს მეშვეობით. ოფლაინ მომსახურების პუნქტი არ არის."]}, {"title": "გადახდის პროვაიდერი", "paragraphs": ["ონლაინ გადახდები მუშავდება WayForPay-ის მეშვეობით. წარმატებული გადახდის შემდეგ არჩეული ციფრული წვდომა აქტიურდება ანგარიშში ან სამუშაო სივრცეში."]}]},
        "hy": {"meta_service_type": "Հեռավար թվային ծառայություններ", "sections": [{"title": "Մատակարարի տվյալներ", "items": ["Անհատ ձեռնարկատեր Petrusenko Maksym Denysovych.", "Հարկային ID: 3795908055.", "Email: cherryxdigital@gmail.com.", "Հեռախոս: +380 (96) 363-59-05.", "Ծառայությունները մատուցվում են հեռավար․ ֆիզիկական սպասարկման կետ չկա։"]}, {"title": "Ծառայության ձևաչափ", "paragraphs": ["Ծառայությունները մատուցվում են հեռավար CherryX Creator Studio-ի միջոցով։ Օֆլայն սպասարկման կետ նախատեսված չէ։"]}, {"title": "Վճարային մատակարար", "paragraphs": ["Առցանց վճարումները մշակվում են WayForPay-ի միջոցով։ Հաջող վճարումից հետո ընտրված թվային մուտքը ակտիվանում է հաշվում կամ աշխատանքային տարածքում։"]}]},
        "it": {"meta_service_type": "Servizi digitali da remoto", "sections": [{"title": "Dati del fornitore", "items": ["Imprenditore individuale Petrusenko Maksym Denysovych.", "Codice fiscale: 3795908055.", "Email: cherryxdigital@gmail.com.", "Telefono: +380 (96) 363-59-05.", "I servizi sono forniti da remoto; non esiste un punto fisico di assistenza."]}, {"title": "Formato del servizio", "paragraphs": ["I servizi sono forniti da remoto tramite CherryX Creator Studio. Non è previsto un punto di assistenza offline."]}, {"title": "Provider di pagamento", "paragraphs": ["I pagamenti online sono elaborati tramite WayForPay. Dopo il pagamento riuscito, l'accesso digitale selezionato viene attivato nell'account o nello spazio di lavoro."]}]},
    }
)


ACTIVE_LEGAL_DOCUMENTS: dict[str, dict[str, dict[str, object]]] = {
    "terms": {
        "en": {
            "meta_service_type": "Remote digital services",
            "sections": [
                {"title": "1. Service", "paragraphs": ["CherryX Creator Studio provides remote digital services: creative tools, AI-assisted processing, file exports, publication assets, account plans and CherryX balance."], "items": ["No physical goods are sold or shipped.", "Access is delivered online through the website account, workspace and Telegram payment flow.", "The customer is responsible for providing correct email, account and Telegram information."]},
                {"title": "2. Prices and CherryX", "paragraphs": ["The website shows prices in CherryX and may show an approximate USD equivalent for clarity. The operational payment amount is tied to Telegram Stars and the current internal Stars-to-CherryX rate."], "items": ["The final Telegram invoice is displayed in Telegram Stars before payment confirmation.", "Approximate USD values are informational and may change with the Stars rate or platform conditions.", "A paid plan or top-up is activated only after successful payment confirmation."]},
                {"title": "3. Telegram Stars payment", "paragraphs": ["Payments are made through the official Telegram bot invoice using Telegram Stars and currency XTR."], "items": ["From the website, the customer clicks the payment button and is redirected to the Telegram bot.", "The bot shows what is being purchased and sends a Telegram Stars invoice.", "After a successful payment, the service records the payment and applies the plan or CherryX balance to the linked website account.", "If no website account is linked, the bot asks for an email and helps create or connect an account."]},
                {"title": "4. Account access", "items": ["The customer must keep login credentials secure.", "If the payment was made from Telegram before account creation, the bot can generate website login details after the customer confirms an available email.", "If the email already exists, support may require website login or manual linking before applying the payment."]},
                {"title": "5. Digital delivery and limitations", "items": ["Paid digital access starts immediately after successful payment and activation.", "Generated files, previews, exports, queues and account balance are digital service results.", "Service quality can depend on source files, browser, device, internet connection and third-party platform limits."]},
                {"title": "6. Support and changes", "paragraphs": ["For payment, account or access questions, contact support using the email or phone listed on this page. These terms may be updated when payment flow, service logic or legal requirements change."]},
            ],
        },
        "ru": {
            "meta_service_type": "Дистанционные цифровые услуги",
            "sections": [
                {"title": "1. Услуга", "paragraphs": ["CherryX Creator Studio предоставляет дистанционные цифровые услуги: креативные инструменты, AI-обработку, экспорт файлов, материалы для публикаций, тарифные планы и баланс CherryX."], "items": ["Физические товары не продаются и не доставляются.", "Доступ предоставляется онлайн через аккаунт сайта, рабочее пространство и платежный сценарий в Telegram.", "Клиент отвечает за корректный email, аккаунт и данные Telegram."]},
                {"title": "2. Цены и CherryX", "paragraphs": ["На сайте цены показываются в CherryX и могут дополнительно отображаться в примерном долларовом эквиваленте. Фактическая логика оплаты привязана к Telegram Stars и текущему внутреннему курсу Stars к CherryX."], "items": ["Итоговый Telegram-инвойс показывается в Telegram Stars до подтверждения оплаты.", "Долларовый эквивалент носит информационный характер и может меняться вместе с курсом Stars или условиями платформы.", "Пакет или пополнение активируется только после успешного подтверждения оплаты."]},
                {"title": "3. Оплата Telegram Stars", "paragraphs": ["Оплата выполняется через официальный инвойс Telegram-бота в Telegram Stars, валюта XTR."], "items": ["На сайте клиент нажимает кнопку оплаты и переходит в Telegram-бот.", "Бот показывает, что покупается, и отправляет инвойс Telegram Stars.", "После успешной оплаты сервис фиксирует платеж и применяет пакет или баланс CherryX к привязанному аккаунту сайта.", "Если аккаунт сайта еще не привязан, бот спрашивает email и помогает создать или подключить аккаунт."]},
                {"title": "4. Доступ к аккаунту", "items": ["Клиент должен хранить логин и пароль безопасно.", "Если оплата сделана из Telegram до создания аккаунта, бот может выдать данные для входа после подтверждения свободного email.", "Если email уже занят, поддержка может попросить войти на сайте или выполнить ручную привязку перед применением оплаты."]},
                {"title": "5. Цифровая доставка и ограничения", "items": ["Платный цифровой доступ начинается сразу после успешной оплаты и активации.", "Сгенерированные файлы, превью, экспорты, очереди обработки и баланс аккаунта являются результатами цифровой услуги.", "Качество работы может зависеть от исходных файлов, браузера, устройства, интернета и ограничений сторонних платформ."]},
                {"title": "6. Поддержка и изменения", "paragraphs": ["По вопросам оплаты, аккаунта или доступа обращайтесь в поддержку по email или телефону на этой странице. Условия могут обновляться при изменении платежного сценария, логики сервиса или требований закона."]},
            ],
        },
        "uk": {
            "meta_service_type": "Дистанційні цифрові послуги",
            "sections": [
                {"title": "1. Послуга", "paragraphs": ["CherryX Creator Studio надає дистанційні цифрові послуги: креативні інструменти, AI-обробку, експорт файлів, матеріали для публікацій, тарифні плани та баланс CherryX."], "items": ["Фізичні товари не продаються і не доставляються.", "Доступ надається онлайн через акаунт сайту, робочий простір і платіжний сценарій у Telegram.", "Клієнт відповідає за коректний email, акаунт і дані Telegram."]},
                {"title": "2. Ціни та CherryX", "paragraphs": ["На сайті ціни показуються в CherryX і можуть додатково відображатися у приблизному доларовому еквіваленті. Фактична логіка оплати прив'язана до Telegram Stars і поточного внутрішнього курсу Stars до CherryX."], "items": ["Підсумковий Telegram-інвойс показується в Telegram Stars до підтвердження оплати.", "Доларовий еквівалент має інформаційний характер і може змінюватися разом із курсом Stars або умовами платформи.", "Пакет або поповнення активується лише після успішного підтвердження оплати."]},
                {"title": "3. Оплата Telegram Stars", "paragraphs": ["Оплата виконується через офіційний інвойс Telegram-бота в Telegram Stars, валюта XTR."], "items": ["На сайті клієнт натискає кнопку оплати і переходить у Telegram-бот.", "Бот показує, що купується, і надсилає інвойс Telegram Stars.", "Після успішної оплати сервіс фіксує платіж і застосовує пакет або баланс CherryX до прив'язаного акаунта сайту.", "Якщо акаунт сайту ще не прив'язаний, бот запитує email і допомагає створити або підключити акаунт."]},
                {"title": "4. Доступ до акаунта", "items": ["Клієнт має безпечно зберігати логін і пароль.", "Якщо оплату зроблено з Telegram до створення акаунта, бот може видати дані для входу після підтвердження вільного email.", "Якщо email уже зайнятий, підтримка може попросити увійти на сайті або виконати ручну прив'язку перед застосуванням оплати."]},
                {"title": "5. Цифрова доставка та обмеження", "items": ["Платний цифровий доступ починається одразу після успішної оплати та активації.", "Згенеровані файли, прев'ю, експорти, черги обробки та баланс акаунта є результатами цифрової послуги.", "Якість роботи може залежати від вихідних файлів, браузера, пристрою, інтернету та обмежень сторонніх платформ."]},
                {"title": "6. Підтримка та зміни", "paragraphs": ["З питань оплати, акаунта або доступу звертайтеся в підтримку за email або телефоном на цій сторінці. Умови можуть оновлюватися при зміні платіжного сценарію, логіки сервісу або вимог закону."]},
            ],
        },
    },
    "refund": {
        "en": {
            "meta_service_type": "Remote digital services",
            "sections": [
                {"title": "1. Digital service rule", "paragraphs": ["This policy applies to Telegram Stars payments for CherryX Creator Studio digital services."], "items": ["The service provides instant digital access after successful payment.", "Because access, balance or processing capacity is delivered digitally, refunds are generally not available after activation.", "No physical goods are returned or exchanged."]},
                {"title": "2. Cases support can review", "items": ["duplicate Telegram Stars payment for the same order;", "successful payment that did not activate the plan or balance because of a technical error;", "wrong account linking where the payment was not applied to the customer who paid;", "other technical incident where paid digital access was not delivered."]},
                {"title": "3. Cases that are not refundable", "items": ["the customer changed their mind after payment;", "the customer did not use the active plan or credited balance;", "the customer entered the wrong email or Telegram account and did not complete linking;", "source files were low quality, incomplete or unsuitable;", "access was restricted because of abuse, prohibited content or terms violation."]},
                {"title": "4. How to request review", "paragraphs": ["Contact support and include Telegram username or ID, website email if available, payment date and time, package or top-up amount in Stars, and screenshots of the Telegram invoice or successful payment if available."]},
                {"title": "5. Telegram Stars specifics", "paragraphs": ["Telegram Stars are processed by Telegram. CherryX records the successful bot payment and applies CherryX access or balance. Any platform-level reversal or Stars handling may depend on Telegram rules and technical possibilities."]},
            ],
        },
        "ru": {
            "meta_service_type": "Дистанционные цифровые услуги",
            "sections": [
                {"title": "1. Правило цифровой услуги", "paragraphs": ["Эта политика применяется к оплатам Telegram Stars за цифровые услуги CherryX Creator Studio."], "items": ["Сервис предоставляет моментальный цифровой доступ после успешной оплаты.", "Поскольку доступ, баланс или мощность обработки доставляются цифровым способом, возврат обычно недоступен после активации.", "Физические товары не возвращаются и не обмениваются."]},
                {"title": "2. Что поддержка может рассмотреть", "items": ["дублирующая оплата Telegram Stars по одному заказу;", "успешная оплата, после которой пакет или баланс не активировался из-за технической ошибки;", "ошибка привязки аккаунта, когда платеж не применился к клиенту, который оплатил;", "другой технический инцидент, при котором оплаченный цифровой доступ не был доставлен."]},
                {"title": "3. Что не возвращается", "items": ["клиент передумал после оплаты;", "клиент не использовал активный пакет или начисленный баланс;", "клиент указал неверный email или Telegram-аккаунт и не завершил привязку;", "исходные файлы были низкого качества, неполными или неподходящими;", "доступ ограничен из-за злоупотребления, запрещенного контента или нарушения условий."]},
                {"title": "4. Как запросить проверку", "paragraphs": ["Напишите в поддержку и укажите Telegram username или ID, email сайта при наличии, дату и время оплаты, пакет или сумму пополнения в Stars, а также скриншоты Telegram-инвойса или успешной оплаты, если они есть."]},
                {"title": "5. Особенности Telegram Stars", "paragraphs": ["Telegram Stars обрабатываются Telegram. CherryX фиксирует успешную оплату через бота и применяет доступ или баланс CherryX. Любой возврат на уровне платформы или обработка Stars может зависеть от правил Telegram и технической возможности."]},
            ],
        },
        "uk": {
            "meta_service_type": "Дистанційні цифрові послуги",
            "sections": [
                {"title": "1. Правило цифрової послуги", "paragraphs": ["Ця політика застосовується до оплат Telegram Stars за цифрові послуги CherryX Creator Studio."], "items": ["Сервіс надає миттєвий цифровий доступ після успішної оплати.", "Оскільки доступ, баланс або потужність обробки доставляються цифровим способом, повернення зазвичай недоступне після активації.", "Фізичні товари не повертаються і не обмінюються."]},
                {"title": "2. Що підтримка може розглянути", "items": ["дублююча оплата Telegram Stars за одним замовленням;", "успішна оплата, після якої пакет або баланс не активувався через технічну помилку;", "помилка прив'язки акаунта, коли платіж не застосувався до клієнта, який оплатив;", "інший технічний інцидент, коли оплачений цифровий доступ не був доставлений."]},
                {"title": "3. Що не повертається", "items": ["клієнт передумав після оплати;", "клієнт не використав активний пакет або нарахований баланс;", "клієнт вказав неправильний email або Telegram-акаунт і не завершив прив'язку;", "вихідні файли були низької якості, неповними або непридатними;", "доступ обмежено через зловживання, заборонений контент або порушення умов."]},
                {"title": "4. Як запросити перевірку", "paragraphs": ["Напишіть у підтримку і вкажіть Telegram username або ID, email сайту за наявності, дату і час оплати, пакет або суму поповнення в Stars, а також скриншоти Telegram-інвойса чи успішної оплати, якщо вони є."]},
                {"title": "5. Особливості Telegram Stars", "paragraphs": ["Telegram Stars обробляються Telegram. CherryX фіксує успішну оплату через бота і застосовує доступ або баланс CherryX. Будь-яке повернення на рівні платформи або обробка Stars може залежати від правил Telegram і технічної можливості."]},
            ],
        },
    },
    "contacts": {
        "en": {
            "meta_service_type": "Remote digital services",
            "sections": [
                {"title": "Contacts", "items": ["Email: cherryxdigital@gmail.com.", "Phone: +380 (96) 363-59-05.", "Support is provided remotely for account, Telegram Stars payment and access questions."]},
                {"title": "How Telegram Stars payment works", "items": ["Choose a package or top-up on the website or in the Telegram bot.", "Confirm the official Telegram Stars invoice in Telegram.", "After successful payment, CherryX activates the package or credits balance to the linked website account.", "If there is no website account yet, the bot asks for email and helps create access."]},
                {"title": "What to send support", "paragraphs": ["For faster help, include Telegram username or ID, website email, payment time, package or Stars amount and a screenshot of the invoice or successful payment."]},
            ],
        },
        "ru": {
            "meta_service_type": "Дистанционные цифровые услуги",
            "sections": [
                {"title": "Контакты", "items": ["Email: cherryxdigital@gmail.com.", "Телефон: +380 (96) 363-59-05.", "Поддержка работает дистанционно по вопросам аккаунта, оплаты Telegram Stars и доступа."]},
                {"title": "Как работает оплата Telegram Stars", "items": ["Выберите пакет или пополнение на сайте либо в Telegram-боте.", "Подтвердите официальный инвойс Telegram Stars в Telegram.", "После успешной оплаты CherryX активирует пакет или начисляет баланс на привязанный аккаунт сайта.", "Если аккаунта сайта еще нет, бот спросит email и поможет создать доступ."]},
                {"title": "Что отправить в поддержку", "paragraphs": ["Для быстрой помощи укажите Telegram username или ID, email сайта, время оплаты, пакет или сумму Stars и скриншот инвойса или успешной оплаты."]},
            ],
        },
        "uk": {
            "meta_service_type": "Дистанційні цифрові послуги",
            "sections": [
                {"title": "Контакти", "items": ["Email: cherryxdigital@gmail.com.", "Телефон: +380 (96) 363-59-05.", "Підтримка працює дистанційно з питань акаунта, оплати Telegram Stars і доступу."]},
                {"title": "Як працює оплата Telegram Stars", "items": ["Оберіть пакет або поповнення на сайті чи в Telegram-боті.", "Підтвердьте офіційний інвойс Telegram Stars у Telegram.", "Після успішної оплати CherryX активує пакет або нараховує баланс на прив'язаний акаунт сайту.", "Якщо акаунта сайту ще немає, бот запитає email і допоможе створити доступ."]},
                {"title": "Що надіслати в підтримку", "paragraphs": ["Для швидкої допомоги вкажіть Telegram username або ID, email сайту, час оплати, пакет або суму Stars і скриншот інвойса чи успішної оплати."]},
            ],
        },
    },
}

_GENERIC_TRANSLATIONS = {
    "fr": {
        "meta": "Services numériques à distance",
        "terms": [
            ("1. Service", ["CherryX Creator Studio fournit des services numériques à distance: outils créatifs, traitement assisté par IA, exports de fichiers, plans de compte et solde CherryX."], ["Aucun bien physique n'est vendu ni livré.", "L'accès est fourni en ligne via le compte du site et le paiement Telegram.", "Le client doit fournir un email, un compte et des données Telegram corrects."]),
            ("2. Prix et CherryX", ["Le site affiche les prix en CherryX et peut montrer un équivalent USD approximatif. Le paiement réel est lié aux Telegram Stars et au taux interne Stars vers CherryX."], ["La facture finale est affichée en Telegram Stars avant confirmation.", "Les montants USD sont indicatifs.", "Le plan ou le rechargement est activé après confirmation du paiement."]),
            ("3. Paiement Telegram Stars", ["Le paiement se fait via la facture officielle du bot Telegram en Telegram Stars, devise XTR."], ["Depuis le site, le client ouvre le bot Telegram.", "Le bot affiche l'achat et envoie la facture Stars.", "Après paiement, CherryX applique le plan ou le solde au compte lié.", "Sans compte lié, le bot demande un email et aide à créer ou connecter l'accès."]),
            ("4. Accès et support", ["L'accès numérique commence immédiatement après paiement réussi. Pour toute question de paiement ou d'accès, contactez le support par email ou téléphone."], []),
        ],
        "refund": [
            ("1. Service numérique", ["Cette politique s'applique aux paiements Telegram Stars pour les services numériques CherryX."], ["Après activation, le remboursement n'est généralement pas disponible.", "Aucun bien physique n'est retourné."]),
            ("2. Vérification possible", [], ["paiement Stars dupliqué;", "paiement réussi sans activation à cause d'une erreur technique;", "erreur de liaison de compte;", "autre incident où l'accès payé n'a pas été livré."]),
            ("3. Demande", ["Contactez le support avec Telegram username ou ID, email du site, date, montant en Stars et capture de la facture ou du paiement réussi."], []),
            ("4. Telegram Stars", ["Les Stars sont traitées par Telegram. CherryX enregistre le paiement du bot et crédite l'accès ou le solde CherryX."], []),
        ],
        "contacts": [
            ("Contacts", [], ["Email: cherryxdigital@gmail.com.", "Téléphone: +380 (96) 363-59-05.", "Support à distance pour compte, paiement Telegram Stars et accès."]),
            ("Paiement Telegram Stars", [], ["Choisissez un plan ou un rechargement.", "Confirmez la facture officielle dans Telegram.", "CherryX active le plan ou crédite le solde du compte lié.", "Sans compte, le bot demande un email et aide à créer l'accès."]),
        ],
    },
    "de": {
        "meta": "Remote digitale Dienstleistungen",
        "terms": [
            ("1. Dienst", ["CherryX Creator Studio bietet digitale Remote-Dienste: Kreativwerkzeuge, KI-gestützte Verarbeitung, Datei-Exporte, Kontopläne und CherryX-Guthaben."], ["Es werden keine physischen Waren verkauft oder geliefert.", "Der Zugriff erfolgt online über Website-Konto und Telegram-Zahlung.", "Der Kunde muss korrekte E-Mail-, Konto- und Telegram-Daten angeben."]),
            ("2. Preise und CherryX", ["Die Website zeigt Preise in CherryX und kann einen ungefähren USD-Wert anzeigen. Die Zahlung ist an Telegram Stars und den internen Stars-zu-CherryX-Kurs gebunden."], ["Die endgültige Rechnung wird vor Bestätigung in Telegram Stars angezeigt.", "USD-Werte dienen nur zur Orientierung.", "Plan oder Guthaben werden nach erfolgreicher Zahlung aktiviert."]),
            ("3. Telegram Stars Zahlung", ["Die Zahlung erfolgt über die offizielle Telegram-Bot-Rechnung in Telegram Stars, Währung XTR."], ["Der Kunde öffnet den Telegram-Bot.", "Der Bot zeigt den Kauf und sendet die Stars-Rechnung.", "Nach Zahlung aktiviert CherryX den Plan oder schreibt Guthaben gut.", "Ohne verknüpftes Konto fragt der Bot nach einer E-Mail."]),
            ("4. Zugriff und Support", ["Digitaler Zugriff beginnt sofort nach erfolgreicher Aktivierung. Bei Zahlungs- oder Zugriffsfragen kontaktieren Sie den Support per E-Mail oder Telefon."], []),
        ],
        "refund": [
            ("1. Digitale Dienstleistung", ["Diese Richtlinie gilt für Telegram Stars-Zahlungen für CherryX-Dienste."], ["Nach Aktivierung ist eine Rückerstattung in der Regel nicht möglich.", "Es gibt keine physischen Waren zur Rückgabe."]),
            ("2. Prüffälle", [], ["doppelte Stars-Zahlung;", "Zahlung ohne Aktivierung wegen technischem Fehler;", "fehlerhafte Kontoverknüpfung;", "anderer technischer Vorfall ohne gelieferten Zugriff."]),
            ("3. Anfrage", ["Kontaktieren Sie den Support mit Telegram-Username oder ID, Website-E-Mail, Datum, Stars-Betrag und Screenshot der Rechnung oder Zahlung."], []),
            ("4. Telegram Stars", ["Stars werden von Telegram verarbeitet. CherryX speichert die Bot-Zahlung und schreibt Zugriff oder Guthaben gut."], []),
        ],
        "contacts": [
            ("Kontakte", [], ["E-Mail: cherryxdigital@gmail.com.", "Telefon: +380 (96) 363-59-05.", "Remote-Support für Konto, Telegram Stars-Zahlung und Zugriff."]),
            ("Telegram Stars Zahlung", [], ["Plan oder Aufladung wählen.", "Offizielle Rechnung in Telegram bestätigen.", "CherryX aktiviert den Plan oder schreibt Guthaben gut.", "Ohne Konto fragt der Bot nach einer E-Mail."]),
        ],
    },
    "es": {
        "meta": "Servicios digitales remotos",
        "terms": [
            ("1. Servicio", ["CherryX Creator Studio presta servicios digitales remotos: herramientas creativas, procesamiento asistido por IA, exportación de archivos, planes de cuenta y saldo CherryX."], ["No se venden ni entregan bienes físicos.", "El acceso se entrega en línea mediante la cuenta del sitio y el pago en Telegram.", "El cliente debe indicar email, cuenta y datos de Telegram correctos."]),
            ("2. Precios y CherryX", ["El sitio muestra precios en CherryX y puede mostrar un equivalente aproximado en USD. El pago está vinculado a Telegram Stars y al tipo interno Stars a CherryX."], ["La factura final se muestra en Telegram Stars antes de confirmar.", "Los importes en USD son informativos.", "El plan o recarga se activa tras el pago correcto."]),
            ("3. Pago con Telegram Stars", ["El pago se realiza mediante la factura oficial del bot de Telegram en Telegram Stars, moneda XTR."], ["El cliente abre el bot de Telegram.", "El bot muestra la compra y envía la factura Stars.", "Tras el pago, CherryX aplica el plan o saldo a la cuenta vinculada.", "Sin cuenta vinculada, el bot pide email y ayuda a crear acceso."]),
            ("4. Acceso y soporte", ["El acceso digital empieza inmediatamente tras la activación. Para preguntas de pago o acceso, contacte soporte por email o teléfono."], []),
        ],
        "refund": [
            ("1. Servicio digital", ["Esta política aplica a pagos con Telegram Stars por servicios digitales de CherryX."], ["Tras la activación, normalmente no hay reembolso.", "No hay bienes físicos que devolver."]),
            ("2. Casos revisables", [], ["pago Stars duplicado;", "pago correcto sin activación por error técnico;", "error de vinculación de cuenta;", "otro incidente técnico sin entrega del acceso pagado."]),
            ("3. Solicitud", ["Contacte soporte con username o ID de Telegram, email del sitio, fecha, importe en Stars y captura de la factura o pago correcto."], []),
            ("4. Telegram Stars", ["Telegram procesa las Stars. CherryX registra el pago del bot y acredita acceso o saldo CherryX."], []),
        ],
        "contacts": [
            ("Contactos", [], ["Email: cherryxdigital@gmail.com.", "Teléfono: +380 (96) 363-59-05.", "Soporte remoto para cuenta, pago Telegram Stars y acceso."]),
            ("Pago Telegram Stars", [], ["Elija un plan o recarga.", "Confirme la factura oficial en Telegram.", "CherryX activa el plan o acredita saldo.", "Sin cuenta, el bot pide email y ayuda a crear acceso."]),
        ],
    },
    "it": {
        "meta": "Servizi digitali da remoto",
        "terms": [
            ("1. Servizio", ["CherryX Creator Studio fornisce servizi digitali da remoto: strumenti creativi, elaborazione assistita da IA, esportazioni, piani account e saldo CherryX."], ["Non vengono venduti o spediti beni fisici.", "L'accesso è fornito online tramite account del sito e pagamento Telegram.", "Il cliente deve indicare email, account e dati Telegram corretti."]),
            ("2. Prezzi e CherryX", ["Il sito mostra prezzi in CherryX e può mostrare un equivalente USD approssimativo. Il pagamento è legato a Telegram Stars e al tasso interno Stars-CherryX."], ["La fattura finale è mostrata in Telegram Stars prima della conferma.", "I valori USD sono informativi.", "Piano o ricarica si attivano dopo il pagamento riuscito."]),
            ("3. Pagamento Telegram Stars", ["Il pagamento avviene tramite fattura ufficiale del bot Telegram in Telegram Stars, valuta XTR."], ["Il cliente apre il bot Telegram.", "Il bot mostra l'acquisto e invia la fattura Stars.", "Dopo il pagamento CherryX applica piano o saldo all'account collegato.", "Senza account collegato, il bot chiede email e aiuta a creare accesso."]),
            ("4. Accesso e supporto", ["L'accesso digitale inizia subito dopo l'attivazione. Per domande su pagamento o accesso, contattare il supporto via email o telefono."], []),
        ],
        "refund": [
            ("1. Servizio digitale", ["Questa politica si applica ai pagamenti Telegram Stars per i servizi digitali CherryX."], ["Dopo l'attivazione, il rimborso generalmente non è disponibile.", "Non ci sono beni fisici da restituire."]),
            ("2. Casi verificabili", [], ["pagamento Stars duplicato;", "pagamento riuscito senza attivazione per errore tecnico;", "errore di collegamento account;", "altro incidente tecnico senza consegna dell'accesso pagato."]),
            ("3. Richiesta", ["Contattare il supporto con username o ID Telegram, email del sito, data, importo Stars e screenshot della fattura o del pagamento riuscito."], []),
            ("4. Telegram Stars", ["Le Stars sono elaborate da Telegram. CherryX registra il pagamento del bot e accredita accesso o saldo CherryX."], []),
        ],
        "contacts": [
            ("Contatti", [], ["Email: cherryxdigital@gmail.com.", "Telefono: +380 (96) 363-59-05.", "Supporto remoto per account, pagamento Telegram Stars e accesso."]),
            ("Pagamento Telegram Stars", [], ["Scegliere un piano o una ricarica.", "Confermare la fattura ufficiale in Telegram.", "CherryX attiva il piano o accredita saldo.", "Senza account, il bot chiede email e aiuta a creare accesso."]),
        ],
    },
    "ka": {
        "meta": "დისტანციური ციფრული სერვისები",
        "terms": [
            ("1. სერვისი", ["CherryX Creator Studio გთავაზობთ დისტანციურ ციფრულ სერვისებს: კრეატიულ ინსტრუმენტებს, AI-დამუშავებას, ფაილების ექსპორტს, ანგარიშის გეგმებს და CherryX ბალანსს."], ["ფიზიკური საქონელი არ იყიდება და არ იგზავნება.", "წვდომა გაიცემა ონლაინ, საიტის ანგარიშისა და Telegram გადახდის მეშვეობით.", "კლიენტი პასუხისმგებელია სწორი email-ის, ანგარიშისა და Telegram მონაცემების მითითებაზე."]),
            ("2. ფასები და CherryX", ["საიტზე ფასები ნაჩვენებია CherryX-ში და შეიძლება გამოჩნდეს მიახლოებითი USD ეკვივალენტი. გადახდა მიბმულია Telegram Stars-ზე და შიდა Stars-to-CherryX კურსზე."], ["საბოლოო ინვოისი Telegram Stars-ში ჩანს დადასტურებამდე.", "USD მნიშვნელობები ინფორმაციულია.", "გეგმა ან შევსება აქტიურდება წარმატებული გადახდის შემდეგ."]),
            ("3. Telegram Stars გადახდა", ["გადახდა ხდება Telegram ბოტის ოფიციალური ინვოისით Telegram Stars-ში, ვალუტა XTR."], ["კლიენტი ხსნის Telegram ბოტს.", "ბოტი აჩვენებს შესყიდვას და აგზავნის Stars ინვოისს.", "გადახდის შემდეგ CherryX ააქტიურებს გეგმას ან ბალანსს დაკავშირებულ ანგარიშზე.", "თუ ანგარიში არ არის დაკავშირებული, ბოტი ითხოვს email-ს."]),
            ("4. წვდომა და მხარდაჭერა", ["ციფრული წვდომა იწყება წარმატებული აქტივაციისთანავე. გადახდის ან წვდომის კითხვებისთვის დაუკავშირდით მხარდაჭერას email-ით ან ტელეფონით."], []),
        ],
        "refund": [
            ("1. ციფრული სერვისი", ["ეს პოლიტიკა ეხება Telegram Stars გადახდებს CherryX-ის ციფრული სერვისებისთვის."], ["აქტივაციის შემდეგ დაბრუნება ჩვეულებრივ არ არის ხელმისაწვდომი.", "ფიზიკური საქონელი დასაბრუნებელი არ არის."]),
            ("2. განხილვადი შემთხვევები", [], ["დუბლირებული Stars გადახდა;", "წარმატებული გადახდა აქტივაციის გარეშე ტექნიკური შეცდომის გამო;", "ანგარიშის დაკავშირების შეცდომა;", "სხვა ტექნიკური შემთხვევა, როცა ფასიანი წვდომა არ მიეწოდა."]),
            ("3. მოთხოვნა", ["მხარდაჭერას გაუგზავნეთ Telegram username ან ID, საიტის email, თარიღი, Stars თანხა და ინვოისის ან წარმატებული გადახდის სქრინი."], []),
            ("4. Telegram Stars", ["Stars მუშავდება Telegram-ის მიერ. CherryX ინახავს ბოტის გადახდას და არიცხავს წვდომას ან CherryX ბალანსს."], []),
        ],
        "contacts": [
            ("კონტაქტები", [], ["Email: cherryxdigital@gmail.com.", "ტელეფონი: +380 (96) 363-59-05.", "დისტანციური მხარდაჭერა ანგარიშის, Telegram Stars გადახდისა და წვდომისთვის."]),
            ("Telegram Stars გადახდა", [], ["აირჩიეთ გეგმა ან შევსება.", "დაადასტურეთ ოფიციალური ინვოისი Telegram-ში.", "CherryX ააქტიურებს გეგმას ან არიცხავს ბალანსს.", "ანგარიშის გარეშე ბოტი ითხოვს email-ს."]),
        ],
    },
    "hy": {
        "meta": "Հեռավար թվային ծառայություններ",
        "terms": [
            ("1. Ծառայություն", ["CherryX Creator Studio-ն տրամադրում է հեռավար թվային ծառայություններ՝ ստեղծագործական գործիքներ, AI-մշակում, ֆայլերի արտահանում, հաշվի պլաններ և CherryX մնացորդ։"], ["Ֆիզիկական ապրանքներ չեն վաճառվում կամ առաքվում։", "Մուտքը տրվում է առցանց՝ կայքի հաշվի և Telegram վճարման միջոցով։", "Հաճախորդը պատասխանատու է ճիշտ email, հաշիվ և Telegram տվյալներ նշելու համար։"]),
            ("2. Գներ և CherryX", ["Կայքում գները ցուցադրվում են CherryX-ով և կարող են ունենալ մոտավոր USD համարժեք։ Վճարումը կապված է Telegram Stars-ի և ներքին Stars-to-CherryX փոխարժեքի հետ։"], ["Վերջնական հաշիվը Telegram Stars-ով ցուցադրվում է հաստատումից առաջ։", "USD արժեքները տեղեկատվական են։", "Պլանը կամ լիցքավորումը ակտիվանում է հաջող վճարումից հետո։"]),
            ("3. Telegram Stars վճարում", ["Վճարումը կատարվում է Telegram բոտի պաշտոնական հաշվով Telegram Stars-ով, արժույթը՝ XTR։"], ["Հաճախորդը բացում է Telegram բոտը։", "Բոտը ցույց է տալիս գնումը և ուղարկում Stars հաշիվը։", "Վճարումից հետո CherryX-ը ակտիվացնում է պլանը կամ մնացորդը կապակցված հաշվին։", "Եթե հաշիվը կապակցված չէ, բոտը խնդրում է email։"]),
            ("4. Մուտք և աջակցություն", ["Թվային մուտքը սկսվում է հաջող ակտիվացումից անմիջապես հետո։ Վճարման կամ մուտքի հարցերով կապվեք աջակցության հետ email-ով կամ հեռախոսով։"], []),
        ],
        "refund": [
            ("1. Թվային ծառայություն", ["Այս քաղաքականությունը վերաբերում է CherryX թվային ծառայությունների Telegram Stars վճարումներին։"], ["Ակտիվացումից հետո վերադարձը սովորաբար հասանելի չէ։", "Ֆիզիկական ապրանք վերադարձնելու համար չկա։"]),
            ("2. Քննվող դեպքեր", [], ["կրկնակի Stars վճարում;", "հաջող վճարում առանց ակտիվացման տեխնիկական սխալի պատճառով;", "հաշվի կապակցման սխալ;", "այլ տեխնիկական դեպք, երբ վճարված մուտքը չի տրամադրվել։"]),
            ("3. Հարցում", ["Աջակցությանը ուղարկեք Telegram username կամ ID, կայքի email, ամսաթիվ, Stars գումար և հաշվի կամ հաջող վճարման screenshot։"], []),
            ("4. Telegram Stars", ["Stars-ը մշակվում է Telegram-ի կողմից։ CherryX-ը գրանցում է բոտի վճարումը և ավելացնում մուտք կամ CherryX մնացորդ։"], []),
        ],
        "contacts": [
            ("Կոնտակտներ", [], ["Email: cherryxdigital@gmail.com.", "Հեռախոս: +380 (96) 363-59-05.", "Հեռավար աջակցություն հաշվի, Telegram Stars վճարման և մուտքի հարցերով։"]),
            ("Telegram Stars վճարում", [], ["Ընտրեք պլան կամ լիցքավորում։", "Հաստատեք պաշտոնական հաշիվը Telegram-ում։", "CherryX-ը ակտիվացնում է պլանը կամ ավելացնում մնացորդ։", "Առանց հաշվի բոտը խնդրում է email։"]),
        ],
    },
}

for _language, _content in _GENERIC_TRANSLATIONS.items():
    for _doc_type in ("terms", "refund", "contacts"):
        ACTIVE_LEGAL_DOCUMENTS.setdefault(_doc_type, {})[_language] = {
            "meta_service_type": _content["meta"],
            "sections": [
                {"title": title, "paragraphs": paragraphs, "items": items}
                for title, paragraphs, items in _content[_doc_type]
            ],
        }


def legal_document_content(document_type: str, language: str | None) -> dict[str, object]:
    language = clean_language(language)
    documents = ACTIVE_LEGAL_DOCUMENTS.get(document_type) or ACTIVE_LEGAL_DOCUMENTS["terms"]
    document = documents.get(language) or documents.get("en") or {"sections": [], "meta_service_type": "Digital services"}
    return {
        "meta_service_type": document.get("meta_service_type", "Digital services"),
        "sections": [
            {
                "title": section.get("title", ""),
                "paragraphs": section.get("paragraphs", []),
                "items": section.get("items", []),
                "after": section.get("after", []),
            }
            for section in document.get("sections", [])
        ],
    }
