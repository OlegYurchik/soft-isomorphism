# Выбор данных для первого эксперимента

Решение от 05.11.2026: **FactKG основной, HotpotQA distractor второй**.
Это замещает прежние пары GTSQA+FactKG и HotpotQA+MetaQA.
FactKG выбран по соответствию короткий документ→внешний KG и пересечению с SimGRAG.
MetaQA дешевле по подготовке KG, но его вход — вопрос, а не документальное утверждение.
Выбор FactKG не означает, что DBpedia легче в обработке: загрузка light snapshot остаётся обязательной.

| Набор | Текст / KG / оценка | Решение |
|---|---|---|
| FactKG | Claims, DBpedia 2015, binary Label; train/dev Evidence задаёт пути, test без Evidence | Основной. Файлы всех splits локально, CPU baseline выполнен. KG light ещё нужен |
| HotpotQA distractor | Вопросы, 10 contexts, supporting facts, ответы; KG строится из contexts | Второй, по рекомендации руководителя. 7 405 validation записей скачаны; NGM-RAG — related work |
| MetaQA | Movie KG и QA 1/2/3-hop; исходных документов нет | Резерв для более дешёвого query-graph пилота. Код предыдущего BM25 prototype сохранён, но не главный B0 |
| PathQuestions (PQ) | Компактный KG и path questions; в SimGRAG используется для структуры запросов | Не выбран: QA-постановка и дополнительная подготовка не решают документальный вход |
| WC2014 | Football KG; single-relation, path и conjunctive QA | Не выбран по той же причине, перенос домена сейчас не нужен |
| GTSQA | Локальный candidate KG + answer subgraph, вход — вопрос | Диагностический архив. Не третий benchmark и не документальный gold |
| Re-DocRED | Реальные документы, mention clusters, отношения PID; в проверенном dev нет entity QID | Не выбран: отдельное entity linking и KG snapshot без утечки значительно расширяют работу |

Для FactKG документ — короткое утверждение. Для длинных документов обобщение не заявляется.
Для HotpotQA query graph из вопроса — перенос алгоритма в QA; это не тот же вход, что FactKG.

## Подтверждённая доступность

Локальный аудит FactKG: train=86 367, dev=13 266, test=9 041.
Только train/dev содержат Evidence. Локальный полный dev baseline использовал только train texts/labels.
HotpotQA validation parquet: 7 405 строк; download 05.11.2026, namespace hotpotqa/hotpot_qa.
Re-DocRED dev: проверены все 500 документов, поля mentions name/type/pos/sent_id/global_pos/index;
отношения h/t/r/evidence. Готового global entity-ID поля нет.

Сырые данные не коммитятся. Хеши, поля, состояния недостающих артефактов и выбранные IDs:
[manifest и protocol](https://github.com/OlegYurchik/soft-isomorphism/tree/docs/issue-7-protocol/configs).

## Источники и права

- [FactKG README](https://github.com/jiho283/FactKG): CC BY-NC-SA 4.0; файл KG light скачивать из авторского ресурса.
- [HotpotQA README](https://github.com/hotpotqa/hotpot): CC BY-SA 4.0 для данных, Apache 2.0 для кода.
- [MetaQA](https://github.com/yuyuz/MetaQA): официальный download и формат KG/QA.
- [SimGRAG appendix](https://aclanthology.org/2025.findings-acl.163.pdf): MetaQA/PQ/WC2014/FactKG и их роль в экспериментах.
- [Re-DocRED](https://github.com/tonytan48/Re-DocRED): проверен data/dev_revised.json, а не только abstract.

## Критерий готовности к graph experiment

Нужны проверенный DBpedia light с checksum, зафиксированный Qwen checkpoint, extraction cache,
реализованные matcher/reader и оценки на фиксированных splits. Пока выполнены аудит файлов,
фиксация дизайна и CPU baseline. Выбор benchmark уже сделан; графовый запуск ещё не выполнен.
