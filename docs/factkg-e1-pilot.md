# FactKG: Qwen3.8-27B pilot and UNKNOWN fallback

Статус задачи #19 на 12.11.2026. Выполнены отдельные прогоны на первых 20
FactKG dev и первых 20 test утверждениях по SHA-256 текста. Это малый
диагностический пилот. Основная гипотеза E1 **не проверена**: при одном
извлечении на claim все веса рёбер равны 1, поэтому B3 и E1 дают одинаковый
результат.

## Входы и режим

| Компонент | Значение |
|---|---|
| FactKG train SHA-256 | `41af6c4d21a76eb00f763c326770cbcbfa7021a23deeabd86f47c8df6a6e82c6` |
| FactKG dev SHA-256 | `eaf611ee9694030b1a7a312aa8d28b5ea60a5f81cae8c1c900b0616ada831670` |
| FactKG test SHA-256 | `9cecb4e5d0438f8abaf1f44402b18223a13d20f116a52f288391aa9a6cbd84a4` |
| DBpedia 2015 light SHA-256 | `da0f515912195f28823c35cb891f12c26698bfd720fc4dc7660faf6bde18c4ed`; 9 913 189 сущностей |
| Модель | ИТМО `iairlab/qwen3.8-27b`, `https://api.duckduck.cloud`, `json_object`, `temperature=0`, `seed=42` |
| Извлечение | 1 вызов на claim, свободные relation phrases, до 512 output tokens, thinking отключён через `chat_template_kwargs.enable_thinking=false` |
| Linking / KG pool | FTS5 trigram index; до 5 KG-кандидатов на узел; радиус 2, максимум 30 incident triples на шаг и 2 000 triples в pool |
| Match / evidence | Beam search; сравнение CamelCase KG relations с фразами; expanded evidence — до 3 реальных соседних фактов KG на query edge, максимум 20 |
| Reader | Та же Qwen3.8-27B, до 256 output tokens; TRUE/FALSE/UNKNOWN по переданным KG-фактам |
| Fallback | Уже выполненный B0: BM25 по train claims, top-5 vote. Применяется **только** при UNKNOWN graph reader |

Ревизия весов модели на сервисе ИТМО не раскрыта. Ключ читается из локального
провайдера KiloCode `itmo_lab` и не сохраняется в артефактах. Сырые FactKG,
DBpedia, модельные ответы и оценки в `data/` игнорируются Git.

## Измеренные результаты

| Одна и та же выборка | Графы | Допустимый mapping | Evidence strict → expanded | Graph reader Accuracy / UNKNOWN | B0 Accuracy | Graph + B0 fallback Accuracy / UNKNOWN |
|---|---:|---:|---:|---:|---:|---:|
| FactKG dev, 20 | 20 | 19 | 4 → 7 | 6/20 = 30%; 14/20 | 10/20 = 50% | 13/20 = 65%; 0/20 |
| FactKG test, 20 | 20 | 17 | 3 → 6 | 5/20 = 25%; 14/20 | 10/20 = 50% | 11/20 = 55%; 0/20 |

На обеих выборках fallback был использован 14 раз из 20; ноль UNKNOWN
получен **по определению гибрида**, а не потому, что KG стал покрывать все
утверждения. У test reader 6 определённых ответов, из них 5 верных.
Размер 20 и подбор инженерных решений на dev не позволяют утверждать
значимое улучшение над B0. Основной B0 результат на другом размере выборки —
56,4% Accuracy на первых 500 test claims — нельзя напрямую сопоставлять с
этим графовым пилотом 20 claims.

Предыдущая версия с тремя запросами Qwen3-32B на dev-20 дала 17 UNKNOWN и
15% Accuracy у B3/E1. Числа двух версий нельзя использовать как чистое
сравнение моделей: одновременно изменились извлечение, отношения и evidence.
Причины прежних 17 UNKNOWN описаны в [аудите](factkg-unknown-diagnosis.md).

## Что изменено и что остаётся ограничением

- Для Qwen3.8-27B параметр `chat_template_kwargs.enable_thinking=false`
  устранил пустые ответы из-за исчерпания лимита токенов на reasoning. Все
  40 извлечений dev+test завершились и прошли проверку графа. Один вызов в
  среднем занял 4,8 с на dev и 9,6 с на test.
- Парсер допускает числовые локальные ID и `?` для неименованной сущности;
  relation phrase может быть не каноническим именем свойства DBpedia. Это
  повышает валидность извлечения, но требует отдельного выравнивания отношений.
- Strict evidence выбирает лишь ребро между отображёнными концами claim.
  Expanded evidence читает настоящие incident triples для отображённого
  субъекта, включая альтернативные значения и обратные связи; оно не
  подменяет отсутствие факта доказательством False.
- Сохраняются ошибки разметки графа, entity linking и KG coverage. FTS shortlist
  не гарантирует глобальный top-5, beam search не гарантирует глобальный
  оптимум. Expanded evidence иногда остаётся пустым после найденного mapping.
- Гибрид использует текстовый контроль для 70% этих claims. Это рабочий способ
  не возвращать UNKNOWN, но пока не самостоятельный научный вклад по soft
  graph matching. Нужно оценивать его отдельно от чистого графового метода.

## Воспроизведение

Для каждого split создать отдельный `--work-dir`. `relations.json` можно
получить фазой `prepare`, которая загружает DBpedia. Ниже пример dev-20;
для test заменить `dev` на `test`, каталог на отдельный и B0-файл на
`data/evaluation/factkg-b0-test-500.json`.

```bash
PYTHONPATH=src python scripts/factkg_e1_pilot.py prepare \
  --work-dir data/evaluation/e1-pilot-itmo-qwen3_8-27b-open-dev
PYTHONPATH=src python scripts/factkg_e1_pilot.py extract \
  --work-dir data/evaluation/e1-pilot-itmo-qwen3_8-27b-open-dev \
  --split dev --limit 20 --server-url https://api.duckduck.cloud \
  --model iairlab/qwen3.8-27b --kilo-auth-provider itmo_lab \
  --json-mode object --extract-views 1 --open-relations --extract-max-tokens 512
PYTHONPATH=src python scripts/factkg_e1_pilot.py match \
  --work-dir data/evaluation/e1-pilot-itmo-qwen3_8-27b-open-dev \
  --split dev --limit 20 --evidence-mode expanded
PYTHONPATH=src python scripts/factkg_e1_pilot.py read \
  --work-dir data/evaluation/e1-pilot-itmo-qwen3_8-27b-open-dev \
  --split dev --limit 20 --server-url https://api.duckduck.cloud \
  --model iairlab/qwen3.8-27b --kilo-auth-provider itmo_lab \
  --json-mode object --reader-max-tokens 256
PYTHONPATH=src python scripts/factkg_e1_pilot.py hybrid \
  --work-dir data/evaluation/e1-pilot-itmo-qwen3_8-27b-open-dev \
  --split dev --b0-file data/evaluation/factkg-b0-dev.json
```

Файлы `extract.jsonl`, `match.jsonl`, `predictions.jsonl`, `summary.json`,
`hybrid.jsonl` и `hybrid-summary.json` сохраняются в work-dir. B0-файлы были
получены отдельной задачей #13 и должны присутствовать локально. Проверка
`make check`: 27 тестов прошли.

## Диагностика поиска кандидатов после первого прогона

На тех же 20 dev claims и сохранённых графах проверили три изменения:
дополнительный поиск по первому слову составного имени (для `Sauli Niinistö`),
точное совпадение ID DBpedia без начального артикля (для
`National_Park_Service`) и генерацию кандидатов для безымянного узла `?`
из соседних троек вместо пустого ID или литерала. Допустимое сопоставление
получено для 20/20 вместо 19/20; непустые расширенные evidence — для 9/20
вместо 7/20. Для памятника `14th_New_Jersey_Volunteer_Infantry_Monument`
появилась непосредственно относящаяся к claim тройка `owner` →
`National_Park_Service`.

Покрытие evidence не равно доказательству утверждения: для claim об
`Aleksey Chirikov` и `Sauli Niinistö` новое сопоставление связало `?` с
`Salo,_Finland` и нашло `placeOfBirth` → `Salo,_Finland`, что не проверяет
отношение руководства страной. Повторное чтение evidence моделью
`iairlab/qwen3.8-27b` завершилось таймаутом первого запроса через 300 с.
Поэтому значения Accuracy и UNKNOWN из предыдущего прогона ниже **не
обновлены**; улучшение качества ответа для изменений поиска кандидатов пока
не подтверждено. Перед финальным сравнением нужен повторный прогон reader и
проверка релевантности evidence, затем независимая выборка для оценки.

Основной фиксированный тест на 500 FactKG claims, B1/B2, доверительные
интервалы и воспроизведение SimGRAG ещё не выполнены.
