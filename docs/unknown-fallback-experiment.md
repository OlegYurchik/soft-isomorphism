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

## Component ablation H10

После подтверждения H11 выполнена post-hoc ablation внутренних компонентов
H10. Выбор упрощённой конфигурации сделан на confirmatory dev-500; test-500
использован один раз только для проверки уже выбранного варианта. Reader,
модель и B1 UNKNOWN gate не менялись. Ответ полного H10 переиспользовался при
совпадающем evidence, поэтому новые model calls делались только для
изменившихся prompts.

| Конфигурация на dev-500 | Accuracy | Macro-F1 | UNKNOWN | Correct сверх B1 |
|---|---:|---:|---:|---:|
| Полный H10 | 66,8% | 0,751 | 112 | +39 |
| Только одношаговые endpoint proposals | 66,6% | 0,748 | 112 | +38 |
| Один новый кандидат на вершину | 67,0% | 0,753 | 113 | +40 |
| Без штрафа нового кандидата | 66,8% | 0,751 | 112 | +39 |
| Только прямые edge alignments | 66,4% | 0,747 | 113 | +37 |
| `lean`: один кандидат, без штрафа | **67,0%** | **0,752** | **112** | **+40** |
| `lean` + одношаговые proposals | 66,6% | 0,750 | 115 | +38 |
| `minimal`: также только прямые alignments | 66,2% | 0,744 | 114 | +36 |

По dev выбран `lean`: для каждой query-вершины добавляется только лучший
новый endpoint-кандидат, отдельный penalty для него не применяется.
Одно-/двухшаговые proposal-пути и одно-/двухшаговые edge alignments
сохранены: их удаление снизило dev accuracy.

На test-500 выбранный `lean` получил Accuracy **65,4%** против 65,0% полного
H10, Macro-F1 **0,7249** против 0,7197 и 34 correct сверх B1 против 32.
UNKNOWN изменился с 106 до 107. Следовательно, второй endpoint-кандидат и
expanded-node penalty не нужны для наблюдаемого прироста; их удаление не
ухудшило качество на dev и test. При этом прямой вызов ядра H10 без B4/H8/H9
дал 153/153 точных совпадения с прежним test retrieval, поэтому эти три
ступени остаются только экспериментальными controls, а не частью production
алгоритма.

Скрипты: `scripts/factkg_h10_component_ablation.py` и
`scripts/factkg_h10_ablation_reader.py`.

## Нужна ли глобальная согласованность графа

Следующая ablation проверяет центральную часть soft graph matching. Контроль
`independent-edges` использует тот же lean endpoint expansion, тот же
MiniLM encoder и те же одно-/двухшаговые KG paths, но выбирает лучший путь
для каждого query-ребра отдельно. Общего отображения query-вершин,
инъективности и graph-level beam search в контроле нет; одна общая
query-вершина может получить разные KG-образы в соседних рёбрах.

На confirmatory dev-500 evidence изменился в 103/164 fallback claims:

| Метод | Accuracy | Macro-F1 | UNKNOWN | Correct сверх B1 |
|---|---:|---:|---:|---:|
| H10-lean, согласованный граф | **67,0%** | 0,7519 | **112** | **+40** |
| Независимые рёбра | 66,8% | **0,7521** | 115 | +39 |

Verdict совпал в 151/164 fallback claims. Lean был единственным правильным
в 6 случаях, independent-edges — в 5. Разность одного правильного ответа не
даёт свидетельства, что глобальная согласованность необходима. Поэтому на
этом наборе гипотеза о преимуществе joint soft graph matching **не
подтверждена**; aggregate accuracy полного H10 и independent-edges одинакова.

Для независимой проверки до просмотра результата зафиксирован следующий
dev-срез: SHA-256 ranks 1500–1999. Extraction выполнен тем же
`iairlab/qwen3.8-27b`, одним open-relation view; lean и independent-edges
заморожены без последующей настройки. Срез не следует использовать для
нового выбора параметров.

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
- H10 component ablation:
  `data/evaluation/h10-component-ablation-dev-500-confirm/` и
  `data/evaluation/h10-component-ablation-test-500/`.
