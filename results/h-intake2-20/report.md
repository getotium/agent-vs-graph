# Run h-intake2-20

One run of [agent-vs-graph](../../README.md), which measures what the same job costs when a fixed workflow graph does it and when agent loops do. Task: `intake`, catalog intake: each item is a listing from a supplier's feed, to be catalogued with page content or skipped as a duplicate or excluded product. The first 500 items were given to every arm below. Every model request was metered; costs are those tokens priced afterwards at each vendor's published rates. This page is generated from the files beside it by `avg publish` and not edited by hand.

Read more: [how to read this report](../../docs/reading-reports.md) · [why it is measured this way](../../docs/design.md) · [all published runs](../README.md)

## In brief

- **Success** is a skip for an item the store should not take (a duplicate, an excluded brand, a book), and for a new product a record with its page content that passes the shared validator and names the right brand. A product listed several times in the feed succeeds when exactly one listing is catalogued.
- **Costs** are per item, as each vendor would bill the run's tokens. The run itself was local: token counts are the local model's, so they compare arms like for like rather than quote a hosted bill.
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
| items | data/intake/items-20.jsonl | the input file: for catalog intake, the mix (items-20: 20% of the feed should be rejected) |

## Scores

How often each arm's output was right, against the catalog's own fields. Columns: [reading a report](../../docs/reading-reports.md#scores).

| Arm | Items | New catalogued | Duplicates skipped | Exclusions skipped | Records for rejects | Success |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | 500 | 97% | 96% | 100% | 2 | 97% |
| claude-code-haiku | 500 | 97% | 100% | 100% | 0 | 97% |
| graph-haiku | 500 | 96% | 94% | 100% | 3 | 96% |
| graph-haiku-gated | 500 | 96% | 96% | 100% | 2 | 97% |

## Task: intake

### Tokens per item

What each arm sent to the model and got back, per item, counted at the wire. Columns: [reading a report](../../docs/reading-reports.md#tokens-per-item).

| Arm | Items | Requests / item | Prompt | Output | Of which thinking | Refused requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | 500 | 3.0 | 7,183 | 2,546 | 1,265 | 0 |
| claude-code-haiku | 500 | 0.2 | 13,770 | 1,516 | 925 | 0 |
| graph-haiku | 500 | 2.2 | 1,926 | 2,452 | 1,707 | 0 |
| graph-haiku-gated | 500 | 3.1 | 2,340 | 2,400 | 1,669 | 0 |

Prompt counts every input token. What a provider would have served from its cache is
replayed from the recorded prompts under each price's own cache rule, below. Refused
requests are not priced: the server reports no usage for them.

### Priced as claude-haiku-5-5 (Anthropic)

What the run's tokens would cost at Anthropic's published prices for claude-haiku-5-5, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | 81% | 97% | $1.50 | $1.54 | $0.0025 | $15.00 ($14.46–$15.59) | $149.97 ($144.55–$155.87) | $1,500 ($1,446–$1,559) | $17,996 |
| claude-code-haiku | real-time | 82% | 97% | $2.19 | $2.24 | $0.0022 | $21.86 | $218.63 | $2,186 | $26,235 |
| graph-haiku | real-time | 2% | 96% | $1.42 | $1.47 | $0.0029 | $14.16 ($13.64–$14.71) | $141.60 ($136.38–$147.08) | $1,416 ($1,364–$1,471) | $16,992 |
| graph-haiku | batch | 2% | 96% | $0.71 | $0.73 | $0.0015 | $7.08 ($6.82–$7.35) | $70.80 ($68.19–$73.54) | $707.98 ($681.89–$735.39) | $8,496 |
| graph-haiku-gated | real-time | 1% | 97% | $1.43 | $1.48 | $0.0030 | $14.32 ($13.68–$15.01) | $143.23 ($136.78–$150.14) | $1,432 ($1,368–$1,501) | $17,187 |
| graph-haiku-gated | batch | 1% | 97% | $0.72 | $0.74 | $0.0015 | $7.16 ($6.84–$7.51) | $71.61 ($68.39–$75.07) | $716.14 ($683.90–$750.71) | $8,594 |

Rates from https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-06. Cache replayed as Anthropic's: prefixes marked where a later request reuses them (the best case), from 512 tokens, 5-minute lifetime. 4,222 requests were answered by claude-haiku-5-5 itself and are priced as Anthropic counted them, cache included, not replayed.

### Priced as gpt-6-luna (OpenAI)

What the run's tokens would cost at OpenAI's published prices for gpt-6-luna, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | 75% | 97% | $1.51 | $1.55 | $0.0025 | $15.09 ($14.55–$15.69) | $150.93 ($145.48–$156.87) | $1,509 ($1,455–$1,569) | $18,111 |
| claude-code-haiku | real-time | 80% | 97% | $1.15 | $1.18 | $0.0011 | $11.48 | $114.84 | $1,148 | $13,781 |
| graph-haiku | real-time | 0% | 96% | $1.42 | $1.47 | $0.0029 | $14.18 ($13.66–$14.73) | $141.85 ($136.65–$147.33) | $1,418 ($1,366–$1,473) | $17,022 |
| graph-haiku | batch | 0% | 96% | $0.71 | $0.74 | $0.0015 | $7.09 ($6.83–$7.37) | $70.92 ($68.32–$73.67) | $709.23 ($683.23–$736.65) | $8,511 |
| graph-haiku-gated | real-time | 0% | 97% | $1.43 | $1.48 | $0.0030 | $14.34 ($13.69–$15.03) | $143.40 ($136.94–$150.31) | $1,434 ($1,369–$1,503) | $17,208 |
| graph-haiku-gated | batch | 0% | 97% | $0.72 | $0.74 | $0.0015 | $7.17 ($6.85–$7.52) | $71.70 ($68.47–$75.16) | $716.99 ($684.69–$751.55) | $8,604 |

Rates from https://openai.com/api/pricing/, checked 2026-10-28. Cache replayed as OpenAI's: every prefix it sees, from 1,024 tokens, 5-minute lifetime. **Unverified:** OpenAI's pricing page refuses automated fetches. Input and output are as recorded on getotium.ai's rate card (2026-10-28); the cached rate assumes OpenAI's usual 10% of input, and the cache rule (automatic from 1,024 tokens in 128-token steps, about 5 minutes idle) is from OpenAI's prompt caching guide as last read, not re-checked. Check both by hand before publishing.

### Priced as otium-small (Otium)

What the run's tokens would cost at Otium's published prices for otium-small, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| graph-haiku | batch | 42% | 96% | $0.64 | $0.67 | $0.0014 | $6.42 ($6.17–$6.67) | $64.16 ($61.72–$66.74) | $641.64 ($617.16–$667.39) | $7,700 |
| graph-haiku-gated | batch | 37% | 97% | $0.65 | $0.67 | $0.0014 | $6.47 ($6.17–$6.79) | $64.68 ($61.67–$67.88) | $646.83 ($616.73–$678.81) | $7,762 |

Rates from https://getotium.ai/pricing, checked 2026-10-28. Cache replayed as Otium's: every prefix it sees, from 16 tokens, 5-minute lifetime.

### Graph against agent, item by item

Each graph arm next to the agent on the same model, so the two differ only in shape, compared on the items both ran. Columns: [reading a report](../../docs/reading-reports.md#graph-against-agent-item-by-item).

| Graph | Agent | Items | Only graph right | Only agent right | Success, graph − agent | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| graph-haiku | agent-haiku | 500 | 2 | 7 | -1.0 pts (-2.0 pts to +0.0 pts) | 0.18 |
| graph-haiku-gated | agent-haiku | 500 | 4 | 8 | -0.8 pts (-2.0 pts to +0.2 pts) | 0.39 |

p is McNemar's exact test on the items where the arms disagree: how likely a split this
uneven would be if neither arm were better.

| Graph | Agent | Priced as | Graph mode | Graph − agent, per 1,000 items | Relative |
| --- | --- | --- | --- | ---: | ---: |
| graph-haiku | agent-haiku | claude-haiku-5-5 | real-time | −$0.08 (−$0.13 to −$0.04) | -6% |
| graph-haiku | agent-haiku | claude-haiku-5-5 | batch | −$0.79 (−$0.84 to −$0.75) | -53% |
| graph-haiku | agent-haiku | gpt-6-luna | real-time | −$0.09 (−$0.14 to −$0.04) | -6% |
| graph-haiku | agent-haiku | gpt-6-luna | batch | −$0.80 (−$0.85 to −$0.76) | -53% |
| graph-haiku-gated | agent-haiku | claude-haiku-5-5 | real-time | −$0.07 (−$0.11 to −$0.02) | -4% |
| graph-haiku-gated | agent-haiku | claude-haiku-5-5 | batch | −$0.78 (−$0.82 to −$0.74) | -52% |
| graph-haiku-gated | agent-haiku | gpt-6-luna | real-time | −$0.08 (−$0.12 to −$0.02) | -5% |
| graph-haiku-gated | agent-haiku | gpt-6-luna | batch | −$0.79 (−$0.83 to −$0.75) | -52% |

The agent is priced real-time throughout; negative means the graph costs less.

### Cost by kind of item, priced as claude-haiku-5-5

What one item of each kind cost each arm, per 1,000 items: a reject stopped early costs little, a kept item pays for its content. Columns: [reading a report](../../docs/reading-reports.md#cost-by-kind-of-item).

| Arm | Mode | Kept | Rejected | New | Catalog duplicate | Feed duplicate | Excluded brand | Book |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | $1.79 | $0.32 | $1.79 | $0.29 | $0.91 | $0.11 | $0.09 |
| graph-haiku | real-time | $1.63 | $0.55 | $1.63 | $0.56 | $0.95 | $0.39 | $0.38 |
| graph-haiku | batch | $0.82 | $0.28 | $0.82 | $0.28 | $0.47 | $0.19 | $0.19 |
| graph-haiku-gated | real-time | $1.73 | $0.26 | $1.73 | $0.16 | $0.93 | $0.06 | $0.03 |
| graph-haiku-gated | batch | $0.86 | $0.13 | $0.86 | $0.08 | $0.47 | $0.03 | $0.02 |

Per 1,000 items, for a feed with this share of rejects (rejects in this run's mix of kinds):

| Arm | Mode | 0% | 20% | 50% | 85% | 90% |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | $1.79 | $1.50 | $1.06 | $0.54 | $0.47 |
| graph-haiku | real-time | $1.63 | $1.42 | $1.09 | $0.71 | $0.66 |
| graph-haiku | batch | $0.82 | $0.71 | $0.55 | $0.36 | $0.33 |
| graph-haiku-gated | real-time | $1.73 | $1.43 | $0.99 | $0.48 | $0.41 |
| graph-haiku-gated | batch | $0.86 | $0.72 | $0.50 | $0.24 | $0.20 |

Not split: claude-code-haiku, handed the whole feed at once, so no request belongs to one item.

A product listed several times in the feed is counted under each listing's own kind, whichever listing was catalogued.

Arms shown at real-time rates only, because their requests wait on each other: agent-haiku, claude-code-haiku.

Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of
the average, not how much a real month will vary.
