# Сравнение методов и границы предполагаемого вклада

Направление подтверждено: мягкое сопоставление графа документа с KG. Рабочий первый
benchmark — FactKG (документ = короткий claim), второй — HotpotQA distractor (QA transfer).
Длинные документы этим дизайном не покрыты. Таблица ниже фиксирует механизмы, а не наше превосходство.

| Работа | Вход, выход и механизм | Как учитывает структуру/ошибки | Связь с E1 |
|---|---|---|---|
| [SimGRAG, §4.2](https://aclanthology.org/2025.findings-acl.163.pdf) | LLM query→pattern; GSD ранжирует KG-subgraphs; затем QA/verification | GSD определён на изоморфном соответствии, суммирует embedding distances узлов/отношений. В статье structural stage игнорирует направления | Основной референс, общий FactKG. Сравниваем устойчивость при несогласованном extracted pattern. Наш directed hard control B2 не равен авторскому SimGRAG |
| [NGM-RAG, §§4–5](https://arxiv.org/pdf/2607.11159) | Query/corpus graphs; Levenshtein+BM25+GNN node scores; reader | LightGCN/GINE и взвешивание сигналов, не полный exact isomorphism | Related work и общий HotpotQA. Его 500 distractor questions неизвестны нам по IDs; published EM/F1 не контрольная группа |
| [NeMa, §§3–6](https://sites.cs.ucsb.edu/~xyan/papers/vldb13_nema.pdf) | Query graph→top-k target matches; labels + neighbourhood cost | Approximate structure, шум labels/edges, heuristic inference | Показывает, что noisy soft matching уже известен. Нельзя объявлять partial matching или corruption experiment новой идеей |
| [Automatic learning of cost functions for graph edit distance](https://www.sciencedirect.com/science/article/pii/S0020025506000569) | Вероятностная модель graph edits, оценка стоимости через обучение | Стоимость правок не обязана быть фиксированной | Даже адаптивные edit costs сами по себе не новизна. Нужен узкий эксперимент про согласованность document extraction |
| [Noisy semantic-property graph matching](https://www.pnnl.gov/publications/using-graph-edit-distance-noisy-subgraph-matching-semantic-property-graphs) | Template/submission graphs, стоимость structural/attribute edits | GED используется для оценки noisy subgraph matches | Дополнительный ближайший класс, который отсутствовал в прежнем обзоре |
| [SubgraphRAG](https://arxiv.org/abs/2410.20724), [GFM-RAG](https://arxiv.org/abs/2502.01113) | Learned retrieval KG evidence для вопросов | Используют структуру; наличие графа не отличает наш метод | Контекст retrieval; не включены в обязательные воспроизведения первого CPU/одна модель эксперимента |

## Что можно защищать как исследовательский вопрос

При одинаковых extracted graphs, candidate pools и reader помогает ли **согласованность
трёх extraction prompts** взвешивать структурные ограничения лучше одинаковых весов,
если требуется проверить короткий документ по внешнему KG?

Различие с SimGRAG: допускаем неподдержанные query edges, сохраняя штраф, вместо требования
полного структурного соответствия. Различие внутри собственного эксперимента:
E1 отличается от B3 только весами извлечённых рёбер. Последнее является главным causal contrast.
Agreement не означает истинность; модель может повторить ошибку. Проверяем также shuffled weights.

Это **кандидат на эмпирический вклад**, не доказанная мировая новизна. Прочитанные работы
не устанавливают, что данный частный pipeline отсутствует во всей литературе. Если найдётся
такой же подход, либо E1 не выигрывает у B3, формулировка вклада пересматривается.
Нельзя подменять этот вопрос утверждением «soft matching ещё никто не делал».

## Корректность сравнения

- Общий benchmark с SimGRAG: FactKG, Accuracy. Но наш первый test subset=500, модель и
  budget другие: нельзя помещать его число рядом с paper accuracy как head-to-head.
- Первое гарантированное сравнение: B1/B2/B3/E1 на одних IDs, одном KG, extractor,
  candidate pool, reader и evaluator. B0 claim-only — отдельный дешёвый supervised контроль.
- Компонентный hard control B2 подписывается своим именем; полного авторского SimGRAG пока нет.
- Для системного сравнения разные системы могут иметь собственные extractor/reader;
  необходимо одинаковое право доступа к данным и единый evaluator, а различия моделей/затрат
  раскрываются. Нельзя требовать идентичную архитектуру и одновременно называть результат
  воспроизведением каждого оригинального метода.
- NGM-RAG остаётся related work до воспроизведения. HotpotQA добавлен по рекомендации
  руководителя, но наличие датасета не является воспроизведением работы.

Точный алгоритм и все параметры:
[дизайн E1 в ветке задачи #7](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/docs/experiment-design-v2.md).

## Подробные разборы для обсуждения

**SimGRAG.** Query text преобразуется LLM в pattern, затем GSD ранжирует candidate
subgraphs по близости узлов и отношений. Работа релевантна из-за FactKG, но опубликованный
pipeline, модель, sample IDs и KG snapshot не совпадают автоматически с нашим пилотом.
Поэтому B2 называется hard topology control, а не репликацией SimGRAG. Проверяемое отличие
E1 — сохранение штрафа за отсутствующую связь вместо требования полного соответствия.

**NGM-RAG.** Система строит query/corpus graphs, сочетает lexical и embedding scores
и использует GNN representations перед reader. HotpotQA делает её релевантной для QA-transfer,
но неизвестны точные 500 IDs и локальный pipeline не подтверждён. Published EM/F1 нельзя
использовать как численный baseline без воспроизведения; в первом запуске это related work.

**NeMa.** Approximate matching оценивает label и neighbourhood compatibility и допускает
шум в графах. Это прямое основание снять общую идею partial/noisy matching с novelty claim.
В нашем пилоте NeMa служит теоретическим аналогом стоимости; мы не называем E1 новой
задачей, пока не проверим agreement-weighting как отдельный эмпирический фактор.

**SubgraphRAG/GFM-RAG.** Обе работы показывают, что структурированный retrieval может
улучшать KGQA, но используют собственные learned retrievers и задачи вопросов. Они нужны
для контекста graph retrieval, а не для обязательной CPU-репликации на FactKG claims.

Для каждого метода при будущей адаптации нужно отдельно записать: источник кода,
единицу входа, генератор кандидатов, функцию стоимости, solver, reader, benchmark,
метрики и изменения интерфейса. Результат адаптации нельзя называть авторским запуском.
