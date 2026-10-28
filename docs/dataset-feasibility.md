# Проверка доступности и пригодности короткого списка

> Последнее обновление: 2026-10-29  
> Контекст: задача О6; входы — [О5](dataset-selection.md) (shortlist), [О3](data-requirements.md) (критерии).  
> Методология: дистанционная проверка через официальные репозитории, dataset cards и публикации.  
> Файловая проверка (команды загрузки и 10–20 примеров) — **документирована как следующий шаг** ниже.  
> (Папки `results/` и `data/` в .gitignore — отчёт хранится в docs/.)

---

## 1. Методология

Проверка выполнена в два слоя:

| Слой | Что сделано | Что требует загрузки файлов |
|------|-------------|----------------------------|
| **Дистанционная** | Лицензия, URL, формат, схема полей, split-размеры — из README, dataset cards, арXiv-статей | — |
| **Файловая** | — | Трассировка 10–20 примеров; контрольные суммы; проверка полей в test-файле |

Файловая проверка задокументирована командами в разделах 2–4; должна быть выполнена вручную до принятия финального решения в О7.

---

## 2. GTSQA (NeurIPS 2025, arXiv:2511.04473)

### 2.1 Доступность

| Параметр | Значение | Источник |
|----------|----------|----------|
| URL | https://huggingface.co/datasets/Graphcore/GTSQA | HF card |
| Лицензия | **CC-BY-4.0** ✓ | HF sidebar |
| Формат | Parquet (gtsqa/train/0000.parquet, gtsqa/test/0000.parquet) | HF tree |
| Доп. вариант | gtsqa-with-graphs (train: 0000–0003, test: 0000) — с графами | HF tree |
| Размер файлов | train ~11.2 MB parquet | HF tree |
| Код генерации | https://github.com/graphcore-research/synth-kgqa | README |

Команда загрузки:
```python
from datasets import load_dataset
ds = load_dataset("Graphcore/GTSQA")
# или вариант с графами:
ds_graphs = load_dataset("Graphcore/GTSQA", "gtsqa-with-graphs")
```

### 2.2 Схема полей (из dataset card + paper Table 1)

| Поле | Тип | Описание |
|------|-----|----------|
| `question` | str | Естественно-языковой вопрос |
| `answer` | list[str] | Правильный ответ (Wikidata entity label) |
| `n_hops` | int | Максимальное число рёбер от seed до answer |
| `graph_isomorphism` | str | Тип изоморфизма answer-subgraph (27 типов) |
| `minimal_graph_isomorphism` | str | Тип без избыточных путей |
| `minimal_seeds_and_queries` | list | Минимальные seed-сущности + SPARQL-запрос |
| `graph` | list[dict] | Тройки answer-subgraph: {head_qid, rel_pid, tail_qid} (только в gtsqa-with-graphs) |

### 2.3 Статистика

| Метрика | Значение |
|---------|----------|
| Всего | 32 099 вопросов |
| Train | 30 477 |
| Test | 1 622 |
| Dev | **отсутствует** — нужно самостоятельно выделить из train |
| Средние hops (train) | 1.48 |
| Средние hops (test) | 2.02 |
| Макс. hops | 5 |
| Типов isomorphism | 27 |
| KG | ogbl-wikikg2 (Wikidata 2015 dump) |

### 2.4 Соответствие must-have

| Критерий | Статус | Детали |
|----------|--------|--------|
| #1 Открытый доступ | ✓ | CC-BY-4.0, HuggingFace |
| #2 Стабильные ID | ✓ | Wikidata QIDs + PIDs |
| #3 Triplet/subgraph разметка | ✓ | ground-truth subgraph в каждом примере |
| #4 Независимая верификация | ✓ | SPARQL-верифицируемый через Wikidata |

### 2.5 Ограничения

- **Нет dev-split** — при обучении нужно самостоятельно стратифицированно разбить train (рекомендуется по `graph_isomorphism`)
- **KG 2015 года** — ogbl-wikikg2 не совпадает с актуальной Wikidata; возможны расхождения при проверке SPARQL на wikidata.org
- **Синтетика** — все вопросы сгенерированы из KG-структур; нет лингвистического разнообразия реальных документов
- **Subgraph = дерево** — answer-subgraphs ограничены деревьями (connected, acyclic); DAG/циклические структуры не представлены

### 2.6 Команды для файловой проверки

```python
from datasets import load_dataset
import pandas as pd

ds = load_dataset("Graphcore/GTSQA", "gtsqa-with-graphs")
sample = ds["test"].select(range(20)).to_pandas()

# Проверить поля
print(sample.columns.tolist())
# Проверить hop-распределение
print(sample["n_hops"].value_counts())
# Посмотреть пример subgraph
print(sample["graph"][0])
```

---

## 3. FactKG (ACL 2023, arXiv:2305.06590)

### 3.1 Доступность

| Параметр | Значение | Источник |
|----------|----------|----------|
| URL | https://github.com/jiho283/FactKG | GitHub README |
| Лицензия | **CC BY-NC-SA 4.0** ⚠ (некоммерческая) | README License section |
| Формат | JSON (предположительно) | из описания в paper |
| KG | DBpedia 2015 (preprocessed) | paper §4 |
| KG-доступ | DBpedia SPARQL endpoint: https://dbpedia.org/sparql | публичный |

> ⚠ **CC BY-NC-SA 4.0** — некоммерческая лицензия. Использование в академической НИР допустимо, но публикация производных данных требует той же лицензии.

### 3.2 Схема полей (реконструирована из paper + ACL Anthology)

| Поле | Тип | Наличие в split | Описание |
|------|-----|----------------|----------|
| `claim` | str | train/dev/test | Естественно-языковое утверждение |
| `label` | bool/str | train/dev/test | True/False — вердикт |
| `type` | str | train/dev/test | Тип reasoning: One-hop, Multi-hop, Conjunction, Existence, Negation |
| `graph` | list[dict] | **train/dev only** | Релевантные тройки KG: субъект → предикат → объект |
| `entities` | list[str] | train/dev/test | DBpedia entity URIs (в test — единственный structured field) |

> ⚠ **Критическое ограничение:** в test-сете поле `graph` отсутствует — только entity URIs. Для оценки Q1 на тесте необходимо самостоятельно извлекать подграфы через DBpedia SPARQL.

### 3.3 Статистика

| Метрика | Значение |
|---------|----------|
| Всего | 108 674 |
| Train | ~86 939 (8/10) |
| Dev | ~10 867 (1/10) |
| Test | ~10 868 (1/10) |
| Split | disjoint по тройкам KG (нет утечки между split'ами) |
| KG | DBpedia 2015, ~0.1B троек |

### 3.4 Соответствие must-have

| Критерий | Статус | Детали |
|----------|--------|--------|
| #1 Открытый доступ | ✓ (ограничено) | CC BY-NC-SA; GitHub; некоммерческое |
| #2 Стабильные ID | ✓ | DBpedia URIs (стабильные) |
| #3 Triplet/subgraph разметка | ✓ в train/dev; ⚠ в test — только entities | Для test нужен SPARQL |
| #4 Независимая верификация | ✓ | Labels в публичном файле |

### 3.5 Ограничения

- **Test без subgraph** — для полноценной оценки Q1 требуется доступ к DBpedia SPARQL и самостоятельное построение подграфов. Это ~2–4 ч дополнительной адаптации
- **DBpedia 2015** — как и GTSQA, использует снимок 2015 года; возможны расхождения с актуальными данными
- **Некоммерческая лицензия** — ограничивает распространение производных датасетов

### 3.6 Команды для файловой проверки

```bash
# Клонировать репозиторий
git clone https://github.com/jiho283/FactKG.git
ls FactKG/data/
```

```python
import json

with open("FactKG/data/factkg_train.json") as f:
    train = json.load(f)

# Проверить структуру первых 5 примеров
for k, v in list(train.items())[:5]:
    print(k, "→", list(v.keys()))

# Проверить структуру test
with open("FactKG/data/factkg_test.json") as f:
    test = json.load(f)
sample_key = list(test.keys())[0]
print("Test fields:", list(test[sample_key].keys()))
# Ожидается: нет поля 'graph', только 'entities'
```

---

## 4. Re-DocRED (EMNLP 2022, arXiv:2205.12696)

### 4.1 Доступность

| Параметр | Значение | Источник |
|----------|----------|----------|
| URL | https://github.com/tonytan48/Re-DocRED | GitHub |
| HuggingFace | https://huggingface.co/datasets/tonytan48/Re-DocRED | HF |
| Лицензия | **MIT** (вероятно) ⚠ — не подтверждено прямым чтением LICENSE | GitHub sidebar / вторичный источник |
| Формат | JSON (та же схема, что DocRED) | paper + DocRED convention |

> ⚠ Лицензия MIT определена из GitHub sidebar и вторичного источника (student repo); **требует прямой проверки LICENSE файла** перед финальным решением.

### 4.2 Схема полей (DocRED-совместимая, из HuggingFace DocRED card)

```json
{
  "title": "...",
  "sents": [["токены", "предложения", "1"], ["токены", "2"]],
  "vertexSet": [
    [{"name": "entity_text", "sent_id": 0, "pos": [0, 1], "type": "ORG"}],
    ...
  ],
  "labels": [
    {
      "h": 0, "t": 1,
      "r": "P17",
      "evidence": [0, 1]
    },
    ...
  ]
}
```

| Поле | Описание |
|------|----------|
| `title` | Заголовок статьи Wikipedia |
| `sents` | Список предложений (токенизированных) |
| `vertexSet` | Список сущностей; каждая — список упоминаний с позицией и типом |
| `labels` | Список троек: head_idx, tail_idx, relation_id (Wikidata PID), evidence sentences |

> Re-DocRED в `labels` добавляет поле `Wikidata` с QID сущностей — это прямая ссылка на KG.

### 4.3 Статистика

| Метрика | Значение |
|---------|----------|
| Docs (train) | 3 053 |
| Docs (dev) | ~500 (ожидается, точно — из файлов) |
| Docs (test) | ~500 (ожидается) |
| Relation types | 96 (Wikidata PIDs) |
| Entities | до 42 на документ (из DocRED) |
| Avg sentences per doc | ~8 |

### 4.4 Соответствие must-have

| Критерий | Статус | Детали |
|----------|--------|--------|
| #1 Открытый доступ | ✓ (условно) | MIT вероятен; требует проверки |
| #2 Стабильные ID | ✓ | Wikidata QIDs и PIDs в поле labels.Wikidata |
| #3 Triplet/subgraph разметка | ✓ | Тройки на уровне документа во всех split'ах |
| #4 Независимая верификация | ✓ | Labels в публичном файле |

### 4.5 Ограничения

- **Лицензия не подтверждена** — нужно прочитать LICENSE файл в репо
- **Задача RE, не subgraph retrieval** — аннотированные тройки = document graph, но «правильный KG-подграф» нужно строить из Wikidata по QIDs самостоятельно; это ~2–3 ч адаптации
- **Нет dev/test в оригинальном DocRED** для test-labels — Re-DocRED это исправляет, но нужно проверить

### 4.6 Команды для файловой проверки

```bash
git clone https://github.com/tonytan48/Re-DocRED.git
cat Re-DocRED/LICENSE   # проверить лицензию
ls Re-DocRED/data/re-docred/
```

```python
import json

with open("Re-DocRED/data/re-docred/train_revised.json") as f:
    train = json.load(f)

print(f"Train docs: {len(train)}")
sample = train[0]
print("Fields:", list(sample.keys()))
print("Labels sample:", sample["labels"][:2])
# Проверить наличие Wikidata QIDs
print("Wikidata field:", sample["labels"][0].get("Wikidata", "ABSENT"))
```

---

## 5. Сводная таблица обновлённых сведений

| Параметр | GTSQA | FactKG | Re-DocRED |
|----------|-------|--------|-----------|
| Лицензия | **CC-BY-4.0** ✓ | **CC BY-NC-SA 4.0** ⚠ | **MIT** (условно) ⚠ |
| Dev-split | **Нет** — нужно создать | ✓ (~10 867) | ✓ (~500) |
| Subgraph в test | ✓ (answer-subgraph) | **Нет** — только entities | ✓ (тройки во всех split'ах) |
| Структурная сложность | Деревья, avg 2.02 hops, 27 типов | 5 типов reasoning (Multi-hop ✓) | 96 rel. types, cross-sentence |
| KG-версия | Wikidata 2015 (ogbl-wikikg2) | DBpedia 2015 | Wikidata (актуальные QIDs) |
| Формат | Parquet (HuggingFace) | JSON (GitHub) | JSON (GitHub / HuggingFace) |
| Must-have all | ✓ все | ✓ с оговоркой | ✓ условно |
| Оценка адаптации | **< 1 ч** (нет dev — 30 мин split) | **2–4 ч** (SPARQL для test subgraph) | **2–3 ч** (Wikidata KG build) |

---

## 6. Блокеры и решение

| Блокер | Датасет | Серьёзность | Решение |
|--------|---------|-------------|---------|
| Лицензия CC BY-NC-SA | FactKG | Средний | Использование в НИР допустимо; нельзя публиковать производные данные коммерчески |
| Нет subgraph в test | FactKG | Высокий для Q1 на тесте | Использовать train/dev для основной оценки + SPARQL-восстановление для test |
| Нет dev-split | GTSQA | Низкий | Самостоятельный stratified split по `graph_isomorphism` |
| Лицензия MIT не подтверждена | Re-DocRED | Средний | Прочитать LICENSE файл (< 5 мин) |
| KG 2015 года | GTSQA, FactKG | Низкий для пилота | Для пилота достаточно; при масштабировании — обновить |

**Нет блокеров, исключающих все три датасета.** Предварительный вывод для О7:

- **Основной датасет:** GTSQA — лицензия чистая, subgraph-эталон в test, минимальная адаптация
- **Дополнительный:** FactKG — покрывает другой аспект (fact verification + типизированный reasoning), использовать train/dev
- **Резерв:** Re-DocRED — после подтверждения лицензии

---

## 7. Неподтверждённое — требует загрузки файлов

| Вопрос | Датасет | Команда |
|--------|---------|---------|
| Точное кол-во примеров в dev/test | Re-DocRED | `len(json.load(open("dev_revised.json")))` |
| Наличие поля `Wikidata` в labels | Re-DocRED | см. §4.6 |
| Поле `graph` отсутствует в test | FactKG | `list(test[k].keys())` — см. §3.6 |
| Колонки parquet файла | GTSQA | `ds["test"].column_names` |
| Реальное hop-распределение test | GTSQA | `ds["test"]["n_hops"]` value_counts |
| Лицензия (LICENSE файл) | Re-DocRED | `cat Re-DocRED/LICENSE` |
