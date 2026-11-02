# Проверка Web Interface Guidelines

Проверены `web/src/main.tsx`, `pages.tsx`, `components.tsx`, `data.ts` и `style.css` по [актуальному источнику](https://raw.githubusercontent.com/vercel-labs/web-interface-guidelines/main/command.md).

- `web/src/main.tsx` — исправлены accessible name логотипа, гонка мобильного меню; сохранён persistent shell, skip link, route title, управление фокусом и URL/history/scroll.
- `web/src/pages.tsx` — графические узлы стали HTML-ссылками с доступными именами и CSS boxes для shared ViewTransition; SVG содержит только связи. Мобильная родословная — отдельные карточки с родителями. Фильтры/история сохраняются в URL. Нет измерения — нет числовой разницы.
- `web/src/components.tsx` — код выводится только текстом; таблицы имеют focusable scroll region; ограничено количество строк; локальный пример явно назван фиксированной контрольной стратегией.
- `web/src/style.css` — видимый focus, dark color-scheme, explicit transition properties, reduced-motion, responsive 360 px, tabular numeric data, перенос хешей, исправленный контраст монограммы.
- `web/src/data.ts` — ограничен streamed JSON, проверяются runtime shape/ссылки и размеры; ошибки/пустой архив имеют собственные состояния.

Итог: 111 браузерных проверок, отсутствие JS errors и page-level horizontal overflow на 360/768/1440. Axe: 0 автоматических нарушений на 16 surfaces. Полные JSON в `output/playwright/`. Контраст сложных SVG, клиппированные/невидимые части таблиц и screen-reader semantics остаются предметом ручного полного AA-аудита; incomplete не объявлены pass. Наличие hover/focus и text alternatives проверено, полного сертификационного аудита нет.

Отдельная native-frame проверка подтвердила old/new snapshots выбранного графического узла, `organism-specimen` и memory boundaries. При reduced-motion активных анимаций 0. Переход к подтверждённому изобретению не тестируется фиктивным объектом: таких изобретений нет.
