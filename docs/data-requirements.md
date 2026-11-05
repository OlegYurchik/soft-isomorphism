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
