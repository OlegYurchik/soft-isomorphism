# Предложения научной новизны

> Создан: 2026-10-29  
> Контекст: задача О9; входы — [О1](research-status.md), [О7](evaluation-protocol.md), [О8](research-status.md#1-прочитанные-работы).  
> Статус решения руководителя: **ОЖИДАЕТ РАССМОТРЕНИЯ** — предложения подготовлены для совместного обсуждения с выбором данных (О7).

---

## 1. Контекст: что уже установлено

**Гипотеза проекта** (из О1): вход в виде графа документа позволяет точнее задавать структурные ограничения при поиске в KG и снижает потери при query-to-pattern шаге.

**Ближайшие конкуренты** (из О8):

| Метод | Вход | Структурное сопоставление | Ограничение |
|-------|------|--------------------------|-------------|
| SimGRAG (Cai 2024) | Текст → паттерн (LLM) | GSD (structure + semantic) | Потеря структуры при text→pattern |
| SubgraphRAG (Li 2025) | Текст → тройки (LLM) | MLP + structural distances | Не использует граф документа |
| NGM-RAG (Chen 2026) | Граф данных | GNN + text, adaptive node weighting | Нет параметризованного cost function |
| GFM-RAG (Luo 2025) | Текстовый запрос | GNN retrieval без explicit matching | Нет explicit структурного соответствия |
| GPR (Wang 2025) | Текстовый запрос | Graph-pretrained retrieval | Retrieval-side, не matching |

**Выбранные данные** (из О7):
- Основной: GTSQA — ground-truth answer-subgraph, 2 727 типов структур, 27 типов `graph_isomorphism`
- Дополнительный: FactKG — 5 типов reasoning (One-hop, Multi-hop, Conjunction, Existence, Negation)
- Единица оценки: answer-subgraph; метрики: Edge Precision/Recall@k, MRR

---

## 2. Вариант 1: Граф документа как структурированный запрос

### 2.1 Суть

**Недостаток аналогов:** SimGRAG, SubgraphRAG и GFM-RAG начинают с текстового запроса и конвертируют его в граф-паттерн или тройки через LLM. Шаг text→pattern теряет структурную информацию: порядок рёбер, типы связей и топология цепочки не сохраняются в паттерне.

**Изменяемый механизм:** заменить text→pattern шаг прямым использованием графа документа как query graph. Document graph строится из извлечённых именованных сущностей и отношений; затем подаётся в GSD-like метрику напрямую для поиска в KG.

**Эксперимент:** на GTSQA сравнить (a) text-query → KG (B0/B2-стиль) и (b) document graph → KG. Измерить Edge Precision@k и MRR раздельно по числу рёбер в answer-subgraph (1-hop vs 2+ hop cases, стратифицируя по `graph_isomorphism`).

### 2.2 Анализ ближайших аналогов

**SimGRAG (Cai 2024)** — [arXiv:2412.15272](https://arxiv.org/abs/2412.15272)

| | |
|---|---|
| Задача | Subgraph retrieval из KG по текстовому запросу |
| Вход/выход | Текстовый запрос → граф-паттерн (LLM) → top-k подграфов |
| Механизм | GSD = w₁·structural_distance + w₂·semantic_distance; двухшаговый pipeline |
| Результаты авторов | Beats naive retrieval на WebQSP, MetaQA, multi-hop датасетах |
| Ограничение | LLM-шаг text→pattern ненадёжен на сложных структурах; GSD не калибруется под тип запроса |
| Код | Доступен (GitHub, ссылка в статье) |
| **Наше отличие** | **Граф документа заменяет LLM-паттерн; ни один промежуточный шаг не теряет топологию** |
| Условие сравнения | GTSQA test split; метрика Edge Precision@k; stratify по `graph_isomorphism` |

**SubgraphRAG (Li 2025)** — [arXiv:2410.20724](https://arxiv.org/abs/2410.20724)

| | |
|---|---|
| Задача | Subgraph retrieval для KG-based QA |
| Вход/выход | Текст → тройки → MLP scoring → ранжированные тройки |
| Механизм | Lightweight MLP; directional structural distances; subgraph size настраивается |
| Результаты авторов | SOTA на WebQSP и CWQ без fine-tuning (с GPT-4o) |
| Ограничение | Тройки теряют топологию подграфа; нет явного graph-to-graph matching |
| Код | Доступен |
| **Наше отличие** | **Сохраняем полный граф документа; matching — граф-к-графу, не список троек** |
| Условие сравнения | GTSQA test split; метрика Edge Recall@k |

**GFM-RAG (Luo NeurIPS 2025)** — [arXiv:2502.01113](https://arxiv.org/abs/2502.01113)

| | |
|---|---|
| Задача | KG retrieval для RAG; transfer across domains |
| Вход/выход | Текстовый запрос → GNN ретривер → релевантные узлы/рёбра |
| Механизм | GNN (~8M параметров), предобучен на 60 KG / 14M троек |
| Результаты авторов | SOTA на 3 multi-hop QA + 7 domain-specific датасетах |
| Ограничение | Не использует структуру на стороне документа; query — embedding текста |
| Код | Доступен |
| **Наше отличие** | **Query side — граф, не текст; explicit graph-to-graph matching, не embedding lookup** |
| Условие сравнения | GTSQA или FactKG; сравнение retrieval quality без downstream QA accuracy |

### 2.3 Условие отказа от заявления о новизне

Если Edge Precision@k для (b) document-graph-query статистически не выше (a) text-query на multi-hop случаях GTSQA (2+ hop subgraphs), гипотеза о преимуществе графового входа не подтверждена на пилоте.

Проверяемость: поле `graph_isomorphism` в GTSQA содержит 27 структурных типов — можно сегментировать результаты.

---

## 3. Вариант 2: Параметризованный soft iso cost function с edge-type constraints

### 3.1 Суть

**Недостаток аналогов:** NGM-RAG использует adaptive node weighting, но не предоставляет интерпретируемую метрику с явным trade-off между структурным и семантическим компонентами. SimGRAG's GSD имеет фиксированные веса и не учитывает тип рёбер.

**Изменяемый механизм:** параметризованная cost function

```
C(u,v) = λ · struct_sim(u,v) + (1-λ) · sem_sim(u,v)
```

где struct_sim кодирует типы рёбер и hop-расстояние (аналог WL-теста из KnowFormer), λ — настраиваемый гиперпараметр. Ключевое: struct_sim явно использует тип релейшена (Wikidata PID) при сопоставлении.

**Эксперимент:** варьировать λ ∈ {0.0, 0.3, 0.5, 0.7, 1.0} на GTSQA, стратифицируя по типу `graph_isomorphism`. Q1: растёт ли оптимальный λ с числом рёбер? Q2: на FactKG — разный ли оптимальный λ для One-hop vs Multi-hop vs Negation?

### 3.2 Анализ ближайших аналогов

**NGM-RAG (Chen 2026)** — [arXiv:2607.11159](https://arxiv.org/abs/2607.11159)

| | |
|---|---|
| Задача | Graph matching для RAG |
| Вход/выход | Граф данных → GNN + text matching → adaptive node weights → генерация |
| Механизм | GNN encoding + text similarity; adaptive weighting по важности узлов |
| Результаты авторов | Превосходит GraphRAG и LightRAG на multi-hop QA и long-context summarization |
| Ограничение | Нет явного trade-off параметра; adaptive weighting — это attention, не интерпретируемая метрика |
| Код | Не указан в обзоре |
| **Наше отличие** | **Явный λ; edge-type aware struct_sim; cost function интерпретируема и воспроизводима** |
| Условие сравнения | Если код NGM-RAG доступен: GTSQA, Edge Precision@5; иначе — сравнение только с SimGRAG |

**SimGRAG (Cai 2024)** — [arXiv:2412.15272](https://arxiv.org/abs/2412.15272)

| | |
|---|---|
| Задача | Subgraph retrieval по GSD |
| Вход/выход | Паттерн → подграфы по GSD = w₁·struct + w₂·sem |
| Механизм | GSD с фиксированными весами; struct = graph edit distance (не hop-count) |
| Ограничение | Веса w₁, w₂ фиксированы для всех типов запросов; тип рёбер не учитывается |
| **Наше отличие** | **λ настраивается по типу структуры; edge-type (Wikidata PID) входит в struct_sim** |
| Условие сравнения | GTSQA; λ-сканирование на dev-split, оценка на test |

**Raj et al. ICLR 2025** — [arXiv:2510.22897](https://arxiv.org/abs/2510.22897)

| | |
|---|---|
| Задача | Дизайн-пространство нейронного subgraph matching |
| Механизм | Early vs late interaction; node/edge embeddings; сравнение на GNN-архитектурах |
| Результаты | Interaction scheme критична; late interaction сильнее для sparse matching |
| Ограничение | Академический subgraph matching, не KG retrieval в RAG |
| **Наше отличие** | **Применяем late-interaction схему из Raj et al. к документ→KG контексту** |

### 3.3 Условие отказа от заявления о новизне

Если нет статистически значимого λ*, при котором edge-type-aware struct_sim превосходит GSD (λ=0.5, без edge types) на multi-hop GTSQA cases, преимущество edge-type constraints не подтверждено.

Дополнительно: если оптимальный λ не различается между 1-hop и 2+ hop структурами, параметризация не несёт информации.

---

## 4. Вариант 3: Hop-aware soft penalty (затухающие ограничения по глубине)

### 4.1 Суть

**Недостаток аналогов:** существующие методы либо требуют точного соответствия на всех hop (B1 exact match), либо применяют единый soft penalty ко всем рёбрам. При matching 3–4-hop документного графа с KG дальние рёбра должны быть мягче ограничены — у KG меньше шансов иметь точный эквивалент для 3-го hop.

**Изменяемый механизм:** cost function с hop-dependent затуханием:

```
C(u,v,d) = λ^d · struct_sim(u,v) + (1 - λ^d) · sem_sim(u,v)
```

где d — глубина hop в document graph. При d=1: строгое структурное ограничение; при d=3: почти полностью семантическое.

**Эксперимент:** на GTSQA сравнить hop-aware cost vs. flat soft cost. Измерить Edge Precision@k по `graph_isomorphism` типам с разным числом hop; на FactKG — по типам reasoning (One-hop vs Multi-hop).

### 4.2 Анализ ближайших аналогов

**FactKG (Kim ACL 2023)** — [arXiv:2305.06590](https://arxiv.org/abs/2305.06590)

| | |
|---|---|
| Задача | Fact verification через KG reasoning |
| Механизм | 5 типов reasoning: One-hop, Conjunction, Existence, Multi-hop, Negation |
| Ценность для нас | Типология reasoning → можно измерить отдельно, где hop-aware помогает |
| **Наше использование** | Стратификация результатов по reasoning type; Multi-hop тип как «сложный» кейс |

**KnowFormer (Liu 2024)** — [arXiv:2409.12865](https://arxiv.org/abs/2409.12865)

| | |
|---|---|
| Задача | Reasoning над KG через transformer |
| Механизм | Message-passing; WL-тест для graph isomorphism |
| Ограничение | Точный изоморфизм; нет soft penalty по глубине |
| **Наше отличие** | **WL-тест заменяется soft WL: hop-dependent λ вместо бинарного match/no-match** |

**SimGRAG (Cai 2024)** — уже описан в варианте 1.

| **Наше отличие** | **GSD не различает hop-глубину; наш cost function затухает с d** |

### 4.3 Условие отказа от заявления о новизне

Если Edge Precision@k для hop-aware cost не выше, чем для flat soft cost на 3+ hop структурах GTSQA, или разница не воспроизводится на FactKG Multi-hop, hop-awareness не несёт пользы на пилотных данных.

---

## 5. Рекомендуемый вклад и стратегия сравнения

**Рекомендация: Вариант 1 + элемент Варианта 2.**

Вариант 1 — наиболее ясно формулируемое отличие от всех конкурентов: «document graph as query source вместо text→pattern». Это проверяется прямым AB-экспериментом на GTSQA без необходимости разрабатывать новую архитектуру с нуля — достаточно адаптировать SimGRAG pipeline.

Элемент Варианта 2 (параметр λ) добавляет глубину: ответ на Q1 (когда структурный компонент критичен) является самостоятельным результатом даже если Вариант 1 не даёт улучшения.

Вариант 3 — наиболее сложный для реализации и проверки в рамках октябрьского пилота; оставить как расширение.

**Главный метод для сравнения: SimGRAG** (Cai 2024).
- Код доступен, датасеты пересекаются
- Предоставляет GSD как прямой аналог нашего cost function
- Позволяет прямое «ablation»: SimGRAG с text query vs. SimGRAG с graph query

Если код NGM-RAG станет доступен до пилота — добавить как второй бейзлайн.

**Необходимые изменения постановки:** нет. Текущий выбор данных (GTSQA + FactKG), метрики (Edge Precision/Recall@k, MRR) и разбиение (stratified по `graph_isomorphism`, seed=42) покрывают проверку Вариантов 1 и 2.

---

## 6. Статус решения руководителя

Варианты 1–3 подготовлены для обсуждения с руководителем (Анатолий Першинов). Реализация не начата. Выбор вклада и стратегии сравнения фиксируется после подтверждения.

| Элемент | Статус |
|---------|--------|
| Выбор основного вклада | Ожидает решения руководителя |
| Выбор второго бейзлайна (NGM-RAG) | Зависит от доступности кода |
| Изменение постановки | Не требуется при выборе В1+В2 |
| Начало реализации | **Не начато** |
