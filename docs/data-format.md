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
CPU B0 читает raw FactKG через самостоятельный script. Адаптер теперь загружает
канонические `data/factkg_unzip/factkg_{train,dev,test}.pickle` и сохраняет Label,
Evidence, Entity_set и types только в `metadata`. В test `gold_edges=None`, потому что
там нет Evidence; это ожидаемый режим verdict-only. Старый JSON loader оставлен только
для синтетических fixtures. Extractor/matcher не получают evaluator-only поля.

## Реальные поля

В локальных FactKG train/dev: Label, Entity_set, Evidence, types; в test отсутствует Evidence.
Evidence — entity→relation paths, а не список полностью заданных triples. Склеивание одношаговых
путей может быть неоднозначным и не должно незаметно превращаться в gold graph.
HotpotQA parquet использует id/question/answer/context/supporting_facts/type/level;
context и supporting_facts могут быть struct of lists. Сохранить исходные title/sentence IDs.

Файлы и hashes: [configs/experiment-v2.json](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/configs/experiment-v2.json).

## Исполняемый контракт FactKG

`load_factkg_records("data/factkg", Split.DEV)` возвращает две отдельные коллекции с
одинаковыми ID: `FactKGInput(id, text)` для методов и `FactKGEvaluation(id, label,
entity_set, evidence, types)` только для оценщика. ID — SHA256 исходного UTF-8 claim,
совпадает с `configs/splits/factkg-e1.json`. Этот API читает все три pickle и отвергает
неверный формат Label, а также дубли ID. Использовать только доверенные upstream pickle:
формат pickle исполняет код при загрузке. Ранее существовавший `load_factkg` оставлен для
совместимости с legacy тестами; E1 должен вызывать `load_factkg_records`.

Проверка на локальных данных: `PYTHONPATH=src python -c 'from soft_isomorphism.data.adapter import load_factkg_records; from soft_isomorphism.data.schema import Split; print(len(load_factkg_records("data/factkg", Split.DEV)[0]))'`.
Ожидается `13266`. Полная проверка: `make check`.

Команда для осмотра небольшого результата импорта: `PYTHONPATH=src python scripts/inspect_factkg.py data/factkg --split dev`.
Она печатает число записей и **один вход метода** вида
`{"count": 13266, "input": {"id": "<sha256 claim>", "text": "<исходный claim>"}}`,
затем число отдельно сохранённых evaluator records. Значения в угловых скобках здесь
обозначают поля примера, а не буквальный вывод. Команда никогда не печатает gold.
Если upstream файл пуст или поле Label/Entity_set/types/Evidence имеет неожиданную форму,
импорт завершается явной ошибкой.
