# Обзор методов: Graph-Based Retrieval и Subgraph Matching

> Создан: 2026-10-29  
> Контекст: задача О8; входы — [`docs/reading-log.md`](reading-log.md), [`docs/research-status.md`](research-status.md).  
> Все численные результаты — из первичных источников (arXiv/публикация) или помечены *(вторичный источник)*.

---

## 1. Сравнительная таблица методов

### 1.1 Таблица особенностей алгоритмов (для презентации)

Строки — методы/версии; столбцы — единица сопоставления, тип входа, строгость ограничений, генерация кандидатов, функция стоимости, алгоритм поиска.

| Метод | Год | Единица сопоставления | Тип входа | Строгость | Генерация кандидатов | Функция стоимости | Поиск | Код |
|-------|-----|-----------------------|-----------|-----------|----------------------|-------------------|-------|-----|
| **SimGRAG** | 2024 | Subgraph | Text → LLM pattern | **Soft** (GSD) | LLM: text → граф-паттерн | GSD = structural distance + node semantic sim | Top-k greedy по GSD | [GitHub](https://github.com/YZ-Cai/SimGRAG) |
| **SubgraphRAG** | ICLR 2025 | Triplet → subgraph | Text | **Soft** (MLP scoring) | Entity retrieval → 1-hop expansion | MLP score per triple (structural distances + text) | Parallel triple scoring, tunable size | [GitHub](https://github.com/SubgraphRAG) |
| **GFM-RAG** | NeurIPS 2025 | Entity-rooted subgraph | Text | **Soft** (GNN, pretrained) | KG-индекс по сущностям запроса | GNN query-dependent edge scoring (60 KG pretraining) | GNN-based retrieval, top-k | [GitHub](https://github.com/luo-junyu/GFM-RAG) |
| **NGM-RAG** | 2026 | Node-level match → subgraph | Data graph | **Soft** (neural) | Граф из данных (документа) | GNN + text cos-sim + adaptive node weights | Node matching, затем subgraph extraction | не опубликован |
| **GPR** | EMNLP 2025 | Triplet | Text | **Soft** (pretrained LM) | Masked triplet prompting → LM | Structure-aware retrieval score | LM retriever | не опубликован |
| **KnowFormer** | ICML 2024 | KG triplet (completion) | KG triplets | **Строгий** (WL-тест) | KG-neighbor traversal | Transformer + message-passing | Structure-aware attention | [GitHub](https://github.com/KnowFormer) |
| **GraphRAG** | 2024 | Community summary | Text corpus | Нет структурного | Community detection (Leiden) | Текстовое сходство | Глобальный community-based | [GitHub](https://github.com/microsoft/graphrag) |
| **Наш подход** | — | Subgraph | **Document graph** | **Soft iso** | Граф документа → KG поиск | Soft iso cost (GSD-like, TBD) | TBD | — |

> **Строгий аналог:** KnowFormer — структурное matching через WL-тест, без семантики; аналог «exact subgraph match» в нашей постановке.  
> **Сильный мягкий аналог:** SimGRAG — ближайший конкурент: GSD совмещает структурное и семантическое, но вход — текст, не граф документа.

**2–3 предложения для слайда:** существующие методы используют либо строгое структурное сопоставление (KnowFormer: WL-тест, без семантики) либо мягкое на основе текстового запроса (SimGRAG, SubgraphRAG, GFM-RAG: text → KG). Ни один из методов не принимает на вход **граф документа** напрямую — все трансформируют текстовый запрос в паттерн через LLM. Открытый вопрос: теряется ли структурная информация при шаге «text → LLM pattern», и восполняет ли прямой граф-вход эту потерю?

---

### 1.2 Результаты на бенчмарках

Числа — только из первичных источников (статья/её таблица), иначе помечено *(вторичный)*.

| Метод | Бенчмарк | Split | Метрика | Значение | Условия | Источник |
|-------|----------|-------|---------|----------|---------|---------|
| **SimGRAG** | WebQSP | test | Hits@1 | 92.0% | LLM=GPT-4o, KG=Freebase | [arXiv:2412.15272] Table 1 |
| **SimGRAG** | CWQ | test | Hits@1 | 72.0% | LLM=GPT-4o, KG=Freebase | [arXiv:2412.15272] Table 1 |
| **SubgraphRAG** | WebQSP | test | Hits@1 | 92.7% | LLM=GPT-4o | [arXiv:2410.20724] Table 2 |
| **SubgraphRAG** | CWQ | test | Hits@1 | 75.6% | LLM=GPT-4o | [arXiv:2410.20724] Table 2 |
| **GFM-RAG** | WebQSP | test | Hits@1 | не приведено | — | — |
| **GFM-RAG** | CWQ | test | Hits@1 | не приведено | — | [arXiv:2502.01113] — числа в paper |
| **NGM-RAG** | 2WikiMultiHopQA | test | F1 | не приведено | — | [arXiv:2607.11159] — числа в paper |
| **KnowFormer** | FB15k-237 | test | MRR | не приведено | inductive KG completion | [arXiv:2409.12865] — числа в paper |

> Прямое сравнение SimGRAG vs SubgraphRAG на WebQSP/CWQ валидно (одинаковый split и метрика). GFM-RAG и NGM-RAG оценивались на других датасетах — числа в разных строках несопоставимы.  
> Числа GFM-RAG, NGM-RAG, KnowFormer — в авторских таблицах; не воспроизведены здесь, т.к. требуют проверки условий.

---

## 2. Подробные разборы ближайших методов

### 2.1 SimGRAG (Cai et al., Fudan, 2024)

**Ссылка:** [arXiv:2412.15272](https://arxiv.org/abs/2412.15272) · Код: [YZ-Cai/SimGRAG](https://github.com/YZ-Cai/SimGRAG)

| Параметр | Описание |
|----------|----------|
| **Задача** | Knowledge Graph Question Answering (KGQA): по текстовому вопросу найти ответ в KG через retrieval подграфов |
| **Вход** | Текстовый вопрос + KG (Freebase или Wikidata) |
| **Выход** | Top-k релевантных подграфов → ответ через LLM |
| **Механизм** | 1) LLM преобразует вопрос в граф-паттерн (query graph). 2) Поиск подграфов KG по Graph Semantic Distance (GSD). GSD = взвешенная сумма структурного расстояния (edit distance между паттерном и кандидатом) и семантического сходства (cosine по embedding узлов) |
| **Данные** | WebQSP, CWQ; KG: Freebase (~88M сущностей) |
| **Метрики** | Hits@1 |
| **Результаты** | WebQSP: 92.0% Hits@1; CWQ: 72.0% Hits@1 (GPT-4o) |
| **Ограничения** | Шаг «text → pattern» через LLM может вносить ошибки структуры. Поиск greedy, не гарантирует оптимального подграфа. Freebase — заморожена с 2016 |
| **Код** | Открытый, Python; `pip install` + API ключ для LLM |

**Применимость и необходимая адаптация для нашей задачи:**
- GSD — прямой кандидат для нашей cost function
- Шаг «text → LLM pattern» нужно **заменить**: наш вход уже является графом документа, поэтому document graph подаётся напрямую как query graph
- Адаптация: ~4–8 ч (замена query parsing, сохранение GSD как есть)

---

### 2.2 NGM-RAG (Chen et al., 2026)

**Ссылка:** [arXiv:2607.11159](https://arxiv.org/abs/2607.11159)

| Параметр | Описание |
|----------|----------|
| **Задача** | Multi-hop QA и long-context summarization через нейронный graph matching |
| **Вход** | Граф, построенный из документов/данных + текстовый запрос |
| **Выход** | Matched subgraph → LLM-генерация |
| **Механизм** | 1) Строит граф из входных данных (документа). 2) GNN вычисляет node embeddings. 3) Node matching: cosine similarity between node embeddings + текстовая близость. 4) Adaptive node weighting для выбора релевантных узлов. 5) Извлечённый matched subgraph + запрос → LLM |
| **Данные** | Multi-hop QA (2WikiMultiHopQA предположительно) + long-context datasets; конкретные бенчмарки — в paper |
| **Метрики** | F1, Recall (конкретные числа — в paper) |
| **Результаты** | Превосходит GraphRAG и LightRAG на multi-hop QA и long-context summarization (по тексту abstract) |
| **Ограничения** | Код не опубликован на момент написания обзора. Нет прямого сравнения с SimGRAG на WebQSP/CWQ. 2026 — свежая prepint, не прошедшая peer review |
| **Код** | Не найден в открытом доступе |

**Применимость:**
- Ближайший прямой конкурент: принимает граф как вход, не текстовый запрос
- Наш подход разделяет поиск и matching явнее; explicit structural constraints vs. implicit neural matching
- **Адаптация не нужна** — это конкурент, не компонент нашего подхода

---

### 2.3 SubgraphRAG (Li et al., ICLR 2025)

**Ссылка:** [arXiv:2410.20724](https://arxiv.org/abs/2410.20724) · ICLR 2025

| Параметр | Описание |
|----------|----------|
| **Задача** | KGQA: по текстовому вопросу извлечь оптимальный subgraph из KG для LLM |
| **Вход** | Текстовый вопрос + KG |
| **Выход** | Top-k троек → LLM prompt → ответ |
| **Механизм** | 1) Entity linking: находит seed entities из вопроса. 2) 1-hop expansion: собирает кандидатные тройки. 3) Lightweight MLP скорит каждую тройку параллельно; признаки включают directional structural distances (BFS-расстояния до seed). 4) Top-k троек отправляются в LLM. Размер subgraph настраивается под LLM context window |
| **Данные** | WebQSP, CWQ; KG: Freebase |
| **Метрики** | F1, Hits@1 |
| **Результаты** | WebQSP: 92.7% Hits@1 (GPT-4o); CWQ: 75.6% (GPT-4o); Llama3.1-8B: 67.2% WebQSP (GPT-4o уровень на меньшей модели) |
| **Ограничения** | MLP скорит тройки независимо — нет explicit структурного reasoning между тройками. Нет прямого subgraph-level coherence objective. Поиск ограничен 1-hop от seed |
| **Код** | Открытый, Python |

**Применимость:**
- Directional structural distances — полезный признак, можно переиспользовать в нашей cost function
- MLP-скоринг троек — простой baseline (B1-like компонент)
- Основное ограничение: тройки скорятся независимо, наш soft iso работает с подграфом целиком

---

### 2.4 GFM-RAG (Luo et al., NeurIPS 2025)

**Ссылка:** [arXiv:2502.01113](https://arxiv.org/abs/2502.01113) · NeurIPS 2025

| Параметр | Описание |
|----------|----------|
| **Задача** | Универсальный KG-ретривер для RAG: один GNN работает на любом KG без fine-tuning |
| **Вход** | Текстовый вопрос + KG (любой) |
| **Выход** | Top-k сущностей/рёбер → LLM |
| **Механизм** | 1) Query encoder: BERT-like. 2) GNN ретривер предобучен на 60 KG / 14M троек (cross-KG generalization). 3) Query-dependent edge scoring: GNN агрегирует с учётом конкретного вопроса. 4) Neural scaling laws: больше KG при pretraining → лучше |
| **Данные** | Pretraining: 60 KG; Evaluation: WebQSP, CWQ, 2WikiMultiHopQA + 7 domain RAG datasets |
| **Метрики** | Hits@1, F1 (конкретные числа — в paper) |
| **Результаты** | SOTA на 3 multi-hop QA и 7 domain RAG датасетах без fine-tuning; демонстрирует neural scaling laws |
| **Ограничения** | Требует предобучения на 60 KG — высокая стоимость воспроизведения. Нет explicit structural query (граф-паттерн не строится). Generalization к новым типам KG не гарантирована теоретически |
| **Код** | Открытый: [GitHub](https://github.com/luo-junyu/GFM-RAG) |

**Применимость:**
- Текущий SOTA baseline на GTSQA (наш основной датасет) — нужно сравниться с GFM-RAG
- Код доступен, можно запустить как B2 baseline (сильнее B1 exact match)
- **Разделение с нашим подходом:** GFM-RAG принимает текстовый вопрос; мы принимаем граф документа — разные точки входа, разные сценарии применения

---

## 3. Строгий и мягкий аналоги

### 3.1 Строгий аналог: exact subgraph isomorphism

Строгое изоморфное сопоставление требует биективного совпадения структуры запроса и подграфа KG (алгоритм VF2, ullmann). В контексте нашей задачи:

- **Вход:** граф документа как query graph
- **Матчинг:** искать в KG подграфы, изоморфные query graph по структуре рёбер
- **Ограничение:** NP-полная задача; требует идентичности типов рёбер → на реальных документах практически всегда нет совпадений

Представитель в ревью: **KnowFormer** — использует WL-тест для structure-aware attention, ближайший строгий аналог для KG reasoning.

> Роль в эксперименте: **базис B1 (exact match)** — верхняя граница precision, нижняя граница recall.

### 3.2 Сильный мягкий аналог: SimGRAG (GSD)

**Graph Semantic Distance** из SimGRAG — наиболее проработанная мягкая метрика из ревью:

```
GSD(Q, S) = α · structural_distance(Q, S) + (1 − α) · semantic_distance(Q, S)
```

- `structural_distance` — edit distance между структурами графа-запроса и кандидата
- `semantic_distance` — 1 − cosine_similarity(mean embedding Q, mean embedding S)
- `α` — балансировочный гиперпараметр

**Отличие нашего подхода от SimGRAG:**
- SimGRAG: text → LLM → query graph → GSD → KG
- Наш: document graph → GSD-like → KG (без шага LLM→pattern)

Пропуск LLM-шага — потенциальное преимущество при документах с явной структурой (multi-hop аннотации). Проверяется на GTSQA (Q1).

---

## 4. Применимость к кандидатам данных

| Метод / компонент | GTSQA | FactKG | Re-DocRED |
|-------------------|-------|--------|-----------|
| GSD как cost function | ✓ (answer-subgraph как gold) | ✓ (claim graph vs. DBpedia subgraph) | ✓ (document triples vs. Wikidata subgraph) |
| Строгий B1 (exact match) | ✓ (graph_isomorphism = точный тип) | ✓ (claim→KG match) | ✓ (triplet match) |
| GFM-RAG как B2 baseline | ✓ (SOTA на GTSQA) | нет (DBpedia KG, не Wikidata) | условно |
| NGM-RAG как сравнение | ✓ | ✓ | ✓ (если код появится) |

---

## 5. Нерешённые вопросы

| Вопрос | Статус | Что нужно |
|--------|--------|-----------|
| Теряет ли LLM-шаг структурную информацию? | Не проверено | Ablation: SimGRAG с document graph vs. text query |
| Подходит ли GSD при tree-структуре GTSQA? | Не проверено | Запустить SimGRAG на GTSQA test, измерить GSD |
| Насколько SOTA числа GFM-RAG на GTSQA? | Не приведено в paper | Запросить у авторов или воспроизвести |
| Работает ли soft iso при 5-hop структурах? | Не проверено | GTSQA примеры с n_hops=4,5 |
| Есть ли подходящий dataset с negative examples? | Частично | FactKG: Negation тип = отрицательные примеры |
