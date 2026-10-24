# Журнал чтения

Формат: ссылка · год · вопрос · метод · результат · связь с работой · оценка.  
Колонка **«Вопрос»** — что хотел узнать до чтения, заполняется вручную.

| Ссылка | Год | Вопрос | Метод | Результат | Связь с работой | Оценка |
|--------|-----|--------|-------|-----------|-----------------|--------|
| [Edge et al. GraphRAG](https://arxiv.org/abs/2404.16130) | 2024 | | Граф сущностей/отношений → communities → summaries → query-focused ответ | Превосходит классический RAG на глобальных вопросах по корпусу | Задаёт контекст: зачем нужна графовая структура, почему классического RAG недостаточно | |
| [Cai et al. SimGRAG](https://arxiv.org/abs/2412.15272) | 2024 | | Текстовый запрос → граф-паттерн (LLM) → поиск подграфов по GSD | GSD позволяет комбинировать структурное и семантическое сходство при поиске в KG | Ближайший аналог; наш подход заменяет текстовый запрос на граф документа | |
| [Liu et al. KnowFormer](https://arxiv.org/abs/2409.12865) | 2024 | | Transformer с message-passing для reasoning над KG; structure-aware attention | Превосходит path-based методы на transductive и inductive бенчмарках | Формализация graph isomorphism через биекцию + WL-тест — теоретическая база | |
| [Chen et al. PolyRAG](https://arxiv.org/abs/2407.21276) | 2025 | | Каскадный retrieval: онтология → KG → raw text | +395% F1 vs GPT-4 baseline; outperforms 19 SOTA на academic и financial QA | Перспектива многоуровневой организации знаний; косвенно связана с задачей | |
| [Li et al. SubgraphRAG](https://arxiv.org/abs/2410.20724) | ICLR 2025 | | Lightweight MLP скорит тройки параллельно; encodes directional structural distances; subgraph size tunable | GPT-4o достигает SOTA на WebQSP и CWQ без fine-tuning; Llama3.1-8B конкурентоспособен | SOTA на тех же бенчмарках что SimGRAG; показывает, что простой скоринг троек эффективен | |
| [Chen et al. NGM-RAG](https://arxiv.org/abs/2607.11159) | 2026 | | Граф из данных → нейронный graph matching (GNN + text) → adaptive node weighting → генерация | Превосходит GraphRAG и LightRAG на multi-hop QA и long-context summarization | Прямой конкурент: тот же класс задач (graph matching + RAG); входная точка — граф, не текст | |
| [Zhang et al. Graph RAG Survey](https://arxiv.org/abs/2501.13958) | 2025 (v3: сен 2025) | | Систематический обзор: graph indexing → graph retrieval → structure-aware generation | Охватывает методы, домены, открытые проблемы; поддерживается Awesome-GraphRAG репо | Закрывает knowledge gap: даёт картину существующих подходов и место SimGRAG/NGM-RAG в ней | |
