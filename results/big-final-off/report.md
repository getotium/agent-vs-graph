# Run big-final-off

One run of [agent-vs-graph](../../README.md), which measures what the same job costs when a fixed workflow graph does it and when agent loops do. Task: `enrich`, product enrichment: each item is a product listing, to be turned into a validated catalog record. The first 500 items were given to every arm below. Every model request was metered; costs are those tokens priced afterwards at each vendor's published rates. This page is generated from the files beside it by `avg publish` and not edited by hand.

Read more: [how to read this report](../../docs/reading-reports.md) · [why it is measured this way](../../docs/design.md) · [all published runs](../README.md)

## In brief

- **Success** is a record that passes the shared validator and names the right brand.
- **Costs** are per item, as each vendor would bill the run's tokens. The run itself was local: token counts are the local model's, so they compare arms like for like rather than quote a hosted bill.
- **Batch** prices apply only to graph arms; an agent's requests wait on each other's answers.
- **Ranges** in brackets are 90% intervals on the average, from resampling the items.
- **Graph against agent** puts the same model in both shapes side by side, item by item.

## Arms

| Arm | Shape | Model |
| --- | --- | --- |
| agent-12b | One tool-calling agent per item | gemma-4-12b |
| agent-e4b | One tool-calling agent per item | gemma-4-e4b |
| graph | Workflow graph; easy steps on the small model, repairs on the large | gemma-4-12b, gemma-4-e4b |
| graph-12b | Workflow graph; every step on one model | gemma-4-12b |

## Conditions

| Setting | Value | Meaning |
| --- | --- | --- |
| limit | 500 | items in the run, the first N of the task's input file |
| slots | 4 | requests a per-item arm keeps in flight at once; changes speed, not tokens |
| thinking | 0 | 0: no thinking phase; N: up to N thinking tokens per reply |
| max_tokens | 4096 | the cap on one reply, thinking included |
| llama_server | llama-b12189 | the llama.cpp build that served the models |
| small | gemma-4-E4B_q4_0-it.gguf | the small model |
| large | gemma-4-12b-it-qat-q4_0.gguf | the large model |
| harness_ctx | 65536 | context window for the whole-file harnesses |
| code | 10603c4a4025 | the commit of this repo the run used |

## Scores

How often each arm's output was right, against the catalog's own fields. Columns: [reading a report](../../docs/reading-reports.md#scores).

| Arm | Items | Valid | Brand | Color | Success |
| --- | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 100% | 90% | 62% | 90% |
| agent-e4b | 500 | 98% | 76% | 57% | 76% |
| graph | 500 | 100% | 81% | 61% | 81% |
| graph-12b | 500 | 100% | 94% | 62% | 94% |

## Task: enrich

### Tokens per item

What each arm sent to the model and got back, per item, counted at the wire. Columns: [reading a report](../../docs/reading-reports.md#tokens-per-item).

| Arm | Items | Requests / item | Prompt | Output | Of which thinking | Refused requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 2.1 | 1,763 | 276 | – | 0 |
| agent-e4b | 500 | 2.2 | 1,931 | 262 | – | 5 |
| graph | 500 | 2.1 | 1,074 | 198 | – | 0 |
| graph-12b | 500 | 2.0 | 1,060 | 235 | – | 0 |

Prompt counts every input token. What a provider would have served from its cache is
replayed from the recorded prompts under each price's own cache rule, below. Refused
requests are not priced: the server reports no usage for them.

### Priced as claude-haiku-5-5 (Anthropic)

What the run's tokens would cost at Anthropic's published prices for claude-haiku-5-5, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 28% | 90% | $0.29 | $0.32 | $0.0004 | $2.89 ($2.84–$2.95) | $28.89 ($28.35–$29.45) | $288.87 ($283.52–$294.53) | $3,466 |
| agent-e4b | real-time | 33% | 76% | $0.29 | $0.38 | $0.0004 | $2.88 ($2.76–$3.00) | $28.76 ($27.60–$30.03) | $287.56 ($275.99–$300.26) | $3,451 |
| graph | real-time | 0% | 81% | $0.21 | $0.25 | $0.0003 | $2.06 ($2.02–$2.12) | $20.65 ($20.16–$21.16) | $206.49 ($201.56–$211.57) | $2,478 |
| graph | batch | 0% | 81% | $0.10 | $0.13 | $0.0002 | $1.03 ($1.01–$1.06) | $10.32 ($10.08–$10.58) | $103.25 ($100.78–$105.78) | $1,239 |
| graph-12b | real-time | 0% | 94% | $0.22 | $0.24 | $0.0003 | $2.23 ($2.19–$2.27) | $22.33 ($21.93–$22.75) | $223.34 ($219.33–$227.50) | $2,680 |
| graph-12b | batch | 0% | 94% | $0.11 | $0.12 | $0.0002 | $1.12 ($1.10–$1.14) | $11.17 ($10.97–$11.37) | $111.67 ($109.66–$113.75) | $1,340 |

Rates from https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-06. Cache replayed as Anthropic's: prefixes marked where a later request reuses them (the best case), from 512 tokens, 5-minute lifetime.

### Priced as gpt-6-luna (OpenAI)

What the run's tokens would cost at OpenAI's published prices for gpt-6-luna, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 7% | 90% | $0.30 | $0.34 | $0.0004 | $3.03 ($2.98–$3.09) | $30.30 ($29.78–$30.88) | $303.03 ($297.75–$308.79) | $3,636 |
| agent-e4b | real-time | 11% | 76% | $0.30 | $0.40 | $0.0004 | $3.04 ($2.92–$3.18) | $30.45 ($29.21–$31.79) | $304.47 ($292.09–$317.89) | $3,654 |
| graph | real-time | 0% | 81% | $0.21 | $0.26 | $0.0003 | $2.07 ($2.02–$2.12) | $20.66 ($20.16–$21.17) | $206.58 ($201.63–$211.70) | $2,479 |
| graph | batch | 0% | 81% | $0.10 | $0.13 | $0.0002 | $1.03 ($1.01–$1.06) | $10.33 ($10.08–$10.58) | $103.29 ($100.81–$105.85) | $1,239 |
| graph-12b | real-time | 0% | 94% | $0.22 | $0.24 | $0.0003 | $2.24 ($2.19–$2.28) | $22.35 ($21.94–$22.77) | $223.54 ($219.45–$227.74) | $2,682 |
| graph-12b | batch | 0% | 94% | $0.11 | $0.12 | $0.0002 | $1.12 ($1.10–$1.14) | $11.18 ($10.97–$11.39) | $111.77 ($109.72–$113.87) | $1,341 |

Rates from https://openai.com/api/pricing/, checked 2026-10-28. Cache replayed as OpenAI's: every prefix it sees, from 1,024 tokens, 5-minute lifetime. **Unverified:** OpenAI's pricing page refuses automated fetches. Input and output are as recorded on getotium.ai's rate card (2026-10-28); the cached rate assumes OpenAI's usual 10% of input, and the cache rule (automatic from 1,024 tokens in 128-token steps, about 5 minutes idle) is from OpenAI's prompt caching guide as last read, not re-checked. Check both by hand before publishing.

### Priced as otium-small (Otium)

What the run's tokens would cost at Otium's published prices for otium-small, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| graph | batch | 36% | 81% | $0.08 | $0.10 | $0.0001 | $0.81 ($0.78–$0.83) | $8.06 ($7.83–$8.29) | $80.61 ($78.31–$82.92) | $967.33 |
| graph-12b | batch | 36% | 94% | $0.09 | $0.09 | $0.0001 | $0.89 ($0.87–$0.91) | $8.92 ($8.73–$9.12) | $89.19 ($87.27–$91.15) | $1,070 |

Rates from https://getotium.ai/pricing, checked 2026-10-28. Cache replayed as Otium's: every prefix it sees, from 16 tokens, 5-minute lifetime.

### Graph against agent, item by item

Each graph arm next to the agent on the same model, so the two differ only in shape, compared on the items both ran. Columns: [reading a report](../../docs/reading-reports.md#graph-against-agent-item-by-item).

| Graph | Agent | Items | Only graph right | Only agent right | Success, graph − agent | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| graph-12b | agent-12b | 500 | 23 | 3 | +4.0 pts (+2.4 pts to +5.6 pts) | 8.8e-05 |

p is McNemar's exact test on the items where the arms disagree: how likely a split this
uneven would be if neither arm were better.

| Graph | Agent | Priced as | Graph mode | Graph − agent, per 1,000 items | Relative |
| --- | --- | --- | --- | ---: | ---: |
| graph-12b | agent-12b | claude-haiku-5-5 | real-time | −$0.07 (−$0.07 to −$0.06) | -23% |
| graph-12b | agent-12b | claude-haiku-5-5 | batch | −$0.18 (−$0.18 to −$0.17) | -61% |
| graph-12b | agent-12b | gpt-6-luna | real-time | −$0.08 (−$0.08 to −$0.07) | -26% |
| graph-12b | agent-12b | gpt-6-luna | batch | −$0.19 (−$0.20 to −$0.19) | -63% |

The agent is priced real-time throughout; negative means the graph costs less.

Arms shown at real-time rates only, because their requests wait on each other: agent-12b, agent-e4b.

Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of
the average, not how much a real month will vary.
