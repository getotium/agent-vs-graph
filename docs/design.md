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

**The lean graph** (`graph-<model>-lean`) is the same graph with thinking off for its describe step,
run beside the plain graph wherever thinking is on. Choosing per step is something a graph can do
and an agent cannot: an agent decides everything in one conversation, so it thinks for all of it
or none. The step was chosen before the variant was run, from where the first thinking runs spent
their tokens. An agent thought once per item, writing the whole record in one turn; the graph
thought in both its steps, and its describe step, which writes prose from attributes the graph has
already settled, added about 860 thinking tokens per item on the 12B. Extract and repair keep their
thinking, since that is where the brand is decided. It is a variant, not a replacement: the plain
graph stays in every run, so the report shows what the choice changed.

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
5. **Early exit.** A graph's checks are steps in a fixed order, so an item that fails one stops
   there and the expensive steps after it never run: a function returning early, a pipeline job
   skipped by its condition. An agent can stop early too, but only once it has decided to, and it
   decides its own order. Measured by the catalog intake task, below, as cost per item against
   the share of the input that should be rejected.

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

### One round of tuning per side, then frozen

The request an agent gets stays loose, as a person would write it: taking a loose request is what
an agent is for, and tightening it would remove the thing being measured. Tuning belongs to the
builder's side, which both shapes have: a graph's steps, prompts and retries; an agent's system
prompt, tools and skills. Each side got one round, decided and written here before it ran:

- **The graph: repair rounds.** The first graph repaired a failed record once per stage, while the
  agent may take up to eight turns to fix its own. No pipeline gives up after one failed fix, and
  in the first Haiku thinking-off run 14 of the 15 items only the agent got right were graph
  records left invalid by that one repair. The graph now validates and fixes up to three rounds
  per stage, each round going only to the items still failing, and a record whose only fault is
  its description gets a new description from the describe step rather than a full repair. This
  is still fixed control flow: code decides each step and the retries are capped, so the cost
  stays bounded and every round can be a batch.
- **The agent: a skill.** `claude-code-skill-<model>` is Claude Code given a plain request
  ("Enrich the product listings in products.jsonl.") and an `enrich-products` skill: the record
  spec, a way of working (batches of about 20, validate after each, fix only what failed, stay
  clear of the limits) and the validator beside it, as a careful builder would package the job.
  The plain `claude-code` arm, handed TASK.md, stays beside it.

After this round both sides are frozen. A later change to either is a bug fix or a new labelled
variant, recorded here with its reason; results published before a change stay published.

A skill that spells out the procedure is a workflow written in prose, which the agent still
decides turn by turn whether to follow, re-reading it as it goes. How far that closes the gap is
part of the result.

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
   validates, repairs only the failures (up to three rounds) and describes. ESCI was chosen for
   real, messy listings with brand and color as partial gold; the sample is filtered to general
   merchandise ([data/enrich/README.md](../data/enrich/README.md)).
2. **Catalog intake** (task 1 with rejects): below.
3. **Repository review** (planned): a pinned set of small public repositories → per-file
   summaries → per-repository findings → one report. Scored by a fixed rubric with a judge model,
   the same for every arm.
4. **Research brief** (planned): a fixed, pre-fetched corpus → notes → a cited brief, scored on
   whether every claim traces to a document.
5. **A task that favors the agent** (planned): steps that depend on what is found, which a graph
   has to enumerate.

## Catalog intake

A store that ingests a supplier's feed does not want everything in it. Some items are already in
its catalog, some appear twice in the same feed, and some are things it does not sell. Knowing
which takes work: the brand, the model and the kind of product have to be read from the listing
before anything can be checked against the catalog or the store's rules. Only the items that pass
should get the expensive part, the content written for the store's pages. How much of a feed is
rejected depends on the supplier: a specialist taking a specialist's feed rejects a fifth or so; a
specialist taking a general retailer's feed can reject most of it.

**Items.** Built from the same ESCI catalog as task 1, by `avg data intake`, seeded, from public
data only. Each input has an opaque id (`p` and eight hex digits), so nothing about an item can be
read from its id. Every item is one of:

| Kind | What it is | Should be |
| --- | --- | --- |
| new | A product the store does not have | Catalogued: a record and its content |
| catalog duplicate | A product already in `catalog.jsonl`, listed again in different words | Skipped |
| feed duplicate | A second (or third) listing of a product earlier in the same feed | Skipped; one listing of the product catalogued |
| excluded brand | A product of a brand on the store's excluded list | Skipped |
| excluded kind | A book. The store does not sell books | Skipped |

- **Re-listings** are made from the original listing by fixed rules, no model involved: the title's
  parts reordered with the brand moved, the bullet points in reverse order, the description dropped
  when there are bullets and cut to its first half when there are not. The brand, model and
  facts survive, the wording does not match. Feed duplicates are an original and its re-listings.
- **Hard cases are in on purpose.** The catalog also holds other products of each duplicated
  product's brand, and some new items share a brand with catalog entries, so a brand match is not
  enough: the product has to match.
- **Books are known by their product id,** which in ESCI is the ISBN-10 for a book; the ids are
  replaced before any arm sees an item. New items are kept clear of anything that could be read as
  a book or other media, so a correct exclusion is never scored as a wrong one.
- **Two mixes of 500 items:** 20% rejects (`items-20.jsonl`) and 85% rejects (`items-85.jsonl`), each
  with its own `catalog-*.jsonl`. Rejects split 30% catalog duplicates, 20% feed duplicates, 25%
  excluded brands, 25% books. The store's rules (`policy.json`: twelve excluded brands, no books)
  are the same for both.

**What a kept item gets.** Task 1's record (category, brand, color, specs, a short description),
plus the content a store page needs: an SEO title of at most 60 characters, a meta description of
120 to 160 characters and a long description of 120 to 200 words, written rather than copied by
the same rule as the short one. The content is the expensive tail; the report says what it cost
against the checks before it.

**Scoring.** A rejected item succeeds if it was skipped, whatever reason was given; a record
written for it is a failure, and the report counts those records separately because their content
is money spent on an item that should have stopped. A new item succeeds as in task 1: a valid
record (now with its content) and the right brand; skipping it is a failure. A feed duplicate's
listings are scored together: every listing of the product succeeds if exactly one of them has a
valid record with the right brand, and every listing fails otherwise.

**The arms,** each the strongest fair version of its shape:

- **Graph.** Extract the attributes and the model number (small) → the store's rules, in code: an
  excluded brand or a book stops here → repair what remains invalid → match against the catalog and
  the rest of the feed: candidates are entries of the same brand, ranked by shared title words, the
  top three sent to one compare step (small) that names the match or none → write the content for
  what is left → validate and fix, up to three rounds. Every step runs over every item before the
  next, so the feed match sees the whole feed at once.
- **Agent, per item.** The record spec, the rules and the instruction to check before writing, with
  tools to look a brand up in the catalog (`lookup_catalog`, which also returns the products other
  agents in the run have already accepted, as a shared store would), to skip an item with a reason,
  and to validate and submit. Agents run four at a time, as in task 1, so two listings of one product
  can be in flight together; that is part of what is measured.
- **Agent, whole file.** Claude Code handed the feed, the catalog and the rules in TASK.md, with the
  validator, which accepts a skip line (`{"id": ..., "skip": "duplicate" | "excluded"}`) as well as
  a record.

**What the report adds:** success by kind of item, records written for rejects, and each arm's cost
split into the cost of a rejected item and of a kept one, so its cost per 1,000 items can be drawn
for any reject share from 0% to 90%. The two measured mixes check the line, and whether skipping
gets less accurate when most of the feed is rejects.

## At volume

A few hundred items is the measurement; the report projects each arm to 10,000, 100,000 and
1,000,000 documents a month and a year from public prices only. An agent handed a whole file
cannot hold 100,000 documents in one context, so it is projected as the chunk it actually handled,
repeated, and labelled as such.
