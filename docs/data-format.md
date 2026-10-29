# Формат данных пилота

> Создан: 2026-10-29  
> Контекст: задача О10; входы — [О7](evaluation-protocol.md), [О6](dataset-feasibility.md), [configs/data-manifest.json](../configs/data-manifest.json).

---

## 1. Общая схема (`soft_isomorphism.data.schema`)

### `Edge`

Направленное именованное ребро в KG. Иммутабельный датакласс (frozen).

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|----------|
| `head_id` | `str` | Да | ID головного узла (Wikidata QID, DBpedia URI и т.п.) |
| `rel_id` | `str` | Да | ID отношения (Wikidata PID, DBpedia property) |
| `tail_id` | `str` | Да | ID хвостового узла |
| `head_label` | `str \| None` | Нет | Текстовая метка головы |
| `rel_label` | `str \| None` | Нет | Текстовая метка отношения |
| `tail_label` | `str \| None` | Нет | Текстовая метка хвоста |

**Инвариант:** все три `*_id` непустые (проверяется при создании `Example`).

### `Example`

Один пример пилота.

| Поле | Тип | Обязательное | Описание |
|------|-----|-------------|----------|
| `id` | `str` | Да | Уникальный ID вида `{source}-{split}-{n}` |
| `source` | `Source` | Да | `"gtsqa"` или `"factkg"` |
| `split` | `Split` | Да | `"train"`, `"train-fit"`, `"train-dev"`, `"dev"`, `"test"` |
| `text` | `str` | Да | Текст вопроса (GTSQA) или утверждения (FactKG) |
| `gold_edges` | `list[Edge]` | Да | **Эталонный answer-subgraph** — только для оценки |
| `metadata` | `dict` | Нет | Поля, специфичные для источника (см. §2–3) |

> **Важно:** `gold_edges` — золотой стандарт, который **не передаётся** методу на этапе retrieval. Метод получает только `text` (и, в нашем подходе, граф документа). `gold_edges` используется только в оценщике (О12).

---

## 2. GTSQA (`source = "gtsqa"`)

**Источник:** HuggingFace `Graphcore/GTSQA`, конфиг `gtsqa-with-graphs`.  
**Лицензия:** CC-BY-4.0.

### 2.1 Формат исходного файла

Parquet-файлы по пути `gtsqa-with-graphs/{train,test}/0000.parquet`.

Ожидаемые поля:

| Поле Parquet | Тип | Маппинг |
|-------------|-----|---------|
| `id` | str/int | `Example.id` |
| `question` | str | `Example.text` |
| `answer` | str | `Example.metadata["answer"]` |
| `graph` | list или dict | `Example.gold_edges` (парсится адаптером) |
| `graph_isomorphism` | str | `Example.metadata["graph_isomorphism"]` |
| `n_hops` | int | `Example.metadata["n_hops"]` |

### 2.2 Форматы поля `graph`

Адаптер поддерживает два формата (точный формат уточняется при первой загрузке):

**Format A — список троек:**
```json
[["Q142", "P36", "Q90"], ["Q90", "P17", "Q142"]]
```

**Format B — словарь с nodes/edges:**
```json
{"edges": [{"head": "Q17", "rel": "P38", "tail": "Q8146"}]}
```

Если формат не совпадает ни с одним, адаптер бросает `ValueError` с диагностикой. После первой загрузки реальных данных обновить `_parse_gtsqa_graph` в `adapter.py`.

### 2.3 Dev-split

Не создаётся адаптером автоматически. Требует предварительного запуска скрипта stratified split (см. `docs/evaluation-protocol.md §2.1`), который сохраняет индексы в `configs/splits/gtsqa_dev_indices.json`.

```
configs/splits/gtsqa_dev_indices.json:
{
  "train-fit": [0, 2, 3, ...],   # 90% от train
  "train-dev": [1, 4, ...]       # 10% от train
}
```

### 2.4 Пример

```python
from soft_isomorphism.data import load_gtsqa, Split

examples = load_gtsqa("data/gtsqa", Split.TEST)
ex = examples[0]
# ex.id       -> "gtsqa-0001"
# ex.text     -> "What is the capital of France?"
# ex.gold_edges -> [Edge(head_id="Q142", rel_id="P36", tail_id="Q90")]
# ex.metadata -> {"answer": "Paris", "graph_isomorphism": "single-hop", "n_hops": 1}
```

---

## 3. FactKG (`source = "factkg"`)

**Источник:** GitHub `jiho283/FactKG`.  
**Лицензия:** CC BY-NC-SA 4.0 (академическое использование допустимо).

### 3.1 Формат исходного файла

JSON-файлы по пути `factkg/data/factkg_{split}.json`.

Структура — словарь `{claim_text: entry}`, где `entry`:

```json
{
  "label": true,
  "type": "One-hop",
  "graph": {"entity_uri": [["relation", "entity_uri"], ...]},
  "entities": ["entity_uri", ...]
}
```

### 3.2 Маппинг полей

| Поле JSON | Маппинг |
|-----------|---------|
| ключ (claim text) | `Example.text` |
| `label` | `Example.metadata["label"]` |
| `type` | `Example.metadata["type"]` |
| `graph` | `Example.gold_edges` (парсится адаптером) |
| `entities` | `Example.metadata["entities"]` |

### 3.3 Ограничение test-split

FactKG `test` не содержит поля `graph` → `load_factkg(path, Split.TEST)` бросает `ValueError`. В пилоте использовать только `Split.TRAIN` и `Split.DEV`.

### 3.4 Пример

```python
from soft_isomorphism.data import load_factkg, Split

examples = load_factkg("data/factkg", Split.DEV)
ex = examples[0]
# ex.text -> "Murda Beatz is a record producer."
# ex.gold_edges -> [Edge(head_id="Murda_Beatz", rel_id="occupation", tail_id="record_producer")]
# ex.metadata -> {"label": True, "type": "One-hop", "entities": ["Murda_Beatz"]}
```

---

## 4. Загрузка данных

```bash
# GTSQA
python - <<'EOF'
from datasets import load_dataset
ds = load_dataset("Graphcore/GTSQA", "gtsqa-with-graphs")
# Сохранить как parquet в нужную структуру
for split_name, split_ds in ds.items():
    split_ds.to_parquet(f"data/gtsqa/gtsqa-with-graphs/{split_name}/0000.parquet")
EOF

# FactKG
git clone https://github.com/jiho283/FactKG data/factkg
```

После загрузки зафиксировать версии в `configs/data-manifest.json`:
- GTSQA: дату доступа (HuggingFace не имеет git-хешей, только revision)
- FactKG: SHA коммита (`git -C data/factkg rev-parse HEAD`)

---

## 5. Связь с манифестом

`configs/data-manifest.json` описывает ожидаемые пути и размеры. Адаптер читает файлы по этим путям, но **не читает манифест напрямую** — маппинг путей захардкожен и проверен относительно манифеста вручную.

При расхождении между реальными данными и манифестом: обновить манифест, не адаптер.
