# Протокол пилота: кандидат для проверки

> Обновлено 05.11.2026. Это конкретный экспериментальный дизайн-кандидат по теме 2.6, а не утверждённая постановка и не описание проведённого запуска. См. benchmark сравнение в [dataset-selection.md](dataset-selection.md).

## 1. Вопрос и гипотеза

**Вопрос:** помогает ли частичное soft subgraph matching сохранить качество retrieval при неполном query graph по сравнению с exact matching и SimGRAG GSD?

**Гипотеза-кандидат:** при controlled edge dropout предложенный matcher с явной ценой пропущенного и лишнего ребра деградирует медленнее VF2; на исходных графах не уступает GSD-подобному методу более заданного порога. Сама новизна не установлена: до заявления проверить NeMa, approximate subgraph matching и graph edit distance.

## 2. Бенчмарк и выбор данных

Предварительный shortlist: **HotpotQA + MetaQA**. HotpotQA совпадает с одной из оценок NGM-RAG; MetaQA — benchmark SimGRAG с командой в авторском README. Реальные файлы ещё не скачаны и выбор требует feasibility/ресурсной проверки.

- MetaQA: один и тот же KG snapshot, official split, Hits@1 по gold answers; дополнительно retrieval evidence metrics только если однозначно определён gold evidence.
- HotpotQA: official distractor setting, фиксированный question subset и paragraphs; answer EM/F1 + supporting-fact precision/recall/F1. NGM-RAG сравним только при воспроизведении полного pipeline на тех же 500 вопросах и контексте.
- GTSQA answer_subgraph нельзя подавать как query graph. GTSQA остаётся пригодным только для текстового KGQA baseline или отдельного controlled corruption эксперимента, где это ограничение явно указано.

После получения данных зафиксировать URL, license, version/commit, split, checksum, IDs subset и исключения в manifest. До этого статистические размеры/метрики считаются сведениями источников, не локально проверенными фактами.

## 3. Дизайн обработки

```
question + benchmark context/KG
       │
fixed query graph extractor (versioned prompt/model)
       │
save Gq; no gold answer/path/evidence in method input
       ├── original Gq
       └── edge dropout p ∈ {0, .1, .2, .4}, fixed seeds
                │
same candidate pool (top-M text index + bounded KG neighborhoods)
       ├── B0 BM25
       ├── B1 VF2 exact match
       ├── B2 SimGRAG/GSD (MetaQA if compatible)
       └── proposed partial mapping + edit penalties
                │
ranked evidence/answer → evaluator-only gold
```

1. Query graph строится только из question/context зафиксированным extractor-ом; сохраняются prompt, model version, raw output, parsed graph и ошибки. Никакой gold path/evidence/answer ID не передаётся.
2. Candidate pool формируется одним зафиксированным entity/relation index; top-M и размер окрестности выбираются на dev. Все graph matchers получают одни кандидаты.
3. B1 использует exact directed relation labels через VF2; логировать coverage, timeout и пустой результат.
4. Proposed matcher ищет ограниченное partial injective mapping query nodes → KG nodes. Стоимость:
   `C = λ_v C_node + λ_r C_relation + λ_m C_missing-edge + λ_x C_extra/incompatible-edge`.
   Label similarities — lexical/embedding distance; веса и search budget подбирать только на dev. Реализация-кандидат: beam search с фиксированными M/beam width и timeout.
5. Контролируемое выпадение рёбер создаётся после extraction из сохранённого Gq с заранее заданными seeds и p уровнями. Это stress test, отдельно от end-to-end основной оценки.

## 4. Baselines

- **B0 BM25:** ранжировать сериализованные triples/paragraphs; без topology. На MetaQA ответ ранжируется агрегацией score связанных сущностей; на HotpotQA — retrieved paragraphs.
- **B1 VF2:** строгий match на том же query graph/candidate pool.
- **B2 SimGRAG:** только совместимый benchmark (первый кандидат MetaQA); авторские результаты с другим extractor/настройками не выдавать за локальный head-to-head.
- **NGM-RAG:** related work. Прямой baseline только при доступности/воспроизводимости полного graph building, GNN, weights и evaluation; локальная GNN-компонента не равна NGM-RAG.

## 5. Метрики и отчёт

**MetaQA:** Hits@1/Hits@k по answer entities, graph-retrieval evidence P/R/F1 при наличии корректного gold; отдельно coverage и latency.

**HotpotQA:** answer EM/F1, supporting-fact P/R/F1/Recall, coverage, latency. Все методы используют одинаковые paragraphs, sample IDs и генератор ответа либо сравнение ограничивается retrieval-only.

Отчёт содержит original-query и каждую dropout severity отдельно. Сравнения paired по одним sample IDs; confidence interval — paired bootstrap на test. Параметры замораживаются до test. Не усреднять метрики разных benchmarks в один score.

## 6. Что считается подтверждением/опровержением

Поддержка гипотезы требует улучшения retrieval/answer robustness на corruption levels при фиксированном extractor/candidate pool и без недопустимого падения качества на исходных запросах. Если выигрыш пропадает при общей генерации графа либо существует только на synthetic corruption, вывод ограничивается robustness к контролируемой неполноте, а не реальным document-graph retrieval.

## 7. Открытые решения

1. Подтвердить тему 2.6 или вернуться к исходной теме алгоритмов изоморфизма/обновления.
2. Подтвердить основной benchmark после feasibility HotpotQA/MetaQA.
3. Утвердить graph extractor, primary metric, candidate budget и baseline scope.
4. До решения не переименовывать текущие адаптеры в реализацию этого эксперимента и не заявлять результаты.

На 05.11.2026 запусков на полных датасетах нет; текущие fixtures не заменяют загрузку и аудит benchmark.
