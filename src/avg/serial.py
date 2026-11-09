"""Running the arms one after another, so a run does not take over the machine it runs on.

Each step starts only the model server(s) its arm needs, runs the arm, and stops the servers
before the next step starts. A per-item arm runs `slots` requests at once, each with a slot of its
own on the server; a harness is one process talking to one slot.

The GPU is chosen by name, not by index. llama.cpp numbers devices in the order the driver lists
them, and on a machine with an integrated GPU a low index can be the iGPU, which shares system
memory with the desktop: prompt processing crawls and the desktop lags. `pick_device` matches a
name against `llama-server --list-devices`. Which device, and the paths, come from avg.config.

The meter runs for the whole sequence, in front of fixed ports; a step's servers come and go
behind it.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from pathlib import Path

from . import ledger


@dataclass(frozen=True)
class Server:
    alias: str  # the model name the arms ask for, and the meter routes on
    gguf: str
    port: int
    ctx: int = 16384  # per slot
    slots: int = 1


@dataclass
class Step:
    arm: str
    servers: list[Server]
    argv: list[str]  # the avg command that runs the arm


@dataclass
class Config:
    run: str
    limit: int
    llama_server: str
    device: str  # a device id as llama.cpp lists it; "" leaves the choice to llama.cpp
    small: Server
    large: Server
    large_harness: Server  # the large model with room for a harness's system prompt
    meter_port: int = 8787
    hermes_bin: str = ""
    slots: int = 1  # requests in flight for the per-item arms
    # Thinking tokens per reply, the same for every arm and harness: 0 off, N a budget, -1 no limit.
    # Off by default: how much a model thinks is its own habit and does not carry over to a hosted
    # model's bill, and an unlimited budget ran some replies into the output cap.
    thinking: int = 0
    harnesses: list[str] = field(default_factory=lambda: ["claude-code", "hermes"])


# The lean graph: the same graph with its describe step's thinking off. Chosen before it was run,
# from where the thinking runs spent their tokens (the description, written from attributes the
# graph has already settled), and run only where thinking is on: otherwise it is the plain graph.
LEAN = ["--no-thinking", "describe"]


def plan(c: Config) -> list[Step]:
    """The arms of task 1, in order."""
    small, large, n = replace(c.small, slots=c.slots), replace(c.large, slots=c.slots), str(c.slots)
    meter = f"http://127.0.0.1:{c.meter_port}"
    common = ["--run", c.run, "--limit", str(c.limit), "--meter", meter]
    out = lambda arm: ["--out", f"runs/{c.run}/{arm}.jsonl"]
    steps = [
        Step("graph", [small, large],
             ["run", "--shape", "graph", "--arm", "graph", *common, "--small", small.alias, "--large", large.alias,
              "--concurrency", n, *out("graph")]),
        Step("graph-12b", [large],
             ["run", "--shape", "graph", "--arm", "graph-12b", *common, "--model", large.alias, "--concurrency", n,
              *out("graph-12b")]),
    ]  # fmt: skip
    if c.thinking != 0:
        steps.append(Step("graph-12b-lean", [large],
                          ["run", "--shape", "graph", "--arm", "graph-12b-lean", *common, "--model", large.alias,
                           *LEAN, "--concurrency", n, *out("graph-12b-lean")]))  # fmt: skip
    steps += [
        Step("agent-12b", [large],
             ["run", "--shape", "agent", "--arm", "agent-12b", *common, "--model", large.alias, "--concurrency", n,
              *out("agent-12b")]),
        Step("agent-e4b", [small],
             ["run", "--shape", "agent", "--arm", "agent-e4b", *common, "--model", small.alias, "--concurrency", n,
              *out("agent-e4b")]),
    ]  # fmt: skip
    for h in c.harnesses:
        extra = ["--bin", c.hermes_bin] if h == "hermes" and c.hermes_bin else []
        steps.append(
            Step(h, [c.large_harness],
                 ["harness", "--harness", h, *common, "--model", c.large_harness.alias, *extra, *out(h)])
        )  # fmt: skip
    return steps


# A hosted run starts no model servers; its Config only carries the run, the slots and the port.
_NO_SERVER = Server("", "", 0)


def hosted_config(run: str, limit: int, slots: int, meter_port: int) -> Config:
    return Config(run=run, limit=limit, llama_server="", device="", small=_NO_SERVER, large=_NO_SERVER,
                  large_harness=_NO_SERVER, meter_port=meter_port, slots=slots)  # fmt: skip


def hosted_plan(c: Config, model: str, thinking: str = "off", tag: str = "haiku") -> list[Step]:
    """The same arms against a hosted Anthropic model: the graph and the per-item agent on the
    native Messages API, and Claude Code. Hermes is left out: it is run against local models.

    Thinking "off" leaves Claude Code out too: it cannot turn thinking off on a model that thinks
    by default (MAX_THINKING_TOKENS and its disable switch do not stop it), and a harness that
    thinks beside arms that do not is not the same condition. "default" runs every arm as the
    model ships."""
    meter, n = f"http://127.0.0.1:{c.meter_port}", str(c.slots)
    common = ["--run", c.run, "--limit", str(c.limit), "--meter", meter]
    out = lambda arm: ["--out", f"runs/{c.run}/{arm}.jsonl"]
    graph, agent, code = f"graph-{tag}", f"agent-{tag}", f"claude-code-{tag}"
    wire = ["--wire", "anthropic", "--thinking", thinking]
    steps = [
        Step(graph, [], ["run", "--shape", "graph", "--arm", graph, *common, "--model", model, *wire,
                         "--concurrency", n, *out(graph)]),
        Step(agent, [], ["run", "--shape", "agent", "--arm", agent, *common, "--model", model, *wire,
                         "--concurrency", n, *out(agent)]),
    ]  # fmt: skip
    if thinking == "default":
        steps.insert(1, Step(f"{graph}-lean", [], ["run", "--shape", "graph", "--arm", f"{graph}-lean", *common,
                                                   "--model", model, *wire, *LEAN, "--concurrency", n,
                                                   *out(f"{graph}-lean")]))  # fmt: skip
        steps.append(Step(code, [], ["harness", "--harness", "claude-code", "--arm", code, *common, "--model", model,
                                     "--hosted", *out(code)]))  # fmt: skip
        skill = f"claude-code-skill-{tag}"
        steps.append(Step(skill, [], ["harness", "--harness", "claude-code", "--arm", skill, *common,
                                      "--model", model, "--hosted", "--skill", *out(skill)]))  # fmt: skip
    return steps


def server_argv(c: Config, s: Server) -> list[str]:
    device = ["--device", c.device] if c.device else []
    if c.thinking == 0:
        think = ["--reasoning", "off"]
    else:
        think = ["--reasoning", "on", "--reasoning-budget", str(c.thinking)]
    return [c.llama_server, "-m", s.gguf, "--alias", s.alias, *device, *think, "-ngl", "99", "--jinja",
            "-np", str(s.slots), "-c", str(s.ctx * s.slots), "--host", "127.0.0.1", "--port", str(s.port)]  # fmt: skip


def healthy(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=2) as r:
            return r.status == 200
    except OSError:
        return False


@dataclass
class Runner:
    """Starts processes and waits on them; the defaults are the real thing, tests swap them."""

    start: Callable[[list[str], Path], subprocess.Popen] = lambda argv, log: subprocess.Popen(
        [resolve(argv[0]), *argv[1:]], stdout=log.open("ab"), stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL
    )
    is_healthy: Callable[[int], bool] = healthy
    run_step: Callable[[list[str]], int] = lambda argv: subprocess.call([sys.executable, "-m", "avg.cli", *argv])
    wait_s: float = 600
    poll_s: float = 2

    def up(self, c: Config, s: Server, logs: Path) -> subprocess.Popen:
        p = self.start(server_argv(c, s), logs / f"llama-{s.alias}.log")
        deadline = time.monotonic() + self.wait_s
        while not self.is_healthy(s.port):
            if p.poll() is not None or time.monotonic() > deadline:
                stop(p)
                raise RuntimeError(f"{s.alias} did not come up; see {logs / f'llama-{s.alias}.log'}")
            time.sleep(self.poll_s)
        return p

    def sequence(
        self,
        c: Config,
        steps: list[Step],
        logs: Path,
        log: Callable[[str], None] = print,
        ledger_path: Path | None = None,
        replace: bool = False,
    ) -> dict[str, int]:
        """Each step's exit code. A step that fails is recorded and the next one still runs.

        A step whose arm already has records for this run in the ledger is refused (-3), since a
        second attempt would be summed with the first; `replace` removes the first attempt. A step
        whose server died while it ran is marked broken (-2): its failures are the server's."""
        logs.mkdir(parents=True, exist_ok=True)
        codes: dict[str, int] = {}
        for step in steps:
            if ledger_path is not None and step.arm in ledger.arms(ledger_path, c.run):
                if not replace:
                    log(f"[serial] {step.arm}: already has records in run {c.run}; pass --replace to rerun it")
                    codes[step.arm] = -3
                    continue
                log(f"[serial] {step.arm}: removed {ledger.drop(ledger_path, c.run, step.arm)} earlier records")
            procs: list[subprocess.Popen] = []
            try:
                for s in step.servers:
                    procs.append(self.up(c, s, logs))
                log(f"[serial] {step.arm}: running with {', '.join(s.alias for s in step.servers)}")
                codes[step.arm] = self.run_step(step.argv)
                dead = [s.alias for s, p in zip(step.servers, procs, strict=True)
                        if p.poll() is not None or not self.is_healthy(s.port)]  # fmt: skip
                if dead:
                    log(f"[serial] {step.arm}: {', '.join(dead)} died during the step; its results are not valid")
                    codes[step.arm] = -2
            except (RuntimeError, OSError) as e:  # a server that will not start, or is not there
                log(f"[serial] {step.arm}: {e}")
                codes[step.arm] = -1
            finally:
                for p in procs:
                    stop(p)
            log(f"[serial] {step.arm}: exit {codes[step.arm]}")
        return codes


_DEVICE_LINE = re.compile(r"^\s*(\w+\d+):\s*(.+?)(?:\s*\(\d+ MiB[^()]*\))?\s*$")


def parse_devices(listing: str) -> dict[str, str]:
    """`llama-server --list-devices` output → {"Vulkan0": "<the device's name>", ...}."""
    out = {}
    for line in listing.splitlines():
        m = _DEVICE_LINE.match(line)
        if m:
            out[m.group(1)] = m.group(2)
    return out


def pick_device(spec: str, devices: dict[str, str]) -> str:
    """The device id for `spec`: an id as listed, or a piece of exactly one device's name."""
    if spec in devices:
        return spec
    hits = [d for d, name in devices.items() if spec.lower() in name.lower()]
    if len(hits) != 1:
        found = ", ".join(f"{d} ({n})" for d, n in devices.items()) or "none"
        raise ValueError(f"device {spec!r} matches {len(hits)} of: {found}")
    return hits[0]


def list_devices(llama_server: str) -> dict[str, str]:
    p = subprocess.run([resolve(llama_server), "--list-devices"], capture_output=True, text=True, check=False)
    return parse_devices(p.stdout + p.stderr)


def resolve(exe: str) -> str:
    """The executable as Windows needs it: CreateProcess does not find a relative path that
    lacks its .exe, which shutil.which does (PATHEXT)."""
    found = shutil.which(exe)
    if found:
        return found
    win = Path(exe + ".exe")
    return str(win.resolve()) if sys.platform == "win32" and win.is_file() else exe


def stop(p: subprocess.Popen) -> None:
    if p.poll() is None:
        p.terminate()
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait()


def code_version(run_git: Callable[[list[str]], str] | None = None) -> str:
    """The commit the code is at, with "-dirty" when tracked files have uncommitted changes, so a
    published run names the code that produced it. "unknown" outside a git checkout."""
    if run_git is None:

        def run_git(args: list[str]) -> str:
            return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout

    try:
        sha = run_git(["rev-parse", "--short=12", "HEAD"]).strip()
        dirty = run_git(["status", "--porcelain", "--untracked-files=no"]).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"
    return f"{sha}-dirty" if dirty else sha


def check_meta(path: Path, meta: dict) -> None:
    """Record a run's conditions, or refuse when the run was started under others. A key the
    earlier file lacks was added after that run began and is left unrecorded, not guessed."""
    if path.exists():
        old = json.loads(path.read_text(encoding="utf-8"))
        changed = sorted(k for k, v in old.items() if meta.get(k) != v)
        if changed:
            raise ValueError(f"{path} was written under other conditions ({', '.join(changed)}); use a new run name")
        return
    path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
