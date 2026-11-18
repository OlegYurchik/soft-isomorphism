# H11: H10 как структурный fallback после B1 UNKNOWN

Дата фиксации: 18.11.2026. Дизайн зафиксирован до запуска на независимых
FactKG dev SHA-256 ranks 1000–1499.

## Мотивация

На диагностических ranks 500–999 H10 улучшил H9, но уступил B1:

| Arm | Accuracy | Macro-F1 | UNKNOWN |
|---|---:|---:|---:|
| H9 | 22,0% | 0,352 | 374/500 |
| H10 | 52,2% | 0,644 | 199/500 |
| B1 | 59,6% | 0,699 | 160/500 |

Парный анализ показал, что H10 правильно решил 43 примера, ошибочных для
B1; в 32 из них B1 вернул UNKNOWN. Напротив, в 80 B1-only correct случаях
H10 вернул UNKNOWN 71 раз. UNKNOWN доступен во время inference и не требует
gold label, поэтому его можно использовать как заранее определённый gate.

## Гипотеза и алгоритм

**H11.** Если сначала запускать широкий lexical baseline B1, а H10-reader
вызывать только после ответа B1=UNKNOWN, структурное evidence H10 восстановит
часть нерешённых claims без потери уже правильных B1 verdicts.

1. Построить B1 evidence с теми же лимитом 20 и ranking, что в H10 diagnostic.
2. Qwen-reader возвращает `TRUE`, `FALSE` или `UNKNOWN` только по B1 evidence.
3. При `TRUE/FALSE` этот verdict окончательный; H10-reader не вызывается.
4. Только при `UNKNOWN` выполнить замороженный H10 retrieval: не более двух
   endpoint proposals на query node, path length 1–2, beam 64, weights
   node/edge 0,3/0,7, path penalty 0,1 и provenance penalty 0,15.
5. Если H10-reader вернул `TRUE/FALSE`, использовать его verdict; иначе
   сохранить UNKNOWN.

Reader фиксирован: `iairlab/qwen3.8-27b`, temperature 0, seed 42, thinking
disabled, одинаковый KG-only prompt. UNKNOWN считается ошибкой. Gold label и
gold Evidence не используются ни retrieval, ни gate.

## Arms и контроли

- `B1`: сильный основной baseline;
- `B1→H8`: fallback с contextual direct-edge evidence;
- `B1→H9`: fallback с edge-to-path, но без endpoint recovery;
- `B1→H10` (`H11`): полный предлагаемый метод.

Все fallback arms заменяют только B1=UNKNOWN. Поэтому они по конструкции не
могут потерять B1-correct claim в Accuracy; научный вопрос — сколько ошибок
они исправляют и нужен ли для этого именно механизм H10.

## Post-hoc diagnostic, не подтверждение

Правило сформулировано после просмотра ranks 500–999, поэтому цифры ниже
используются только для выбора H11 и не являются evidence её обобщаемости.

| Метод | Accuracy | Macro-F1 | UNKNOWN | Correct сверх B1 |
|---|---:|---:|---:|---:|
| B1 | 59,6% | 0,699 | 160 | — |
| B1→H8 | 61,0% | 0,710 | 152 | +7 |
| B1→H9 | 61,6% | 0,712 | 146 | +10 |
| B1→H10 | 66,0% | 0,740 | 119 | +32 |

Для post-hoc B1→H10: H11-only/B1-only correct = 32/0, exact two-sided
paired `p = 4,66e-10`; fallback был вызван для 160/500 (32%) claims.

## Независимый confirmatory run

Выборка: FactKG dev, стабильная сортировка по SHA-256, ranks 1000–1499.
Она не использовалась при формулировке H9–H11 и не пересекается с
diagnostic ranks 500–999. До результата запрещено менять retrieval,
reader, budgets, prompt, gate или пороги.

H11 подтверждается, только если одновременно:

- Accuracy выше B1 минимум на 3 п.п. (15/500 claims);
- H11-only correct > B1-only correct при exact two-sided paired `p < 0,05`;
- Macro-F1 не ниже B1 более чем на 0,01;
- UNKNOWN снижен минимум на 15% относительно B1;
- H11 восстанавливает минимум на 10 claims больше, чем `B1→H9`;
- fallback rate не выше 40%; отдельно считаются calls и токены reader.

При провале любого quality gate H11 не переносится на test. При успехе
параметры остаются замороженными и запускается заранее выбранный test subset.

## Confirmatory result on ranks 1000–1499

Независимый прогон выполнен без изменения алгоритма, reader, budgets или
gates. Все 500 claims обработаны одной моделью `iairlab/qwen3.8-27b`.

| Метод | Accuracy | Macro-F1 | UNKNOWN | Correct сверх B1 |
|---|---:|---:|---:|---:|
| B1 | 59,0% | 0,703 | 164 | — |
| B1→H8 | 61,2% | 0,720 | 152 | +11 |
| B1→H9 | 62,2% | 0,725 | 144 | +16 |
| B1→H10 (H11) | **66,8%** | **0,751** | **112** | **+39** |

Для главного контраста H11-only/B1-only correct = 39/0, exact two-sided
paired `p = 3,64e-12`. Fallback был вызван для 164/500 (32,8%) claims.
H11 восстановил на 23 правильных ответа больше, чем контроль `B1→H9`.

Все заранее зафиксированные gates пройдены:

- Accuracy gain: `+7,8` п.п. при пороге `+3`;
- paired `p = 3,64e-12` при пороге `0,05`;
- Macro-F1 вырос на `0,047`, а не снизился;
- UNKNOWN снизился на 31,7% при пороге 15%;
- преимущество восстановлений над `B1→H9`: 23 при пороге 10;
- fallback rate 32,8% при максимуме 40%.

Production-вариант H11 (`B1` + `H10`, без ablation arms) потребовал 646
уникальных model calls, 345 655 токенов и 402,37 с суммарного reader time.
Полный confirmatory run с H8/H9 controls потребовал 685 уникальных calls.

**Решение:** H11 подтверждена на независимой dev-выборке. Параметры
остаются замороженными; следующий этап — заранее фиксированный FactKG test
subset, после него перенос на второй benchmark.

## Замороженный test protocol

Test subset был выбран в исходном experiment design до экспериментов H9–H11:
первые 500 FactKG test claims после стабильной сортировки по SHA-256,
`offset = 0`. На test без изменений переносятся extraction prompt, Qwen model,
B1 budget, H10 matcher и UNKNOWN gate. Повторно применяются те же шесть gates,
что и на confirmatory dev; дополнительная настройка по test запрещена.

## Безопасная оптимизация исполнения

Изначальный исследовательский конвейер вычислял B4, H8, H9 и H10 для всех
claims, хотя H11 использует эти результаты только после `B1 = UNKNOWN`.
Оптимизированный конвейер разделён на две фазы: B1-reader работает для всех
claims, а графовый retrieval запускается только для UNKNOWN. Параметры,
формулы стоимости, пороги и reader prompt не менялись. Один и тот же
экземпляр замороженного ONNX encoder переиспользуется между B4–H10.

На фиксированном test-500 B1 вернул 153 UNKNOWN. Поэтому графовый retrieval
был полностью пропущен для 347 из 500 claims (69,4%). Строгая проверка по
эталонным артефактам дала 153/153 точных совпадения на каждом этапе B4, H8,
H9 и H10. Итоговый `reader-summary.json` также совпал побайтно
(`SHA-256 e1330507d9fe6ac84333a0ec8bf2dd070bec86377c79b43f4411247305134b49`):
Accuracy 65,0%, Macro-F1 0,7197, UNKNOWN 106. Значит, оптимизация сокращает
лишнюю работу, но не меняет экспериментальный результат.

Реализация: `scripts/factkg_h11_lazy_retrieval.py`; двухфазный reader:
`scripts/factkg_h11_unknown_fallback.py --phase b1|fallback`.

## Артефакты

- diagnostic B1 predictions: `data/evaluation/h8-dev-500-c7/predictions.jsonl`;
- diagnostic H9/H10 predictions:
  `data/evaluation/h10-dev-500-diagnostic/predictions.jsonl`;
- независимые артефакты должны храниться в каталогах с суффиксом
  `dev-500-confirm` и offset 1000;
- confirmatory retrieval:
  `data/evaluation/h11-dev-500-confirm-h10/retrieval-summary.json`;
- confirmatory reader:
  `data/evaluation/h11-dev-500-confirm-reader/reader-summary.json`.
- test lazy-retrieval verification:
  `data/evaluation/h11-test-500-lazy/summary.json`.
