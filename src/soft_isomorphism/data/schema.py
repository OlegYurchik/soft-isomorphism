from dataclasses import dataclass, field
from enum import Enum


class Source(str, Enum):
    GTSQA = "gtsqa"
    FACTKG = "factkg"


class Split(str, Enum):
    TRAIN = "train"
    TRAIN_FIT = "train-fit"
    TRAIN_DEV = "train-dev"
    DEV = "dev"
    TEST = "test"


@dataclass(frozen=True)
class Edge:
    """Directed labelled edge: head --rel--> tail."""

    head_id: str
    rel_id: str
    tail_id: str
    head_label: str | None = None
    rel_label: str | None = None
    tail_label: str | None = None

    def to_triple(self) -> tuple[str, str, str]:
        return (self.head_id, self.rel_id, self.tail_id)


@dataclass
class Example:
    """Single pilot example in the unified format.

    gold_edges stores the ground-truth answer subgraph and is kept separate
    from any input graph the method receives — never pass gold_edges to the
    retrieval step.
    """

    id: str
    source: Source
    split: Split
    text: str
    gold_edges: list[Edge]
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id must be non-empty")
        if not self.text:
            raise ValueError("text must be non-empty")
        if not self.gold_edges:
            raise ValueError(f"gold_edges is empty for example {self.id!r}")
        for edge in self.gold_edges:
            if not edge.head_id or not edge.rel_id or not edge.tail_id:
                raise ValueError(
                    f"Edge in example {self.id!r} has empty head/rel/tail: {edge}"
                )
