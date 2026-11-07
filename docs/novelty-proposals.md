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

## Три проверяемых варианта

| Вариант | Изменение | Главный контроль | Критерий поддержки | Когда снимаем claim |
|---|---|---|---|---|
| **E1 — agreement-weighted soft matching** | Вес ребра равен согласованности трёх extraction views | B3: те же Q/pool/reader, все веса = 1 | Нижняя граница 95% CI для E1−B3 по Accuracy выше 0 | E1 не лучше B3, либо найден идентичный опубликованный pipeline |
| **E2 — calibrated agreement** | Agreement калибруется по train/dev error audit, а не используется напрямую | E1 с сырыми весами и B3 | Улучшение E2 на заранее заданном dev slice без падения coverage | Калибровка требует gold leakage или не улучшает E1 |
| **E3 — hop-aware penalty** | Вес структурного штрафа зависит от расстояния ребра до корня | B3 и E1 на тех же графах | Улучшение отдельно на Multi-hop при фиксированном общем Accuracy protocol | Нет стабильного эффекта по hop-группам |

Рекомендация для первого запуска — E1: он минимально меняет pipeline и допускает чистое
парное сравнение. E2 и E3 остаются расширениями, которые нельзя выбирать после просмотра
test-результатов. Во всех вариантах novelty означает проверяемую гипотезу для document→KG
verification; общая идея soft matching, learned cost или partial mapping уже известна.
