# Методы сравнения (бейзлайны)

> Пересмотрено 05.11.2026 по замечаниям руководителя. Это план-кандидат для О9, не отчёт запусков. Выбор benchmark и научного вопроса пока открыт.

## Сводка

| ID | Метод | Что контролирует | Условия |
|---|---|---|---|
| B0 | BM25 по текстовым фактам/абзацам | Поиск без топологии | Обязателен на том же sample и corpus |
| B1 | VF2 exact subgraph match | Эффект строгих структурных ограничений | Только если query graph строится независимо от gold; тот же candidate pool |
| B2 | SimGRAG / GSD | Мягкий graph-pattern retrieval аналог | Кандидат на MetaQA или FactKG; проверить совместимость кода/условий |
| R1 | NGM-RAG | Связанная работа по neural graph matching | Не выбранный baseline: нужны HotpotQA/MultiHop-RAG и полный воспроизводимый pipeline |

## B0 — BM25

Индексировать каждую тройку KG как `head label — relation label — tail label` (или абзацы HotpotQA отдельным вариантом). Для каждого вопроса ранжировать факты по BM25, агрегировать их score для ответа/evidence. Фиксировать tokenizer, top-k, tie-breaking и corpus snapshot. Считать benchmark-native метрики; для HotpotQA — answer EM/F1 и supporting-fact recall, для MetaQA — Hits@1. Не использовать gold path/evidence как query.

## B1 — VF2

Строить directed labeled query graph из тех же независимо полученных query patterns, которые доступны proposed matcher. Ограничивать поиск тем же candidate pool и лимитом времени/кандидатов; записывать coverage и timeout. VF2 не является «верхней границей precision» гарантированно: report фактические precision/recall и долю запросов без exact match. NetworkX VF2 применим как простой прототип на ограниченном pool.

## B2 — SimGRAG

SimGRAG не запускался. Авторский README документирует команды MetaQA и FactKG; опубликованная конфигурация использует Llama 3 70B/Ollama, Nomic embeddings и Milvus. Замена extractor/backbone или candidate KG — адаптация, а не точное воспроизведение статьи. Сначала проверить время установки и совместимость данных; сравнение только при общих split, candidate KG, query patterns и evaluator.

## NGM-RAG

NGM-RAG статья использует HotpotQA, MultiHop-RAG (по 500 вопросов) и UltraDomain. Официальная ссылка на код не найдена при проверке 05.11.2026. В статье query/target graphs строятся из текста, затем используются Levenshtein, BM25, BGE и LightGCN/GINE representations с weighted scoring. Не включать как реализуемый baseline, пока не подтверждён код/полное описание и бюджет. Можно цитировать как related work и как мотиватор общего benchmark HotpotQA.

## Сравнимость

Результаты должны использовать одну и ту же выборку, corpus/KG snapshot, gold definition, extractor и candidate generator. Если отличается один из этих пунктов, называть это адаптацией или отдельным экспериментом, а не head-to-head. Метрики разных benchmark не агрегировать.
