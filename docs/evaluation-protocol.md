# Протокол первого эксперимента

Версия E1-v2: FactKG + HotpotQA distractor.

Полный нормативный документ: [experiment-design-v2.md](experiment-design-v2.md).
Параметры и проверенные файлы: [manifest](../configs/experiment-v2.json).
Sample IDs: [splits](../configs/splits/).

Имена: B0 claim-only; B1 lexical triples; B2 hard topology; B3 uniform soft; E1 agreement-weighted soft.
Primary contrast E1−B3; primary metric FactKG Accuracy. Graph experiment ещё не запущен.
Предыдущие схемы на GTSQA и MetaQA, gold edge F1 для всего FactKG и обозначение B2=SimGRAG отменены.

## Decision log and launch gate

Решение 06.11.2026: FactKG — основной benchmark для коротких claims; HotpotQA distractor
— отдельная проверка переноса в QA. SimGRAG остаётся reference work, NGM-RAG — related work;
ни одна работа не считается воспроизведённой только из-за совпадения датасета.

Перед первым графовым запуском должны быть отмечены все пункты:

- DBpedia 2015 light скачан из авторского источника, checksum записан;
- Qwen/Qwen2.5-7B-Instruct revision, runtime, tokenizer и веса зафиксированы;
- extractor и reader проходят JSON validation на smoke set;
- candidate pool сохраняется и одинаков для B1/B2/B3/E1;
- evaluator принимает extraction error, empty pool, timeout и UNKNOWN без удаления из знаменателя;
- первые 500 test IDs не использовались для prompt/model/parameter tuning.

Если любой пункт не выполнен, запуск называется smoke test или blocked run, а не результатом
пилота. После запуска основной contrast остаётся E1−B3; сравнение с B0 публикуется отдельно.
