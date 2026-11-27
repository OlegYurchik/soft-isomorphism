# H10: path-guided endpoint linking для edge-to-path matching

Дата фиксации: 15.11.2026. Ветка задачи #19.

## Мотивация

H9 разрешил сопоставлять одно query edge с направленным KG-путём
длины 1–2. На диагностических 500 FactKG dev claims он поднял
path coverage с 219/767 (28,55%) у H8 до 239/767 (31,16%), не потеряв
ни одного пути H8. Прирост 2,61 п.п. не прошёл gate 5 п.п.

Последующий oracle показал:

- в полном KG pool имеются 152/242 gold paths длины 2;
- между исходными entity candidates достижимы только 20/242;
- H9 выбрал 8/20 достижимых.

Следовательно, одного edge-to-path scoring недостаточно: нужно
восстанавливать пропущенный конец сопоставления. При этом наивное
расширение H7 уже ухудшало coverage, поэтому H10 ограничивает число
новых кандидатов и явно штрафует их происхождение.

## Гипотеза

**H10.** Если добавить в домен каждого query node не более двух
KG endpoints, предложенных лучшими путями от уже связанного соседнего
узла, а в mapping cost штрафовать такое расширение, H10 покроет больше
gold paths, чем H9, без деградации уже покрытых H9 paths.

## Алгоритм

1. Входные query graph, initial entity domains и KG pool идентичны H9.
2. Для query edge `u -> v` и каждого исходного кандида `u`
   перечисляются направленные простые KG paths длины 1–2; их концы
   предлагаются для `v`. Симметрично пути, заканчивающиеся в исходных
   кандидатах `v`, предлагают начала для `u`.
3. Дешёвый proposal score:
   `0.7 * cosine(query_relation, relation_sequence)`
   `+ 0.3 * (1 - label_distance(query_node, endpoint))`
   `- 0.1 * (path_length - 1)`.
   Relation sequence кодирует тот же MiniLM, но без полных endpoint texts;
   это сокращает поиск с десятков тысяч полных путей на claim.
4. На каждый query node добавляются не более `2` новых endpoints.
   Исходные кандидаты не удаляются; один endpoint добавляется только один раз
   по лучшему его proposal.
5. H9 edge-to-path beam search повторяется на расширенных domains.
   Его path penalty `0.1`, node/edge weights `0.3/0.7`, beam width 64,
   инъективность и 80% node coverage не меняются.
6. К node cost добавляется `0.15` за каждый mapping в endpoint,
   которого не было в initial domain. Штраф усредняется вместе с
   остальной node cost и затем умножается на node weight `0.3`.

## Контрасты и gate

- `H8`: contextual edge-to-edge с initial domains;
- `H9`: edge-to-path с initial domains;
- `H10`: path-guided expansion + edge-to-path;
- `B1`: внешний baseline.

Текущие 500 claims остаются диагностическими, так как H10 выведена из
их анализа. Параметры выше фиксируются до запуска. H10 проходит gate,
если одновременно:

- overall path coverage выше H9 минимум на 5 п.п.;
- покрыто минимум 18 gold paths длины 2 против 8 у H9;
- non-empty evidence не ниже 245/500;
- число потерянных H9 gold paths не превышает числа новых;
- expanded endpoint используется best mapping минимум в 10 claims.

При успехе параметры замораживаются для неиспользованных FactKG dev
SHA-256 ranks 1000–1499. Reader запускается только после retrieval gate.

До первого reader-запуска также фиксируется end-to-end gate. На тех же
500 диагностических claims H10 должен одновременно:

- превысить Accuracy H9 минимум на 5 п.п. (25/500 claims);
- снизить число UNKNOWN относительно H9;
- не снизить Macro-F1 более чем на 1 п.п.;
- иметь больше H10-only correct verdicts, чем H9-only, при exact
  two-sided paired `p < 0,05`.

Все arms оценивает один `iairlab/qwen3.8-27b` reader с temperature 0,
одинаковым KG-only prompt и UNKNOWN как ошибкой. Если end-to-end gate не
пройден, H10 считается retrieval-улучшением, но не переносится на
новую выборку. Это избегает расхода на 500 новых LLM extractions до
проверки того, что рост retrieval превращается в рост качества ответа.

## Диагностический результат на 500 dev claims

Параметры из дизайна не менялись. H10 использовал те же query graphs,
KG pools, encoder и beam search, что H9. Различались только заранее
зафиксированные endpoint proposals и provenance penalty.

| Метод | Claims с evidence | Среднее triples/claim | Path coverage | Gold length 1 | Gold length 2 |
|---|---:|---:|---:|---:|---:|
| B1 | 481/500 | 19,186 | 416/767 = 54,24% | 387/517 | 29/242 |
| H8 | 178/500 | 0,458 | 219/767 = 28,55% | 219/517 | 0/242 |
| H9 | 245/500 | 0,826 | 239/767 = 31,16% | 231/517 | 8/242 |
| H10 | 481/500 | 1,744 | 321/767 = 41,85% | 293/517 | 28/242 |

H10 изменил best mapping и использовал хотя бы один расширенный
endpoint в 368/500 claims. В точном парном сравнении gold paths H10
покрывает 85 paths, которых нет у H9; H9 покрывает три, которых
нет у H10. Exact two-sided sign/McNemar test для этого retrieval contrast:
`p = 7,34e-22`. Это диагностическая, а не подтверждающая статистика.

H10 прошёл все зафиксированные retrieval gates:

- прирост coverage относительно H9: `+10,69` п.п. при пороге 5;
- gold paths длины 2: 28 при пороге 18;
- non-empty evidence: 481/500 при порге 245;
- 85 новых paths против трёх потерянных;
- expanded endpoint использован в 368 claims при пороге 10.

## End-to-end reader, 18.11.2026

После восстановления ITMO LiteLLM один и тот же
`iairlab/qwen3.8-27b` reader был запущен на всех 500 claims. Prompt,
temperature 0 и правило `UNKNOWN = error` одинаковы для arms.

| Метод | Accuracy | Macro-F1 | UNKNOWN |
|---|---:|---:|---:|
| H9 | 22,0% | 0,352 | 374/500 |
| H10 | 52,2% | 0,644 | 199/500 |
| B1 | 59,6% | 0,699 | 160/500 |

Относительно непосредственной ablation H9 H10 прошёл весь reader-gate:
Accuracy выросла на 30,2 п.п., Macro-F1 — на 0,292, UNKNOWN стало меньше
на 175. H10-only correct / H9-only correct = 153/2, exact two-sided
paired `p = 5,29e-43`.

Однако сильный простой B1 остаётся лучше H10: разница Accuracy
`-7,4` п.п., Macro-F1 `-0,055`, UNKNOWN на 39 больше. В парном сравнении
H10-only correct / B1-only correct = 43/80, exact two-sided
`p = 0,00108`. Поэтому рост структурного retrieval относительно H9
превратился в рост качества ответа, но не дал улучшения над B1.

**Решение:** локальная гипотеза H10 против H9 поддержана, а основная
гипотеза о превосходстве над сильным baseline B1 отклонена. H10 не
переносится на независимые ranks 1000–1499 как кандидат на подтверждение.
Следующий эксперимент должен быть сформулирован после парного анализа
43 H10-only и 80 B1-only ошибок; естественный контроль — проверка
заранее заданного hybrid/gating правила, а не дальнейшее увеличение
domain expansion.

Возобновляемый запуск reader зафиксирован одной командой:

```bash
scripts/run_h10_reader.sh
```

Скрипт не меняет дизайн и не перезаписывает завершённые ответы:
каждая строка кэша проверяется по model id и SHA-256 evidence.

Локальные сырые артефакты: `data/evaluation/h10-dev-500-diagnostic/`.
