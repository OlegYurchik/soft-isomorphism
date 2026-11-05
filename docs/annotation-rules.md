# Эталоны для E1

Основной результат FactKG — binary verdict, gold=`Label[0]`. Test содержит labels, но не
Evidence. Наличие test labels разрешает evaluation, но не extraction/tuning.
Gold граф для всего FactKG автоматически из Evidence не создаём: пути могут не задавать
промежуточные узлы однозначно. Существующий legacy gold-builder не является evaluator E1.

Primary metric: Accuracy по всем заранее зафиксированным IDs, включая extraction/search/reader failures.
UNKNOWN/invalid prediction всегда ошибочен и отдельно входит в abstention rate.
Для macro-F1 неизвестный ответ добавляет FN фактическому классу; не образует третий оцениваемый класс.

Только на положительных dev claims с непустым Evidence: path-constraint coverage.
Каждое ограничение — start entity и последовательность relations. Проверяем существование
такого пути в retrieved subgraph; `~r` означает обратное направление. Дубликаты ограничений
удаляются, метрика усредняется сначала внутри claim, затем по claims.
Ограничения без подтверждённого endpoint не считаются уникальной gold-тройкой.
Эта диагностика не доказывает полноту evidence и не называется edge F1.
Отрицательные claims нельзя использовать как набор подтверждённых KG edges.

HotpotQA: gold answer и supporting_facts используются только evaluator. Evidence edges
имеют source provenance, преобразуем её в deduplicated `(title,sent_id)` и считаем supporting-fact
P/R/F1. Answer EM/F1 считать официальным evaluation script. Ни source graph, ни question graph
не строятся из gold supporting facts.

Аудит: фиксировать malformed rows, exact split overlaps, zero paths, missing KG entities,
ошибки extraction, кандидаты без реализации constraints. Не исключать их после просмотра score.
В full-dev B0 найден 1 exact train/dev overlap; сообщены полная метрика и дополнительная
метрика на 13 265 непересекающихся claims. Test B0 пока не запускался.

Полный протокол: [E1](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/docs/experiment-design-v2.md).
