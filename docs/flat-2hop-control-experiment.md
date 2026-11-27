# Flat-2hop: контроль доступа к дополнительным фактам

Дата фиксации: 22.11.2026. Дизайн зафиксирован до получения reader verdicts
на FactKG dev SHA-256 ranks 1500–1999.

## Исследовательский вопрос

H10-lean устойчиво улучшил B1 после `UNKNOWN`, но сравнение с
`independent-edges` не подтвердило пользу единого graph-level mapping:
Accuracy 67,0% против 66,8% на confirmatory dev-500. Поэтому остаётся более
простой альтернативный механизм: reader выигрывает только потому, что
fallback даёт ему доступ к дополнительным фактам из двухшаговой окрестности.

**Flat-2hop control** проверяет эту альтернативу без endpoint proposals,
query-edge-to-path matching, инъективности и beam search.

## Зафиксированный алгоритм

Контроль запускается только для тех же claims, где замороженный B1-reader
вернул `UNKNOWN`.

1. Использовать тот же сохранённый candidate pool радиуса 2, что H10-lean.
2. Преобразовать каждую реальную KG-тройку в текст
   `source: ...; relation: ...; target: ...`.
3. Замороженным `all-MiniLM-L6-v2` вычислить cosine similarity между полным
   текстом claim и полным текстом каждой тройки.
4. Отсортировать тройки по убыванию similarity; ties разрешать
   лексикографически по `(source, relation, target)`.
5. Для каждого claim взять ровно столько верхних уникальных троек, сколько
   evidence-троек вернул замороженный H10-lean на этом же claim.
6. Передать evidence тому же Qwen3.8-27B KG-only reader с неизменным prompt.
7. Как и в H11, заменить только B1=`UNKNOWN`; B1=`TRUE/FALSE` сохранить.

Per-claim budget заимствуется только как число и не раскрывает gold label,
gold Evidence, mapping или score H10-lean. Если H10-lean вернул пустое
evidence, Flat-2hop также получает нулевой budget. Это изолирует способ
выбора фактов при одинаковом объёме контекста.

## Что намеренно отсутствует

- query graph не используется при ranking;
- entity candidates не расширяются;
- endpoint proposals не строятся;
- KG paths не оцениваются как единое целое;
- общий mapping query nodes в KG nodes отсутствует;
- инъективность и beam search отсутствуют.

## Arms и контрасты

- `B1`: lexical KG baseline;
- `B1 → Flat-2hop`: главный простой access control;
- `B1 → independent-edges`: secondary control без общего mapping, но с
  edge-to-path matching;
- `B1 → H10-lean`: предлагаемый согласованный graph matcher.

Primary contrast: `H10-lean − Flat-2hop`. Secondary contrast:
`independent-edges − Flat-2hop`.

Одинаковыми остаются B1 eligibility, sample IDs, extraction, KG pool,
MiniLM checkpoint, reader model/prompt, temperature, seed и evidence budget.

## Выборка и запрет настройки

Независимая выборка зафиксирована ранее: FactKG dev, SHA-256 ranks
1500–1999. Она не пересекается с diagnostic ranks 500–999 и confirmatory
ranks 1000–1499. На 22.11.2026 extraction готов для 500/500 claims,
candidate pool — для 9/500; reader verdicts не получены.

После запуска запрещено менять ranking, budget, reader prompt или параметры
H10-lean по результатам этой выборки. Срез используется только для проверки
зафиксированных методов, не для нового tuning.

## Метрики и правило вывода

Для каждого arm считаются:

- overall Accuracy и Macro-F1 на всех 500 claims;
- число `UNKNOWN` и fallback rate;
- method-only / control-only correct и exact two-sided paired p-value;
- число и средний размер evidence;
- retrieval wall time, reader calls, tokens и reader time.

Retrieval дополнительно сохраняет CPU time и peak RSS. Результат пишется
после каждого claim и переиспользуется только при совпадении SHA-256 полного
входа `(claim, pool triples, budget)`, поэтому длинный запуск возобновляем и
не может молча использовать evidence от другого pool или budget.

Польза **структурного endpoint/path matching поверх плоского доступа к тем же
фактам** считается поддержанной на этом срезе, только если H10-lean
одновременно:

- даёт минимум 10 дополнительных правильных ответов net относительно
  Flat-2hop (2 процентных пункта на 500 claims);
- имеет exact paired `p < 0,05`;
- не снижает Macro-F1 более чем на 0,01.

Если хотя бы одно условие не выполнено, формулировка ограничивается:
`структурный endpoint/path matching не получил подтверждения на этом срезе`.
Это не доказывает его бесполезность на всех данных.

Этот primary contrast сам по себе **не изолирует пользу единого отображения
вершин**: H10-lean отличается от Flat-2hop сразу структурным edge-to-path
matching и joint mapping. Польза именно joint mapping проверяется отдельным
контрастом `H10-lean − independent-edges`.

## Результат на зафиксированном срезе

Эксперимент завершён 22.11.2026 без изменения зафиксированного ranking,
evidence budget, reader prompt или параметров H10-lean. Все методы заменяли
ответ только на одних и тех же 234 claims, где B1 вернул `UNKNOWN`.

| Метод | Accuracy | Macro-F1 | UNKNOWN | Correct сверх B1 |
|---|---:|---:|---:|---:|
| B1 | 45,8% | 0,5957 | 234 | — |
| B1 → Flat-2hop | 48,8% | 0,6087 | 203 | +15 |
| B1 → independent-edges | 50,2% | 0,6259 | 201 | +22 |
| B1 → H10-lean | **51,0%** | **0,6337** | **199** | **+26** |

В главном парном сравнении H10-lean был единственным правильным в 15
случаях, Flat-2hop — в 4. Net gain равен 11 claims, или 2,2 процентного
пункта на всей выборке; exact two-sided p-value = **0,0192**. Macro-F1 также
выше на 0,0250. Следовательно, выполнены все три заранее заданных условия.

**Поддержанный вывод:** структурное использование query edges, endpoint
recovery и одно-/двухшаговых KG paths выбирает evidence лучше, чем плоское
семантическое ранжирование тех же KG-троек при том же per-claim budget.
Прирост нельзя объяснить только доступом к дополнительным двухшаговым фактам.

В отдельном контрасте H10-lean против independent-edges lean был единственным
правильным в 4 случаях, контроль — в 0; p = **0,125**. Поэтому польза общей
инъективной карты и graph-level beam search **не подтверждена**. Научный
claim следует формулировать как структурный endpoint/path retrieval, а не
как уже доказанное преимущество глобально согласованного soft isomorphism.

## Стоимость и обнаруженный bottleneck

- extraction: 500 Qwen-вызовов, 174 839 токенов и 733,89 с model time;
- построение pool и B1 evidence: 771,05 с wall time, 718,26 с CPU time,
  peak RSS около 11,34 ГБ;
- B1-reader: 378 фактических вызовов, 248 322 токена и 261,12 с;
- H10-lean retrieval на 234 fallback claims: 18,27 с wall time;
- Flat-2hop retrieval: 244,74 с wall time и 3422,30 с CPU time — примерно в
  13,4 раза медленнее lean по wall time, потому что заново кодирует тексты
  всех троек pool;
- fallback reader для lean: 112 фактических вызовов, 14 371 токен и 61,63 с.

B1 вернул `UNKNOWN` для 46,8% claims, что хуже прежнего операционного порога
40%. У 122/500 claims query graph не дал рёбер, поэтому pool и evidence были
пустыми; все три fallback-варианта остались без evidence. Диагностика raw
responses показала, что 107/122 ответов extraction обрезаны лимитом 256
output-токенов (`finish_reason=length`), а 15 завершённых ответов не прошли
строгую валидацию JSON/schema/exact quotes. Следующий безопасный эксперимент
— повторять только невалидные extraction с увеличенным output budget, не
изменяя уже проверенный matcher.

## Реализация

- retrieval: `scripts/factkg_flat_2hop_control.py`;
- candidate pools без неиспользуемого B4 beam search:
  `scripts/factkg_prepare_candidate_pools.py`;
- общий frozen reader: `scripts/factkg_h10_ablation_reader.py`;
- unit tests: `tests/test_factkg_flat_2hop_control.py`.

Артефакты результата:

- candidate pools: `data/evaluation/h12-dev-500-confirm/`;
- B1: `data/evaluation/h12-dev-500-confirm-reader/`;
- lean и independent edges:
  `data/evaluation/h12-dev-500-confirm-matching/`;
- Flat-2hop retrieval: `data/evaluation/h12-dev-500-confirm-flat/`;
- reader verdicts и парные сравнения:
  `data/evaluation/h12-dev-500-confirm-method-reader/`.
