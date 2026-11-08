# agent-vs-graph

What does the same job cost when an agent loop drives it, and when it is written down as a fixed
workflow graph? This benchmark measures it: the same tasks, the same inputs, the same models and
tools, scored the same way, run both ways, with every model request counted at the wire.

It is not trying to show that one shape always wins. Agents are the right tool when the steps
are not known in advance; graphs are cheaper when they are. The point is to measure where the
line is and how much it is worth, so you can pick the right shape for your own work.

> **Status: in development.** Task 1 (product enrichment) runs on every arm locally, and its
> first 500-item run is published in [`results/`](results/); the other tasks come next (see
> [Plan](#plan)). Small development runs are not results and are not published.

Why it is built this way, and the decisions behind it: [docs/design.md](docs/design.md).

## What is compared

| Arm | Shape |
| --- | --- |
| **Graph** | A fixed sequence of steps; each step runs over every item at once and reads only its own input. |
| **Agent, per item** | One tool-calling agent per item, deciding its own steps. A minimal loop, so the mechanism is in plain view. |
| **Agent, whole file** | A general-purpose agent harness handed the whole input ("process this file"): Claude Code and Hermes Agent, at their defaults. |

The costs we expect to differ, each reported separately so you can weigh them:

1. **Re-reading.** An agent's turn N sends turns 1 to N−1 again. Prompt caching makes those
   re-reads cheap, so each price gets its provider's cache, replayed over the recorded prompts
   (below), and caching gets full credit where the provider gives it.
2. **Model size per step.** A graph can send easy steps to a small model; an agent uses one
   model for every decision. Each arm runs on a small and a larger model.
3. **Batchability.** Every graph step can be a batch, which vendors sell at half price. An
   agent's turns wait on each other and cannot.
4. **Predictability.** A graph's cost can be estimated before it runs; the spread of cost per
   item shows how far each arm's varies.

## How it measures

Every arm talks to its model through **the meter**, a pass-through proxy that records each
request's tokens and the shape of its prompt (a hash at each point a cache could match, never the
text) to a ledger. The local server's own cache hits are not priced: they depend on how many
slots it runs. The report replays each arm's prompts against each provider's cache rule instead
(automatic from 1,024 tokens for OpenAI; for Anthropic, prefixes marked where a later request
reuses them, the caller's best case). An arm is pointed
at a base URL that names what it is doing:

```
http://127.0.0.1:8787/t/<run>/<arm>/<task>/<item>
```

The meter forwards the rest to the real endpoint, in OpenAI chat-completions or Anthropic
Messages format, streamed or not. Measuring at the wire means no framework can hide or
double-count a request, and a harness that only lets you set a base URL needs nothing else.

The ledger holds tokens, never money. **The report** prices it afterwards from a price sheet
([`prices/default.yaml`](prices/default.yaml)) whose every entry names its source page and the
date it was checked, so a price change needs no rerun and any run can be priced as any model.
It projects each arm to 10,000, 100,000 and 1,000,000 documents a month and a year, with a 90%
bootstrap interval on the cost per item.

Every arm runs the same items, so a graph arm and the agent arm on the same model are also
compared item by item: success with McNemar's exact test on the items where they disagree, cost
as a bootstrap interval on the per-item difference. Pairing takes out the items' own spread (a
long listing costs more in every arm), so a real difference shows with far fewer items.

Runs are local first: llama.cpp's `llama-server` on one GPU, with Google's Gemma 4 at two sizes
(E4B and 12B, the official QAT builds), so the numbers cost nothing to reproduce. A small check
against a hosted API (Claude Haiku 5.5) shows whether the token counts carry over.

## Quick start

Needs Python 3.11+ and [Task](https://taskfile.dev).

```
task setup     # virtualenv and dependencies
task test      # the tests: no network, no GPU, no API key
task check     # lint, format check and tests
```

A dry run against the stand-in model:

```
task stub                                   # a fake model on :8080
task meter                                  # the meter on :8787, in front of it
curl -s http://127.0.0.1:8787/t/dry/graph/demo/item-1/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"m","messages":[{"role":"user","content":"hi"}]}'
task report                                 # price runs/ledger.jsonl
```

## Running task 1 locally

Needs a GPU with about 16 GB free for both models (llama.cpp's Vulkan build is pinned for
Windows; on Linux, set `LLAMA_SERVER` to your own build of the same release).

```
task models llama            # the two Gemma 4 GGUFs and llama.cpp, checked by SHA-256
task serve:12b               # in one terminal; the GPU is `device` in local.toml (see below)
task serve:e4b               # in another
task meter:local LEDGER=runs/r1/ledger.jsonl
avg run --shape graph --arm graph --run r1 --limit 20 --small gemma-4-e4b --large gemma-4-12b --out runs/r1/graph.jsonl
avg run --shape agent --arm agent-12b --run r1 --limit 20 --model gemma-4-12b --out runs/r1/agent-12b.jsonl
avg harness --harness claude-code --run r1 --limit 20 --model gemma-4-12b --out runs/r1/claude-code.jsonl
avg score runs/r1/*.jsonl --out runs/r1/scores.json
avg report runs/r1/ledger.jsonl --scores runs/r1/scores.json --items enrich:claude-code=20
```

A run started by `task serial` records its conditions in `runs/<run>/meta.json`, including the
commit of this repo it ran on; a rerun under other conditions is refused. `task publish RUN=r1`
copies a finished run to [`results/`](results/), the committed record: its conditions, ledger,
each arm's outputs, scores and a generated report. Server logs stay behind, since they name the
machine's hardware.

Settings for your machine go in `local.toml` (gitignored), which overrides any key of
[`local.default.toml`](local.default.toml): the GPU (`device`, a piece of its name as
`llama-server --list-devices` prints it), the model files, Hermes's executable. Pin the GPU by
name. Unpinned, llama.cpp splits a model across every device it finds, and a low device index
can be an integrated GPU. `task serial RUN=r1` then runs every arm in turn, one model loaded at
a time.

The harness arms need a larger context than the default four slots give each request: serve
the model with `SLOTS=1 CTX=65536` for them. Hermes Agent is run from its own source checkout and
virtualenv (pass its executable with `--bin`); Claude Code from `claude` on your PATH. Both run
in a scratch workspace with an empty config home, no credentials, and only the meter to talk to.

The inputs are 1,000 listings from Amazon's Shopping Queries dataset, Apache-2.0; see
[data/enrich/README.md](data/enrich/README.md) for the attribution and how the sample is drawn.

## Plan

1. The meter, ledger, price sheets and report. **Done.**
2. Task 1, product enrichment over a public catalog (Amazon's Shopping Queries dataset,
   Apache-2.0), all arms, a small sample. **Built; first development runs done.**
3. Task 2 (repository review) and task 3 (a cited research brief over a fixed corpus), and a task
   whose steps are open-ended, where an agent should win.
4. The full local run and its report, committed with the ledger. **Task 1 at 500 items, thinking
   off, is in [`results/`](results/); thinking on is running.**
5. The hosted check.

Prompts, tool schemas and graph definitions will all be in this repo. If you can make an agent
arm cheaper without hurting its score, open a pull request: a better agent makes a better
benchmark.

## License

Apache-2.0. Built by [Otium](https://getotium.ai); the benchmark does not use or need Otium.
