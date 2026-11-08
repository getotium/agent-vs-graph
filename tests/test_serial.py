"""The serial runner: which servers each step gets, and that steps never overlap."""

import sys
from pathlib import Path

import pytest

from avg import serial

SMALL = serial.Server("small", "s.gguf", 8082)
LARGE = serial.Server("large", "l.gguf", 8081)
CFG = serial.Config(
    run="r", limit=5, llama_server="llama-server", device="Vulkan1", small=SMALL, large=LARGE,
    large_harness=serial.Server("large", "l.gguf", 8081, ctx=65536), hermes_bin="/h/hermes",
)  # fmt: skip


def test_plan_loads_only_what_each_arm_needs():
    steps = {s.arm: s for s in serial.plan(CFG)}
    assert list(steps) == ["graph", "graph-12b", "agent-12b", "agent-e4b", "claude-code", "hermes"]
    assert [s.alias for s in steps["graph"].servers] == ["small", "large"], "the graph uses both sizes"
    assert [s.alias for s in steps["agent-e4b"].servers] == ["small"]
    assert steps["claude-code"].servers[0].ctx == 65536, "a harness gets room for its system prompt"
    for s in steps.values():
        if s.argv[0] == "run":
            assert s.argv[s.argv.index("--concurrency") + 1] == "1", "one request in flight by default"
    assert steps["hermes"].argv[steps["hermes"].argv.index("--bin") + 1] == "/h/hermes"


def test_server_has_one_slot_on_the_chosen_device():
    argv = serial.server_argv(CFG, LARGE)
    assert argv[argv.index("-np") + 1] == "1" and argv[argv.index("--device") + 1] == "Vulkan1"


class FakeProc:
    def __init__(self, events, name):
        self.events, self.name, self.code = events, name, None

    def poll(self):
        return self.code

    def terminate(self):
        self.events.append(f"stop {self.name}")
        self.code = 0

    def wait(self, timeout=None):
        return self.code


def test_steps_run_one_at_a_time_and_servers_stop_between(tmp_path: Path):
    events: list[str] = []

    def start(argv, log):
        name = argv[argv.index("--alias") + 1]
        events.append(f"start {name}")
        return FakeProc(events, name)

    def run_step(argv):
        events.append(f"run {argv[argv.index('--out') + 1].split('/')[-1]}")
        return 0 if "agent-12b" not in " ".join(argv) else 3

    runner = serial.Runner(start=start, is_healthy=lambda port: True, run_step=run_step, poll_s=0)
    steps = [s for s in serial.plan(CFG) if s.arm in ("graph", "agent-12b", "agent-e4b")]
    codes = runner.sequence(CFG, steps, tmp_path, log=lambda m: None)

    assert codes == {"graph": 0, "agent-12b": 3, "agent-e4b": 0}, "a failed step does not stop the rest"
    assert events == [
        "start small", "start large", "run graph.jsonl", "stop small", "stop large",
        "start large", "run agent-12b.jsonl", "stop large",
        "start small", "run agent-e4b.jsonl", "stop small",
    ]  # fmt: skip


def test_a_server_that_dies_fails_its_step_only(tmp_path: Path):
    events: list[str] = []

    def start(argv, log):
        p = FakeProc(events, argv[argv.index("--alias") + 1])
        p.code = 1  # exited straight away
        return p

    runner = serial.Runner(start=start, is_healthy=lambda port: False, run_step=lambda argv: 0, poll_s=0)
    steps = [s for s in serial.plan(CFG) if s.arm == "agent-e4b"]
    assert runner.sequence(CFG, steps, tmp_path, log=lambda m: None) == {"agent-e4b": -1}


def test_a_missing_binary_fails_its_step_only(tmp_path: Path):
    def start(argv, log):
        raise FileNotFoundError(argv[0])

    runner = serial.Runner(start=start, is_healthy=lambda port: True, run_step=lambda argv: 0, poll_s=0)
    steps = [s for s in serial.plan(CFG) if s.arm in ("agent-e4b", "agent-12b")]
    assert runner.sequence(CFG, steps, tmp_path, log=lambda m: None) == {"agent-12b": -1, "agent-e4b": -1}


def test_resolve_finds_the_real_llama_server_path():
    assert serial.resolve("no-such-binary-xyz") == "no-such-binary-xyz"
    assert serial.resolve(sys.executable) == sys.executable


LISTING = """ggml_vulkan: Found 3 Vulkan devices:
Available devices:
  Vulkan0: Acme GT 100 (8192 MiB, 7000 MiB free)
  Vulkan1: Bolt(TM) Integrated Graphics (16384 MiB, 15000 MiB free)
  Vulkan2: Acme(R) Pro X9 Graphics (32768 MiB, 31000 MiB free)
"""


def test_device_is_picked_by_name_not_index():
    devices = serial.parse_devices(LISTING)
    assert devices == {
        "Vulkan0": "Acme GT 100",
        "Vulkan1": "Bolt(TM) Integrated Graphics",
        "Vulkan2": "Acme(R) Pro X9 Graphics",
    }, "a (TM) in the name is kept; the memory note is not"
    assert serial.pick_device("X9", devices) == "Vulkan2"
    assert serial.pick_device("vulkan0", {"vulkan0": "x"}) == "vulkan0", "an id as listed is taken as is"


def test_an_ambiguous_or_unknown_device_is_refused():
    devices = serial.parse_devices(LISTING)
    for spec in ("Graphics", "H100"):  # two matches; none
        try:
            serial.pick_device(spec, devices)
        except ValueError as e:
            assert "Vulkan2 (Acme(R) Pro X9 Graphics)" in str(e), "the error lists what there is"
        else:
            raise AssertionError(spec)


def test_no_device_leaves_the_choice_to_llama_cpp():
    from dataclasses import replace

    assert "--device" not in serial.server_argv(replace(CFG, device=""), LARGE)


def test_slots_give_each_request_its_own_context_but_a_harness_one():
    from dataclasses import replace

    steps = {s.arm: s for s in serial.plan(replace(CFG, slots=4))}
    agent = steps["agent-12b"]
    assert agent.argv[agent.argv.index("--concurrency") + 1] == "4"
    argv = serial.server_argv(CFG, agent.servers[0])
    assert argv[argv.index("-np") + 1] == "4" and argv[argv.index("-c") + 1] == str(4 * 16384), "ctx is per slot"
    assert steps["claude-code"].servers[0].slots == 1


def test_an_arm_already_in_the_ledger_is_not_run_twice(tmp_path: Path):
    from avg import ledger
    from avg.ledger import Record

    path = tmp_path / "ledger.jsonl"
    ledger.append(path, Record(run="r", arm="agent-e4b", task="t", item="i", wire="openai", model="m", input=1,
                               cache_read=0, cache_write=0, output=1, latency_ms=1, status=200))  # fmt: skip
    ran: list[str] = []
    runner = serial.Runner(start=lambda argv, log: FakeProc([], "x"), is_healthy=lambda port: True,
                           run_step=lambda argv: ran.append(argv[argv.index("--arm") + 1]) or 0, poll_s=0)  # fmt: skip
    steps = [s for s in serial.plan(CFG) if s.arm == "agent-e4b"]
    quiet = lambda m: None
    assert runner.sequence(CFG, steps, tmp_path, quiet, ledger_path=path) == {"agent-e4b": -3}
    assert ran == [], "refused before anything started"
    assert runner.sequence(CFG, steps, tmp_path, quiet, ledger_path=path, replace=True) == {"agent-e4b": 0}
    assert ran == ["agent-e4b"] and ledger.arms(path, "r") == set(), "the first attempt was removed"


def test_a_server_that_dies_during_a_step_marks_it_broken(tmp_path: Path):
    procs: list[FakeProc] = []

    def start(argv, log):
        procs.append(FakeProc([], "x"))
        return procs[-1]

    def run_step(argv):
        procs[-1].code = 1  # the server crashed while the arm ran
        return 0

    runner = serial.Runner(start=start, is_healthy=lambda port: procs[-1].code is None, run_step=run_step, poll_s=0)
    steps = [s for s in serial.plan(CFG) if s.arm == "agent-e4b"]
    assert runner.sequence(CFG, steps, tmp_path, log=lambda m: None) == {"agent-e4b": -2}


def test_thinking_is_off_unless_given_a_budget():
    from dataclasses import replace

    off = serial.server_argv(CFG, LARGE)
    assert off[off.index("--reasoning") + 1] == "off" and "--reasoning-budget" not in off
    on = serial.server_argv(replace(CFG, thinking=1024), LARGE)
    assert on[on.index("--reasoning-budget") + 1] == "1024"


def test_code_version_names_the_commit_and_uncommitted_changes():
    def git(clean):
        return lambda args: "abc123def456\n" if args[0] == "rev-parse" else ("" if clean else " M src/avg/cli.py\n")

    assert serial.code_version(git(True)) == "abc123def456"
    assert serial.code_version(git(False)) == "abc123def456-dirty"

    def no_git(args):
        raise OSError("git not found")

    assert serial.code_version(no_git) == "unknown"


def test_a_run_keeps_the_conditions_it_started_under(tmp_path: Path):
    path = tmp_path / "meta.json"
    serial.check_meta(path, {"limit": 5, "thinking": 0, "code": "a"})
    serial.check_meta(path, {"limit": 5, "thinking": 0, "code": "a"})  # a resumed run: same conditions
    with pytest.raises(ValueError, match="code, thinking"):
        serial.check_meta(path, {"limit": 5, "thinking": 3072, "code": "b"})


def test_a_run_started_before_a_condition_was_recorded_is_not_backfilled(tmp_path: Path):
    path = tmp_path / "meta.json"
    path.write_text('{"limit": 5}', encoding="utf-8")
    serial.check_meta(path, {"limit": 5, "code": "b"})
    assert path.read_text(encoding="utf-8") == '{"limit": 5}', "the code it started at is not known, so not guessed"
