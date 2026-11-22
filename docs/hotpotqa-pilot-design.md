# HotpotQA transfer pilot

Дата фиксации: 22.11.2026, до получения reader answers на HotpotQA.

## Цель и границы

Проверить, переносится ли структурный retrieval из FactKG в multi-hop QA.
HotpotQA distractor — общий benchmark с NGM-RAG, но этот пилот не является
репликацией NGM-RAG: неизвестны их sample IDs, используется другой retriever
и другая reader model.

Первый этап — **feasibility на первых 20 IDs** из уже зафиксированного списка
`development` в `configs/splits/hotpotqa-e1.json`. Остальные 180 development
и все 500 evaluation IDs не используются до фиксации рабочего pipeline.

## Данные и запрет утечки

Runtime получает только `id`, `question` и десять distractor contexts с
исходными `(title, sentence_id)`. `answer` и `supporting_facts` доступны
только evaluator. Исходный parquet имеет SHA-256
`c20b638ca82b21d04fe12e14ff417ad05153d4d215a65de54497fca4e972f7c6`.

## B1-Hotpot: простой baseline

1. Развернуть десять contexts в отдельные предложения с provenance.
2. Ранжировать все предложения BM25 относительно полного question;
   `k1=1.5`, `b=0.75`, lower-case alphanumeric tokenization.
3. При равном score сортировать по `(title, sentence_id)`.
4. Передать top-5 предложений Qwen3.8-27B reader.
5. Reader получает только question и evidence и возвращает один короткий
   JSON answer. Temperature 0, seed 42, max output 128.

Evidence budget 5 замораживается для B1 и будущего graph arm.

## Планируемый structured arm

Для каждого context paragraph Qwen извлекает grounded relation triples с
provenance `(title, sentence_id, exact quote)`. Query graph извлекается из
question с неизвестным answer endpoint.

Feasibility-настройка после первых 14 вызовов: query output budget 512;
context budget 1536; не более 8 центральных edges и 12 nodes на paragraph.
Причина зафиксирована в raw cache: 10/12 первых context outputs были
обрезаны при 1024 токенах, два использовали уникальный node label вместо
локального ID. Последний формат нормализуется только при одном точном
совпадении label; остальные grounding-проверки не ослабляются. После этой
нормализации применяется тот же принцип H10-lean:

- lexical/semantic anchors query nodes в context graph;
- один лучший новый endpoint candidate на query node;
- сопоставление query edge с направленным context path длины 1–2;
- не более пяти уникальных provenance sentences как evidence;
- тот же reader и prompt, что у B1-Hotpot.

Evidence budget фиксирован до получения structured reader results. Сначала
берутся уникальные предложения из найденных graph paths в порядке matcher,
затем свободные места до пяти заполняются BM25-предложениями. Если query
graph невалиден или matcher не нашёл ни одного grounded path, structured arm
использует ровно B1 evidence. Невалидный context paragraph не даёт triples,
но не отменяет валидные grounded paths из остальных paragraphs. Для каждого
примера сохраняются режим `graph`/`fallback`, число доступных triples и
число graph-selected sentences.

Flat sentence ranking и structured retrieval отличаются только выбором
пяти evidence sentences. Corpus extraction кешируется и не получает gold.

## Метрики

- official-style answer Exact Match и token F1;
- supporting-fact Precision, Recall, F1 и exact set match по
  `(title, sentence_id)`;
- invalid reader answers;
- Qwen calls, tokens, model time и retrieval wall time.

Feasibility-20 не используется для научного сравнения и не имеет quality
gate. Готовность к development-200 требует: корректно загружены 20/20
примеров; provenance не теряется; baseline и evaluator детерминированы;
каждый метод возвращает не более пяти предложений; все ошибки остаются в
знаменателе. После технической проверки параметры graph extraction и
matching фиксируются до запуска development-200, затем отдельно — до
evaluation-500.

## B1 feasibility result

На первых 20 development IDs baseline завершён без invalid answers:

| Метрика | Результат |
|---|---:|
| Answer Exact Match | 35,0% |
| Answer token F1 | 50,96% |
| Supporting-fact exact set match | 0,0% |
| Supporting-fact Precision | 25,0% |
| Supporting-fact Recall | 53,75% |
| Supporting-fact F1 | 33,69% |

Reader потребовал 20 Qwen calls, 7 297 токенов и 13,41 с model time.
BM25 retrieval занял 0,006 с. Нулевой exact set match при recall выше 50%
показывает конкретный режим ошибки: плоский ranking часто находит часть
supporting chain, но добавляет distractors или пропускает второй hop.

## Результат structured feasibility

Строгую проверку прошли 16/20 query graphs и 179/200 context paragraph
graphs. Structured retrieval сработал на 16 примерах, четыре использовали
заранее определённый fallback к B1. Сравнение при одинаковом бюджете из
пяти evidence sentences:

| Метрика | B1-Hotpot | Structured | Δ |
|---|---:|---:|---:|
| Answer Exact Match | 35,00% | 35,00% | 0,00 п.п. |
| Answer token F1 | 50,96% | 51,08% | +0,12 п.п. |
| Supporting-fact exact set match | 0,00% | 0,00% | 0,00 п.п. |
| Supporting-fact Precision | 25,00% | 25,00% | 0,00 п.п. |
| Supporting-fact Recall | 53,75% | 52,92% | −0,83 п.п. |
| Supporting-fact F1 | 33,69% | 33,51% | −0,18 п.п. |

По answer F1 structured arm улучшил 2 примера, ухудшил 2 и не изменил 16.
Это не свидетельство выигрыша: эффект практически нулевой и нестабильный.
Финальный кеш содержит 220 extraction results и 197 448 токенов; с учётом
первого формата и повторов реально выполнен 261 extraction call на 238 156
токенов. Для сравнения, B1 reader использовал 7 297 токенов. Таким образом,
текущая реализация приблизительно в 33 раза дороже по model tokens полного
B1 feasibility run и не улучшает retrieval metrics.

Решение после feasibility: не запускать эту конфигурацию на development-200.
Проверена реализуемость переноса H10-lean, но не подтверждена его полезность
поверх sentence BM25 на HotpotQA. Следующая модификация должна сначала
устранить главный источник overhead: не извлекать LLM-граф для всех десяти
paragraphs. Следующий контроль фиксируется как shortlist из трёх paragraphs,
упорядоченных по позиции их лучшего предложения в том же sentence BM25;
затем graph extraction и matching выполняются только внутри shortlist. До
reader run он должен показать снижение extraction calls минимум вдвое и не
худший supporting-fact recall, чем B1, на тех же 20 development IDs.

Shortlist-3 снизил расчётное число extraction calls с 220 до 80, но не
прошёл quality gate: supporting recall 51,25% против 53,75% у B1, supporting
F1 32,26% против 33,69%. Answer EM составил 40%, однако это единственный
дополнительный exact answer; paired answer F1 имеет одно улучшение, одно
ухудшение и 18 ties. Разбор единственной потери supporting fact показал
причину: lexical shortlist предпочёл paragraphs с общими словами `casinos`
и `border`, исключив paragraph с точным query entity `WrestleMania IX`.

Следующий контроль фиксируется до запуска: при том же лимите 3 сначала
добавлять paragraph, title которого точно совпадает после нормализации с
известным query-node label, а оставшиеся места заполнять прежним BM25
порядком. Узел `?` игнорируется. Gate остаётся прежним: не более 110
расчётных extraction calls и supporting recall не ниже 53,75%.

Anchor-first shortlist сохранил 80 расчётных calls, но дал те же retrieval
metrics, поэтому gate снова не пройден. Детальный разбор показывает два
ограничения, которые нельзя исправлять постфактум подбором threshold:

1. В вопросе `What two casinos ...?` один query node `?` обозначает ответ из
   двух сущностей. Текущий one-to-one matcher может назначить ему только одну
   context entity; для таких вопросов нужна set-valued answer representation
   или отдельная операция раскрытия соседей после сопоставления anchor.
2. Graph retrieval нашёл прямое предложение `WrestleMania IX ... took place
   at Caesars Palace`, но Hotpot gold размечает альтернативное предложение
   из `WrestleMania XXIV`, сообщающее ту же связь. Official supporting-fact
   metric корректно считается по gold, однако может штрафовать альтернативное
   достаточное evidence; поэтому answer metrics остаются обязательными.

Следующую гипотезу нельзя формулировать как ещё один вес matcher. Нужен
контролируемый structural operator: после сопоставления известного anchor
разрешить unknown node вернуть множество соседей, удовлетворяющих одному и
тому же query relation. Его надо отдельно оценить на single-answer и
multi-answer вопросах, не меняя extraction prompt и reader.

До set-valued operator проверяется более ранний failure point: proposal stage
поставил корректный `Caesars Palace ← took place at — WrestleMania IX` лишь
на 10-е место, поскольку сравнивал голые relations `hosted` и
`inverse took place at`. Exact anchor также не был фиксирован и позже был
заменён на `WrestleMania XXVI`. Диагностическая абляция на тех же 20 IDs и
полном context pool содержит четыре arms: исходный matcher; только фиксация
нулевого label-distance anchor; только proposal similarity по полному
labeled edge/path; обе модификации. Сначала считаются только retrieval
metrics, без новых reader calls. Комбинация допускается к reader лишь если
supporting recall не ниже B1 53,75%; иначе set-valued operator откладывается,
поскольку он не исправит неверное сопоставление anchor.

Результат абляции:

| Proposal arm | Support Recall | Support F1 |
|---|---:|---:|
| Исходный | 52,92% | 33,51% |
| Только freeze exact anchors | 52,92% | 33,51% |
| Contextual full edge/path | **54,58%** | **34,76%** |
| Contextual + freeze | **54,58%** | **34,76%** |

Минимальный contextual arm прошёл gate; freeze exact anchors не добавляет
качества и исключается. Reader при contextual evidence получил Answer EM
35,00% и token F1 52,96% против 35,00% и 50,96% у B1. В paired разборе это
одно улучшение, ноль ухудшений и 19 ties. На 20 примерах это перспективный,
но не подтверждающий результат: статистической мощности недостаточно.

Последний feasibility-контроль до масштабирования фиксируется как
`anchor-first shortlist-3 + contextual proposals`: он объединяет единственную
полезную matcher-модификацию с 80-call retrieval design. Gate: supporting
recall не ниже B1 53,75%. Reader вызывается только после прохождения gate.

Shortlist-3 + contextual proposal сохранил 80 calls, но получил recall 52,92%
и gate не прошёл; reader не запускался. Последний допустимый размер без
изменения метода — anchor-first shortlist-4: 100 calls, то есть меньше
половины полного 220-call design. Если его recall ниже 53,75%, дальнейший
подбор shortlist size прекращается как post-hoc tuning.

Shortlist-4 также получил recall 52,92% и gate не прошёл. Подбор размера
остановлен, reader не запускался. Итог feasibility: contextual proposal
улучшает soft graph matching при полном context pool, но дешёвый lexical
shortlist теряет нужный paragraph раньше matcher. Поэтому development-200
пока не запускается: сначала нужен отдельный graph-aware paragraph retrieval
design, а не дополнительная настройка весов текущего matcher.

## Graph-aware paragraph retrieval: preregistration

Новый arm меняет только выбор максимум четырёх context paragraphs; extraction
prompt, contextual matcher, evidence budget 5 и reader остаются заморожены.
Алгоритм не использует gold:

1. Exact normalized query labels, совпадающие с paragraph titles, образуют
   seed anchors. Если их нет, seed — первый paragraph по sentence BM25.
2. Из grounded triples уже выбранного paragraph берутся endpoint labels,
   точно совпадающие с ещё не выбранными titles.
3. Такие переходы ранжируются по максимальной MiniLM similarity между полным
   labeled query edge и полным направленным triple/reverse-triple.
4. Лучшие новые titles добавляются в frontier до бюджета 4; незаполненные
   места детерминированно дополняются прежним BM25 title order.
5. Contextual soft matching работает только на triples этих paragraphs.

На feasibility-20 это соответствует максимум 20 query + 80 context = 100
extraction calls против 220 у full-context arm. Primary gate до reader:
Supporting Recall ≥ 53,75% и Supporting F1 ≥ 33,69% (не хуже B1). Если хотя
бы один gate не пройден, reader не вызывается и development-200 не запускается.

## Graph-aware feasibility result

Оба retrieval gate пройдены при фиксированном бюджете 4 paragraphs:

| Метрика | B1 | Graph-aware | Δ |
|---|---:|---:|---:|
| Расчётные extraction calls | 220 | 100 | −54,5% |
| Supporting Recall | 53,75% | **55,00%** | +1,25 п.п. |
| Supporting F1 | 33,69% | **34,90%** | +1,21 п.п. |
| Answer Exact Match | 35,00% | **40,00%** | +5,00 п.п. |
| Answer token F1 | 50,96% | **56,08%** | +5,12 п.п. |

Reader завершил 20/20 ответов без invalid. Paired answer F1: 2 улучшения,
1 ухудшение, 17 ties; Exact Match: 1 win, 0 losses, 19 ties. Paired
supporting F1: 3 улучшения, 2 ухудшения, 15 ties. Эксперимент использовал
ранее извлечённый cache, но selector читал triples только четырёх выбранных
paragraphs; 100 calls — стоимость эквивалентного запуска без cache.

На диагностическом multi-answer примере selector восстановил переход
`WrestleMania IX → Caesars Palace`, которого не было в lexical shortlist.
Ответ всё ещё неверен, поскольку один узел `?` не представляет множество
`Bellagio and The Mirage`; это отдельная следующая гипотеза, а не ошибка
paragraph retrieval.

Вывод ограничен feasibility-20: graph-aware retrieval прошёл критерии допуска,
но эффект не считается подтверждённым. Перед development-200 параметры
фиксируются: paragraph budget 4, exact-title seeds, exact endpoint-to-title
expansion, contextual proposal scoring, evidence budget 5. Нужен реальный
двухфазный extractor, который сначала извлекает query/seed paragraphs, а
затем только обнаруженные frontier paragraphs; после этого можно запускать
development-200 без предварительно извлечённого полного context pool.
