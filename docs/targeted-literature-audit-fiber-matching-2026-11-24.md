# Targeted literature audit: node-to-subgraph soft matching

Дата поиска: 24.11.2026. Статус вывода: **кандидат на узкую гипотезу,
но не подтверждённая новизна**.

## 1. Что именно проверялось

После отрицательного end-to-end результата на HotpotQA была предложена
следующая идея: вместо отображения каждой вершины query graph в одну вершину
document graph разрешить ей отображаться в небольшое связное множество
вершин. Такое множество далее называется `fiber` (слой, или branch set).

Формально для query graph \(Q=(V_Q,E_Q)\) и document graph \(G=(V_G,E_G)\):

- обычный point matcher ищет \(f:V_Q\rightarrow V_G\);
- предлагаемый matcher ищет \(F:V_Q\rightarrow 2^{V_G}\), где
  \(1\leq |F(v)|\leq k\) и \(G[F(v)]\) связен;
- для каждого \((u,v)\in E_Q\) между \(F(u)\) и \(F(v)\) должен существовать
  семантически подходящий grounded path;
- все выбранные вершины и рёбра должны сохранять ссылки на исходные
  предложения;
- общий размер возвращаемого evidence фиксирован, чтобы прирост нельзя было
  объяснить только большим контекстом.

Аудит проверяет пять возможных заявлений:

1. ново ли само many-to-many / node-to-set сопоставление;
2. ново ли query edge → target path;
3. нова ли поддержка нескольких сущностей или ответов для одной переменной;
4. нова ли работа с n-ary facts, фрагментацией и разной гранулярностью;
5. остаётся ли более узкий незакрытый вопрос для document GraphRAG.

Поиск проводился по ACL Anthology, PVLDB, arXiv и публикациям по теории
графов. Запросы комбинировали `many-to-many graph matching`, `graph minor
branch set`, `path homomorphism`, `query graph edge to path`, `n-ary KGQA`,
`multi-answer QA`, `GraphRAG fragmentation`, `multi-granularity GraphRAG`,
`sentence provenance` и `connected subgraph matching`. Отсутствие найденной
работы не является доказательством её отсутствия; ниже отдельно указаны
проверенные совпадения и оставшийся риск.

## 2. Краткий вердикт

**Исходную формулировку нельзя заявлять как новую.** Она объединяет несколько
уже известных конструкций:

- отображение одной вершины в связный target subgraph структурно совпадает с
  `branch set` в модели графового минора;
- many-to-many graph matching с сопоставлением кластеров вершин формализован
  как минимум в 2010 году;
- query edge → target path формализован в path homomorphism и затем применён
  в SAFE и MGRAG;
- одна query variable, возвращающая множество сущностей, является обычной
  семантикой KGQA/SPARQL, а QAMPARI специально оценивает вопросы с большим
  числом ответов;
- n-ary evidence, фрагментация сущностей, multi-granularity graphs и
  provenance уже являются предметом HyperPathsRAG, HEAR-RAG, ReGraphRAG и
  FlowRAG.

Поэтому научный вклад нельзя формулировать как «мы впервые сопоставляем одну
вершину с несколькими» или «впервые восстанавливаем составное понятие».

## 3. Матрица ближайших работ

| Работа | Что уже сделано | Пересечение с идеей | Что работа не устанавливает |
|---|---|---|---|
| [Zaslavskiy et al., Many-to-Many Graph Matching](https://arxiv.org/abs/1004.4965) | Кластеры вершин одного графа сопоставляются с кластерами другого; задача задана как дискретная оптимизация с continuous relaxation | Прямо опровергает новизну generic node-to-set / many-to-many matching | Не GraphRAG, нет textual semantics и sentence provenance |
| [Joret & Wood, graph-minor branch sets](https://users.monash.edu/~davidwo/papers/CliqueMinors.pdf) | Вершина pattern graph представляется связным branch set в host graph; соседние branch sets должны соприкасаться | Предлагаемое связное множество является семантически взвешенным вариантом известной структуры | Нет soft semantic cost, retrieval budget и RAG |
| [Fan et al., Graph Homomorphism Revisited](https://vldb.org/pvldb/vol3/R103.pdf) | `p-hom` отображает pattern edges в непустые paths и учитывает similarity узлов | Теоретический предшественник edge-to-path matching | Отображение вершины остаётся point-valued; не document RAG |
| [SAFE](https://aclanthology.org/2025.emnlp-main.883/) | LLM pseudo-query graph; query edge удовлетворяется KG path ограниченной длины; schema-aware approximate join | Прямой GraphRAG/KGQA аналог topology relaxation | Не использует node-to-connected-set как явную переменную оптимизации |
| [MGRAG](https://doi.org/10.14778/3819518.3819565) | Point mapping query nodes → KG nodes, semantic aggregation target paths, lazy query-specific KG construction | Совпадают path matching и lazy expansion | В опубликованной формализации нет явного bounded fiber для query node |
| [HyperPathsRAG](https://aclanthology.org/2026.findings-emnlp.1530/) | N-ary subquestions совместно сопоставляются с hypergraph facts и evidence paths | Очень близко к мотивации «бинарный граф раздробил один факт» | Использует hypergraph decomposition, а не оптимизацию semantic branch sets |
| [HEAR-RAG](https://aclanthology.org/2026.emnlp-main.2210/) | Higher-order facts, source chunks и relation-aware clustering entity mentions объединяются в evidence hypergraph | Уже решает fragmentation, higher-order evidence и source grounding | Иная retrieval formulation; точное соответствие fiber matcher не найдено |
| [ReGraphRAG](https://aclanthology.org/2025.findings-emnlp.290/) | Реорганизует и обогащает фрагментированные document KGs перед retrieval | Прямо пересекается с мотивом graph fragmentation | Repair/reorganization вместо query-pattern branch-set matching |
| [FlowRAG](https://aclanthology.org/2026.findings-acl.1050/) | Строит heterogeneous graph passage–summary–sentence–entity и использует dual-granularity activation | Multi-granularity и sentence-level grounding уже не уникальны | Не найдено явного query node → bounded connected fiber |
| [QAMPARI](https://aclanthology.org/2023.gem-1.9/) | Open-domain вопросы с десятками возможных ответов и Wikipedia evidence | Подходящий stress test для answer cardinality | Multi-answer evaluation само по себе не является graph-matching вкладом |
| [Fact-Tree Reasoning](https://aclanthology.org/2022.findings-acl.66/) | N-ary KGQA рассматривает facts как единицы и строит reasoning tree | N-ary reasoning существовал до GraphRAG | Нет document extraction и нашего retrieval constraint |

## 4. Проверка возможных claims

| Возможное заявление | Вердикт | Причина |
|---|---|---|
| «Новый many-to-many soft graph matcher» | **Нельзя заявлять** | Many-to-many matching уже формализован; soft/inexact matching — большая существующая область |
| «Вершина запроса впервые отображается в связный подграф» | **Нельзя заявлять в общем виде** | Это близко к классическому branch-set / minor model |
| «Ребро запроса впервые соответствует пути» | **Нельзя заявлять** | p-hom, SAFE и MGRAG делают это явно |
| «Одна переменная впервые соответствует нескольким ответам» | **Нельзя заявлять** | Answer sets стандартны для KGQA; есть QAMPARI |
| «Первое решение разной гранулярности и раздробленных facts» | **Нельзя заявлять** | HyperPathsRAG, HEAR-RAG, ReGraphRAG и FlowRAG закрывают значительные части мотивации |
| «Первый provenance-preserving semantic branch-set matcher для document GraphRAG» | **Точного аналога в targeted search не найдено, но claim рискованный** | Компоненты известны по отдельности, а поиск не доказывает приоритет |
| «Первое контролируемое исследование robustness matching к split/merge/reification при равном evidence budget» | **Наиболее перспективный кандидат** | В проверенных работах не найден такой paired stress-test; требуется дополнительная проверка benchmark literature |

## 5. Рекомендуемая переформулировка гипотезы

Вместо гипотезы «fiber matching лучше point matching» предлагается проверять
конкретное свойство — устойчивость к изменению гранулярности представления.

> **H13-R (granularity robustness).** Если текстовое evidence остаётся тем
> же, но его графовое представление подвергается контролируемому node split,
> node merge или relation reification, bounded semantic branch-set matching
> сохраняет evidence-chain recovery и Answer F1 лучше, чем point-valued
> path matching и независимое top-k объединение, при одинаковом числе
> evidence sentences и без дополнительных LLM-вызовов во время retrieval.

В этой формулировке:

- объект исследования — не известная конструкция branch set сама по себе;
- независимая переменная — способ представления одного и того же evidence;
- измеряемый эффект — падение качества относительно неповреждённого графа;
- сравнение отделяет пользу согласованного set-valued matching от простого
  увеличения числа кандидатов;
- provenance нужен для проверки, что преобразования не меняют исходный текст.

Даже H13-R пока является **кандидатом**, а не готовым novelty claim.

## 6. Минимальный контрольный эксперимент

### Данные

Нужен новый development split, не использованный для выбора H8–H12 и не
входящий в финальные 500 HotpotQA примеров. Для каждого исходного grounded
graph автоматически строятся четыре версии:

1. `original` — граф без преобразований;
2. `split` — одна сущность представлена двумя узлами с сохранением всех
   исходных sentence IDs;
3. `merge` — две контекстно близкие сущности объединены;
4. `reified` — отношение заменено промежуточным event/relation node.

Преобразования обязаны сохранять исходные предложения и правильный ответ.
Сначала достаточно 50–100 вручную проверенных случаев. QAMPARI можно добавить
как вторичный real-world multi-answer benchmark, но он не заменяет
контролируемую проверку гранулярности.

### Методы

- `P1`: текущий point-valued B1/H12 matcher;
- `P2`: top-k point candidates без совместного ограничения;
- `P3`: preprocessing contraction/mention clustering + point matcher;
- `F1`: bounded branch-set matcher, \(k\in\{2,3\}\), с совместным score;
- `oracle`: matching по сохранённым gold provenance IDs — верхняя граница.

`P3` обязателен: если простое объединение раздробленных mentions даёт тот же
результат, сложный fiber matcher не нужен.

### Метрики

- `Evidence Recall@B` и Supporting F1 при одинаковом budget \(B\);
- Answer EM/F1 одним и тем же reader;
- `Robustness drop = score(original) - score(transformed)`;
- доля случаев, где найден полный provenance chain;
- latency, число рассмотренных states и peak memory;
- число дополнительных LLM calls — целевое значение во время matching: 0.

Основная статистика — paired difference между `F1` и каждым control на одних
и тех же вопросах, bootstrap CI и permutation test. Успех — меньший
robustness drop на всех трёх преобразованиях, а не только средний gain на
одном варианте.

## 7. Stop/go criteria до реализации полного алгоритма

### Go

Продолжать, только если одновременно выполнены условия:

1. полный разбор алгоритмов HyperPathsRAG и HEAR-RAG не обнаруживает
   эквивалентного query-unit → connected-set matching;
2. минимум 30% вручную проверенной pilot-выборки действительно содержит
   granularity failure у point matcher;
3. `P3` mention contraction не устраняет большую часть ошибок;
4. существует точный solver или beam search, не требующий новых LLM calls.

### Stop или переформулировать вклад

- HyperPathsRAG/HEAR-RAG уже реализуют эквивалентную переменную и objective;
- ошибки вызваны не granularity, а extraction omissions или reader failure;
- top-k union либо contraction не хуже fiber matcher;
- прирост появляется только при большем evidence budget;
- search overhead несоразмерен retrieval gain.

## 8. Итог аудита

Targeted audit **не подтверждает качественно новую гипотезу в исходном виде**.
Generic fiber matching представляет собой семантическую комбинацию известных
many-to-many matching, branch sets и path homomorphism. Ближайшие GraphRAG
работы дополнительно занимают n-ary, fragmentation, provenance и
multi-granularity части мотивации.

Остающийся исследовательский вопрос уже и проверяемее: даёт ли совместное
bounded branch-set matching устойчивость к *representation granularity
shift* при неизменном тексте и равном evidence budget. Наиболее честный
потенциальный вклад — формализация такого stress test, controls и
экспериментальный результат. До выполнения stop/go checks нельзя называть
это доказанной новизной или переходить к дорогому полному запуску.
