"""The whole-file arms: a general-purpose agent harness handed the task as files.

Each harness gets a fresh workspace holding the products (never the gold), a TASK.md, and the
same validator the graph and the scorer use (record.py, copied verbatim, behind validate.py). It
is told to do the task in TASK.md and left alone: it decides how to read the file, how many
products to handle per step, and when it is done. Its model requests go through the meter like
every other arm's, all labelled with the item "all", so the report spreads them over the items
(`--items enrich:<arm>=N`).

Isolation, so a run measures the harness at its defaults and not this machine's setup:

- the workspace lives outside any repository (default: the system temp directory), so no
  CLAUDE.md or rules file from a parent directory is read;
- each harness gets its own empty config home (CLAUDE_CONFIG_DIR, HERMES_HOME), so no user
  settings, memory or plugins load; Hermes also runs with --safe-mode;
- the environment is an allowlist: the OS basics plus the variables that point the harness at
  the meter. No API key or other credential is passed.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .tasks import record as record_module
from .tasks.enrich import Item
from .tasks.record import RECORD_SPEC

TASK_MD = f"""# Task: enrich product listings

`products.jsonl` has one product listing per line, as JSON with the keys "id", "title",
"bullets" and "description".

For every product, write a catalog record and append it to `records.jsonl` as one line of JSON:

    {{"id": "<the product's id>", "record": {{...}}}}

{RECORD_SPEC}

Check your work with `python validate.py`. It reads `records.jsonl` and lists every product
whose record is missing or invalid. If a product appears more than once, its last line counts.
The task is done when `python validate.py` reports that every record is valid.
"""

PROMPT = "Do the task described in TASK.md in the current directory."

VALIDATE_PY = '''"""Checks records.jsonl against products.jsonl. Run: python validate.py"""

import json
import os
import sys

from record import listing_text, validate

products = {}
for line in open("products.jsonl", encoding="utf-8"):
    if line.strip():
        p = json.loads(line)
        products[p["id"]] = p
ids = list(products)
records, unreadable = {}, 0
if os.path.exists("records.jsonl"):
    for line in open("records.jsonl", encoding="utf-8"):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
            records[row["id"]] = row["record"]
        except (ValueError, KeyError, TypeError):
            unreadable += 1
problems = []
for i in ids:
    if i not in records:
        problems.append(f"{i}: missing")
    else:
        errs = validate(records[i], listing=listing_text(products[i]))
        if errs:
            problems.append(f"{i}: " + "; ".join(errs))
if unreadable:
    problems.append(f"{unreadable} line(s) of records.jsonl are not {{\\"id\\": ..., \\"record\\": ...}} JSON")
if problems:
    print(f"{len(problems)} problem(s):")
    print("\\n".join(problems))
    sys.exit(1)
print(f"All {len(ids)} records are valid.")
'''

# The OS basics a process needs on Windows, macOS or Linux. Nothing else is inherited.
_BASE_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
             "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "PROGRAMDATA", "PROGRAMFILES", "LANG")  # fmt: skip


def workspace(root: Path, items: list[Item]) -> Path:
    """A fresh workspace at `root` (emptied if it exists) with the task's files."""
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    with (root / "products.jsonl").open("w", encoding="utf-8", newline="\n") as f:
        f.writelines(json.dumps(it.public(), ensure_ascii=False) + "\n" for it in items)
    (root / "TASK.md").write_text(TASK_MD, encoding="utf-8", newline="\n")
    (root / "validate.py").write_text(VALIDATE_PY, encoding="utf-8", newline="\n")
    shutil.copyfile(record_module.__file__, root / "record.py")
    return root


def collect(root: Path) -> dict[str, object]:
    """What the harness wrote: id → record, the last readable line per id. Validity is the
    scorer's business, so invalid records are kept."""
    out: dict[str, object] = {}
    path = root / "records.jsonl"
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            row = json.loads(line)
            out[str(row["id"])] = row["record"]
        except (ValueError, KeyError, TypeError):
            continue
    return out


@dataclass
class Invocation:
    argv: list[str]
    env: dict[str, str]
    cwd: Path


def _env(extra: dict[str, str]) -> dict[str, str]:
    env = {k: os.environ[k] for k in _BASE_ENV if k in os.environ}
    env.update(extra)
    return env


def claude_code(root: Path, base_url: str, model: str, max_turns: int, binary: str = "claude") -> Invocation:
    """Claude Code headless (`claude -p`), every model it uses pointed at `model` through the meter,
    including the small model it calls for side tasks: those requests are part of its cost."""
    home = root / ".home" / "claude"
    home.mkdir(parents=True, exist_ok=True)
    env = _env({
        "ANTHROPIC_BASE_URL": base_url,
        "ANTHROPIC_AUTH_TOKEN": "local",  # the meter and llama-server ignore it; never a real key
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_SMALL_FAST_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "CLAUDE_CONFIG_DIR": str(home),
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    })  # fmt: skip
    argv = [binary, "-p", PROMPT, "--output-format", "json", "--permission-mode", "bypassPermissions",
            "--model", model, "--max-turns", str(max_turns)]  # fmt: skip
    return Invocation(argv, env, root)


def hermes(root: Path, base_url: str, model: str, max_turns: int, binary: str = "hermes") -> Invocation:
    """Hermes Agent one-shot, in safe mode (no user config, memory or plugins), against the meter
    as a custom OpenAI-compatible endpoint."""
    home = root / ".home" / "hermes"
    home.mkdir(parents=True, exist_ok=True)
    env = _env({"HERMES_HOME": str(home)})
    argv = [binary, "chat", "--safe-mode", "--provider", "custom", "--base-url", f"{base_url}/v1",
            "--api-key", "local", "--model", model, "--oneshot", "--quiet", "--yolo", "--source", "tool",
            "--max-turns", str(max_turns), "-q", PROMPT]  # fmt: skip
    return Invocation(argv, env, root)


HARNESSES = {"claude-code": claude_code, "hermes": hermes}


def run(inv: Invocation, timeout_s: int) -> int:
    """Run the harness to completion (or the timeout), its output kept in the workspace."""
    with (inv.cwd / "harness.out").open("wb") as out, (inv.cwd / "harness.err").open("wb") as err:
        try:
            # The binary is resolved here, so a Windows .cmd/.exe shim on PATH is found.
            exe = shutil.which(inv.argv[0], path=inv.env.get("PATH")) or inv.argv[0]
            p = subprocess.run([exe, *inv.argv[1:]], cwd=inv.cwd, env=inv.env, stdout=out, stderr=err,
                               stdin=subprocess.DEVNULL, timeout=timeout_s, check=False)  # fmt: skip
            return p.returncode
        except subprocess.TimeoutExpired:
            err.write(f"\n[avg] timed out after {timeout_s}s\n".encode())
            return -1
