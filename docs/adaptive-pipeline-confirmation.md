# H14: подтверждение полного adaptive pipeline

Дата фиксации: 22.11.2026, до extraction на новой выборке.

## Выборка

FactKG dev, 500 claims с SHA-256 ranks 2000–2499. Срез не пересекается с
diagnostic ranks 500–999, confirmatory ranks 1000–1499 и control ranks
1500–1999. Срез не используется для настройки параметров.

## Замороженный pipeline

1. Qwen3.8-27B extraction: один open-relation view, JSON object mode,
   temperature 0, seed 42, output budget 256.
2. Если extraction не проходит прежнюю строгую валидацию, повторить тот же
   prompt один раз с budget 512. Валидные первые ответы не пересчитывать.
3. Построить локальный KG pool прежними параметрами: radius 2, incident
   BM25 cap 30, общий cap 2000 triples.
4. B1: до 20 BM25 triples и тот же KG-only Qwen reader.
5. Только после B1=`UNKNOWN` запустить замороженный H10-lean: один новый
   endpoint на query node, пути длины 1–2, MiniLM scoring, прежний beam и
   тот же reader.

После начала extraction запрещено менять prompt, validation, budgets,
candidate generation, matcher, reader или gates по результату этого среза.

## Метрики и заранее заданные gates

- invalid extraction до/после retry и recovery rate;
- Qwen calls, tokens и model time отдельно для initial extraction, retry,
  B1 и lean reader;
- pool wall/CPU time и peak RSS;
- B1 и B1→H10-lean: Accuracy, Macro-F1, UNKNOWN;
- paired method-only/B1-only correct и exact two-sided p-value.

Operational pipeline считается подтверждённым на этом срезе, если
одновременно:

- retry восстанавливает не менее 80% первоначально невалидных graphs;
- B1 fallback rate не превышает 40%;
- H10-lean даёт не менее +3 п.п. Accuracy поверх B1;
- exact paired p-value H10-lean против B1 меньше 0,05;
- Macro-F1 H10-lean не ниже B1 более чем на 0,01.

Независимо от исхода должны быть опубликованы все пять условий и стоимость.
Flat-2hop и independent-edges на этом срезе не запускаются: их научные
контрасты уже проверены на ranks 1500–1999, а H14 проверяет переносимость
замороженного operational pipeline.

## Промежуточный результат

Первичный extraction завершён для 500/500 claims:

- 126 графов были невалидны: 119 ответов завершились по лимиту, 7 — с
  `stop`, но не прошли строгую валидацию;
- 500 initial calls использовали 175 120 токенов и 1086,18 с model time.

Замороженный retry 512 восстановил **113/126** графов, или **89,7%**;
первый gate ≥80% выполнен. Все 374/374 исходно валидных extraction остались
неизменными. Retry потребовал 126 calls, 60 466 токенов и 459,39 с model
time. После retry осталось 13 невалидных графов.

Построение candidate pools, B1-reader и H10-lean ещё выполняются; до их
завершения остальные четыре gates не оцениваются.
