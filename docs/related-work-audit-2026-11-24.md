# Повторный аудит ближайших работ

Дата поиска: 24.11.2026. Цель аудита — проверить не общую близость к
GraphRAG, а наличие уже опубликованных методов с теми же ключевыми
операциями, что у текущего HotpotQA-прототипа:

1. LLM преобразует вопрос в небольшой query graph;
2. документы преобразуются в grounded triples;
3. query node сопоставляется с entity документа не только точно;
4. одному query edge разрешено соответствовать пути из одного-двух рёбер;
5. граф документа строится или раскрывается только для релевантного
   query-guided frontier;
6. найденные пути превращаются в ограниченный набор evidence для reader.

Поиск проведён по ACL Anthology, PVLDB и arXiv по сочетаниям `semantic
subgraph matching`, `query graph`, `edge-to-path`, `lazy graph construction`,
`multi-hop RAG` и `HotpotQA`. Ниже приведены только первичные публикации.

## Главный вывод

Широкая формулировка новизны **«мягкое сопоставление query-графа с графом
документов, где ребро может соответствовать пути» уже занята**. Особенно
близки SAFE и MGRAG:

- SAFE разрешает query edge соответствовать KG path в пределах заданной
  длины и ранжирует приближённые сопоставления;
- MGRAG одновременно использует ленивое query-specific построение графа и
  path-based semantic subgraph matching.

Следовательно, текущий результат следует позиционировать не как новый класс
graph matching, а как **лёгкую, training-free и provenance-preserving
реализацию известной идеи для text-only distractor QA**, с фиксированными
бюджетами и парной проверкой против sentence BM25. Даже эта узкая
формулировка пока является рабочим позиционированием, а не доказанной
публикационной новизной.

## Сравнение

| Работа | Что именно сопоставляется | Допускает topology mismatch | Как сокращает поиск | Обучение | Данные | Пересечение с нами | Что остаётся отличием |
|---|---|---|---|---|---|---|---|
| [SimGRAG](https://aclanthology.org/2025.findings-acl.163/) | LLM query pattern и KG subgraph; Graph Semantic Distance по nodes/relations | Семантика мягкая, но topology кандидата изоморфна pattern | Оптимизированный top-k subgraph search | Нет специального retriever training | MetaQA, WebQSP, CWQ, FactKG | LLM query graph, semantic graph distance, KG-RAG | Мы разрешаем query edge → path и работаем с document triples/provenance |
| [SAFE](https://aclanthology.org/2025.emnlp-main.883/) | LLM pseudo-query graph и KG | **Да:** query edge удовлетворяется KG path длины ≤ δ | Schema graph как компактный distance oracle, ranked search | Нет GNN training | WebQSP, CWQ, GrailQA | Очень близкая edge-to-path релаксация и согласованное subgraph matching | У нас нет schema graph; есть sentence provenance и distractor-document setting |
| [MGRAG](https://doi.org/10.14778/3819518.3819565) | Query graph и query-specific multimodal KG | **Да:** relation edge сопоставляется с семантически агрегированным path | **Lazy top-down KG construction**, остановка после найденного match | Training-free matcher | 7 multimodal QA datasets | Ближайший аналог: lazy construction + contextual semantic path matching | Мы text-only, используем exact-title frontier, max path 2, фиксированный evidence budget и не решаем KV caching |
| [NGM-RAG](https://arxiv.org/abs/2607.11159) | Nodes query graph и corpus graph | Косвенно через GNN neighbourhood, но не явное edge → path | Top-k node ranking | GINE arm обучается; LightGCN arm parameter-free | HotpotQA, MultiHop-RAG, UltraDomain | Одинаковые LLM graph construction, lexical + structural signals, HotpotQA | У нас явные пути и grounded sentences, нет GNN и обучения |
| [HyperPathsRAG](https://aclanthology.org/2026.findings-emnlp.1530/) | Набор n-ary subquestions и hypergraph paths | Да, через совместное multi-target path retrieval | Chain-completeness scoring | Не является нашим детерминированным matcher | HotpotQA, 2Wiki, MuSiQue hard subsets | Multi-hop path retrieval и HotpotQA candidate-passage setting | У нас бинарные triples, единый query graph и явное node mapping; у них гиперграф и n-ary decomposition |
| [GRAG](https://aclanthology.org/2025.findings-naacl.232/) | Query и textual subgraph | Soft pruning, но не наш явный edge-to-path mapping | Divide-and-conquer по ego-graphs | Graph encoder/prompt components | Graph-text tasks, включая WebQSP | Извлечение компактного связного textual subgraph | Иная целевая функция и представление запроса |
| [TopoRAG](https://aclanthology.org/2026.findings-acl.1703/) | Query embedding и множество KG entities | Diameter constraint вместо query-pattern alignment | Topology-aware ANN | Не требует нашего LLM matcher | KG retrieval benchmarks | Контроль шума и связности retrieval | Нет query graph и семантического edge-to-path сопоставления |
| [G³RAG](https://arxiv.org/abs/2609.19622) | Query seeds и document embedding graph | Controlled one-step diffusion | Геометрические edge weights, без LLM extraction | Нет | HotpotQA, 2Wiki, MuSiQue | Дешёвое graph-guided расширение документов на HotpotQA | Вообще не строит entity-relation query/document graphs; существенно дешевле |

## Что нельзя заявлять

- «Первое мягкое сопоставление графов для RAG» — уже есть SimGRAG, SAFE,
  MGRAG и NGM-RAG.
- «Первое сопоставление query edge с KG path» — явно есть SAFE и MGRAG.
- «Первое ленивое построение query-specific document KG» — явно есть MGRAG.
- «Первый graph-guided multi-hop retrieval на HotpotQA» — NGM-RAG,
  HyperPathsRAG, G³RAG и другие уже оцениваются на HotpotQA.

## Защищаемая узкая формулировка текущей работы

> Мы проверяем, может ли компактный training-free matcher с согласованным
> отображением узлов, contextual edge-to-path similarity и сохранением
> sentence provenance улучшить sentence BM25 при одинаковом evidence budget
> в HotpotQA distractor setting. Чтобы ограничить стоимость LLM extraction,
> граф документов строится только по exact-title seeded frontier размером
> четыре. Вклад текущего этапа — не изобретение edge-to-path matching, а
> воспроизводимый дизайн, component controls и независимая парная оценка его
> качества и стоимости.

Эта формулировка честно отделяет реализацию от существующих алгоритмических
идей. Если финальный evaluation-500 не покажет значимого прироста Answer F1,
вклад следует сузить ещё сильнее до отрицательного экспериментального
результата: улучшение retrieval recall не гарантирует улучшение ответа и
требует большого LLM extraction overhead.

## Что сравнивать дальше

1. **Обязательный conceptual reference — MGRAG**, потому что совпадают обе
   центральные операции: lazy graph construction и semantic edge-to-path
   matching.
2. **Обязательный algorithmic reference — SAFE**, потому что он формализует
   устойчивость к промежуточным KG nodes через approximate distance join.
3. **Обязательный benchmark reference — NGM-RAG**, потому что он использует
   HotpotQA distractor и 500 вопросов, хотя неизвестно совпадение sample IDs.
4. **Efficiency control — G³RAG**, потому что он показывает альтернативу без
   LLM graph extraction на HotpotQA.
5. Для прямого численного сравнения нельзя переносить опубликованные числа в
   одну таблицу как head-to-head результат без одинаковых IDs, reader,
   contexts и evidence budget. Корректны conceptual comparison и наш парный
   B1 control; репликация чужого кода является отдельным экспериментом.
