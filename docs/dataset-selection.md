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

## Рабочий выбор после обсуждения 05.11.2026

Пользователь подтвердил тему 2.6: мягкое сопоставление графа документа с графом знаний. Рабочий выбор для дальнейшей feasibility — **HotpotQA (основной по рекомендации руководителя) + MetaQA (второй, с готовым KG и SimGRAG-run commands)**. Это не обещание прямого сравнения с NGM-RAG: его полный код/пipeline не найден.

Роли различаются:
- **HotpotQA** пересекается по benchmark с NGM-RAG и имеет supporting-fact gold, но это корпус paragraphs, не готовый KG. Для graph retrieval ещё требуется определить и зафиксировать построение candidate graph/KG; если это не удастся, HotpotQA останется отдельным BM25 QA/retrieval benchmark, не доказательством graph-to-KG matching.
- **MetaQA** даёт явный movie KG и QA splits, удобен для первого BM25 baseline и проверки matcher-ов на KGQA. Он принимает текстовый вопрос, а не готовый document graph; query graph надо строить из вопроса без gold path.

Первым реализуется B0 на MetaQA, затем проводится оценка затрат HotpotQA graph construction. На обоих наборах результаты и метрики отчётно разделять. Перед полноценным запуском проверить pinned files/splits, license, hashes и 10–20 реальных примеров; локальные данные пока не скачаны.

## Что уже есть локально

- Адаптеры GTSQA/FactKG и schema из задачи #10.
- Fixtures — только несколько примеров для проверки парсинга; это не реальные данные и не feasibility аудит.
- Manifest отмечает реальные данные как `NOT_DOWNLOADED`.
- Поэтому сейчас нет результатов скачивания, checksum, статистики полной выборки или экспериментальных метрик.
