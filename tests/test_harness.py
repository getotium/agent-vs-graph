"""The whole-file arms: the workspace a harness gets, what is collected from it, and the
isolation of its invocation. The harnesses themselves are not run here."""

import json
import subprocess
import sys

from avg import harness
from avg.tasks import enrich

STEEL = "A steel kettle that boils a full litre of water in under four minutes on any stove"
ITEMS = [
    enrich.Item("p1", "Acme kettle", STEEL, "", {"brand": "SECRET-BRAND", "color": "SECRET-COLOR"}),
    enrich.Item("p2", "Bolt kettle", "", "A kettle.", {"brand": "SECRET-BRAND", "color": "SECRET-COLOR"}),
]
GOOD = {
    "category": "Home & Kitchen",
    "brand": "Acme",
    "color": None,
    "specs": {"material": "steel"},
    "description": " ".join(["word"] * 20),
}


def test_workspace_has_the_task_and_never_the_gold(tmp_path):
    ws = harness.workspace(tmp_path / "ws", ITEMS)
    assert sorted(p.name for p in ws.iterdir()) == ["TASK.md", "products.jsonl", "record.py", "validate.py"]
    for p in ws.iterdir():
        assert "SECRET" not in p.read_text(encoding="utf-8"), p.name
    rows = [json.loads(line) for line in (ws / "products.jsonl").read_text(encoding="utf-8").splitlines()]
    assert rows[0] == {"id": "p1", "title": "Acme kettle", "bullets": STEEL, "description": ""}
    assert "Home & Kitchen" in (ws / "TASK.md").read_text(encoding="utf-8"), "the record spec is in the task"


def test_workspace_is_fresh(tmp_path):
    ws = harness.workspace(tmp_path / "ws", ITEMS)
    (ws / "records.jsonl").write_text("left over\n")
    harness.workspace(ws, ITEMS)
    assert not (ws / "records.jsonl").exists()


def validate_in(ws):
    # The workspace's own script, run the way a harness runs it: plain `python validate.py`.
    return subprocess.run([sys.executable, "validate.py"], cwd=ws, capture_output=True, text=True, check=False)


def test_validate_script_reports_then_passes(tmp_path):
    ws = harness.workspace(tmp_path / "ws", ITEMS)
    first = validate_in(ws)
    assert first.returncode == 1 and "p1: missing" in first.stdout and "p2: missing" in first.stdout

    lines = [{"id": "p1", "record": GOOD}, {"id": "p2", "record": {**GOOD, "category": "Kettles"}}]
    (ws / "records.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines) + "not json\n")
    second = validate_in(ws)
    assert second.returncode == 1
    assert "p2: category 'Kettles' is not one of the allowed categories" in second.stdout
    assert "1 line(s) of records.jsonl" in second.stdout and "p1" not in second.stdout

    copied = {**GOOD, "description": STEEL}
    lines.append({"id": "p1", "record": copied})
    (ws / "records.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    assert "p1: description repeats the listing" in validate_in(ws).stdout, "the copy check runs in the workspace"

    lines.append({"id": "p1", "record": GOOD})
    lines.append({"id": "p2", "record": GOOD})  # the last line for an id counts
    (ws / "records.jsonl").write_text("".join(json.dumps(x) + "\n" for x in lines))
    third = validate_in(ws)
    assert third.returncode == 0 and "All 2 records are valid." in third.stdout


def test_collect_takes_the_last_readable_line_per_id(tmp_path):
    ws = harness.workspace(tmp_path / "ws", ITEMS)
    assert harness.collect(ws) == {}
    rows = [{"id": "p1", "record": {"brand": "old"}}, "garbage", {"id": "p1", "record": GOOD}, {"no": "id"}]
    (ws / "records.jsonl").write_text("".join((json.dumps(r) if isinstance(r, dict) else r) + "\n" for r in rows))
    assert harness.collect(ws) == {"p1": GOOD}


def test_invocations_are_isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-real-key")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-real-key")
    monkeypatch.setenv("CLAUDECODE", "1")
    base = "http://127.0.0.1:8787/t/r/claude-code/enrich/all"

    cc = harness.claude_code(tmp_path, base, "gemma-4-12b", max_turns=50)
    assert cc.env["ANTHROPIC_BASE_URL"] == base and cc.env["ANTHROPIC_SMALL_FAST_MODEL"] == "gemma-4-12b"
    assert cc.env["CLAUDE_CONFIG_DIR"].startswith(str(tmp_path)), "an empty config home, not the user's"
    assert cc.argv[:2] == ["claude", "-p"] and cc.argv[cc.argv.index("--max-turns") + 1] == "50"

    h = harness.hermes(tmp_path, base, "gemma-4-12b", max_turns=50)
    assert "--safe-mode" in h.argv and h.argv[h.argv.index("--base-url") + 1] == base + "/v1"
    assert h.env["HERMES_HOME"].startswith(str(tmp_path))

    for inv in (cc, h):
        assert "sk-real-key" not in json.dumps(inv.env) + json.dumps(inv.argv), "no credential is passed on"
        assert "CLAUDECODE" not in inv.env
        assert inv.cwd == tmp_path
