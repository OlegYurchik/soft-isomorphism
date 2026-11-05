# B0 baseline: BM25 over MetaQA triples

> First implementation step for issue #13. This is a text-only lower bound, not a graph matching method and not an experiment result.

## Dataset

MetaQA provides a movie KG in `kb.txt` (`subject|relation|object`) and separate vanilla QA files for 1-, 2-, and 3-hop questions. Each QA row has a question and one or more answers. The official README reports train/dev/test splits and links the files from Google Drive. The repository's license file is CC BY 3.0; check the upstream MovieQA/WikiMovies terms before redistributing derived data.

- Dataset: [official repository](https://github.com/yuyuz/MetaQA), paper [Zhang et al., AAAI 2018](https://arxiv.org/abs/1709.04071)
- SimGRAG lists MetaQA and provides run commands; its documented stack includes Llama 3 70B, Nomic embeddings, and Milvus. We do not claim a SimGRAG reproduction.

## Baseline procedure

1. Index each KG triple as natural-language text: subject, relation label (underscores replaced with spaces), object.
2. Score the question against every triple with Okapi BM25 (`k1=1.5`, `b=0.75`).
3. Take the top 1,000 facts (configurable). Add each fact's score divided by `log2(rank + 1)` to its non-topic entities. Topic entities are marked in MetaQA questions with brackets and are excluded from answer candidates.
4. Rank entities by aggregate score. Do not use gold answers or relation paths at retrieval time.
5. Evaluate the benchmark's official question-answer split with Hits@1/5/10 and MRR. Report 1-, 2-, and 3-hop separately, plus no-prediction rate and runtime.

The baseline ranks answers from facts; it does **not** produce a coherent subgraph. This gives a fast lower bound for KGQA, while graph-level precision/recall must wait for a dataset/protocol with an independent query graph and gold evidence graph.

## Next steps before a reported run

- Obtain the official vanilla files and record download date, file hashes, and license text.
- First use dev to choose `fact_limit`; freeze it before test. Do not tune using test.
- Compare against the same split and answer metric as SimGRAG where possible. Treat published SimGRAG numbers as context unless the same candidate KG, prompt/model settings, and evaluator are reproduced.
- Keep HotpotQA as a second benchmark candidate, not part of this baseline: its official dataset is text passages with supporting-fact labels, not a prebuilt KG.
