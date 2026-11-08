# Run big-think

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
| thinking | 3072 | 0: no thinking phase; N: up to N thinking tokens per reply |
| max_tokens | 4096 | the cap on one reply, thinking included |
| llama_server | llama-b12189 | the llama.cpp build that served the models |
| small | gemma-4-E4B_q4_0-it.gguf | the small model |
| large | gemma-4-12b-it-qat-q4_0.gguf | the large model |
| harness_ctx | 65536 | context window for the whole-file harnesses |
| code | 129d8922befc | the commit of this repo the run used |

On `code`: recorded at publication, from the commit the run was started at.

## Scores

How often each arm's output was right, against the catalog's own fields. Columns: [reading a report](../../docs/reading-reports.md#scores).

| Arm | Items | Valid | Brand | Color | Success |
| --- | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 100% | 96% | 62% | 96% |
| agent-e4b | 500 | 100% | 93% | 60% | 93% |
| graph | 500 | 100% | 94% | 61% | 94% |
| graph-12b | 500 | 100% | 96% | 61% | 96% |

## Task: enrich

### Tokens per item

What each arm sent to the model and got back, per item, counted at the wire. Columns: [reading a report](../../docs/reading-reports.md#tokens-per-item).

| Arm | Items | Requests / item | Prompt | Output | Of which thinking | Refused requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 2.0 | 1,709 | 1,483 | – | 0 |
| agent-e4b | 500 | 2.0 | 1,690 | 1,182 | – | 6 |
| graph | 500 | 2.0 | 1,044 | 1,275 | – | 0 |
| graph-12b | 500 | 2.0 | 1,042 | 2,273 | – | 0 |

Prompt counts every input token. What a provider would have served from its cache is
replayed from the recorded prompts under each price's own cache rule, below. Refused
requests are not priced: the server reports no usage for them.

### Priced as claude-haiku-5-5 (Anthropic)

What the run's tokens would cost at Anthropic's published prices for claude-haiku-5-5, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 29% | 96% | $0.89 | $0.92 | $0.0019 | $8.87 ($8.54–$9.19) | $88.68 ($85.38–$91.92) | $886.78 ($853.78–$919.23) | $10,641 |
| agent-e4b | real-time | 26% | 93% | $0.74 | $0.79 | $0.0009 | $7.39 ($7.28–$7.51) | $73.94 ($72.80–$75.06) | $739.36 ($728.03–$750.60) | $8,872 |
| graph | real-time | 0% | 94% | $0.74 | $0.79 | $0.0009 | $7.42 ($7.33–$7.52) | $74.20 ($73.28–$75.24) | $742.04 ($732.79–$752.43) | $8,904 |
| graph | batch | 0% | 94% | $0.37 | $0.40 | $0.0004 | $3.71 ($3.66–$3.76) | $37.10 ($36.64–$37.62) | $371.02 ($366.40–$376.22) | $4,452 |
| graph-12b | real-time | 0% | 96% | $1.24 | $1.29 | $0.0021 | $12.41 ($12.07–$12.76) | $124.07 ($120.71–$127.58) | $1,241 ($1,207–$1,276) | $14,888 |
| graph-12b | batch | 0% | 96% | $0.62 | $0.64 | $0.0011 | $6.20 ($6.04–$6.38) | $62.03 ($60.35–$63.79) | $620.35 ($603.54–$637.91) | $7,444 |

Rates from https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-06. Cache replayed as Anthropic's: prefixes marked where a later request reuses them (the best case), from 512 tokens, 5-minute lifetime.

### Priced as gpt-6-luna (OpenAI)

What the run's tokens would cost at OpenAI's published prices for gpt-6-luna, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 6% | 96% | $0.90 | $0.94 | $0.0019 | $9.04 ($8.71–$9.36) | $90.37 ($87.10–$93.62) | $903.66 ($871.04–$936.23) | $10,844 |
| agent-e4b | real-time | 5% | 93% | $0.75 | $0.81 | $0.0009 | $7.52 ($7.41–$7.63) | $75.19 ($74.12–$76.31) | $751.94 ($741.19–$763.10) | $9,023 |
| graph | real-time | 0% | 94% | $0.74 | $0.79 | $0.0009 | $7.42 ($7.33–$7.52) | $74.20 ($73.28–$75.24) | $742.04 ($732.79–$752.43) | $8,904 |
| graph | batch | 0% | 94% | $0.37 | $0.40 | $0.0004 | $3.71 ($3.66–$3.76) | $37.10 ($36.64–$37.62) | $371.02 ($366.40–$376.22) | $4,452 |
| graph-12b | real-time | 0% | 96% | $1.24 | $1.29 | $0.0021 | $12.41 ($12.07–$12.76) | $124.07 ($120.71–$127.58) | $1,241 ($1,207–$1,276) | $14,888 |
| graph-12b | batch | 0% | 96% | $0.62 | $0.64 | $0.0011 | $6.20 ($6.04–$6.38) | $62.03 ($60.35–$63.79) | $620.35 ($603.54–$637.91) | $7,444 |

Rates from https://openai.com/api/pricing/, checked 2026-10-28. Cache replayed as OpenAI's: every prefix it sees, from 1,024 tokens, 5-minute lifetime. **Unverified:** OpenAI's pricing page refuses automated fetches. Input and output are as recorded on getotium.ai's rate card (2026-10-28); the cached rate assumes OpenAI's usual 10% of input, and the cache rule (automatic from 1,024 tokens in 128-token steps, about 5 minutes idle) is from OpenAI's prompt caching guide as last read, not re-checked. Check both by hand before publishing.

### Priced as otium-small (Otium)

What the run's tokens would cost at Otium's published prices for otium-small, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| graph | batch | 36% | 94% | $0.34 | $0.36 | $0.0004 | $3.38 ($3.34–$3.43) | $33.84 ($33.39–$34.34) | $338.38 ($333.89–$343.44) | $4,061 |
| graph-12b | batch | 36% | 96% | $0.58 | $0.60 | $0.0010 | $5.78 ($5.62–$5.95) | $57.77 ($56.15–$59.46) | $577.71 ($561.52–$594.56) | $6,933 |

Rates from https://getotium.ai/pricing, checked 2026-10-28. Cache replayed as Otium's: every prefix it sees, from 16 tokens, 5-minute lifetime.

### Graph against agent, item by item

Each graph arm next to the agent on the same model, so the two differ only in shape, compared on the items both ran. Columns: [reading a report](../../docs/reading-reports.md#graph-against-agent-item-by-item).

| Graph | Agent | Items | Only graph right | Only agent right | Success, graph − agent | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| graph-12b | agent-12b | 500 | 4 | 2 | +0.4 pts (-0.4 pts to +1.2 pts) | 0.69 |

p is McNemar's exact test on the items where the arms disagree: how likely a split this
uneven would be if neither arm were better.

| Graph | Agent | Priced as | Graph mode | Graph − agent, per 1,000 items | Relative |
| --- | --- | --- | --- | ---: | ---: |
| graph-12b | agent-12b | claude-haiku-5-5 | real-time | +$0.35 (+$0.32 to +$0.40) | +40% |
| graph-12b | agent-12b | claude-haiku-5-5 | batch | −$0.27 (−$0.30 to −$0.23) | -30% |
| graph-12b | agent-12b | gpt-6-luna | real-time | +$0.34 (+$0.30 to +$0.38) | +37% |
| graph-12b | agent-12b | gpt-6-luna | batch | −$0.28 (−$0.31 to −$0.25) | -31% |

The agent is priced real-time throughout; negative means the graph costs less.

Arms shown at real-time rates only, because their requests wait on each other: agent-12b, agent-e4b.

Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of
the average, not how much a real month will vary.
