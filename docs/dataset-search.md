# Поиск данных: итог проверки 05.11.2026

Проверены кандидаты руководителя: HotpotQA, MetaQA, PQ, WC2014, FactKG. Выбраны FactKG (короткий документ→DBpedia, общий с SimGRAG) и HotpotQA distractor (перенос в QA, общий с NGM-RAG).



- [FactKG README](https://github.com/jiho283/FactKG): CC BY-NC-SA 4.0; файл KG light скачивать из авторского ресурса.
- [HotpotQA README](https://github.com/hotpotqa/hotpot): CC BY-SA 4.0 для данных, Apache 2.0 для кода.
- [MetaQA](https://github.com/yuyuz/MetaQA): официальный download и формат KG/QA.
- [SimGRAG appendix](https://aclanthology.org/2025.findings-acl.163.pdf): MetaQA/PQ/WC2014/FactKG и их роль в экспериментах.
- [Re-DocRED](https://github.com/tonytan48/Re-DocRED): проверен data/dev_revised.json, а не только abstract.


## Дополнительный аудит

Скачаны HotpotQA validation и Re-DocRED dev. В последнем проверены все 500 записей: entity QID отсутствуют, поэтому готового document→Wikidata benchmark из него не получается. GTSQA уже есть локально, но его query — вопрос.

MetaQA/PQ/WC2014 компактнее/проще для KGQA, но не обеспечивают документальный вход. FactKG требует отдельной загрузки авторского DBpedia light; его нельзя подменить графом из gold Evidence.

[Итоговый выбор #5](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-5-comparison-table/docs/dataset-selection.md)

## Воспроизводимый журнал поиска

Поиск проводился 29.10–05.11.2026. Использовались первичные страницы публикаций,
официальные репозитории и страницы загрузки данных.

| Направление запроса | Проверенные источники | Результат |
|---|---|---|
| approximate/subgraph matching | arXiv, publisher pages, Semantic Scholar | NeMa, noisy GED, SimGRAG |
| document-level relation extraction | ACL Anthology, GitHub | Re-DocRED, FactKG |
| KG fact verification | FactKG repository, ACL Anthology | FactKG; verdict есть, Evidence отсутствует в test |
| graph retrieval / QA | SimGRAG и NGM-RAG papers/README | MetaQA, PQ, WC2014, HotpotQA |
| ground-truth answer subgraphs | Hugging Face, GTSQA repository | GTSQA; входом является вопрос |

Разные версии одного корпуса не считались разными наборами. MetaQA, PQ, WC2014 и
GTSQA оставлены резервом из-за QA-входа; Re-DocRED исключён после проверки отсутствия
глобальных entity QID. FactKG требует отдельного DBpedia light, а HotpotQA — построения
corpus-derived KG. Итоговый выбор FactKG + HotpotQA сделан по требованиям постановки,
до запуска предлагаемого метода.
