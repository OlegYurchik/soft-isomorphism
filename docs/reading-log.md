# Журнал чтения

Формат: ссылка · год · вопрос · метод · результат · связь с работой · оценка.  
Колонка **«Вопрос»** — что хотел узнать до чтения, заполняется вручную.

| Ссылка | Год | Вопрос | Метод | Результат | Связь с работой | Оценка |
|--------|-----|--------|-------|-----------|-----------------|--------|
| [Edge et al. GraphRAG](https://arxiv.org/abs/2404.16130) | 2024 | | Граф сущностей/отношений → communities → summaries → query-focused ответ | Превосходит классический RAG на глобальных вопросах по корпусу | Задаёт контекст: зачем нужна графовая структура, почему классического RAG недостаточно | |
| [Cai et al. SimGRAG](https://aclanthology.org/2025.findings-acl.163/) | 2025 | KGQA/fact verification retrieval | LLM text→pattern; GSD ranks structurally corresponding subgraphs using node/relation embeddings | MetaQA, PQ, WC2014, FactKG; WebQSP-WD additionally in appendix | Strong related work; official README commands for MetaQA and FactKG, but no local run |
| [Liu et al. KnowFormer](https://arxiv.org/abs/2409.12865) | 2024 | KG reasoning/completion | Transformer with message passing and structure-aware attention | KG reasoning benchmarks | Related work; not an exact subgraph-isomorphism baseline |
| [Chen et al. PolyRAG](https://arxiv.org/abs/2407.21276) | 2025 | | Каскадный retrieval: онтология → KG → raw text | +395% F1 vs GPT-4 baseline; outperforms 19 SOTA на academic и financial QA | Перспектива многоуровневой организации знаний; косвенно связана с задачей | |
| [Li et al. SubgraphRAG](https://arxiv.org/abs/2410.20724) | ICLR 2025 | | Lightweight MLP скорит тройки параллельно; encodes directional structural distances; subgraph size tunable | GPT-4o достигает SOTA на WebQSP и CWQ без fine-tuning; Llama3.1-8B конкурентоспособен | SOTA на тех же бенчмарках что SimGRAG; показывает, что простой скоринг троек эффективен | |
| [Chen et al. NGM-RAG](https://arxiv.org/abs/2607.11159) | 2026 | Multi-hop and long-context QA | LLM builds query/target graphs; Levenshtein + BM25 + BGE + LightGCN/GINE node representations with weighted scoring | HotpotQA and MultiHop-RAG (500 questions each, EM/F1); UltraDomain (pairwise LLM-as-judge) | Related work; not a baseline on GTSQA/FactKG. Full code/pipeline not found |
| [Zhang et al. Graph RAG Survey](https://arxiv.org/abs/2501.13958) | 2025 (v3: сен 2025) | | Систематический обзор: graph indexing → graph retrieval → structure-aware generation | Охватывает методы, домены, открытые проблемы; поддерживается Awesome-GraphRAG репо | Закрывает knowledge gap: даёт картину существующих подходов и место SimGRAG/NGM-RAG в ней | |
