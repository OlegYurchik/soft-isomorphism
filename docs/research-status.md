# Научный статус

Дата обновления: 24.11.2026.

Тема: мягкое сопоставление графа запроса/документа с графом знаний или
извлечённым графом документов для graph-guided RAG.

## Что установлено экспериментально

- На FactKG подтверждён селективный pipeline `B1 → graph fallback` для
  случаев, где B1-reader вернул `UNKNOWN`; этот результат относится к fact
  verification и не доказывает перенос на QA.
- На HotpotQA создан training-free graph-aware retriever: exact-title seed,
  query-guided paragraph frontier, grounded triples, contextual
  edge-to-path matching длины 1–2 и evidence budget 5.
- На confirmation-180 Answer F1 вырос на 2,17 п.п., но статистически значимый
  эффект не подтверждён (`p=0,193`, CI включает ноль).
- На финальном evaluation-500 Supporting F1 достоверно вырос на 3,06 п.п.
  (`p≈1,0×10⁻⁵`), однако Answer F1 вырос лишь на 0,29 п.п. (`p=0,777`,
  95% CI `[−1,71; +2,27]` п.п.). Главная end-to-end гипотеза не подтверждена.
- Graph extraction для evaluation-500 потребовал 2 230 Qwen calls и
  1 781 453 токена. При текущем качестве ответа overhead не оправдан.

## Статус новизны

Повторный поиск выявил прямые аналоги, отсутствовавшие в ранней таблице:
SAFE уже допускает query edge → KG path, а MGRAG сочетает semantic path
matching с lazy query-specific graph construction. Поэтому нельзя заявлять
новизну самого принципа мягкого edge-to-path matching или ленивого построения
графа.

Допустимая узкая формулировка текущего вклада: воспроизводимая text-only,
training-free и provenance-preserving реализация с фиксированным бюджетом,
component controls и независимой парной оценкой качества/стоимости. На
HotpotQA она дала положительный retrieval result, но отрицательный
end-to-end result.

Подробности: [`hotpotqa-pilot-design.md`](hotpotqa-pilot-design.md) и
[`related-work-audit-2026-11-24.md`](related-work-audit-2026-11-24.md).

## Следующая гипотеза после targeted audit

Идея отображать одну query node в связное множество document nodes не может
заявляться как новый общий вид matching: существуют many-to-many graph
matching, graph-minor branch sets и path homomorphism; HyperPathsRAG,
HEAR-RAG, ReGraphRAG и FlowRAG закрывают значительную часть n-ary,
fragmentation, provenance и multi-granularity мотивации.

Рабочий кандидат `H13-R` проверяет не новизну самой конструкции, а
**устойчивость к representation granularity shift**: при неизменном текстовом
evidence и контролируемых node split, node merge и relation reification
bounded semantic branch-set matcher должен терять меньше качества, чем
point-valued path matcher, top-k union и mention contraction при одинаковом
evidence budget. До выполнения stop/go checks это не подтверждённый вклад.

Подробности:
[`targeted-literature-audit-fiber-matching-2026-11-24.md`](targeted-literature-audit-fiber-matching-2026-11-24.md).

## Новая основная гипотеза-кандидат: H14

H13-R оставлен как диагностический benchmark, а не основной алгоритмический
вклад. Более сильная гипотеза `H14` — **certified provenance-constrained soft
matching**. Matcher должен возвращать не только evidence, но и sound
сертификат того, что выбранные исходные предложения не изменятся при любом
допустимом provenance-preserving исправлении extracted graph в пределах
заданного edit radius. При отсутствии сертификата возвращается минимальный
failure witness.

Targeted search нашёл certified GNN, visual graph matching и обычный RAG, а
также uncertain subgraph matching, но не точный аналог сертификации
semantic evidence-chain retrieval под extraction-equivalent graph rewrites.
Новизна предварительная; перед claim «first» нужен systematic review.

Дизайн и falsification pilot:
[`h14-certified-soft-matching-hypothesis.md`](h14-certified-soft-matching-hypothesis.md).
