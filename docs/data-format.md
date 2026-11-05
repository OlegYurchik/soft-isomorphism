# Контракт данных E1

Нормативный дизайн: [задача #7](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/docs/experiment-design-v2.md).

## Входы runtime

- FactKG `input`: `{id: sha256(claim), text: claim}`. Только текст отправляется extractor.
- HotpotQA `input`: `{id, question, contexts:[{title,sentences}]}`. Все distractor contexts сохраняются.
- `query_graph`: `{nodes:[{id,label}], edges:[{source,relation,target,polarity,quote,agreement}]}`.
  IDs локальные. Agreement = число extraction views / 3 с floor 0.2; не gold confidence.
- `candidate_graph`: реальные triple IDs и labels из внешнего KG (FactKG) или graph extraction
  всех contexts (HotpotQA). Для HotpotQA обязательна provenance `(title,sent_id)`.
- `prediction`: `{id,status,mappings,evidence,verdict,latency,expanded_states}`.
  status включает extraction_error / empty_candidates / budget_exhausted / reader_error.

## Evaluator-only

- FactKG: Label, Entity_set, Evidence, types.
- HotpotQA: answer, supporting_facts.
- Вычисление sample IDs не зависит от этих значений; поля не могут попасть в extraction prompt,
  candidate generation или reader. Oracle Entity_set experiment маркируется отдельным режимом.

FactKG test загружается как claim+label без требования Evidence. Старый `Example.gold_edges`
не подходит для этого режима: наличие edge gold не является обязательным условием verification.
CPU B0 читает raw FactKG через самостоятельный script и не использует legacy adapter.
Старые GTSQA/FactKG edge adapters сохраняются как legacy; они не объявляются готовой реализацией E1.
Новый graph runtime должен реализовать этот контракт; сейчас создан его дизайн, не код.

## Реальные поля

В локальных FactKG train/dev: Label, Entity_set, Evidence, types; в test отсутствует Evidence.
Evidence — entity→relation paths, а не список полностью заданных triples. Склеивание одношаговых
путей может быть неоднозначным и не должно незаметно превращаться в gold graph.
HotpotQA parquet использует id/question/answer/context/supporting_facts/type/level;
context и supporting_facts могут быть struct of lists. Сохранить исходные title/sentence IDs.

Файлы и hashes: [configs/experiment-v2.json](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/configs/experiment-v2.json).
