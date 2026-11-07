"""Data adapters for GTSQA and FactKG datasets.

Usage
-----
GTSQA (requires datasets + pyarrow installed and data downloaded):
    examples = load_gtsqa("data/gtsqa", split=Split.TEST)

FactKG (requires data downloaded from github.com/jiho283/FactKG):
    examples = load_factkg("data/factkg", split=Split.DEV)

The data directory must match configs/data-manifest.json:
  gtsqa/   -> gtsqa-with-graphs/train/0000.parquet
                                test/0000.parquet
  factkg/  -> data/factkg_train.json
               data/factkg_dev.json
"""

import hashlib
import json
import logging
import pickle
from dataclasses import dataclass
from pathlib import Path

from .schema import Edge, Example, Source, Split

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FactKGInput:
    id: str
    text: str


@dataclass(frozen=True)
class FactKGEvaluation:
    id: str
    label: bool
    entity_set: tuple[str, ...]
    evidence: dict | None
    types: tuple[str, ...]


def load_factkg_records(
    data_dir: str | Path, split: Split
) -> tuple[list[FactKGInput], list[FactKGEvaluation]]:
    """Return separate method inputs and evaluator records from trusted FactKG files."""
    if split not in (Split.TRAIN, Split.DEV, Split.TEST):
        raise ValueError(f"Unsupported FactKG split: {split.value}")
    path = Path(data_dir) / "data" / "factkg_unzip" / f"factkg_{split.value}.pickle"
    if not path.is_file():
        raise FileNotFoundError(f"FactKG pickle not found: {path}")
    with path.open("rb") as stream:
        rows = pickle.load(stream)  # Only load files from the trusted upstream checkout.
    if not isinstance(rows, dict):
        raise ValueError("FactKG pickle must contain a claim-to-annotation dictionary")
    inputs: list[FactKGInput] = []
    evaluation: list[FactKGEvaluation] = []
    for claim, annotation in rows.items():
        if not isinstance(claim, str) or not claim or not isinstance(annotation, dict):
            raise ValueError("Invalid FactKG claim or annotation")
        labels = annotation.get("Label")
        if not isinstance(labels, list) or len(labels) != 1 or type(labels[0]) is not bool:
            raise ValueError(f"FactKG Label must be a one-item boolean list: {claim[:80]}")
        identifier = hashlib.sha256(claim.encode("utf-8")).hexdigest()
        inputs.append(FactKGInput(identifier, claim))
        evaluation.append(
            FactKGEvaluation(
                identifier,
                labels[0],
                tuple(annotation.get("Entity_set", ())),
                annotation.get("Evidence"),
                tuple(annotation.get("types", ())),
            )
        )
    if len({item.id for item in inputs}) != len(inputs):
        raise ValueError("Duplicate FactKG claim IDs")
    return inputs, evaluation


# GTSQA gold-subgraph field formats (verify against pinned downloaded revision)
_GTSQA_GRAPH_FORMATS = ("edge_list", "dict_nodes_edges", "list_of_triples")


def load_gtsqa(data_dir: str | Path, split: Split) -> list[Example]:
    """Load GTSQA examples from local parquet files.

    Parameters
    ----------
    data_dir:
        Root directory that contains ``gtsqa-with-graphs/``.
        Matches the layout in configs/data-manifest.json.
    split:
        One of Split.TRAIN, Split.TEST.
        Split.TRAIN_FIT / Split.TRAIN_DEV require configs/splits/gtsqa_dev_indices.json
        to exist (created by the stratified-split script, not by this function).
    """
    data_dir = Path(data_dir)
    split_file = _gtsqa_parquet_path(data_dir, split)

    if not split_file.exists():
        raise FileNotFoundError(
            f"GTSQA parquet not found: {split_file}\n"
            "Download the dataset first:\n"
            "  from datasets import load_dataset\n"
            "  ds = load_dataset('Graphcore/GTSQA', 'gtsqa-with-graphs')\n"
            "  ds.save_to_disk('<data_dir>')\n"
            "See configs/data-manifest.json for expected layout."
        )

    try:
        import pyarrow.parquet as pq
    except ImportError as exc:
        raise ImportError("Install pyarrow to load GTSQA: pip install pyarrow") from exc

    table = pq.read_table(split_file)
    rows = table.to_pylist()

    base_split = Split.TRAIN if split in (Split.TRAIN_FIT, Split.TRAIN_DEV) else split
    indices = _gtsqa_split_indices(data_dir, split) if split != base_split else None

    examples: list[Example] = []
    skipped = 0
    for i, row in enumerate(rows):
        if indices is not None and i not in indices:
            continue
        example_id = str(row.get("id", f"gtsqa-{split.value}-{i}"))
        try:
            gold_edges = _parse_gtsqa_graph(row["full_answer_subgraph_wikikg2"], example_id)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("Skipping GTSQA example %s: %s", example_id, exc)
            skipped += 1
            continue

        examples.append(
            Example(
                id=example_id,
                source=Source.GTSQA,
                split=split,
                text=str(row["question"]),
                gold_edges=gold_edges,
                metadata={
                    "answer": row.get("answer_node"),
                    "answers": row.get("all_answers_wikikg2", []),
                    "candidate_graph_available": row.get("graph") is not None,
                    "graph_isomorphism": row.get("graph_isomorphism"),
                    "n_hops": row.get("n_hops"),
                },
            )
        )

    if skipped:
        logger.warning("GTSQA %s: skipped %d / %d rows", split.value, skipped, len(rows))

    logger.info("Loaded %d GTSQA examples (split=%s)", len(examples), split.value)
    return examples


def load_factkg(data_dir: str | Path, split: Split) -> list[Example]:
    """Load canonical FactKG pickle files (with legacy JSON fixture support).

    Parameters
    ----------
    data_dir:
    Root directory that contains ``data/factkg_unzip/factkg_{split}.pickle``.
        Matches the layout in configs/data-manifest.json.
    split:
    All splits are supported. Evidence remains evaluator-only metadata.
    """
    data_dir = Path(data_dir)
    pickle_file = data_dir / "data" / "factkg_unzip" / f"factkg_{split.value}.pickle"
    json_file = data_dir / "data" / f"factkg_{split.value}.json"

    if pickle_file.exists():
        with pickle_file.open("rb") as fh:
            raw = pickle.load(fh)
    elif json_file.exists():
        with json_file.open(encoding="utf-8") as fh:
            raw = json.load(fh)
    else:
        raise FileNotFoundError(
            f"FactKG pickle not found: {pickle_file}\n"
            "Clone the dataset first:\n"
            "  git clone https://github.com/jiho283/FactKG data/factkg\n"
            "See configs/data-manifest.json for expected layout."
        )

    examples: list[Example] = []
    skipped = 0
    for idx, (claim_text, entry) in enumerate(raw.items()):
        example_id = f"factkg-{split.value}-{idx}"
        gold_edges = None
        if "graph" in entry:  # legacy fixture; never used by the E1 runtime
            try:
                gold_edges = _parse_factkg_graph(entry["graph"], example_id)
            except (TypeError, ValueError) as exc:
                logger.warning("Skipping FactKG example %s: %s", example_id, exc)
                skipped += 1
                continue

        examples.append(
            Example(
                id=example_id,
                source=Source.FACTKG,
                split=split,
                text=claim_text,
                gold_edges=gold_edges,
                metadata={
                    "label": entry.get("label", entry.get("Label")),
                    "type": entry.get("type", entry.get("types")),
                    "entities": entry.get("entities", entry.get("Entity_set", [])),
                    "evidence": entry.get("Evidence"),
                    "gold_available": gold_edges is not None,
                },
            )
        )

    if skipped:
        logger.warning("FactKG %s: skipped %d / %d rows", split.value, skipped, len(raw))

    logger.info("Loaded %d FactKG examples (split=%s)", len(examples), split.value)
    return examples


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _gtsqa_parquet_path(data_dir: Path, split: Split) -> Path:
    base = Split.TRAIN if split in (Split.TRAIN_FIT, Split.TRAIN_DEV) else split
    subdir = "train" if base == Split.TRAIN else "test"
    return data_dir / "gtsqa-with-graphs" / subdir / "0000.parquet"


def _gtsqa_split_indices(data_dir: Path, split: Split) -> set[int]:
    index_file = data_dir / "configs" / "splits" / "gtsqa_dev_indices.json"
    if not index_file.exists():
        raise FileNotFoundError(
            f"Dev-split index not found: {index_file}\n"
            "Run the stratified-split script first (see docs/evaluation-protocol.md §2.1)."
        )
    with index_file.open() as fh:
        indices = json.load(fh)
    key = split.value  # "train-dev" or "train-fit"
    if key not in indices:
        raise KeyError(
            f"Key {key!r} not found in {index_file}. Expected 'train-dev' or 'train-fit'."
        )
    return set(indices[key])


def _parse_gtsqa_graph(graph_field: object, example_id: str) -> list[Edge]:
    """Parse GTSQA graph field into a list of Edge.

    In 'gtsqa-with-graphs', 'graph' is the candidate search graph (up to 30k edges),
    not the gold. Gold is 'full_answer_subgraph_wikikg2'. Do not substitute 'graph'
    or 'answer_subgraph' for this field; verify the downloaded schema before use.
    this function handles the two most likely formats.

    Format A — list of triples: [[head_qid, rel_pid, tail_qid], ...]
    Format B — dict with 'nodes' and 'edges': {"nodes": [...], "edges": [...]}

    Raises ValueError with a diagnostic message if neither format matches.
    """
    if graph_field is None:
        raise ValueError("graph field is None")

    # Format A: list of [head, rel, tail]
    if isinstance(graph_field, list):
        edges = []
        for item in graph_field:
            if not (isinstance(item, (list, tuple)) and len(item) == 3):
                raise ValueError(f"Expected triple [head, rel, tail], got {item!r} in {example_id}")
            edges.append(Edge(head_id=str(item[0]), rel_id=str(item[1]), tail_id=str(item[2])))
        if not edges:
            raise ValueError("graph field is an empty list")
        return edges

    # Format B: {"nodes": [...], "edges": [{"head": ..., "rel": ..., "tail": ...}]}
    if isinstance(graph_field, dict) and "edges" in graph_field:
        edges = []
        for e in graph_field["edges"]:
            edges.append(
                Edge(
                    head_id=str(e["head"]),
                    rel_id=str(e["rel"]),
                    tail_id=str(e["tail"]),
                )
            )
        if not edges:
            raise ValueError("graph.edges is empty")
        return edges

    raise ValueError(
        f"Unknown GTSQA graph format in {example_id!r}: {type(graph_field).__name__}. "
        "Expected gold full_answer_subgraph_wikikg2 as list-of-triples or dict-with-edges. "
        "Update _parse_gtsqa_graph once the real format is confirmed."
    )


def _parse_factkg_graph(graph_field: object, example_id: str) -> list[Edge]:
    """Parse FactKG graph field into a list of Edge.

    FactKG stores graphs as a dict:
      {entity_uri: [[relation, entity_uri], ...], ...}

    The entity keys and relation strings are DBpedia URIs or short labels.
    """
    if not isinstance(graph_field, dict):
        raise ValueError(
            f"Expected dict for FactKG graph in {example_id!r}, got {type(graph_field).__name__}"
        )

    edges = []
    for head, adjacency in graph_field.items():
        if not isinstance(adjacency, list):
            raise ValueError(f"Adjacency for {head!r} in {example_id!r} is not a list")
        for entry in adjacency:
            if not (isinstance(entry, (list, tuple)) and len(entry) == 2):
                raise ValueError(f"Expected [relation, tail] in {example_id!r}, got {entry!r}")
            edges.append(Edge(head_id=str(head), rel_id=str(entry[0]), tail_id=str(entry[1])))

    if not edges:
        raise ValueError(f"graph dict is empty in {example_id!r}")
    return edges
