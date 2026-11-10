# Run h-intake2-85

One run of [agent-vs-graph](../../README.md), which measures what the same job costs when a fixed workflow graph does it and when agent loops do. Task: `intake`, catalog intake: each item is a listing from a supplier's feed, to be catalogued with page content or skipped as a duplicate or excluded product. The first 500 items were given to every arm below. Every model request was metered; costs are those tokens priced afterwards at each vendor's published rates. This page is generated from the files beside it by `avg publish` and not edited by hand.

Read more: [how to read this report](../../docs/reading-reports.md) · [why it is measured this way](../../docs/design.md) · [all published runs](../README.md)

## In brief

- **Success** is a skip for an item the store should not take (a duplicate, an excluded brand, a book), and for a new product a record with its page content that passes the shared validator and names the right brand. A product listed several times in the feed succeeds when exactly one listing is catalogued.
- **Costs** are per item, as each vendor would bill the run's tokens. The run used claude-haiku-5-5 through its vendor's API: priced as that model, the figures are what the run cost. Priced as another model, they use this model's token counts, so they compare arms like for like rather than quote a bill.
- **Batch** prices apply only to graph arms; an agent's requests wait on each other's answers.
- **Ranges** in brackets are 90% intervals on the average, from resampling the items.
- **Graph against agent** puts the same model in both shapes side by side, item by item.

## Arms

| Arm | Shape | Model |
| --- | --- | --- |
| agent-haiku | One tool-calling agent per item | claude-haiku-5-5 |
| claude-code-haiku | Agent harness handed the whole input file | claude-haiku-5-5 |
| graph-haiku | Workflow graph; every step on one model | claude-haiku-5-5 |
| graph-haiku-gated | Workflow graph; every step on one model, a cheap sort step first and loose brand matching | claude-haiku-5-5 |

## Conditions

| Setting | Value | Meaning |
| --- | --- | --- |
| limit | 500 | items in the run, the first N of the task's input file |
| slots | 4 | requests a per-item arm keeps in flight at once; changes speed, not tokens |
| thinking | model default | 0: no thinking phase; N: up to N thinking tokens per reply |
| max_tokens | 4096 | the cap on one reply, thinking included |
| provider | anthropic | the hosted API the run used; its own counts are the bill when priced as its model |
| model | claude-haiku-5-5 | the hosted model every arm used |
| anthropic_version | 2023-06-01 | the Messages API version the requests named |
| code | 58e3365d4570 | the commit of this repo the run used |
| task | intake | the task, when it is not task 1 |
| items | data/intake/items-85.jsonl | the input file: for catalog intake, the mix (items-20: 20% of the feed should be rejected) |

## Scores

How often each arm's output was right, against the catalog's own fields. Columns: [reading a report](../../docs/reading-reports.md#scores).

| Arm | Items | New catalogued | Duplicates skipped | Exclusions skipped | Records for rejects | Success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | 500 | 92% | 94% | 100% | 8 | 96% |
| claude-code-haiku | 500 | 95% | 97% | 100% | 2 | 98% |
| graph-haiku | 500 | 96% | 94% | 98% | 13 | 96% |
| graph-haiku-gated | 500 | 93% | 94% | 100% | 8 | 96% |

## Task: intake

### Tokens per item

What each arm sent to the model and got back, per item, counted at the wire. Columns: [reading a report](../../docs/reading-reports.md#tokens-per-item).

| Arm | Items | Requests / item | Prompt | Output | Of which thinking | Refused requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | 500 | 1.8 | 3,770 | 669 | 342 | 0 |
| claude-code-haiku | 500 | 0.1 | 7,659 | 232 | 126 | 0 |
| graph-haiku | 500 | 1.7 | 1,262 | 1,057 | 725 | 0 |
| graph-haiku-gated | 500 | 1.8 | 1,012 | 533 | 361 | 0 |

Prompt counts every input token. What a provider would have served from its cache is
replayed from the recorded prompts under each price's own cache rule, below. Refused
requests are not priced: the server reports no usage for them.

### Priced as claude-haiku-5-5 (Anthropic)

What the run's tokens would cost at Anthropic's published prices for claude-haiku-5-5, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | 82% | 96% | $0.45 | $0.47 | $0.0020 | $4.49 ($4.02–$4.98) | $44.91 ($40.22–$49.79) | $449.15 ($402.18–$497.93) | $5,390 |
| claude-code-haiku | real-time | 93% | 98% | $1.15 | $1.17 | $0.0011 | $11.48 | $114.78 | $1,148 | $13,773 |
| graph-haiku | real-time | 1% | 96% | $0.65 | $0.68 | $0.0017 | $6.54 ($6.16–$6.96) | $65.43 ($61.61–$69.59) | $654.30 ($616.10–$695.94) | $7,852 |
| graph-haiku | batch | 1% | 96% | $0.33 | $0.34 | $0.0008 | $3.27 ($3.08–$3.48) | $32.71 ($30.80–$34.80) | $327.15 ($308.05–$347.97) | $3,926 |
| graph-haiku-gated | real-time | 0% | 96% | $0.37 | $0.38 | $0.0017 | $3.68 ($3.20–$4.18) | $36.79 ($32.02–$41.83) | $367.95 ($320.18–$418.26) | $4,415 |
| graph-haiku-gated | batch | 0% | 96% | $0.18 | $0.19 | $0.0009 | $1.84 ($1.60–$2.09) | $18.40 ($16.01–$20.91) | $183.97 ($160.09–$209.13) | $2,208 |

Rates from https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-06. Cache replayed as Anthropic's: prefixes marked where a later request reuses them (the best case), from 512 tokens, 5-minute lifetime. 2,706 requests were answered by claude-haiku-5-5 itself and are priced as Anthropic counted them, cache included, not replayed.

### Priced as gpt-6-luna (OpenAI)

What the run's tokens would cost at OpenAI's published prices for gpt-6-luna, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | 77% | 96% | $0.45 | $0.47 | $0.0020 | $4.49 ($4.01–$4.98) | $44.90 ($40.14–$49.84) | $449.00 ($401.42–$498.44) | $5,388 |
| claude-code-haiku | real-time | 92% | 98% | $0.24 | $0.25 | $0.0002 | $2.45 | $24.47 | $244.74 | $2,937 |
| graph-haiku | real-time | 0% | 96% | $0.65 | $0.68 | $0.0017 | $6.55 ($6.17–$6.96) | $65.47 ($61.66–$69.62) | $654.70 ($616.61–$696.18) | $7,856 |
| graph-haiku | batch | 0% | 96% | $0.33 | $0.34 | $0.0008 | $3.27 ($3.08–$3.48) | $32.74 ($30.83–$34.81) | $327.35 ($308.30–$348.09) | $3,928 |
| graph-haiku-gated | real-time | 0% | 96% | $0.37 | $0.38 | $0.0017 | $3.68 ($3.20–$4.18) | $36.79 ($32.02–$41.82) | $367.89 ($320.18–$418.19) | $4,415 |
| graph-haiku-gated | batch | 0% | 96% | $0.18 | $0.19 | $0.0009 | $1.84 ($1.60–$2.09) | $18.39 ($16.01–$20.91) | $183.95 ($160.09–$209.09) | $2,207 |

Rates from https://openai.com/api/pricing/, checked 2026-10-28. Cache replayed as OpenAI's: every prefix it sees, from 1,024 tokens, 5-minute lifetime. **Unverified:** OpenAI's pricing page refuses automated fetches. Input and output are as recorded on getotium.ai's rate card (2026-10-28); the cached rate assumes OpenAI's usual 10% of input, and the cache rule (automatic from 1,024 tokens in 128-token steps, about 5 minutes idle) is from OpenAI's prompt caching guide as last read, not re-checked. Check both by hand before publishing.

### Priced as otium-small (Otium)

What the run's tokens would cost at Otium's published prices for otium-small, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| graph-haiku | batch | 49% | 96% | $0.28 | $0.30 | $0.0008 | $2.84 ($2.67–$3.04) | $28.44 ($26.66–$30.37) | $284.41 ($266.62–$303.68) | $3,413 |
| graph-haiku-gated | batch | 33% | 96% | $0.16 | $0.17 | $0.0008 | $1.61 ($1.39–$1.84) | $16.05 ($13.86–$18.36) | $160.52 ($138.61–$183.64) | $1,926 |

Rates from https://getotium.ai/pricing, checked 2026-10-28. Cache replayed as Otium's: every prefix it sees, from 16 tokens, 5-minute lifetime.

### Graph against agent, item by item

Each graph arm next to the agent on the same model, so the two differ only in shape, compared on the items both ran. Columns: [reading a report](../../docs/reading-reports.md#graph-against-agent-item-by-item).

| Graph | Agent | Items | Only graph right | Only agent right | Success, graph − agent | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| graph-haiku | agent-haiku | 500 | 13 | 13 | +0.0 pts (-1.6 pts to +1.6 pts) | 1 |
| graph-haiku-gated | agent-haiku | 500 | 7 | 5 | +0.4 pts (-0.8 pts to +1.6 pts) | 0.77 |

p is McNemar's exact test on the items where the arms disagree: how likely a split this
uneven would be if neither arm were better.

| Graph | Agent | Priced as | Graph mode | Graph − agent, per 1,000 items | Relative |
| --- | --- | --- | --- | ---: | ---: |
| graph-haiku | agent-haiku | claude-haiku-5-5 | real-time | +$0.21 (+$0.17 to +$0.24) | +46% |
| graph-haiku | agent-haiku | claude-haiku-5-5 | batch | −$0.12 (−$0.16 to −$0.09) | -27% |
| graph-haiku | agent-haiku | gpt-6-luna | real-time | +$0.21 (+$0.17 to +$0.24) | +46% |
| graph-haiku | agent-haiku | gpt-6-luna | batch | −$0.12 (−$0.16 to −$0.09) | -27% |
| graph-haiku-gated | agent-haiku | claude-haiku-5-5 | real-time | −$0.08 (−$0.11 to −$0.06) | -18% |
| graph-haiku-gated | agent-haiku | claude-haiku-5-5 | batch | −$0.27 (−$0.29 to −$0.24) | -59% |
| graph-haiku-gated | agent-haiku | gpt-6-luna | real-time | −$0.08 (−$0.11 to −$0.06) | -18% |
| graph-haiku-gated | agent-haiku | gpt-6-luna | batch | −$0.27 (−$0.29 to −$0.24) | -59% |

The agent is priced real-time throughout; negative means the graph costs less.

### Cost by kind of item, priced as claude-haiku-5-5

What one item of each kind cost each arm, per 1,000 items: a reject stopped early costs little, a kept item pays for its content. Columns: [reading a report](../../docs/reading-reports.md#cost-by-kind-of-item).

| Arm | Mode | Kept | Rejected | New | Catalog duplicate | Feed duplicate | Excluded brand | Book |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | $1.22 | $0.31 | $1.22 | $0.27 | $0.87 | $0.12 | $0.12 |
| graph-haiku | real-time | $1.26 | $0.55 | $1.26 | $0.54 | $0.87 | $0.42 | $0.42 |
| graph-haiku | batch | $0.63 | $0.27 | $0.63 | $0.27 | $0.44 | $0.21 | $0.21 |
| graph-haiku-gated | real-time | $1.14 | $0.23 | $1.14 | $0.16 | $0.78 | $0.06 | $0.05 |
| graph-haiku-gated | batch | $0.57 | $0.12 | $0.57 | $0.08 | $0.39 | $0.03 | $0.03 |

Per 1,000 items, for a feed with this share of rejects (rejects in this run's mix of kinds):

| Arm | Mode | 0% | 20% | 50% | 85% | 90% |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | $1.22 | $1.04 | $0.76 | $0.45 | $0.40 |
| graph-haiku | real-time | $1.26 | $1.12 | $0.90 | $0.65 | $0.62 |
| graph-haiku | batch | $0.63 | $0.56 | $0.45 | $0.33 | $0.31 |
| graph-haiku-gated | real-time | $1.14 | $0.96 | $0.68 | $0.37 | $0.32 |
| graph-haiku-gated | batch | $0.57 | $0.48 | $0.34 | $0.18 | $0.16 |

Not split: claude-code-haiku, handed the whole feed at once, so no request belongs to one item.

A product listed several times in the feed is counted under each listing's own kind, whichever listing was catalogued.

Arms shown at real-time rates only, because their requests wait on each other: agent-haiku, claude-code-haiku.

Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of
the average, not how much a real month will vary.
