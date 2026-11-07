# Методы первого эксперимента: единые имена

| ID | Метод | Выход | Роль |
|---|---|---|---|
| B0 | Claim-only BM25 top-5 train neighbors + majority vote | FactKG verdict | Быстрый supervised контроль; реализован и запущен |
| B1 | BM25 candidate KG triples, budget 20 | Evidence → общий reader → verdict | Контроль без структурного score |
| B2 | Hard topology + lexical label cost, bounded search | Evidence → общий reader → verdict | Контроль полного структурного соответствия; **не** SimGRAG и **не** авторская реализация VF2 |
| B3 | Soft constraints, одинаковые веса рёбер | Evidence → общий reader → verdict | Главный научный контроль |
| E1 | Тот же B3, веса по agreement трёх extractor prompts | Evidence → общий reader → verdict | Проверяемая гипотеза |

Все B1/B2/B3/E1 получают одинаковые Q, KG и candidate pool. Primary metric — Accuracy;
macro-F1, coverage, time вторичны. Для B0 используются train labels; различие supervision
от graph arms явно указывается. Выигрыш E1 над B0 не является доказательством новизны.
SimGRAG — референс на FactKG, отдельное system reproduction пока не выполнено.
NGM-RAG — related work, общего HotpotQA недостаточно для paper-score сравнения.

Алгоритмы и диаграммы: [нормативный протокол](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/docs/experiment-design-v2.md).
Старые обозначения B2=SimGRAG или B2=proposed отменены.
