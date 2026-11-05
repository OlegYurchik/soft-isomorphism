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
