# Научный статус проекта

> Последнее обновление: 2026-10-29  
> Состояние репозитория на момент проверки 05.10.2026: только каркас LightRAG (commit `06f2776`), экспериментальных артефактов нет.

---

## 1. Прочитанные работы

Исходные PDF: `~/Obsidian/Personal/Образование/ИТМО/BIg Data and Machine Learning/НИР/`. Журнал чтения: [`docs/reading-log.md`](reading-log.md).

| # | Работа | Ссылка | Степень прочтения | Ключевой вывод |
|---|--------|--------|-------------------|----------------|
| 1 | Edge et al. **"From Local to Global: A Graph RAG Approach to Query-Focused Summarization"** (Microsoft, 2024) | [arXiv:2404.16130](https://arxiv.org/abs/2404.16130) | Полностью | GraphRAG строит граф сущностей/отношений, выделяет communities и их summaries — даёт ответы на глобальные вопросы по корпусу, которые классический RAG не осиливает. Не решает задачу точного сопоставления структур. |
| 2 | Cai et al. **"SimGRAG: Leveraging Similar Subgraphs for Knowledge Graphs Driven Retrieval-Augmented Generation"** (Fudan, 2024) | [arXiv:2412.15272](https://arxiv.org/abs/2412.15272) | Полностью | Двухшаговый pipeline: (1) запрос → граф-паттерн (LLM), (2) паттерн → top-k подграфов по Graph Semantic Distance (GSD). Ближайший аналог нашего подхода. **Центральная работа для обзора конкурентов.** |
| 3 | Liu et al. **"KnowFormer: Revisiting Transformers for Knowledge Graph Reasoning"** (ICML 2024) | [arXiv:2409.12865](https://arxiv.org/abs/2409.12865) | Просмотрена | Reasoning над KG через трансформеры с message-passing; формализует graph isomorphism через биекцию + WL-тест. Полезна для понимания структурной составляющей. |
| 4 | Chen et al. **"Knowledge Pyramid Construction for Multi-Level Retrieval-Augmented Generation"** (PolyRAG, PolyU HK, 2025) | [arXiv:2407.21276](https://arxiv.org/abs/2407.21276) | Просмотрена | Онтология → KG → сырой текст: каскадный retrieval по уровням. Outperforms 19 SOTA методов на academic и financial QA. Даёт перспективу на многоуровневую организацию знаний, к ядру задачи примыкает косвенно. |
| 5 | Li et al. **"Simple Is Effective: The Roles of Graphs and Large Language Models in Knowledge-Graph-Based Retrieval-Augmented Generation"** (SubgraphRAG, ICLR 2025) | [arXiv:2410.20724](https://arxiv.org/abs/2410.20724) | Просмотрена | Lightweight MLP скорит тройки параллельно; кодирует directional structural distances; размер подграфа настраивается под запрос и LLM. SOTA на WebQSP и CWQ без fine-tuning. Показывает текущую планку на тех же бенчмарках, что используют SimGRAG. |
| 6 | Chen et al. **"NGM-RAG: Neural Graph Matching based Retrieval-Augmented Generation"** (2026) | [arXiv:2607.11159](https://arxiv.org/abs/2607.11159) | Просмотрена | Строит граф из данных, матчит через GNN + текстовое сходство с adaptive node weighting, затем генерирует ответ. Превосходит GraphRAG и LightRAG на multi-hop QA и long-context summarization. **Ближайший прямой конкурент** нашего подхода: граф как вход, нейронный matching как ядро. |
| 7 | Zhang et al. **"A Survey of Graph Retrieval-Augmented Generation for Customized LLMs"** (2025, v3 сен 2025) | [arXiv:2501.13958](https://arxiv.org/abs/2501.13958) | Просмотрена | Систематический обзор Graph RAG: graph indexing → retrieval → structure-aware generation. Охватывает методы, домены, открытые проблемы. Поддерживается Awesome-GraphRAG репозиторием. Закрывает knowledge gap из раздела 3.3. |

| 8 | Luo et al. **"GFM-RAG: Graph Foundation Model for Retrieval Augmented Generation"** (NeurIPS 2025) | [arXiv:2502.01113](https://arxiv.org/abs/2502.01113) | Просмотрена | GNN-ретривер (~8M параметров), предобучен на 60 KG и 14M троек; query-dependent retrieval по KG-индексу без fine-tuning. SOTA на 3 multi-hop QA + 7 domain-specific датасетах. Прямой конкурент: структурный ретривал из KG без явного graph matching. |
| 9 | Wang et al. **"GPR: Empowering Generation with Graph-Pretrained Retriever"** (EMNLP 2025) | [arXiv:2506.00261](https://arxiv.org/abs/2506.00261) | Просмотрена | Graph-pretrained retriever: синтетические вопросы из троек (masked triplet prompting) + structure-aware objective. Улучшает retrieval на WebQSP и CWQ vs text-pretrained. Конкурент на retrieval-side; показывает ценность graph-специфичного pretraining. |
| 10 | Kim et al. **"FactKG: Fact Verification via Reasoning on Knowledge Graphs"** (ACL 2023) | [arXiv:2305.06590](https://arxiv.org/abs/2305.06590) | Просмотрена | 108k claims из DBpedia; 5 типов reasoning (One-hop, Conjunction, Existence, Multi-hop, Negation); fact verification. **Кандидат датасет**: document→KG mapping, multi-hop структуры, открытая лицензия. |
| 11 | Ho et al. **"Constructing A Multi-hop QA Dataset for Comprehensive Evaluation of Reasoning Steps"** (2WikiMultiHopQA, COLING 2020) | [arXiv:2011.01060](https://arxiv.org/abs/2011.01060) | Просмотрена | Wikipedia + Wikidata; шаблоны + логические правила; каждый пример содержит явный reasoning path. Требует multi-hop reasoning. **Кандидат датасет**: Wikidata как KG, structured reasoning paths. |
| 12 | Tan et al. **"Revisiting DocRED – Addressing the False Negative Problem in Relation Extraction"** (Re-DocRED, EMNLP 2022) | [arXiv:2205.12696](https://arxiv.org/abs/2205.12696) | Просмотрена | Переразметка 4053 DocRED-документов: восстановлены пропущенные relation triples, исправлены coreference ошибки. +13 F1 vs оригинала. **Кандидат датасет**: document-level extraction с KG (Wikidata), нетривиальные структуры. |
| 13 | Raj et al. **"Charting the Design Space of Neural Graph Representations for Subgraph Matching"** (ICLR 2025) | [arXiv:2510.22897](https://arxiv.org/abs/2510.22897) | Просмотрена | Систематика нейронных subgraph matching: early vs late interaction, node/edge embeddings. Показывает, что схема взаимодействия критична для качества. **Теоретическая база**: систематика для разработки нашей soft iso метрики. |

> **Пробелы:** ~~нет бенчмарк-статей~~ — закрыто (#10–#12). Теоретическая база subgraph matching закрыта (#13). Остаётся: проверить FactKG, 2WikiMultiHopQA и Re-DocRED на соответствие must-have критериям из `data-requirements.md` (задача **#6**).

---

## 2. Концептуальная цепочка работ

Четыре прочитанных работы акцентируют разные уровни одной проблемы:

| Работа | Основной вопрос |
|--------|-----------------|
| **GraphRAG** (Edge 2024) | Как представить большой корпус через граф и communities, чтобы отвечать на глобальные вопросы? |
| **KnowFormer** (Liu 2024) | Как выполнять reasoning над Knowledge Graph структурно? |
| **PolyRAG** (Chen 2025) | Как организовать retrieval между несколькими уровнями представления знаний? |
| **SimGRAG** (Cai 2024) | Как использовать графовую структуру и graph matching для поиска релевантных подграфов? |

Связь между ними:

```
Documents
    │
    ▼
Knowledge Graph
    │
    ├───────────────┐
    │               │
    ▼               ▼
GraphRAG         Graph Reasoning (KnowFormer)
    │               │
Communities       KG structure
    │               │
Summaries         Isomorphism
    │               │
    └───────┬───────┘
            ▼
      Graph-based Retrieval (SimGRAG, PolyRAG)
            │
            ▼
     Semantic Matching
            │
            ▼
           LLM
```

Graph-based RAG можно рассматривать как переход: `text similarity → graph structure → graph matching → semantic graph matching → LLM generation`.

**Graph isomorphism** — фундаментальный инструмент для этапа структурного соответствия. SimGRAG разделяет: (1) structural matching — найти подграфы подходящей структуры; (2) semantic matching — определить, какие из них наиболее близки по смыслу.

---

## 3. Идеи и гипотезы

### 3.1 Что предлагается

Классический graph isomorphism ищет точное структурное соответствие. В реальных документах и KG это требование слишком жёсткое. Предложение проекта — **мягкое сопоставление (soft isomorphism)**:

```
Document graph  ←→  Knowledge graph
       \                 /
        soft matching cost
             (GSD-like)
```

Граф документа (извлечённые сущности + отношения) сопоставляется с подграфами KG через метрику, учитывающую структурное и семантическое сходство. Это расширение SimGRAG: SimGRAG идёт от **текстового запроса → паттерна → KG**; наш подход идёт от **графа документа → KG**, что позволяет работать с multi-hop и структурно нетривиальными документами.

### 3.2 Отличие от аналогов

| Метод | Точка входа | Структурное сопоставление | Семантика | Масштаб |
|-------|-------------|--------------------------|-----------|---------|
| GraphRAG (Edge 2024) | Текст → communities | Нет | Да | Корпус |
| SimGRAG (Cai 2024) | Текст → паттерн | Да (GSD, частично soft) | Да | ~10M рёбер |
| KnowFormer (Liu 2024) | KG triplets | Да (WL-тест) | Нет | Inductive KG |
| SubgraphRAG (Li 2025) | Текст → тройки | Да (structural distances) | Да | WebQSP/CWQ |
| NGM-RAG (Chen 2026) | Граф данных | Да (GNN matching) | Да | Multi-hop QA |
| **Наш подход** | **Граф документа** | **Да (soft iso)** | **Да** | TBD |

Ключевая гипотеза (не подтверждена): вход в виде графа документа позволяет точнее задавать структурные ограничения и снижает потери при query-to-pattern шаге.

### 3.3 Открытые вопросы

- **Knowledge gap:** ~~не найдена survey~~ — закрыто: Zhang et al. 2025 (#7) + GFM-RAG (NeurIPS 2025, #8) и GPR (EMNLP 2025, #9) — актуальный ландшафт методов.
- **Данные:** какой KG использовать (Freebase/Wikidata/домен)? Какие документы как источник графов? Какой benchmark позволяет измерить улучшение? Нет ответа.
- **Метрика:** GSD из SimGRAG — прямой кандидат, но нужно проверить, работает ли он при входе из графа документа (не из текстового паттерна).
- **Стоимость поиска:** ограниченный поиск отображения нужен, чтобы задача не была NP-полной в явном виде.
- **Gold dataset:** нужен датасет с нетривиальными случаями (не простые QA), где есть поле для прироста над baseline.

---

## 4. Проведённые проверки

**Экспериментов не было.** В репозитории на 05.10.2026 — только инфраструктурный каркас (docker-compose с LightRAG, .env.example). Код сопоставления, метрики и данные отсутствуют. Все проверки — концептуальные: чтение статей, формирование понятийного аппарата.

---

## 5. Связь с текущим планом

### Задача #3 (Определить требования к данным) переиспользует:

- Понимание задачи сопоставления (раздел 3.1) → определяет требования к структуре документного графа и KG.
- Список аналогов (раздел 3.2) → бенчмарки из SimGRAG и GraphRAG (WebQSP, FactKG, 2WikiMultiHopQA и др.) — стартовый список для оценки.
- Открытые вопросы по данным (раздел 3.3) → напрямую становятся критериями в #3.

### Задача #8 (Актуализировать обзор сильных методов) переиспользует:

- Таблицу аналогов (раздел 3.2) — основа для сравнительной таблицы методов.
- Список прочитанных работ (раздел 1) — 4 работы уже покрыты; нужны ещё ~6–10 для полноценного обзора.
- SimGRAG как ближайший конкурент (B3) — уже описан.
- Открытый вопрос по knowledge gap (раздел 3.3) — определяет направление поиска новых работ.
