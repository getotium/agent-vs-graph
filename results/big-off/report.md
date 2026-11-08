# Run big-off

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
| code | 129d8922befc | the commit of this repo the run used |

On `code`: recorded at publication: the run started on a pre-release commit that was squashed into this one; the code that runs and scores the arms is identical.

## Scores

How often each arm's output was right, against the catalog's own fields. Columns: [reading a report](../../docs/reading-reports.md#scores).

| Arm | Items | Valid | Brand | Color | Success |
| --- | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 100% | 90% | 62% | 90% |
| agent-e4b | 500 | 97% | 75% | 56% | 75% |
| graph | 500 | 100% | 81% | 61% | 81% |
| graph-12b | 500 | 100% | 94% | 62% | 94% |

## Task: enrich

### Tokens per item

What each arm sent to the model and got back, per item, counted at the wire. Columns: [reading a report](../../docs/reading-reports.md#tokens-per-item).

| Arm | Items | Requests / item | Prompt | Output | Refused requests |
| --- | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 2.1 | 1,763 | 276 | 0 |
| agent-e4b | 500 | 2.3 | 1,976 | 265 | 5 |
| graph | 500 | 2.1 | 1,072 | 198 | 0 |
| graph-12b | 500 | 2.0 | 1,057 | 234 | 0 |

Prompt counts every input token. What a provider would have served from its cache is
replayed from the recorded prompts under each price's own cache rule, below. Refused
requests are not priced: the server reports no usage for them.

### Priced as claude-haiku-5-5 (Anthropic)

What the run's tokens would cost at Anthropic's published prices for claude-haiku-5-5, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 27% | 90% | $0.29 | $0.32 | $0.0004 | $2.92 ($2.86–$2.98) | $29.16 ($28.63–$29.75) | $291.64 ($286.31–$297.50) | $3,500 |
| agent-e4b | real-time | 34% | 75% | $0.29 | $0.39 | $0.0004 | $2.91 ($2.79–$3.04) | $29.05 ($27.88–$30.37) | $290.51 ($278.82–$303.73) | $3,486 |
| graph | real-time | 0% | 81% | $0.21 | $0.25 | $0.0003 | $2.06 ($2.01–$2.11) | $20.60 ($20.11–$21.08) | $205.96 ($201.14–$210.79) | $2,471 |
| graph | batch | 0% | 81% | $0.10 | $0.13 | $0.0002 | $1.03 ($1.01–$1.05) | $10.30 ($10.06–$10.54) | $102.98 ($100.57–$105.40) | $1,236 |
| graph-12b | real-time | 0% | 94% | $0.22 | $0.24 | $0.0003 | $2.23 ($2.19–$2.27) | $22.29 ($21.89–$22.70) | $222.92 ($218.95–$227.01) | $2,675 |
| graph-12b | batch | 0% | 94% | $0.11 | $0.12 | $0.0002 | $1.11 ($1.09–$1.14) | $11.15 ($10.95–$11.35) | $111.46 ($109.47–$113.50) | $1,338 |

Rates from https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-06. Cache replayed as Anthropic's: prefixes marked where a later request reuses them (the best case), from 512 tokens, 5-minute lifetime.

### Priced as gpt-6-luna (OpenAI)

What the run's tokens would cost at OpenAI's published prices for gpt-6-luna, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 7% | 90% | $0.30 | $0.34 | $0.0004 | $3.04 ($2.98–$3.09) | $30.35 ($29.82–$30.94) | $303.51 ($298.20–$309.40) | $3,642 |
| agent-e4b | real-time | 12% | 75% | $0.31 | $0.41 | $0.0004 | $3.09 ($2.96–$3.23) | $30.89 ($29.64–$32.29) | $308.91 ($296.43–$322.90) | $3,707 |
| graph | real-time | 0% | 81% | $0.21 | $0.25 | $0.0003 | $2.06 ($2.01–$2.11) | $20.60 ($20.11–$21.08) | $205.96 ($201.14–$210.79) | $2,471 |
| graph | batch | 0% | 81% | $0.10 | $0.13 | $0.0002 | $1.03 ($1.01–$1.05) | $10.30 ($10.06–$10.54) | $102.98 ($100.57–$105.40) | $1,236 |
| graph-12b | real-time | 0% | 94% | $0.22 | $0.24 | $0.0003 | $2.23 ($2.19–$2.27) | $22.29 ($21.89–$22.70) | $222.92 ($218.95–$227.01) | $2,675 |
| graph-12b | batch | 0% | 94% | $0.11 | $0.12 | $0.0002 | $1.11 ($1.09–$1.14) | $11.15 ($10.95–$11.35) | $111.46 ($109.47–$113.50) | $1,338 |

Rates from https://openai.com/api/pricing/, checked 2026-10-28. Cache replayed as OpenAI's: every prefix it sees, from 1,024 tokens, 5-minute lifetime. **Unverified:** OpenAI's pricing page refuses automated fetches. Input and output are as recorded on getotium.ai's rate card (2026-10-28); the cached rate assumes OpenAI's usual 10% of input, and the cache rule (automatic from 1,024 tokens in 128-token steps, about 5 minutes idle) is from OpenAI's prompt caching guide as last read, not re-checked. Check both by hand before publishing.

### Priced as otium-small (Otium)

What the run's tokens would cost at Otium's published prices for otium-small, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| graph | batch | 36% | 81% | $0.08 | $0.10 | $0.0001 | $0.80 ($0.78–$0.83) | $8.04 ($7.82–$8.27) | $80.41 ($78.19–$82.66) | $964.86 |
| graph-12b | batch | 35% | 94% | $0.09 | $0.09 | $0.0001 | $0.89 ($0.87–$0.91) | $8.91 ($8.72–$9.10) | $89.06 ($87.17–$91.02) | $1,069 |

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
| graph-12b | agent-12b | claude-haiku-5-5 | real-time | −$0.07 (−$0.07 to −$0.06) | -24% |
| graph-12b | agent-12b | claude-haiku-5-5 | batch | −$0.18 (−$0.18 to −$0.18) | -62% |
| graph-12b | agent-12b | gpt-6-luna | real-time | −$0.08 (−$0.09 to −$0.08) | -27% |
| graph-12b | agent-12b | gpt-6-luna | batch | −$0.19 (−$0.20 to −$0.19) | -63% |

The agent is priced real-time throughout; negative means the graph costs less.

Arms shown at real-time rates only, because their requests wait on each other: agent-12b, agent-e4b.

Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of
the average, not how much a real month will vary.
