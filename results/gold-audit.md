# Аудит эталона — актуализация 05.11.2026

Для E1 gold FactKG — Label[0], test Evidence отсутствует. Legacy gold-builder не является evaluator нового протокола.

Фактический аудит raw files: train 86 367, dev 13 266, test 9 041. Evidence проверен как entity→relation paths, а не готовые gold triples. Верификационный baseline использует только train texts/labels; 1 exact train/dev text overlap учтён отдельной метрикой.

Реальный train пример: A Glastonbury Romance / Weymouth Sands / John Cowper Powys. Evidence содержит subsequentWork и author, включая обратные пути. Эти ограничения прочитаны из аннотаций; наличие соответствующих фактов в DBpedia light ещё не проверено, поскольку KG не скачан. Нельзя объявлять их независимо верифицированным полным gold graph.

HotpotQA: validation 7 405, supporting_facts доступны только evaluator. Нельзя превращать их в query graph.

Ограниченный старый fixture audit не подтверждает качество реальных графов. Новый графовый gold/evidence evaluator ещё не реализован.

Правила: [annotation-rules.md](../docs/annotation-rules.md).
Версии и sample IDs: [протокол #7](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-7-protocol/configs/experiment-v2.json).
