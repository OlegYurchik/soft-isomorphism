# H8: контекстная edge cost без расширения кандидатов

Дата фиксации: 13.11.2026. Ветка задачи #19.

## Происхождение и гипотеза

H8 выделена после retrieval-диагностики H7. На ранее изученных dev-20
абляция C7 с исходными candidate domains подняла positive path coverage
с 8/32 у B4 до 18/32. Полная H7 с расширением domains дала 16/32 и не
восстановила ни одного отдельного path сверх C7. Поэтому расширение
исключается, а reader dev-20 остаётся exploratory проверкой.

**H8.** Замена relation-only edge distance на cosine между полными
вербализациями query edge и KG edge улучшит end-to-end verdict относительно
B4 при неизменных entity candidates и том же beam search.

## Контраст и gate

Primary contrast: `C7 − B4`. B1 приводится только как сильный внешний
baseline. Query graph, candidate pool, candidate domains, node cost
`0.3`, edge cost `0.7`, beam width 64 и reader одинаковы.

Exploratory gate для перехода к неиспользованному dev:

- Accuracy C7 выше B4 минимум на 10 процентных пунктов;
- UNKNOWN C7 меньше B4 минимум на 3 claims;
- C7 даёт хотя бы один правильный verdict, которого нет у B4.

Результат dev-20 не может подтвердить H8, поскольку retrieval-механизм уже
просмотрен. При успехе параметры замораживаются для нового dev; test до
этого не запускается.

До запуска независимого пилота фиксируется выборка: 50 FactKG dev claims
с SHA-256 ranks 500–549. Она не пересекается с диагностическими ranks
0–19. Условия пилота: C7 превосходит B4 по path coverage и Accuracy,
снижает UNKNOWN и даёт минимум три uniquely correct verdicts. B1
оценивается на тех же claims как внешний baseline. Пилот из 50 примеров
не заменяет последующую оценку на 500 claims.

## Результаты

На диагностических dev ranks 0–19 C7 прошёл exploratory gate:

| Метод | Accuracy | UNKNOWN | Path coverage |
|---|---:|---:|---:|
| B4 | 1/20 = 5% | 19/20 | 8/32 |
| C7 | 5/20 = 25% | 14/20 | 18/32 |

C7 дал четыре uniquely correct verdicts, B4 — ноль.

Затем без изменения cost, domains, beam и reader выполнен независимый
пилот на зафиксированных dev SHA-256 ranks 500–549:

| Метод | Непустые evidence | Path coverage | Accuracy | UNKNOWN |
|---|---:|---:|---:|---:|
| B1 | 50/50 | 30/57 = 52,63% | 31/50 = 62% | 17/50 |
| B4 | 6/50 | 4/57 = 7,02% | 1/50 = 2% | 49/50 |
| C7 | 14/50 | 14/57 = 24,56% | 4/50 = 8% | 46/50 |

В парном сравнении C7 имеет три uniquely correct verdicts против B4;
B4 не имеет ни одного. Все четыре правильных C7 также правильны у B1.
Зафиксированные условия независимого пилота выполнены: C7 выше B4 по
coverage и Accuracy, уменьшает UNKNOWN на три и даёт три uniquely correct
ответа.

**Вывод:** H8 получила независимую пилотную поддержку как улучшение
текущего soft graph matcher относительно B4. Она пока не подтверждена на
500 claims и не конкурентна с B1: главный оставшийся bottleneck — coverage
entity candidates и исполнимых KG edges, поскольку C7 имеет evidence
только для 14/50 claims.

Локальные артефакты находятся в игнорируемых каталогах
`data/evaluation/h8-dev-50-extract/`, `h8-dev-50/` и `h8-dev-50-c7/`.
