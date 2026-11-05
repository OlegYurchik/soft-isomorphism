# Обзор методов: graph retrieval и matching

> Обновлено после замечаний руководителя 05.11.2026. НИР пока рассматривается в рамках темы 2.6; возможность возврата к прежней теме алгоритмов изоморфизма/обновления графа требует отдельного согласования. Числа ниже — результаты авторов, не наши запуски.

## Сравнение работ

| Работа | Вход и задача | Механизм | Бенчмарки / метрики | Код и применимость |
|---|---|---|---|---|
| **SimGRAG** ([ACL 2025](https://aclanthology.org/2025.findings-acl.163.pdf), [код](https://github.com/YZ-Cai/SimGRAG)) | Текстовый запрос → retrieval подграфа KG → ответ/верификация | LLM строит graph pattern; семантический поиск формирует кандидатов; Graph Semantic Distance сравнивает соответствующие узлы и отношения через embeddings с учётом структуры | MetaQA (Hits@1: 98.0/98.4/97.8 для 1/2/3-hop), PathQuestions (88.7/78.6 для 2/3-hop), WC2014 (98.1), FactKG (accuracy 86.8). Дополнительно WebQSP-WD в приложении | Репозиторий содержит команды для MetaQA и FactKG; исходная конфигурация использует Ollama/Llama 3 70B, Nomic embeddings, Milvus. Не считать текстовый→pattern pipeline «безграфовым» |
| **NGM-RAG** ([arXiv 2607.11159](https://arxiv.org/html/2607.11159)) | Multi-hop QA / long-context QA; граф вопроса сопоставляется с графом корпуса | LLM строит query/target graphs; узловые признаки и соответствия используют Levenshtein, BM25, BGE и LightGCN/GINE representations; взвешенный score выбирает evidence | HotpotQA и MultiHop-RAG (по 500 вопросов, EM/F1); UltraDomain Agriculture/Mix (pairwise LLM-as-judge) | Официальный код в статье не указан и при проверке не найден. GTSQA/FactKG не являются его benchmark. Реализация одной GNN не воспроизводит полный метод |
| **SubgraphRAG** ([ICLR 2025](https://arxiv.org/abs/2410.20724)) | Текстовый вопрос → KG evidence | Entity linking, 1-hop expansion, MLP scoring троек с directional structural features | WebQSP/CWQ, KGQA метрики | Related method; результаты допустимо сопоставлять только на общем benchmark и протоколе |
| **GFM-RAG** ([NeurIPS 2025](https://arxiv.org/abs/2502.01113)) | Текстовый запрос → универсальный KG retrieval | Предобученный GNN retriever, query-dependent edge scoring | Собственные KGQA и domain-RAG наборы статьи | Сильная related work; это не exact matching algorithm |
| **KnowFormer** ([arXiv 2409.12865](https://arxiv.org/abs/2409.12865)) | KG reasoning / completion | Transformer с message passing и structure-aware attention | KG completion/reasoning benchmarks | Не использовать как baseline точного подграфового изоморфизма |
| **VF2 / NetworkX** | Заданный query graph → точное структурное совпадение | Exact subgraph isomorphism при заданной схеме candidate generation | Метрики того же retrieval benchmark | Алгоритмический B1, не научная работа-конкурент |

## Что можно и нельзя заключить

SimGRAG и NGM-RAG оба используют графовую структуру, но различаются точкой входа и задачей. SimGRAG строит pattern из текста и сопоставляет с KG; NGM-RAG строит query/target graphs из вопроса и корпуса, затем применяет нейронное matching. Следовательно, сам факт «мы используем граф» не является knowledge gap.

Потенциальная гипотеза, требующая проверки по approximate subgraph matching/graph edit distance работам: **частичное отображение с раздельными штрафами за пропущенные и лишние рёбра может быть устойчивее exact matching при контролируемой неполноте query graph**. Это пока не подтверждённая новизна.

## Бенчмарки и корректность сравнения

- Пересечение SimGRAG и NGM-RAG в основных таблицах не установлено: MetaQA/PQ/WC2014/FactKG против HotpotQA/MultiHop-RAG/UltraDomain.
- MetaQA — возможная площадка сравнения с SimGRAG. HotpotQA — площадка, использованная NGM-RAG, но прямое сравнение с NGM-RAG возможно лишь при воспроизводимой реализации и совпадающем pipeline.
- Нельзя сопоставлять числа из разных датасетов, разных split, разных генераторов графов или метрик.
- Наличие answer-subgraph в GTSQA само по себе не означает наличие независимого query graph: подстановка gold answer-subgraph на вход matching создаёт утечку.
- Мы пока не проводили собственных запусков и не воспроизводили результаты перечисленных работ.

## Источники

- SimGRAG: https://aclanthology.org/2025.findings-acl.163/ и https://github.com/YZ-Cai/SimGRAG
- NGM-RAG: https://arxiv.org/html/2607.11159
- SubgraphRAG: https://arxiv.org/abs/2410.20724
- GFM-RAG: https://arxiv.org/abs/2502.01113
- KnowFormer: https://arxiv.org/abs/2409.12865
