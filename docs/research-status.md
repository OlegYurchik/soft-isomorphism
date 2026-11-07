# Научный статус — 05.11.2026

Подтверждённая тема: мягкое сопоставление графа документа с KG. Первый документ — FactKG claim; второй benchmark HotpotQA distractor для QA transfer.

Получено: аудит FactKG train/dev/test (86 367/13 266/9 041), загружен HotpotQA validation (7 405), проверены все 500 Re-DocRED dev документов (глобальных QID сущностей нет).
Реальный CPU B0 на полном FactKG dev: Accuracy 55.2766%, macro-F1 55.2649%; majority Accuracy 51.5604%. Найден 1 exact train/dev overlap, показана отдельная метрика без него.

Сформулирован конкретный E1: веса структурных ограничений по agreement трёх extraction prompts. NeMa/GED и learned edit costs показывают, что общая идея мягкого сопоставления не нова. Вклад E1 — гипотеза, преимущество не установлено.

Готовы дизайн, формула, схемы, параметры, сравнения, splits и CPU baseline. Не выполнены загрузка DBpedia light/весов Qwen, реализация и запуск graph arms, репликации SimGRAG/NGM-RAG.

- [Обзор #8](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-8-methods-review/docs/literature-review.md)
- [Протокол #7](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/docs/experiment-design-v2.md)
- [Baseline и результаты #13](https://github.com/OlegYurchik/soft-isomorphism/blob/feat/issue-13-bm25-baseline/docs/baseline-factkg.md)

Прежние заявления о закрытом knowledge gap, готовом независимом document graph в GTSQA и отсутствии любых локальных данных отменены. Не называем будущие результаты выполненной работой.

## Степень проработки источников

По доступным заметкам предметно разобраны механизмы и условия сравнения SimGRAG,
NGM-RAG, SubgraphRAG и GFM-RAG. Для них зафиксированы вход, выход, роль графа,
benchmark и ограничения в обзоре задачи #8. Обзор GraphRAG, KnowFormer, PolyRAG и
классические методы soft/noisy matching представлены как предварительное чтение.
В репозитории нет подтверждения, что какая-либо статья прочитана полностью от начала
до конца; такой статус может проставить только исследователь после личной проверки.

## Связь с задачами проекта

- #3 превращает тему в проверяемый вопрос: помогает ли структура находить evidence и
  как это отдельно оценивается от конечного TRUE/FALSE verdict.
- #4–#6 проверяют, где есть независимый внешний KG и воспроизводимые IDs; итогом стали
  FactKG как основной набор и HotpotQA как QA-transfer.
- #8 фиксирует аналоги и границы claims; #9 сужает возможный вклад до agreement-весов
  extraction, а не до общей идеи soft matching.
- #10 должен дать единый raw-вход для runtime; его старый edge-gold интерфейс не
  является готовым E1 loader.

## Открытые вопросы

1. Попадут ли названия сущностей из extracted graph в candidate pool DBpedia?
2. Будет ли E1 лучше B3 при одинаковых cached graphs, pool и reader?
3. Запустится ли зафиксированный Qwen runtime в доступном ресурсе?
4. Поддерживает ли результат перенос на HotpotQA, где KG строится из contexts?

Эти вопросы требуют запусков. Наличие дизайна и baseline не является ответом на них.
