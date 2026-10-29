# Аудит эталона (gold-audit)

> Создан: 2026-10-29  
> Контекст: задача О11; правила — [annotation-rules.md](../docs/annotation-rules.md).

---

## 1. Методология

Аудит преследует три цели:

1. Убедиться, что адаптер ([О10](../docs/data-format.md)) корректно парсит поля `graph` в `gold_edges`.
2. Вручную проверить небольшую выборку примеров на соответствие первичным источникам (Wikidata, DBpedia).
3. Зафиксировать исключения и пограничные случаи **до** запуска методов.

**Порядок аудита:**
- Выгрузить все примеры адаптером → проверить уникальность ID, непустые `gold_edges`, тип `graph_isomorphism`.
- Проверить выборку вручную (≥10 примеров на датасет) по первичным источникам.
- Применить правила исключения из §4–5 `annotation-rules.md`.
- Записать каждое решение в §3 этого документа.

---

## 2. Покрытие

### 2.1 Статус по датасетам

| Датасет | Split | Всего | Оценимо | Исключено | Неизвестно | Thin gold | Статус |
|---------|-------|-------|---------|-----------|------------|-----------|--------|
| GTSQA | test | 1 622 | — | — | — | — | ожидает загрузки данных |
| GTSQA | train-dev | ~3 048 | — | — | — | — | ожидает загрузки данных |
| FactKG | dev | ~10 867 | — | — | — | — | ожидает загрузки данных |

После загрузки данных и запуска `scripts/build_gold.py` таблица обновляется автоматически.

### 2.2 Ожидаемые причины исключений

На основании описания датасетов (до скачивания):

- **GTSQA:** маловероятны пустые графы (датасет построен вокруг answer-subgraph). Ожидаем <1% исключений по `empty_gold`.
- **FactKG:** тип `Existence` может иметь разреженный граф (`thin_gold`). Тип `Negation` может не иметь прямого supporting graph — нужна ручная проверка.

---

## 3. Журнал ручной проверки

### 3.1 Проверка синтетических примеров (fixtures)

Проверено 6 синтетических примеров, используемых в тестах адаптера. Примеры синтетические — они не входят в реальные датасеты и не являются частью тестовой выборки.

#### GTSQA fixtures (`tests/fixtures/gtsqa_sample.json`)

| ID | Вопрос | Золото (из файла) | Проверка | Статус | Примечание |
|----|--------|-------------------|----------|--------|------------|
| `gtsqa-0001` | What is the capital of France? | `(Q142, P36, Q90)` | Q142=Франция, P36=столица, Q90=Париж — корректно ✓ | evaluable | — |
| `gtsqa-0002` | Who directed the film Inception? | `(Q25188, P57, Q25191)`, `(Q25188, P495, Q30)` | Q25188=Inception, P57=director, Q25191=Nolan, P495=country, Q30=USA — две тройки корректны ✓ | evaluable | Граф включает страну производства (P495) помимо режиссёра (P57) — typical multi-edge pattern |
| `gtsqa-0003` | What is the currency of Japan? | `(Q17, P38, Q8146)` | Q17=Япония, P38=валюта, Q8146=японская иена — корректно ✓; Format B (dict) парсится корректно ✓ | evaluable | Тест парсера Format B |

#### FactKG fixtures (`tests/fixtures/factkg_sample.json`)

| ID | Утверждение | Золото (из файла) | Метка | Проверка | Статус | Примечание |
|----|-------------|-------------------|-------|----------|--------|------------|
| `factkg-dev-0` | Murda Beatz is a record producer. | `(Murda_Beatz, occupation, record_producer)` | true | Одна тройка, тип One-hop ✓ | evaluable | — |
| `factkg-dev-1` | The Eiffel Tower is located in Berlin and was built in 1889. | `(Eiffel_Tower, location, Paris)`, `(Eiffel_Tower, inception, 1889)` | false | Метка false: Tower в Париже, не в Берлине. Граф показывает правдивые факты, метка отражает ложность утверждения ✓ | evaluable | Conjunction. label=false, но gold_edges содержат реальные факты из KG — корректная схема. |
| `factkg-dev-2` | Barack Obama was born in Hawaii and served as US president. | `(Barack_Obama, place_of_birth, Hawaii)`, `(Hawaii, country, United_States)` | true | Двухшаговая цепочка. Multi-hop ✓ | evaluable | thin_gold — связь с US president отсутствует в gold_edges (неполный supporting graph — типично для Multi-hop) |

#### Итог по fixtures

- Все 6 примеров: статус `evaluable`.
- `factkg-dev-2` помечен `thin_gold`: gold_edges не содержит тройку "Obama — president — USA", хотя утверждение это включает. Ожидаемое поведение Multi-hop в FactKG — не дефект данных.
- Парсеры Format A и Format B адаптера работают корректно.

### 3.2 Проверка реальных данных

**Статус:** ожидает загрузки датасетов.

После загрузки провести проверку:
- GTSQA test: случайная выборка 15 примеров (seed=42), проверить QID/PID через Wikidata API.
- FactKG dev: по 5 примеров на каждый из 5 типов reasoning = 25 примеров.

Результаты записать в таблицу аналогичного формата в §3.3.

---

## 4. Правила, установленные до сравнения методов

Зафиксированы в [annotation-rules.md §4–5](../docs/annotation-rules.md). Ключевые:

1. `gold_edges = []` или `None` → исключить с причиной `empty_gold`.
2. `graph_isomorphism = null` → исключить с причиной `null_type`.
3. FactKG Existence с ≤1 ребром → не исключать, пометить `thin_gold`.
4. Отсутствие записи в эталоне ≠ отрицательная метка.
5. Правила не меняются по итогам работы методов.

---

## 5. Команды воспроизведения

```bash
# Загрузить данные (если ещё не загружены)
python - <<'EOF'
from datasets import load_dataset
ds = load_dataset("Graphcore/GTSQA", "gtsqa-with-graphs")
for split_name, split_ds in ds.items():
    split_ds.to_parquet(f"data/gtsqa/gtsqa-with-graphs/{split_name}/0000.parquet")
EOF

git clone https://github.com/jiho283/FactKG data/factkg

# Сгенерировать gold.jsonl
uv run python scripts/build_gold.py

# Проверить покрытие
uv run python scripts/build_gold.py --report
```

---

## 6. Журнал изменений аудита

| Дата | Действие | Автор |
|------|----------|-------|
| 2026-10-29 | Создан; проверены 6 fixture-примеров | @OlegYurchik |
