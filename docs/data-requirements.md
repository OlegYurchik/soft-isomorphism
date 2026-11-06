# Требования к данным: документ → KG

Выбранная тема: мягкое сопоставление графа документа с KG. Первый документ — короткий
FactKG claim. Длинные документы не входят в первый эксперимент. Второй набор HotpotQA
служит для переноса matching в QA, где query — вопрос.

Для основного эксперимента необходимы: исходный текст, независимый внешний KG,
фиксированные train/dev/test, оценочный verdict, воспроизводимые IDs/версии/права доступа.
Граф документа строится только из текста. Эталонные labels, evidence и Entity_set не доступны
retriever; иначе меняется постановка и требуется oracle-marking.

Baseline и proposed сравниваются по общей выходной задаче (FactKG verification Accuracy).
Отдельно можно анализировать evidence; нельзя требовать edge gold там, где dataset содержит
только пути или бинарные labels. HotpotQA даёт sentence-level gold, не gold KG triples.

Обязательные записи: исходный URL и SHA256, точные sample IDs, способ построения KG,
prompt/model/runtime revision, входные поля каждого компонента, budget, метрики/failures.
Все tune decisions принимаются по train/dev; test selection не зависит от результатов.
Пустые/неудачные запросы остаются в знаменателе. Raw datasets и веса не включаются в Git.

Простой baseline должен запускаться на CPU; графовый дизайн рассчитан на одну локальную
7B модель без обучения GNN. Возможность запуска Qwen и DBpedia light пока не проверена;
до неё нельзя обещать конкретный срок полного эксперимента.

Решение по данным: FactKG основной + HotpotQA distractor дополнительный.
[Полный дизайн и ограничения](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/docs/experiment-design-v2.md).

## Вопрос → вход → оценка

| Вопрос | Вход метода | Единица оценки | Независимый gold | Метрика |
|---|---|---|---|---|
| Помогает ли структура при verification? | FactKG claim, внешний DBpedia light | одно утверждение | binary `Label` | Accuracy (primary), macro-F1 |
| Где теряются кандидаты? | extracted query graph и candidate pool | сущность/ребро, только dev-диагностика | Entity_set/Evidence, evaluator-only | linked-node rate, path-constraint coverage |
| Помогают ли agreement-веса? | один cached graph Q, один pool | одно утверждение | `Label` | paired ΔAccuracy E1−B3, 95% bootstrap CI |
| Переносится ли retrieval в QA? | HotpotQA question + contexts | вопрос | answer + supporting facts | EM/F1, provenance P/R/F1 |

Edge F1 для всего FactKG не заявляется: `Evidence` хранит пути, а test не содержит
evidence. Supporting facts HotpotQA также не являются KG-тройками.

## Обязательные и желательные условия

Обязательны: публичный источник и права использования, стабильный ID, фиксированная
версия и checksum, независимый gold соответствующего уровня, возможность разделить
настройку и оценку, сохранение ошибок и таймаутов в знаменателе. Желательны: общий
benchmark с reference work, несколько hop-типов, естественные отрицательные claims,
sentence/entity provenance и доступный CPU smoke test.

## Ресурсы и границы

Подготовка документов и аудита ограничена 6–8 часами, ручная проверка — 20 примерами
на выбранный набор. B0 должен запускаться на CPU. Graph arms рассчитаны на один локальный
Qwen/Qwen2.5-7B-Instruct без обучения GNN; до проверки runtime это условие считается
риском. DBpedia light и веса модели не хранятся в Git. Если runtime не запускается,
фиксируется блокер и не подменяется другой моделью без новой версии протокола.
