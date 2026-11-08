"""The ledger: one JSON line per model request, written by the meter, read by the report.

Costs are never stored. They are computed from the token counts and a price sheet when the
report runs, so a price change never needs a rerun.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Record:
    run: str
    arm: str
    task: str
    item: str
    wire: str  # "openai" or "anthropic"
    model: str
    input: int
    cache_read: int
    cache_write: int
    output: int
    latency_ms: int
    status: int
    ts: float = 0.0
    streamed: bool = False
    extra: dict = field(default_factory=dict)

    @property
    def prompt(self) -> int:
        return self.input + self.cache_read + self.cache_write


def append(path: Path, rec: Record) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(asdict(rec), separators=(",", ":")) + "\n")


def read(paths: Iterable[Path]) -> Iterator[Record]:
    for path in paths:
        with Path(path).open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    yield Record(**json.loads(line))


def arms(path: Path, run: str) -> set[str]:
    """The arms with records for `run` in a ledger file (none if it does not exist)."""
    return {r.arm for r in read([path]) if r.run == run} if Path(path).exists() else set()


def drop(path: Path, run: str, arm: str) -> int:
    """Remove one arm's records for one run, rewriting the file in place; how many went."""
    path = Path(path)
    if not path.exists():
        return 0
    keep, dropped = [], 0
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        if rec.get("run") == run and rec.get("arm") == arm:
            dropped += 1
        else:
            keep.append(line)
    tmp = path.with_suffix(".tmp")
    tmp.write_text("".join(x + "\n" for x in keep), encoding="utf-8", newline="\n")
    tmp.replace(path)
    return dropped
