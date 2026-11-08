# Design

Why the benchmark measures what it does, and the decisions behind it. The README says how to run
it; this says why it is built this way. When a decision changes, change it here with the reason.

## The question

When the steps of a job are known in advance, does writing them down as a fixed workflow graph
cost less than letting an agent loop drive the same work, and by how much? Agents are the right
tool when the steps are not known; the point is to find where the line is and what it is worth,
with numbers anyone can rerun, and with the agent side built the way people actually build agents.

## The arms

The same tasks, inputs, models and tools, scored the same way, run as:

| Arm | Shape |
| --- | --- |
| **Graph** | A fixed sequence of steps; each step runs over every item at once and reads only its own input. |
| **Agent, per item** | One tool-calling agent per item, deciding its own steps: the common "agent per record". A minimal loop, so the mechanism is in plain view. |
| **Agent, whole file** | A general-purpose agent harness handed the whole input ("process this file"), deciding everything: Claude Code and Hermes Agent, at their defaults. |

Arm names say the shape and the model: `graph-12b` and `agent-12b` run on the same model, so they
differ only in shape; `graph` routes its easy steps to the small model and repairs to the large one.

## What should differ, and how each is measured

1. **Re-reading.** An agent's turn N sends turns 1 to N−1 again, with its tool definitions; a
   graph step sends its own input. Measured as prompt tokens per item, with each provider's prompt
   cache replayed over the recorded prompts so caching gets full credit (below).
2. **Model size per step.** A graph can send easy steps to a small model; an agent uses one model
   for every decision. Every arm runs on two sizes.
3. **Batchability.** Every graph step can be a batch, which vendors sell at about half price. An
   agent's turns wait on each other and cannot. The report prices graphs at both rates and agents
   at real-time only, so the saving from the shape and the saving from the discount read apart.
4. **Predictability.** A graph's cost can be estimated before it runs; the report shows each
   arm's per-item tail (p95, max) beside the mean.

## Measuring at the wire

Every request goes through the meter, a pass-through proxy that records tokens, latency and the
shape of the prompt to a ledger. No framework can hide or double-count a request, and a harness
that only lets you set a base URL needs nothing else. The ledger holds tokens, never money: the
report prices it afterwards from a sheet whose every entry names its source page and the date it
was checked, so a price change never needs a rerun.

**Prompt caching is replayed, not read from the local server.** The local server's cache hits
depend on how many slots it runs, which says nothing about what a provider would bill. The meter
records a hash of the prompt at each point a cache could match (never the text), and the report
replays each provider's own rule over them: automatic caching of every prefix past a minimum for
OpenAI, prefixes marked where a later request reuses them for Anthropic (the caller's best case),
each with its minimum length and lifetime. An entry is usable only once the request that wrote it
has finished.

## Scoring

Task 1's record has a shared validator, used by the graph, by every agent to check its work, and
by the scorer: the same code everywhere. Success is a valid record with the right brand (the
catalog's own field is the gold answer); color agreement is reported beside it but is not part of
success.

**Records must be written, not copied.** Without a check, an arm can pass by pasting the listing
back. The validator rejects a description whose 5-word phrases are more than half verbatim from
the listing, and a spec value of six or more words cut from the listing mid-word. The thresholds
were set from the first 20 items' outputs: descriptions a model wrote peaked at 40% copied, ones
assembled from the listing's sentences ran 70% to 100%. The spec states the rule in words only:
stating the numbers made the 12B count phrases while it thought until it ran out of tokens.

## Fairness

The benchmark counts only if an agent builder reading it agrees the agent side is how they would
build it.

- **Cost per successful item** is reported beside raw cost and success rate: an arm cannot look
  cheap by failing.
- **Prompts in the open:** every system prompt, tool schema and graph definition is in this repo,
  and the record spec is shared word for word by every arm.
- **Harnesses at their defaults,** pinned by version; the minimal loop shows the mechanism, it is
  not the only agent.
- **A failure that is the run's, not the model's, never counts against an arm.** An unreachable
  server stops the run loudly instead of scoring as failed items; a tool call the local server
  cannot parse costs the agent a turn and a message saying so, not the item.
- **Where agents win is stated:** open-ended work whose steps are not known in advance. One task
  is built to favor the agent.
- **Pull requests that make an agent arm cheaper without hurting its score are welcome.**

## Statistics

Each arm's mean cost per item carries a 90% bootstrap interval: how sure the sample makes us of
the average, not how much a real month will vary. At 500 items the intervals are about ±2%.

Every arm runs the same items, so a graph arm and the agent on the same model are compared item by
item: success with McNemar's exact test (only the items where the arms disagree say which is
better), cost as a bootstrap interval on the per-item difference. Pairing removes the items' own
spread, which is most of the variation.

## Running conditions

- **Local first.** llama.cpp's `llama-server` with Google's Gemma 4 at two sizes, E4B and 12B, the
  official QAT builds pinned by revision and SHA-256. The same family and quantization at both
  sizes, so size is the only thing that changes. Local runs cost nothing to reproduce; a small
  hosted check shows whether the token counts carry over.
- **One model loaded at a time.** `avg serial` runs the arms in turn, starting only the servers
  each arm needs, so a run does not take over the machine. Per-item arms run four requests at once,
  each with its own server slot; a harness gets one slot with a larger context.
- **Thinking is a condition of the run,** off or a fixed token budget for every arm, recorded with
  the run. Both conditions are published: thinking changes output length several times over, and
  which shape it favors is a result.
- **Hosted runs** put the same arms on Claude Haiku 5.5 through Anthropic's own API, so the
  agent arms run on a model of the kind they are built for, and the token counts and cache use
  are the vendor's, not estimates. Our own arms speak the native Messages API rather than an
  OpenAI-compatible shim, so caching can be set as a careful builder would: every arm marks its
  shared system prompt, and the agent also turns on automatic caching of its growing conversation
  (the documented pattern for agent loops). A graph step's request ends in one item's listing, so
  caching its tail would only pay the write premium. Sampling is left at the model's default,
  which this model requires. Requests the priced model answered itself are billed as the vendor
  counted them; nothing is replayed for them.
- **Hosted runs have two conditions.** *Model default*: every arm runs the model as it ships
  (Haiku 5.5: adaptive thinking at medium effort), the way customers use it. *Thinking off*: the
  graph and the per-item agent with thinking disabled, matching the local thinking-off runs.
  Claude Code is not in the thinking-off runs: on a model that thinks by default it cannot turn
  thinking off (its `MAX_THINKING_TOKENS` and disable switch do not stop it), and a harness that
  thinks beside arms that do not would not be the same condition. Thinking tokens are reported
  separately where the server gives them, so how much of an arm's output was thinking is visible.
  Arms are compared only within one run: model, tokenizer and thinking all change the counts.
- **A run records its conditions** (items, slots, thinking, token cap, models, the llama.cpp
  build and the commit of this repo) and refuses to resume under different ones.

## Tasks

Each with public inputs under a checked license, a gold answer or a fixed rubric, and an item
count that keeps a local run to hours.

1. **Product enrichment.** Listings from Amazon's Shopping Queries Dataset (ESCI, Apache-2.0) →
   category, brand, color, specs and a short description as validated JSON. The graph extracts,
   validates, repairs only the failures and describes. ESCI was chosen for real, messy listings
   with brand and color as partial gold; the sample is filtered to general merchandise
   ([data/enrich/README.md](../data/enrich/README.md)).
2. **Repository review** (planned): a pinned set of small public repositories → per-file
   summaries → per-repository findings → one report. Scored by a fixed rubric with a judge model,
   the same for every arm.
3. **Research brief** (planned): a fixed, pre-fetched corpus → notes → a cited brief, scored on
   whether every claim traces to a document.
4. **A task that favors the agent** (planned): steps that depend on what is found, which a graph
   has to enumerate.

## At volume

A few hundred items is the measurement; the report projects each arm to 10,000, 100,000 and
1,000,000 documents a month and a year from public prices only. An agent handed a whole file
cannot hold 100,000 documents in one context, so it is projected as the chunk it actually handled,
repeated, and labelled as such.
