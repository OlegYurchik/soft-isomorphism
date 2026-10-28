# Поиск датасетов и бенчмарков

> Дата поиска: 2026-10-29  
> Контекст: задача О4; требования — из [О3](data-requirements.md).

---

## 1. Журнал поиска

| # | Запрос | Площадка | Результат |
|---|--------|----------|-----------|
| 1 | `knowledge graph fact verification benchmark dataset 2025 arXiv` | WebSearch (extended) | FactNet-Bench, KGQAGen-10k, ClaimPKG |
| 2 | `multi-hop knowledge graph question answering benchmark dataset 2025 arXiv new` | WebSearch (extended) | GTSQA, CR-LT-KGQA, ссылки на старые WebQSP/2WikiMultiHopQA |
| 3 | `document graph to knowledge graph matching subgraph retrieval benchmark 2025` | WebSearch (extended) | GTSQA, Pitfalls paper, MKG-RAG-Bench |
| 4 | `ground-truth subgraphs training evaluation knowledge graph augmented LLMs arXiv 2511.04473` | WebSearch | GTSQA (полное описание) |
| 5 | `KG-RAG benchmark pitfalls diagnosing reliable evaluation 2025 arXiv 2505.23495` | WebSearch | KGQAGen-10k (полное описание) |
| 6 | `FactNet billion-scale knowledge graph multilingual factual grounding benchmark arXiv 2602.03417` | WebSearch | FactNet-Bench (полное описание) |
| 7 | `OpenEA DBP2.0 entity alignment knowledge graph dataset paper arXiv` | WebSearch | OpenEA/DBP2.0 — задача entity alignment, не наша |
| 8 | `MuSiQue multistep question answering dataset reasoning 2022 arXiv` | WebSearch | MuSiQue — нет KG-backing, исключён |

---

## 2. Кандидаты

### 2.1 Основные кандидаты

#### GTSQA
- **Работа:** Cattaneo et al., «Ground-Truth Subgraphs for Better Training and Evaluation of Knowledge Graph Augmented LLMs» (NeurIPS 2025)
- **arXiv:** [2511.04473](https://arxiv.org/abs/2511.04473) · **Данные:** [Graphcore/GTSQA](https://huggingface.co/datasets/Graphcore/GTSQA) · **Код:** [graphcore-research/synth-kgqa](https://github.com/graphcore-research/synth-kgqa)
- **Задача:** KGQA с явными ground-truth подграфами; framework SynthKGQA генерирует вопросы из любого KG и сразу фиксирует правильный answer-subgraph.
- **Размер:** 32 099 вопросов, 2 727 уникальных структур подграфов; KG — Wikidata.
- **Разметка:** каждый вопрос снабжён точным answer-subgraph (тройки + структура) → соответствует минимально достаточному уровню для Q1.
- **Соответствие must-have:** ✓ публично доступен (HuggingFace), ✓ Wikidata QIDs (стабильные ID), ✓ явный subgraph-эталон, ✓ независимая верификация.
- **Примечание:** синтетически сгенерирован из Wikidata — document graph нужно строить дополнительно, но ground-truth subgraph уже есть; это упрощает создание эталона.

---

#### KGQAGen-10k
- **Работа:** Zhang et al., «Diagnosing and Addressing Pitfalls in KG-RAG Datasets: Toward More Reliable Benchmarking» (NeurIPS 2025, Datasets & Benchmarks)
- **arXiv:** [2505.23495](https://arxiv.org/abs/2505.23495)
- **Задача:** KGQA-бенчмарк с LLM-верификацией качества; авторы аудировали 16 популярных датасетов (средняя корректность ~57%) и построили более надёжный.
- **Размер:** 10 000 вопросов; KG — Wikidata; символическая верификация ответов.
- **Соответствие must-have:** ✓ Wikidata (стабильные QIDs), ✓ LLM+symbolic верификация, ✓ публичный; нужно проверить разметку на уровне troек (ожидается да).
- **Примечание:** свежий (2025) и сложнее существующих бенчмарков — GPT-4.1 берёт только умеренно.

---

#### FactKG
- **Работа:** Kim et al., «FactKG: Fact Verification via Reasoning on Knowledge Graphs» (ACL 2023)
- **arXiv:** [2305.06590](https://arxiv.org/abs/2305.06590) · **Данные:** [jiho283/FactKG](https://github.com/jiho283/FactKG)
- **Задача:** Верификация утверждений (claims) с опорой на KG; 5 типов reasoning: One-hop, Conjunction, Existence, Multi-hop, Negation.
- **Размер:** 108 674 примера; KG — DBpedia (0.1B троек).
- **Соответствие must-have:** ✓ публично (GitHub), ✓ DBpedia URI, ✓ claim→KG mapping + тройки, ✓ test labels в файле.
- **Примечание:** наиболее близко к задаче Q1 из всех — документ (claim) сопоставляется с подграфом KG, и требуется структурный reasoning.

---

#### FactNet-MFC
- **Работа:** Shen et al., «FactNet: A Billion-Scale Knowledge Graph for Multilingual Factual Grounding» (arXiv 2026)
- **arXiv:** [2602.03417](https://arxiv.org/abs/2602.03417) · **Данные:** [openbmb/factnet](https://huggingface.co/openbmb/factnet) · **Код:** [yl-shen/factnet](https://github.com/yl-shen/factnet)
- **Задача:** Три бенчмарка: KGC, MKQA (multilingual QA), и **MFC** (multilingual fact-checking); 1.7B утверждений + 3.01B указателей на свидетельства из 316 Wikipedia-версий.
- **KG:** Wikidata + Wikimedia; детерминированный pipeline без LLM-генерации.
- **Соответствие must-have:** ✓ HuggingFace (открыто), ✓ Wikidata QIDs, ✓ claim→evidence mapping; нужно проверить уровень разметки (tройки vs. только text).
- **Примечание:** самый свежий (фев 2026); огромный масштаб может быть избыточен для пилота, но MFC-подмножество может быть компактнее.

---

#### Re-DocRED
- **Работа:** Tan et al., «Revisiting DocRED – Addressing the False Negative Problem in Relation Extraction» (EMNLP 2022)
- **arXiv:** [2205.12696](https://arxiv.org/abs/2205.12696) · **Данные:** [tonytan48/Re-DocRED](https://github.com/tonytan48/Re-DocRED)
- **Задача:** Document-level relation extraction: извлечение троек (субъект, отношение, объект) из многопредложенческих документов с KG-backing (Wikidata).
- **Размер:** 4 053 переразмеченных документа (полный DocRED — 3 053 train + 1 000 dev/test); отношения: 96 типов из Wikidata.
- **Соответствие must-have:** ✓ GitHub (открыто), ✓ Wikidata QIDs, ✓ явные тройки на уровне документа, ✓ публичный тест-эталон.
- **Примечание:** единственный кандидат с реальными документами (не синтетическими вопросами); document graph строится напрямую из аннотированных троек.

---

#### 2WikiMultiHopQA
- **Работа:** Ho et al., «Constructing A Multi-hop QA Dataset for Comprehensive Evaluation of Reasoning Steps» (COLING 2020)
- **arXiv:** [2011.01060](https://arxiv.org/abs/2011.01060)
- **Задача:** Multi-hop QA из Wikipedia + Wikidata; каждый пример содержит явный reasoning path.
- **Размер:** ~167K вопросов (train/dev/test); KG — Wikidata; пути глубиной 2–4.
- **Соответствие must-have:** ✓ публично, ✓ Wikidata QIDs, ✓ reasoning paths = субграфовые цепочки, ✓ публичный эталон.
- **Примечание:** датасет 2020 года, но активно используется как бенчмарк в свежих работах (GFM-RAG, NGM-RAG, SubgraphRAG); reasoning path — прямой аналог document graph.

---

### 2.2 Исключённые кандидаты

| Датасет | Причина исключения |
|---------|-------------------|
| **OpenEA / DBP2.0** (Sun et al., ACL 2021) | Задача entity alignment между двумя KG — нет document graph; нарушает must-have #3 (нет document→KG mapping) |
| **MuSiQue** (Trivedi et al., TACL 2022, arXiv:2108.00573) | Нет KG-backing — только Wikipedia-текст; нельзя построить document→KG subgraph match |
| **WebQSP** (Yih et al., ACL 2016) | Freebase заморожена с 2016; нет SPARQL-endpoint для независимой верификации; нарушает must-have #4 |
| **GrailQA** (Gu et al., WWW 2021) | Та же причина: Freebase; плюс нет document graph, только text questions |
| **MKG-RAG-Bench** (Wang et al., arXiv:2606.26458) | Multimodal focus (изображения + текст); наша задача — text document graphs |
| **DocRED (оригинал)** (Yao et al., ACL 2019, arXiv:1906.06127) | Систематические false negatives; Re-DocRED — исправленная версия того же корпуса, поэтому DocRED-оригинал не нужен отдельно |

---

## 3. Итоговый список для О5

6 кандидатов передаются в [О5](https://github.com/OlegYurchik/soft-isomorphism/issues/5) для сравнительной таблицы:

| Приоритет | Датасет | Год | KG | Тип задачи | Почему интересен |
|-----------|---------|-----|----|------------|-----------------|
| ★★★ | **GTSQA** | NeurIPS 2025 | Wikidata | KGQA + ground-truth subgraphs | Ground-truth subgraph = готовый эталон для Q1 |
| ★★★ | **FactKG** | ACL 2023 | DBpedia | Fact verification | Ближе всего к задаче: claim→KG subgraph matching |
| ★★ | **KGQAGen-10k** | NeurIPS 2025 | Wikidata | KGQA (verified) | Свежий, сложный, symbolic verification |
| ★★ | **Re-DocRED** | EMNLP 2022 | Wikidata | Relation extraction | Реальные документы → тройки → KG; document graph строится напрямую |
| ★★ | **FactNet-MFC** | arXiv 2026 | Wikidata | Fact checking (multilingual) | Свежайший; нужно проверить размер MFC-подмножества |
| ★ | **2WikiMultiHopQA** | COLING 2020 | Wikidata | Multi-hop QA | Стандартный бенчмарк; reasoning paths = document graph proxy |
