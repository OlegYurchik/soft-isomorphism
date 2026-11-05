# Сравнение бенчмарков и предварительная рекомендация

> Обновлено 05.11.2026 по замечаниям научного руководителя. Ветки/PR #4–#6 содержали shortlist GTSQA + FactKG как будто это выбранные данные. Это решение преждевременно: GTSQA даёт gold answer_subgraph, но не независимый query graph; FactKG решает claim verification, а test evidence graph в локальном аудите не подтверждён. Исходные датасеты в рабочую копию не загружены.

## Критерии выбора

Для задачи «графовый запрос → retrieval подграфа KG» benchmark должен содержать или позволять независимо получить:

1. Текст вопроса/документа как источник query graph.
2. KG или corpus, из которого строятся кандидаты.
3. Gold answer/evidence, доступный только evaluator.
4. Непересекающиеся train/dev/test или фиксированный официальный split.
5. Метрики, соответствующие заявленной задаче; benchmark-specific QA score отдельно от retrieval quality.

Наличие gold answer_subgraph не доказывает наличие query graph. Использовать gold ответ/путь как вход matching нельзя, кроме отдельного искусственного corruption stress test, который явно не выдаётся за end-to-end результат.

## Сравнение приоритетных вариантов

| Benchmark | Связь с работами | Вход / gold | Метрики | Преимущества | Риски и проверка |
|---|---|---|---|---|---|
| **HotpotQA** | Использован NGM-RAG (500-question sample) | Вопрос + paragraphs/supporting facts; KG нужно строить отдельно | Answer EM/F1; supporting-fact precision/recall | Прямое пересечение benchmark с NGM-RAG; руководитель рекомендует проверить | NGM-RAG code не найден; corpus graph extraction нужно реализовать; согласовать subset/split |
| **MetaQA** | SimGRAG; код содержит команду запуска | Вопрос + movie KG + gold answers | Hits@1/Hits@k по ответам; graph retrieval metrics отдельно | Практичный второй набор с опубликованной базовой точкой SimGRAG | Query graph не дан: строить из вопроса, не из answer path; проверить реальные файлы и license |
| **FactKG** | SimGRAG | Текст claim + DBpedia; classification labels | Accuracy/F1 для verification; retrieval metrics требуют evidence gold | Локальный parser уже есть; reasoning categories | Test evidence graph не подтверждён; не называть текущий адаптер тестом retrieval |
| **GTSQA** | KGQA | Вопрос + full search graph + gold answer_subgraph | QA/retrieval score по gold | Подграфовый gold удобен для evaluator | Отдельный независимый query graph отсутствует; нельзя подавать answer_subgraph как query |
| **PQ / WC2014** | SimGRAG | KGQA и KG | Hits@1 | Два дополнительных benchmark SimGRAG | README авторского кода не документирует команды; адаптацию оценить после проверки данных |

## Предварительная рекомендация

Подготовить feasibility **HotpotQA + MetaQA**: первый даёт пересечение по benchmark с NGM-RAG и закрывает вопрос руководителя, второй — прямой кандидат для запуска SimGRAG. Это shortlist для проверки, не утверждённый выбор и не обещание head-to-head с NGM-RAG. Сначала проверить официальный файлы/splits/license, sample schema, объём графостроения, API/GPU/runtime. Если ресурсов хватает только на один benchmark, выбрать MetaQA для быстрого controlled matcher comparison; HotpotQA оставить для последующего NGM-compatible track.

Финальный выбор должен совместно учитывать постановку руководителя. Если тема возвращается к общим алгоритмам изоморфизма/обновления графа, эта benchmark пара может быть неадекватной.

## Что уже есть локально

- Адаптеры GTSQA/FactKG и schema из задачи #10.
- Fixtures — только несколько примеров для проверки парсинга; это не реальные данные и не feasibility аудит.
- Manifest отмечает реальные данные как `NOT_DOWNLOADED`.
- Поэтому сейчас нет результатов скачивания, checksum, статистики полной выборки или экспериментальных метрик.
