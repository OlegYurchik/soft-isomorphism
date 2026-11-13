# E4 path-consistency: первый запуск и решение по текущей версии

Дата: 13.11.2026. Ветка задачи #19. Дизайн E4/B4 зафиксирован в
[ветке задачи #9](https://github.com/OlegYurchik/soft-isomorphism/blob/docs/issue-9-novelty/docs/path-consistency-experiment.md).
Это **диагностический**, а не финальный прогон гипотезы: использованы
ранее просмотренные первые 20 FactKG dev и первые 20 test claims по
SHA-256 текста. Новые test ranks 20–519 и dev ranks 500–999 не запускались.

## Что реально выполнено

Взяты сохранённые графы из однопроходного извлечения
`iairlab/qwen3.8-27b`. Для каждого claim заново построен общий KG pool
из DBpedia 2015 light и сохранены до 50 отображений из B3 beam search.
B4 и E4 ранжировали **одни и те же** отображения по семантической стоимости
отношений; E4 добавлял фиксированный штраф `0.2·P(f)` за незавершённые
направленные простые пути длиной 2–3. B1 выбирал до 20 BM25-троек из
1-hop окрестности тех же якорей и того же pool. Все evidence — настоящие
KG-тройки, без использования `Label`, `Entity_set`, `Evidence` при retrieval.

Encoder: `sentence-transformers/all-MiniLM-L6-v2`, ревизия
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, CPU ONNX, mean pooling,
нормализация вектора. SHA-256 `onnx/model.onnx`:
`6fd5d72fe4589f189f8ebc006442dbb529bb7ce38f8082112682524616046452`;
`tokenizer.json`:
`be50c3628f2bf5bb5e3a7f17b1f74611b2561a3a27eeab05e5aa30f411572037`.
Порог семантического witness `cos≥0.55` и вес пути `0.2` взяты из
дизайна до этого запуска и не менялись по результатам.

## Retrieval-результаты

| Метрика | dev-20 | test-20 |
|---|---:|---:|
| Извлечённый граф с ≥2 рёбрами | 11 | 12 |
| Есть хотя бы один направленный query path длиной 2–3 | 6 | 5 |
| Среди top-50 mapping число завершённых путей различается | **0** | **0** |
| B4 и E4 выбрали разные mapping / evidence | **0 / 0** | **0 / 0** |
| Непустые evidence B1 / B4 / E4 | **20 / 3 / 3** | **20 / 1 / 1** |
| Покрытые авторские path constraints у положительных claims | **B1: 19/32; B4: 8/32; E4: 8/32** | На test аннотаций `Evidence` нет |

Для каждого claim, где нет query path, `P(f)=0` для всех mapping. В 11
claims с query paths (6 dev, 5 test) **ни у одного из top-50 mapping нет
завершённого пути**, поэтому `P(f)=1` для всех. Следовательно, на этих
40 claims штраф E4 постоянен внутри каждого списка кандидатов и не может
изменить ранжирование B4. Это точное объяснение наблюдаемых 0 различий;
при одинаковом reader E4 и B4 получат одинаковые verdict и Accuracy на
этих claims. Равенство не переносится автоматически на другие выборки.

Порог также отсекает часть правдоподобных paraphrases: например, cosine
между `was built by` и `shipBuilder` здесь равен 0.343, ниже 0.55. Отсюда
малая доля непустых evidence у B4/E4; одно лишь семантическое кодирование
коротких relation names не решило проблему retrieval.

Reader и Accuracy **не запускались**: сервис ИТМО
`https://api.duckduck.cloud` в день прогона не отвечал даже на `GET
/v1/models` с авторизацией (таймаут 8 с) и короткий chat-запрос (таймаут
15 с). Отсутствующий результат нельзя заменять прежней Accuracy B3 или
гибрида с B0. На test-20 авторских path annotations нет, поэтому там
публикуется только наличие evidence и точное равенство B4/E4.

## Решение

**Текущая версия E4 не прошла диагностическую проверку механизма.** На
этих сохранённых графах у path penalty нет вариации между кандидатами,
а B1 покрывает больше авторских путей на dev. Масштабировать эту же
конфигурацию на 500 claims до исправления extraction/relation alignment
нецелесообразно. Это инженерное решение по текущему алгоритму, не
статистическое опровержение H4 на независимом test subset. Для следующей
версии нужно сначала показать непостоянный path score на неиспользованной
dev выборке и сравнить его с B1 при том же бюджете evidence.

## Воспроизведение

Сырые `candidate-pools.jsonl`, `reranked.jsonl`, `retrieval-audit.jsonl`,
`retrieval-summary.json`, `encoder.json` находятся локально в игнорируемых
Git каталогах `data/evaluation/e4-dev-20/` и `e4-test-20/`. Для test
заменить dev-файл извлечения на сохранённый test-20, `--out-dir` на
`data/evaluation/e4-test-20`, `--split` на `test`.

```bash
PYTHONPATH=src python scripts/factkg_e4_experiment.py prepare \
  --extract-file data/evaluation/e1-pilot-itmo-qwen3_8-27b-open-dev/extract.jsonl \
  --out-dir data/evaluation/e4-dev-20
PYTHONPATH=src uv run --extra e4 python scripts/factkg_e4_experiment.py score \
  --extract-file data/evaluation/e1-pilot-itmo-qwen3_8-27b-open-dev/extract.jsonl \
  --out-dir data/evaluation/e4-dev-20
PYTHONPATH=src python scripts/factkg_e4_experiment.py evaluate \
  --extract-file data/evaluation/e1-pilot-itmo-qwen3_8-27b-open-dev/extract.jsonl \
  --out-dir data/evaluation/e4-dev-20 --split dev
```

Команда `read` подготовлена для отдельной оценки Accuracy после
восстановления API; она использует один KG-only reader для B1/B4/E4 и
возобновляет работу по сохранённым claim IDs.
