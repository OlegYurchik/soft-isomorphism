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
| Структурно возможен полный путь среди top-50 при игнорировании сходства отношений | **1/6** | **0/5** |
| B4 и E4 выбрали разные mapping / evidence | **0 / 0** | **0 / 0** |
| Непустые evidence B1 / B4 / E4 | **20 / 3 / 3** | **20 / 1 / 1** |
| Покрытые авторские path constraints у положительных claims | **B1: 19/32; B4: 8/32; E4: 8/32** | На test аннотаций `Evidence` нет |
| Accuracy B1 / B4 / E4 (UNKNOWN считается ошибкой) | **0.60 / 0.05 / 0.05** | **0.70 / 0.00 / 0.00** |
| UNKNOWN B1 / B4 / E4 | **6 / 19 / 19** | **5 / 20 / 20** |

Для каждого claim, где нет query path, `P(f)=0` для всех mapping. В 11
claims с query paths (6 dev, 5 test) **ни у одного из top-50 mapping нет
завершённого пути**, поэтому `P(f)=1` для всех. Следовательно, на этих
40 claims штраф E4 постоянен внутри каждого списка кандидатов и не может
изменить ранжирование B4. Это точное объяснение наблюдаемых 0 различий;
при одинаковом reader E4 и B4 получат одинаковые verdict и Accuracy на
этих claims. Равенство не переносится автоматически на другие выборки.

Отдельная проверка убрала порог сходства отношений, сохранив те же
`candidate-pools.jsonl` и top-50 mapping. Структурно полный путь нашёлся
только для одного dev claim из 11 claims с query paths: «Bananaman ...
shown on the BBC and BBC is located in London». Путь есть у mapping
рангов 1 и 6; в остальных десяти claims его нет ни в одном top-50
mapping даже без порога. Для найденного пути MiniLM оценил `shown on` ↔
`network` как 0.247, а `located in` ↔ `locationCity` как 0.586. Первый
witness не проходит порог 0.55. Это разделяет две причины: ограничение
pool/beam для 10 claims и несовпадение коротких названий отношений для
оставшегося. Проверка структурной достижимости — постфактум диагностика,
не дополнительный эксперимент по Accuracy.

Порог также отсекает часть правдоподобных paraphrases: например, cosine
между `was built by` и `shipBuilder` здесь равен 0.343, ниже 0.55. Отсюда
малая доля непустых evidence у B4/E4; одно лишь семантическое кодирование
коротких relation names не решило проблему retrieval.

Reader запущен 13.11.2026 на `iairlab/qwen3.8-27b` с temperature 0 и
одинаковым KG-only prompt для всех методов. Первоначальные таймауты
сменились Cloudflare 1010: gateway отклонял стандартный `Python-urllib`
User-Agent. После явного API-клиентского User-Agent сервер вернул 200;
это исправление транспорта, prompt и данные не менялись. B1 правильно
классифицировал 12/20 dev и 14/20 test claims; среди не-UNKNOWN ответов
это 12/14 и 14/15 соответственно. Такая условная доля не заменяет
основную Accuracy, где UNKNOWN считается ошибкой. B4 и E4 дали один и
тот же ответ на каждом claim, как и следует из одинаковых evidence.

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

Команда `read` использует один KG-only reader для B1/B4/E4, проверяет
SHA-256 evidence при возобновлении и сохраняет `predictions.jsonl` и
`reader-summary.json` в игнорируемом каталоге результата.

Структурную достижимость из таблицы можно воспроизвести без encoder и API:

```bash
PYTHONPATH=src:scripts python - <<'PY'
from pathlib import Path
from factkg_e1_pilot import read_jsonl
from factkg_e4_experiment import mapping_evidence, query_paths
from soft_isomorphism.matching import Triple

for split in ('dev', 'test'):
    rows = read_jsonl(Path(f'data/evaluation/e4-{split}-20/candidate-pools.jsonl'))
    eligible = feasible = 0
    for row in rows:
        if row['status'] != 'ok' or not query_paths(row['graph']):
            continue
        eligible += 1
        triples = [Triple(**t) for t in row['pool_triples']]
        feasible += any(
            mapping_evidence(row['graph'], mapping, triples, lambda _a, _b: 1.0)['complete_paths']
            for mapping in row['mappings']
        )
    print(split, feasible, eligible)
PY
```
