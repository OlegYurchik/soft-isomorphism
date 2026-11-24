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
