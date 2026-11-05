# Покрытие требований руководителя

Тема: мягкое сопоставление графа документа с KG. Основной набор — FactKG (короткие claims),
второй — HotpotQA distractor. Все имена методов и параметры задаёт протокол v2.

| Требование | Конкретный материал | Статус |
|---|---|---|
| 0. Работы и knowledge gap | [Таблица, задача #8](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-8-methods-review/docs/literature-review.md), включая NeMa/GED | Обзор расширен; общая новизна soft matching отвергнута. Узкий вклад остаётся гипотезой |
| 1. Простой baseline | [B0, задача #13](https://github.com/OlegYurchik/soft-isomorphism/blob/feat/issue-13-bm25-baseline/docs/baseline-factkg.md) | Дизайн, схема, код и реальный full-dev результат готовы |
| 2. Первый эксперимент | [E1, задача #7](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/docs/experiment-design-v2.md), [гипотеза #9](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-9-novelty/docs/novelty-proposals.md) | Зафиксированы формула, prompts, solver, controls, ограничения, метрики и пример. Graph run пока не выполнен |
| 3. Один-два benchmark | [Выбор #5](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-5-comparison-table/docs/dataset-selection.md), [аудит #6](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-6-feasibility/docs/dataset-feasibility.md) | FactKG splits и HotpotQA validation локально проверены; checksum/IDs сохранены. DBpedia light отсутствует |
| 4. Работа сравнения и улучшение | SimGRAG/FactKG — референс; B3 — исполнимый контроль вклада. NGM-RAG — related work + HotpotQA | Механизм предполагаемого улучшения описан; улучшение и воспроизведение авторских систем не заявлены |

## Как объяснить первый эксперимент устно

Берём утверждение FactKG как короткий документ и трижды извлекаем из него связи разными
фиксированными инструкциями одной модели. По совпадению результатов назначаем связям веса.
Во внешнем DBpedia ищем кандидатов по названиям сущностей, строим ограниченный общий pool
и сопоставляем граф документа с ним. Сравниваем одинаковый мягкий matcher с равными весами
и с весами согласованности extraction. По найденным фактам один и тот же reader выдаёт verdict.
Считаем Accuracy на заранее выбранных test IDs и парный доверительный интервал разницы.
Проверяем, не объясняется ли эффект просто случайными весами или большим бюджетом evidence.

## Реально получено

Полный FactKG dev (13 266): B0 Accuracy=55.2766%, macro-F1=55.2649%; majority Accuracy=51.5604%.
Один exact overlap с train, отдельная оценка без него даёт Accuracy=55.2733%.
HotpotQA validation: 7 405 записей скачаны и прочитаны. Re-DocRED: 500 dev документов проверены,
entity QID отсутствуют, поэтому набор исключён из первого дизайна.

## Чего пока нет

DBpedia light, pinned Qwen weights/runtime, extraction cache, реализация и результаты
graph arms B1/B2/B3/E1. Не доказана научная новизна agreement weighting, не получен выигрыш E1.
Для встречи можно показать конкретный дизайн и выполненный B0; нельзя объявлять НИР или
все implementation issues завершёнными. Руководитель явно разрешил обсуждать ещё не
подтверждённый вклад при наличии качественного сравнения работ.

Этот файл заменяет прежний разветвлённый план с альтернативными парами датасетов и разными
значениями dropout. Канонические параметры находятся в configs/experiment-v2.json ветки #7.
