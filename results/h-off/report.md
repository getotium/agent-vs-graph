# Run h-off

One run of [agent-vs-graph](../../README.md), which measures what the same job costs when a fixed workflow graph does it and when agent loops do. Task: `enrich`, product enrichment: each item is a product listing, to be turned into a validated catalog record. The first 500 items were given to every arm below. Every model request was metered; costs are those tokens priced afterwards at each vendor's published rates. This page is generated from the files beside it by `avg publish` and not edited by hand.

Read more: [how to read this report](../../docs/reading-reports.md) · [why it is measured this way](../../docs/design.md) · [all published runs](../README.md)

## In brief

- **Success** is a record that passes the shared validator and names the right brand.
- **Costs** are per item, as each vendor would bill the run's tokens. The run used claude-haiku-5-5 through its vendor's API: priced as that model, the figures are what the run cost. Priced as another model, they use this model's token counts, so they compare arms like for like rather than quote a bill.
- **Batch** prices apply only to graph arms; an agent's requests wait on each other's answers.
- **Ranges** in brackets are 90% intervals on the average, from resampling the items.
- **Graph against agent** puts the same model in both shapes side by side, item by item.

## Arms

| Arm | Shape | Model |
| --- | --- | --- |
| agent-haiku | One tool-calling agent per item | claude-haiku-5-5 |
| graph-haiku | Workflow graph; every step on one model | claude-haiku-5-5 |

## Conditions

| Setting | Value | Meaning |
| --- | --- | --- |
| limit | 500 | items in the run, the first N of the task's input file |
| slots | 4 | requests a per-item arm keeps in flight at once; changes speed, not tokens |
| thinking | 0 | 0: no thinking phase; N: up to N thinking tokens per reply |
| max_tokens | 4096 | the cap on one reply, thinking included |
| provider | anthropic | the hosted API the run used; its own counts are the bill when priced as its model |
| model | claude-haiku-5-5 | the hosted model every arm used |
| anthropic_version | 2023-06-01 | the Messages API version the requests named |
| code | dc71ae39c340 | the commit of this repo the run used |

## Scores

How often each arm's output was right, against the catalog's own fields. Columns: [reading a report](../../docs/reading-reports.md#scores).

| Arm | Items | Valid | Brand | Color | Success |
| --- | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | 500 | 100% | 96% | 62% | 96% |
| graph-haiku | 500 | 97% | 94% | 58% | 94% |

## Task: enrich

### Tokens per item

What each arm sent to the model and got back, per item, counted at the wire. Columns: [reading a report](../../docs/reading-reports.md#tokens-per-item).

| Arm | Items | Requests / item | Prompt | Output | Of which thinking | Refused requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | 500 | 2.0 | 3,259 | 581 | 0 | 0 |
| graph-haiku | 500 | 2.3 | 2,025 | 454 | 0 | 0 |

Prompt counts every input token. What a provider would have served from its cache is
replayed from the recorded prompts under each price's own cache rule, below. Refused
requests are not priced: the server reports no usage for them.

### Priced as claude-haiku-5-5 (Anthropic)

What the run's tokens would cost at Anthropic's published prices for claude-haiku-5-5, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | 73% | 96% | $0.43 | $0.44 | $0.0006 | $4.25 ($4.18–$4.32) | $42.51 ($41.84–$43.15) | $425.14 ($418.43–$431.51) | $5,102 |
| graph-haiku | real-time | 0% | 94% | $0.43 | $0.46 | $0.0008 | $4.29 ($4.15–$4.45) | $42.93 ($41.47–$44.48) | $429.35 ($414.65–$444.78) | $5,152 |
| graph-haiku | batch | 0% | 94% | $0.21 | $0.23 | $0.0004 | $2.15 ($2.07–$2.22) | $21.47 ($20.73–$22.24) | $214.67 ($207.33–$222.39) | $2,576 |

Rates from https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-06. Cache replayed as Anthropic's: prefixes marked where a later request reuses them (the best case), from 512 tokens, 5-minute lifetime. 2,160 requests were answered by claude-haiku-5-5 itself and are priced as Anthropic counted them, cache included, not replayed.

### Priced as gpt-6-luna (OpenAI)

What the run's tokens would cost at OpenAI's published prices for gpt-6-luna, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | 21% | 96% | $0.55 | $0.57 | $0.0008 | $5.54 ($5.46–$5.62) | $55.37 ($54.58–$56.18) | $553.69 ($545.77–$561.80) | $6,644 |
| graph-haiku | real-time | 0% | 94% | $0.43 | $0.46 | $0.0008 | $4.29 ($4.15–$4.45) | $42.93 ($41.47–$44.48) | $429.35 ($414.65–$444.78) | $5,152 |
| graph-haiku | batch | 0% | 94% | $0.21 | $0.23 | $0.0004 | $2.15 ($2.07–$2.22) | $21.47 ($20.73–$22.24) | $214.67 ($207.33–$222.39) | $2,576 |

Rates from https://openai.com/api/pricing/, checked 2026-10-28. Cache replayed as OpenAI's: every prefix it sees, from 1,024 tokens, 5-minute lifetime. **Unverified:** OpenAI's pricing page refuses automated fetches. Input and output are as recorded on getotium.ai's rate card (2026-10-28); the cached rate assumes OpenAI's usual 10% of input, and the cache rule (automatic from 1,024 tokens in 128-token steps, about 5 minutes idle) is from OpenAI's prompt caching guide as last read, not re-checked. Check both by hand before publishing.

### Priced as otium-small (Otium)

What the run's tokens would cost at Otium's published prices for otium-small, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| graph-haiku | batch | 35% | 94% | $0.17 | $0.18 | $0.0004 | $1.72 ($1.66–$1.79) | $17.21 ($16.58–$17.86) | $172.13 ($165.76–$178.62) | $2,066 |

Rates from https://getotium.ai/pricing, checked 2026-10-28. Cache replayed as Otium's: every prefix it sees, from 16 tokens, 5-minute lifetime.

### Graph against agent, item by item

Each graph arm next to the agent on the same model, so the two differ only in shape, compared on the items both ran. Columns: [reading a report](../../docs/reading-reports.md#graph-against-agent-item-by-item).

| Graph | Agent | Items | Only graph right | Only agent right | Success, graph − agent | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| graph-haiku | agent-haiku | 500 | 2 | 15 | -2.6 pts (-4.0 pts to -1.2 pts) | 0.0023 |

p is McNemar's exact test on the items where the arms disagree: how likely a split this
uneven would be if neither arm were better.

| Graph | Agent | Priced as | Graph mode | Graph − agent, per 1,000 items | Relative |
| --- | --- | --- | --- | ---: | ---: |
| graph-haiku | agent-haiku | claude-haiku-5-5 | real-time | +$0.0042 (−$0.0076 to +$0.02) | +1% |
| graph-haiku | agent-haiku | claude-haiku-5-5 | batch | −$0.21 (−$0.22 to −$0.20) | -50% |
| graph-haiku | agent-haiku | gpt-6-luna | real-time | −$0.12 (−$0.14 to −$0.11) | -22% |
| graph-haiku | agent-haiku | gpt-6-luna | batch | −$0.34 (−$0.35 to −$0.33) | -61% |

The agent is priced real-time throughout; negative means the graph costs less.

Arms shown at real-time rates only, because their requests wait on each other: agent-haiku.

Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of
the average, not how much a real month will vary.
