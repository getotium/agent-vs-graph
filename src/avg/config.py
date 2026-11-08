"""Settings for running the arms on local models: which binaries, which model files, which GPU.

`local.default.toml` (committed) holds generic defaults. `local.toml` (gitignored) overrides any of
its keys for one machine, so a machine's GPU names and paths never land in the repository. A key
that is not in the defaults is refused, so a typo does not pass silently.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, fields
from pathlib import Path

DEFAULT = Path("local.default.toml")
LOCAL = Path("local.toml")


@dataclass(frozen=True)
class Local:
    llama_server: str
    device: str  # a device id or a piece of its name (llama-server --list-devices); "" = llama.cpp's choice
    small_gguf: str
    large_gguf: str
    harness_ctx: int
    slots: int  # requests in flight for the per-item arms, each with its own slot on the server
    hermes_bin: str


def load(default: Path = DEFAULT, local: Path = LOCAL) -> Local:
    values = tomllib.loads(default.read_text(encoding="utf-8"))
    if local.exists():
        override = tomllib.loads(local.read_text(encoding="utf-8"))
        unknown = sorted(set(override) - set(values))
        if unknown:
            raise ValueError(f"{local}: unknown key(s) {', '.join(unknown)}; the keys are those in {default}")
        values |= override
    names = {f.name for f in fields(Local)}
    missing = sorted(names - set(values))
    if missing:
        raise ValueError(f"{default}: missing key(s) {', '.join(missing)}")
    return Local(**{k: values[k] for k in names})
