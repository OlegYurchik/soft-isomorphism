# H14: certified provenance-constrained soft matching

Статус: новая основная гипотеза-кандидат после targeted audit. Дата:
24.11.2026. Новизна предварительная, а не установленный приоритет.

## 1. Научная проблема

Текущий matcher возвращает лучшее отображение query graph в document graph и
его score. Но score не отвечает на более важный вопрос:

> Изменится ли выбранная evidence chain, если LLM-extractor допустил одну
> правдоподобную структурную ошибку?

Два почти одинаковых извлечения одного предложения могут отличаться:

- алиас представлен отдельной вершиной или объединён с сущностью;
- отношение записано прямым ребром или через промежуточный event node;
- одна grounded triple пропущена;
- relation label перефразирован;
- одно составное утверждение разбито на две triples.

Обычный soft matcher всегда выдаёт победителя, даже если победитель меняется
после одной такой операции. Confidence LLM или semantic score не являются
гарантией устойчивости.

## 2. Идея, отличающая H14 от предыдущих гипотез

H14 не добавляет ещё один retrieval heuristic. Она меняет контракт matcher:

```text
обычный matcher:    query + extracted graph -> best evidence
H14 matcher:        query + extracted graph -> best evidence
                                           + certified edit radius
                                           + failure witness
```

`Certified edit radius r` означает: для всех допустимых
provenance-preserving вариантов графа, отличающихся не более чем на `r`
операций, выбранный набор исходных evidence sentences остаётся тем же.

Если сертификат построить нельзя, алгоритм возвращает конкретный
контрпример: какая правдоподобная операция меняет победителя и какое evidence
становится альтернативой. Это позволяет отличить устойчивое graph evidence
от случайного результата extraction.

## 3. Формальная постановка

Пусть:

- `Q` — query graph;
- `G` — извлечённый document graph;
- `P(x)` — множество sentence IDs, из которых получен graph element `x`;
- `M(Q,G)` — множество допустимых soft mappings;
- `S(m;Q,G)` — score mapping `m`;
- `E(m)` — множество исходных evidence sentence IDs mapping `m`.

Определим семейство допустимых преобразований `T_P`, которые не добавляют
новый текстовый источник и сохраняют provenance:

1. `alias-split/merge` внутри одного provenance component;
2. `edge-reify/unreify` с тем же sentence ID;
3. `relation-paraphrase` из заранее ограниченного semantic neighbourhood;
4. удаление одной низкоуверенной extracted triple;
5. `triple-split/join`, если обе части grounded в одном предложении.

Множество возможных миров радиуса `r`:

```text
U_r(G, P) = {G' | G' получен из G не более чем r операциями из T_P}.
```

Для победителя `m*` требуется не неизменность внутренних node IDs, а
неизменность текстового evidence:

```text
forall G' in U_r(G,P):
    E(argmax_m S(m; Q,G')) = E(m*).
```

Это существенно: split или reification меняют вершины и рёбра, но не должны
менять предложения, которые алгоритм считает доказательством.

## 4. Предлагаемый алгоритм

### 4.1 Candidate mappings

Текущий beam search расширяется до `k-best` mappings. Для каждого mapping
хранятся:

- score;
- evidence sentence set;
- использованные graph elements;
- provenance каждого элемента;
- локальный вклад каждого node/edge alignment.

Mappings с одинаковым evidence set объединяются: сертифицируется retrieval,
а не внутренний способ пройти по графу.

### 4.2 Adversarial sensitivity

Для каждой допустимой операции `t` вычисляется верхняя граница того, насколько
она может уменьшить разницу между победителем `m*` и конкурентом `m`:

```text
impact(t, m*, m) >=
    [S(m*; G) - S(m; G)] - [S(m*; t(G)) - S(m; t(G))].
```

Для аддитивного matching score воздействие локализуется на изменяемых
node/edge terms. Поэтому не нужно повторно запускать LLM и в пилоте можно
пересчитать только затронутые mappings.

### 4.3 Certificate

Пусть `margin(m) = S(m*;G) - S(m;G)`. Для каждого конкурента ищется
максимальное суммарное воздействие не более чем `r` совместимых операций.
Если для всех конкурентов

```text
margin(m) > worst_impact_r(m*, m),
```

то evidence `E(m*)` сертифицировано на радиусе `r`.

На первом этапе `worst_impact` можно считать точно перебором при `r <= 2` и
маленьких query graphs. Затем возможна branch-and-bound или knapsack bound.
Сертификат должен быть **sound**: разрешены ложные отказы в сертификации, но
не разрешён сертификат, нарушаемый допустимым преобразованием.

### 4.4 Failure witness

Если сертификата нет, алгоритм возвращает минимальный набор операций,
меняющий evidence winner:

```text
original evidence -> operation(s) -> competing evidence.
```

Это не объяснение от LLM, а воспроизводимый контрпример к устойчивости
retrieval.

## 5. Основная гипотеза

> **H14.** Для semantic graph retrieval значительная часть ошибочных
> evidence chains имеет нулевой certified provenance-preserving edit radius.
> Отбор или fallback по сертификату радиуса `r >= 1` повышает Evidence
> Precision и Answer F1 на принятой части примеров по сравнению с отбором по
> raw matching score при сопоставимой coverage. Сертификат остаётся sound на
> исчерпывающем наборе допустимых преобразований.

Гипотеза состоит из двух независимо опровергаемых частей:

1. **формальная:** certifier никогда не принимает evidence, которое можно
   изменить допустимой операцией в заявленном радиусе;
2. **эмпирическая:** certified radius полезно предсказывает правильность, а
   не является константой или дубликатом raw score.

Даже если вторая часть не подтвердится, корректный certifier и анализ причин
его бесполезности остаются отдельным алгоритмическим результатом. Однако
публикационный вклад будет слабым, если сертификат почти всегда нулевой.

## 6. Почему это не просто инженерный прирост

- вводится новый формальный контракт retrieval — invariance guarantee;
- задаётся специфичный для text-to-graph extraction класс допустимых
  provenance-preserving perturbations;
- требуется доказать soundness сертификата;
- результат включает проверяемый failure witness;
- качество оценивается не только Answer F1, но и certified coverage,
  soundness и selective risk;
- алгоритм не требует новой LLM-эвристики или дополнительного prompt chain.

Новизна не в понятии certified robustness вообще. Она может находиться в
сертификации **semantic evidence-chain matching** относительно ошибок
извлечённого document graph с сохранением sentence provenance.

## 7. Что уже существует и где граница claim

| Направление | Известный результат | Почему H14 не должна повторять его |
|---|---|---|
| [Uncertain subgraph matching](https://linqs.org/assets/resources/moustafa-icde14.pdf) | Pattern queries по probabilistic entity graphs с identity, attribute и edge uncertainty | Нельзя заявлять «первый matcher неопределённых графов»; H14 сертифицирует evidence invariance под provenance-preserving rewrites |
| [Certified visual graph matching](https://openreview.net/pdf?id=zkzf0VkiNv) | Randomized smoothing сертифицирует deep visual correspondence при feature perturbations | Нельзя заявлять «первая сертификация graph matching»; у нас дискретные extraction rewrites и textual evidence sets |
| [Certified GNN robustness](https://www.usenix.org/conference/usenixsecurity25/presentation/li-jiate) | Гарантии для node/graph classification при edge/node/feature attacks | Наша задача — combinatorial evidence retrieval, не GNN classification |
| [RobustRAG](https://openreview.net/pdf?id=qsEeACAJjD) | Certifiable robustness ответа к внедрённым/испорченным passages | Нельзя заявлять «первый certified RAG»; H14 рассматривает внутреннюю text-to-graph representation и retrieval winner |
| [RAGSentinel](https://aclanthology.org/2026.emnlp-main.546/) | Сертифицируемое удаление poisoned documents через geometric consensus | Threat model — adversarial documents, а не extraction-equivalent graphs |
| [C2RAG](https://arxiv.org/abs/2603.14828) | Constraint-based retrieval, sufficiency check, textual recovery и lower bound на вероятность top candidate | Ближайшая robust GraphRAG работа, но в проверенной формализации нет гарантии неизменности evidence при всех допустимых graph rewrites |

Targeted search не обнаружил точного аналога H14, но это не доказательство
приоритета. До claim «first» необходим отдельный systematic search по
`robust combinatorial optimization`, `sensitivity analysis of graph matching`,
`certain answers on uncertain graphs` и database provenance.

## 8. Минимальный falsification pilot

Полный GraphRAG запуск пока не нужен.

### Выборка

- 50 новых HotpotQA dev examples, не использованных в H8–H12;
- сохранённые query/document graphs и sentence provenance;
- только вопросы, где найдено минимум два разных evidence candidates.

### Perturbation set v0

Включить только три строго проверяемые операции:

1. edge reification/unreification;
2. alias split/merge по exact normalized label;
3. удаление одной triple с confidence ниже порога.

Это уже позволяет проверить алгоритм. Relation paraphrase и triple split/join
добавляются только после ручной проверки, что они сохраняют семантику.

### Сравнения

- `B1`: winner по текущему score;
- `Margin`: abstention по разнице top-1/top-2 без сертификата;
- `Augmentation`: усреднение score по явно сгенерированным вариантам;
- `H14`: certified radius + fallback при `r=0`;
- `Oracle`: исчерпывающий перебор всех миров `r<=1`.

### Метрики

- `certificate soundness`: доля сертификатов без контрпримера в exhaustive
  oracle; требуется 100%;
- `certified coverage@r`: доля примеров с radius не ниже `r`;
- risk–coverage curve по Evidence Precision и Answer F1;
- корреляция radius с правильностью;
- дополнительное время и число LLM calls; новых LLM calls должно быть 0;
- насколько H14 лучше простого top-1/top-2 margin при одинаковой coverage.

### Решение после пилота

`GO`, если:

- soundness = 100%;
- coverage при `r>=1` не ниже 20%;
- radius лучше raw margin разделяет правильные и ошибочные retrieval cases;
- найден хотя бы один реальный пример, где большой raw score ошибочен, но
  сертификат корректно обнаруживает нестабильность.

`STOP`, если:

- radius почти всегда 0 или всегда максимален;
- raw margin даёт ту же selective-risk curve;
- допустимые rewrites невозможно определить без неоднозначного LLM judge;
- последующий systematic review обнаруживает эквивалентный формальный
  сертификат.

## 9. Практический вывод

H14 заметно сильнее H13-R как кандидат на алгоритмическую новизну. H13-R
только измеряет чувствительность к гранулярности; H14 строит matcher с
проверяемой гарантией и контрпримером. При этом пилот дешёвый: существующие
графы и scores можно переиспользовать, а все первые преобразования
детерминированы.

Следующий шаг — не полный эксперимент, а реализация exhaustive oracle и
certifier для `r=1` на 10–20 примерах. Это быстро покажет, является ли
сертификат содержательным или сводится к обычному score margin.
