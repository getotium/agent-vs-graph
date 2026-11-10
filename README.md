# agent-vs-graph

A benchmark utility that compares the cost and accuracy of two kinds of AI inference workload run
on the same job:

- **Agent:** the model is given the goal and some tools, and decides each next step itself until
  it is done.
- **Workflow graph:** the steps are written down in advance and run in a fixed order, with the
  model doing one step at a time.

Both get the same tasks, inputs, models and tools, and are scored the same way. Every request to
the model passes through a proxy that counts its tokens, so costs are measured, not estimated.
Neither approach is expected to win everywhere: agents suit work whose steps cannot be known in
advance. The results show where each is cheaper or more accurate, and by how much.

> **About Otium.** This benchmark is maintained by [Otium](https://getotium.ai), which runs batch
> AI workflows on spare cloud GPUs. The benchmark does not use or need Otium: every run here used
> a local GPU or Anthropic's API, and Otium appears in the reports only as one price beside
> OpenAI's and Anthropic's.

> **Status: in development.** Two tasks are published in [`results/`](results/): product
> enrichment, and catalog intake (the same job, with items that should be turned away). Product
> enrichment ran on open models on a local GPU and on Claude Haiku 5.5 through Anthropic's API;
> catalog intake ran on Haiku 5.5. More tasks come next (see [Plan](#plan)). Small test runs are
> not results and are not published.

Why it is built this way: [docs/design.md](docs/design.md). What each table in a report means:
[docs/reading-reports.md](docs/reading-reports.md).

## Results so far

Each run gave the same 500 items to every approach. Each side had one round of improvements
before these runs, then was frozen. Costs are per 1,000 items, at Claude Haiku 5.5's published
prices. Each figure comes from a single run.

| Run | Right, graph vs agent | p | Graph cost | Agent cost | Graph cost, batch |
| --- | --- | ---: | ---: | ---: | ---: |
| [`big-final-think`](results/big-final-think/report.md): Gemma 4 12B, thinking on | 97% vs 95% | 0.012 | $1.25 | $0.88 | $0.62 |
| [`big-final-off`](results/big-final-off/report.md): Gemma 4 12B, thinking off | 94% vs 90% | < 0.001 | $0.22 | $0.29 | $0.11 |
| [`h-final`](results/h-final/report.md): Haiku 5.5, thinking at its default | 97% vs 96% | 0.62 | $0.66 | $0.53 | $0.33 |
| [`h-final-off`](results/h-final-off/report.md): Haiku 5.5, thinking off | 96% vs 96% | – | $0.43 | $0.43 | $0.22 |
| [`h-intake2-20`](results/h-intake2-20/report.md): catalog intake, 20% to turn away | 97% vs 97% | 0.39 | $1.43 | $1.50 | $0.72 |
| [`h-intake2-85`](results/h-intake2-85/report.md): catalog intake, 85% to turn away | 96% vs 96% | 0.77 | $0.37 | $0.45 | $0.18 |

How to read it:

- **p** is the chance of seeing a gap this big if the two were really equally accurate. Below 0.05
  means the gap is probably real; above it, call it a tie.
- **Batch** is the same work sent as a batch: the provider runs it within a day instead of right
  away, at half price. A graph can do this because each step's requests do not depend on each
  other. An agent cannot, because each of its turns waits for the answer to the one before.
- **Thinking** is the model reasoning before it answers. It often helps, and it costs tokens.
- The intake rows use the graph that checks for rejects first (below).

What the runs show so far:

- **The graph was never measurably less accurate.** On the smaller local model it was more
  accurate, with thinking on and off. On Haiku every comparison is a tie.
- **Sent right away, neither is reliably cheaper.** The agent re-sends its whole conversation
  each turn, but providers charge little for text they have just seen (prompt caching). The
  graph's short, separate prompts get little of that discount.
- **Sent as a batch, the graph cost 27–62% less than the agent in every published run.** This is
  its clearest advantage.
- **A graph can turn thinking on and off step by step.** Turning it off for the step that writes
  the product description alone kept the 12B at 97% and cut its cost from $1.25 to $0.85 ($0.42
  in batch). An agent has one setting for the whole conversation.
- **The off-the-shelf agent cost the most.** Claude Code, handed the whole file, cost $1.01 against
  the simple agent's $0.53 for the same 96%. With extra instructions for the task (a skill) it
  cost $3.27 and got 94%.
- **Stopping early only pays if you check before the expensive step.** The agent stops early on
  its own. The first intake graph only checked for rejects after its most expensive step, and cost
  $0.65 per 1,000 items when 85% were rejects. The second checks first and cost $0.37. More in
  [docs/design.md](docs/design.md#catalog-intake).

## What is compared

| Approach | What it is |
| --- | --- |
| **Graph** | A fixed sequence of steps. Each step runs over every item at once and sees only what it needs. |
| **Agent, one per item** | A small tool-using agent for each item, deciding its own steps. Kept minimal, so you can read exactly what it does. |
| **Agent, whole file** | An off-the-shelf agent (Claude Code, Hermes Agent) told "process this file", with its default settings. |

Where we expect the costs to differ, each reported separately:

1. **Re-reading.** On every turn, an agent sends the whole conversation so far back to the model.
   Prompt caching makes the repeated part cheap, and the reports give each provider's caching
   discount in full.
2. **Model size.** A graph can send easy steps to a small, cheap model. An agent uses one model for
   every decision. Each approach is run on a small and a larger model.
3. **Batching.** Every graph step can go as a batch at half price. An agent's turns cannot.
4. **Predictability.** A graph's cost can be estimated before it runs. The reports show how much
   the cost per item varies for each approach.

## How it measures

Every approach talks to its model through **the meter**: a small proxy that passes each request
through unchanged and writes down how many tokens it used. (A token is a piece of a word; providers
charge per token.) It also records a fingerprint of each prompt, so caching can be priced later,
but never the prompt's text. Each approach is pointed at an address that says what it is doing:

```
http://127.0.0.1:8787/t/<run>/<arm>/<task>/<item>
```

The meter works with OpenAI-style and Anthropic-style requests. Because it counts at the point the
request leaves, no framework can hide or double-count a call, and an off-the-shelf agent that lets
you set its server address needs nothing else.

The meter records tokens, not money. **The report** prices them afterwards from a price list
([`prices/default.yaml`](prices/default.yaml)) in which every price names the page it came from and
the date it was checked. So a price change needs no rerun, and any run can be priced as any model.
Caching is priced by replaying each approach's prompts under each provider's own caching rules,
giving the approach the best discount that provider allows. Reports also project the cost to
10,000, 100,000 and 1,000,000 items a month.

Every approach gets the same items, so the graph and the agent on the same model are also compared
item by item: on how many items only one of them was right (McNemar's exact test, which gives the
p above), and on the cost difference per item. Comparing item by item cancels out the items' own
differences (a long listing costs more for everyone), so a real gap shows up with fewer items.

Runs are local first, with llama.cpp serving Google's Gemma 4 at two sizes (E4B and 12B) on one
GPU, so anyone can reproduce the numbers for free. The same tasks are then run on Claude Haiku 5.5
to check that the picture holds on a hosted model.

## Quick start

Needs Python 3.11+ and [Task](https://taskfile.dev).

```
task setup     # create the virtualenv and install
task test      # the tests: no network, no GPU, no API key needed
task check     # lint, format check and tests
```

A dry run against a fake model, to see the meter work:

```
task stub                                   # a fake model on port 8080
task meter                                  # the meter on port 8787, in front of it
curl -s http://127.0.0.1:8787/t/dry/graph/demo/item-1/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model":"m","messages":[{"role":"user","content":"hi"}]}'
task report                                 # price what the meter recorded
```

## Running on your own GPU

Needs a GPU with about 16 GB of free memory for both models. The Taskfile downloads llama.cpp's
Windows (Vulkan) build; on Linux, set `LLAMA_SERVER` to your own build of the same release.

```
task models llama            # download both Gemma 4 models and llama.cpp, checking their hashes
task serve:12b               # in one terminal
task serve:e4b               # in another
task meter:local LEDGER=runs/r1/ledger.jsonl
avg run --shape graph --arm graph --run r1 --limit 20 --small gemma-4-e4b --large gemma-4-12b --out runs/r1/graph.jsonl
avg run --shape agent --arm agent-12b --run r1 --limit 20 --model gemma-4-12b --out runs/r1/agent-12b.jsonl
avg harness --harness claude-code --run r1 --limit 20 --model gemma-4-12b --out runs/r1/claude-code.jsonl
avg score runs/r1/*.jsonl --out runs/r1/scores.json
avg report runs/r1/ledger.jsonl --scores runs/r1/scores.json --items enrich:claude-code=20
```

Or let `task serial RUN=r1` run every approach in turn, one model loaded at a time. It records the
run's settings, including the commit of this repo, in `runs/<run>/meta.json`, and refuses to add to
a run under different settings. `task publish RUN=r1` copies a finished run to
[`results/`](results/): its settings, the meter's records, each approach's outputs, the scores and a
generated report. Server logs are left out, since they describe the machine.

Settings for your machine go in `local.toml` (not committed), which overrides
[`local.default.toml`](local.default.toml): which GPU to use, where the model files are, and where
Hermes Agent is installed. Name the GPU (`device`, part of its name as
`llama-server --list-devices` prints it). Otherwise llama.cpp may spread a model across every GPU
it finds, including a built-in one.

The off-the-shelf agents read the whole file, so they need more room than the default settings
give: serve the model with `SLOTS=1 CTX=65536` for them. Hermes Agent runs from its own checkout
(pass its executable with `--bin`), and Claude Code from `claude` on your PATH. Both run in an
empty scratch folder, with no saved settings or credentials, and can reach only the meter.

## Running on Claude Haiku 5.5

`task hosted RUN=h1 LIMIT=50` runs the graph, the per-item agent and Claude Code on Claude Haiku
5.5 through Anthropic's API. Put your API key in `.env.local` as `ANTHROPIC_API_KEY=...`. That file
is never committed, and only the Taskfile reads it. The meter runs on its own port, so a local run
can go on at the same time.

Options, for `task serial` too:

- `THINKING=default` lets the model decide how much to think. Thinking is off otherwise.
- `INTAKE=20` or `INTAKE=85` runs catalog intake instead of product enrichment, with that
  percentage of items to turn away.

The items are 1,000 product listings from Amazon's Shopping Queries dataset (Apache-2.0). See
[data/enrich/README.md](data/enrich/README.md) for the credit and how they were chosen.

## Plan

1. The meter, price lists and reports. **Done.**
2. Task 1, product enrichment: turn a product listing into a clean catalog record. **Done.**
3. Full runs on a local GPU, with the reports and the meter's records committed. **Done:** 500
   items, thinking on and off.
4. The same task on Claude Haiku 5.5. **Done:** thinking off and at the model's default.
5. Catalog intake: the same task with items that should be turned away, to measure stopping early.
   **Done:** on Haiku, with 20% and 85% to turn away.
6. Task 2 (reviewing code repositories), task 3 (a research brief that cites its sources), and a
   task whose steps cannot be known in advance, where an agent should win.

Every prompt, tool and graph is in this repo. If you can make an agent cheaper without lowering its
score, open a pull request: a better agent makes a better benchmark.

## License

Apache-2.0.
