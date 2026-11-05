# E1: согласованность extraction как вес структурных ограничений

Тема подтверждена: мягкое сопоставление графа документа с KG. Основной benchmark FactKG,
дополнительный HotpotQA. Это заменяет предыдущий вариант «partial matching + dropout».

**Вопрос:** помогает ли agreement трёх фиксированных extraction prompts взвешивать
рёбра графа короткого документа при поиске KG evidence лучше одинаковых весов?
Метод допускает неполное структурное соответствие; дополнительным KG-рёбрам штраф не начисляется.
Главное сравнение — E1 vs B3 (тот же soft matcher, все веса=1), а не только E1 vs VF2/BM25.

Конкретная формула, beam search, candidate generation, prompts, пример реального claim,
метрики, split IDs и блок-схемы находятся в единственном нормативном документе:
[полный дизайн E1](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/docs/experiment-design-v2.md).

**Гипотеза:** E1 повышает FactKG Accuracy относительно B3 при одинаковых cached Q,
candidate pools, reader и evidence budget. Paired 95% bootstrap CI для разницы должен
иметь нижнюю границу выше нуля. UNKNOWN и failures считаются ошибками, сохраняются в denominator.

Noise experiments — дополнительная диагностика: deletion/insertion/substitution/reversal
раздельно, p=0/0.1/0.25/0.5, seeds=17/42/73. Удаление query edge может облегчать
non-induced matching, поэтому исходное обещание неизбежной деградации VF2 снято.
Новые веса не кодируют известную экспериментатору метку corruption. Переставленные c — обязательный ablation.

**Научный статус:** NeMa, noisy subgraph matching и learned GED costs уже существуют.
Agreement-weighted document matching — кандидат на прикладной/эмпирический вклад;
его мировая новизна не установлена. Обзор и границы утверждений:
[сравнение работ](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-8-methods-review/docs/literature-review.md).
Если аналогичная постановка найдена или E1 не лучше B3, заявление об улучшении снимается.
Это соответствует разрешённому руководителем варианту: проработанный обзор и обсуждаемый эксперимент,
без выдуманного доказательства новизны.

Baseline claim-only уже запущен на FactKG dev. Графовый эксперимент и репликации SimGRAG/NGM-RAG не выполнены.
