# Предложение первого эксперимента и возможного вклада

> Обновлено после замечаний руководителя 05.11.2026. Ниже — проверяемый дизайн-кандидат для темы 2.6, а не утверждённая новизна и не отчёт о выполненных запусках. Прежние формулировки на GTSQA/FactKG и прямое сравнение с NGM-RAG были преждевременными.

## 1. Что уже делают ближайшие работы

- **SimGRAG**: из текстового вопроса LLM строит граф-паттерн, затем Graph Semantic Distance ранжирует соответствующие структуры KG. Основные benchmarks: MetaQA, PQ, WC2014, FactKG; официальный репозиторий даёт команды как минимум для MetaQA и FactKG.
- **NGM-RAG**: строит query/target graphs из вопроса и корпуса, совмещает Levenshtein, BM25 и GNN node representations; оценка на HotpotQA, MultiHop-RAG (по 500 вопросов) и UltraDomain. Официальный код при проверке не найден.
- Поэтому недостатки «предыдущие методы не используют графы», «GSD = простой graph edit distance» и «NGM-RAG не имеет весов» нельзя использовать как обоснование новизны.

## 2. Вариант первого эксперимента

**Исследовательский вопрос.** Снижает ли частичное soft matching потерю качества при контролируемой неполноте query graph по сравнению с exact subgraph matching и GSD-подходом?

**Предварительная гипотеза.** При удалении рёбер из query graph частичное отображение с отдельными штрафами за пропущенные и несогласованные рёбра сохраняет retrieval/QA качество лучше VF2; на исходных запросах оно не должно заметно уступать SimGRAG. Эта гипотеза требует проверки новизны по NeMa, approximate subgraph matching и graph edit distance до заявления вклада.

### Поток данных

```
вопрос + KG/корпус benchmark
          │
фиксированный query-to-graph extractor (prompt/model/version)
          │
     query graph Gq
          ├── controlled edge dropout p = 0, 0.1, 0.2, 0.4
          │
одинаковый candidate pool для сравниваемых методов
          ├── B0 BM25 по текстовым фактам (без топологии)
          ├── B1 VF2 exact matching
          ├── B2 SimGRAG/GSD (только на совместимом benchmark)
          └── proposed partial mapping + explicit edit penalties
                         │
               evidence / answer ranking
                         │
     retrieval metrics + QA metrics + latency / coverage
```

### Детали протокола

1. Выбрать test split и зафиксировать sample IDs, версии файлов и checksum. Query graph строить только из вопроса и доступного текста-контекста; gold answer/path/evidence используется только evaluator.
2. Один и тот же extractor, его prompt, output schema и candidate-generation step использовать для B1/B2/proposed. Сохранить извлечённые графы и ошибки extractor; отдельно дать end-to-end и conditional matching результаты.
3. Построить общий candidate pool: top-M entity/relation candidates из одного lexical index и ограниченные связные окрестности KG. Значение M и budget поиска выбрать на dev и заморозить до test.
4. Для proposed метода найти ограниченное частичное инъективное отображение query nodes → KG nodes. Стоимость: semantic distance узлов/отношений + штраф пропущенного query edge + штраф лишнего/несовместимого candidate edge. Оптимизация — beam search с фиксированным budget. Весы подбирать только на dev.
5. Создать corrupted queries детерминированным удалением рёбер с фиксированными seeds. Отдельно измерить исходные графы и каждый dropout уровень; не менять gold.
6. Report coverage (доля запросов с непустым извлечённым/сопоставленным графом), retrieval recall/precision/F1 по evidence, QA Hits@1/EM/F1 и latency. На HotpotQA дополнительно supporting-fact recall; на MetaQA — Hits@1 по gold answers. Считать paired bootstrap CI на одних и тех же примерах.

## 3. Бенчмарки и сравнения

| Benchmark | Зачем | Что сравнивать | Ограничения |
|---|---|---|---|
| **MetaQA** | SimGRAG использует его; авторский код содержит команду запуска | BM25, VF2, SimGRAG GSD, proposed — при едином candidate pool и разделении extractor/matcher | Придётся сгенерировать query graph из вопроса; не подавать gold path/answer на вход |
| **HotpotQA** | Benchmark NGM-RAG и рекомендация руководителя для потенциального пересечения | BM25 и наши методы; NGM-RAG — только при доступном/reproduced full pipeline | NGM использовал 500 вопросов; нужен заранее фиксированный общий subset и соответствующий контекстный corpus |
| **FactKG** | SimGRAG benchmark; локальный адаптер уже есть | Возможная отдельная проверка fact verification | Не считать его универсальной заменой KGQA: test evidence graph не подтверждён локальным аудитом, а основная метрика статьи — accuracy |

**Рабочая рекомендация:** подготовить feasibility для пары HotpotQA + MetaQA: HotpotQA покрывает сопоставление с постановкой NGM-RAG, MetaQA даёт практическую площадку SimGRAG. До проверки данных/ресурсов это shortlist, не окончательно выбранная пара. Не сравнивать published scores разных benchmarks напрямую; NGM-RAG пока related work, а не baseline.

## 4. Критерии результата и фальсификации

- H1 поддерживается, если при dropout proposed method статистически значимо превосходит VF2 по QA/evidence метрике и не теряет покрытие; опубликованные SimGRAG числа сами по себе не являются контрольной группой.
- Если преимущество исчезает при одинаковом extractor/candidate pool, либо достигается только после подбора на test, гипотеза не подтверждена.
- Сравнение с SimGRAG называется head-to-head только при общем benchmark, одинаковой выборке, candidate KG, extractor/LLM settings и evaluator. Иначе это адаптация/сравнение опубликованного контекста с оговорками.
- Сравнение с NGM-RAG — только при полном воспроизведении его graph construction, weights, GNN, sampling и evaluation; запуск LightGCN/GINE-компоненты не достаточен.

## 5. Решения, требующие согласования

1. Остаётся ли тема 2.6 или возвращаемся к исходным алгоритмам изоморфизма и обновления графа?
2. Принимается ли устойчивость к неполноте query graph как первый вопрос с возможной новизной?
3. Согласовать MetaQA + HotpotQA после проверки файлов и доступных ресурсов.
4. Утвердить extractor, candidate-pool budget, primary metric и режим сравнения.

Собственных прогонов нет; текущий локальный аудит адаптеров охватывает только fixtures, а реальные исходные наборы не загружены.
