# Run big-lean

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
| graph-12b | Workflow graph; every step on one model | gemma-4-12b |
| graph-12b-lean | Workflow graph; every step on one model, the description written without thinking | gemma-4-12b |

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
| code | 4b26f5e44514 | the commit of this repo the run used |

## Scores

How often each arm's output was right, against the catalog's own fields. Columns: [reading a report](../../docs/reading-reports.md#scores).

| Arm | Items | Valid | Brand | Color | Success |
| --- | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 100% | 96% | 61% | 96% |
| graph-12b | 500 | 100% | 96% | 62% | 96% |
| graph-12b-lean | 500 | 100% | 97% | 62% | 97% |

## Task: enrich

### Tokens per item

What each arm sent to the model and got back, per item, counted at the wire. Columns: [reading a report](../../docs/reading-reports.md#tokens-per-item).

| Arm | Items | Requests / item | Prompt | Output | Of which thinking | Refused requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 2.0 | 1,710 | 1,514 | – | 0 |
| graph-12b | 500 | 2.0 | 1,043 | 2,278 | – | 0 |
| graph-12b-lean | 500 | 2.0 | 1,043 | 1,449 | – | 0 |

Prompt counts every input token. What a provider would have served from its cache is
replayed from the recorded prompts under each price's own cache rule, below. Refused
requests are not priced: the server reports no usage for them.

### Priced as claude-haiku-5-5 (Anthropic)

What the run's tokens would cost at Anthropic's published prices for claude-haiku-5-5, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 27% | 96% | $0.91 | $0.95 | $0.0019 | $9.05 ($8.71–$9.39) | $90.55 ($87.14–$93.90) | $905.48 ($871.43–$939.05) | $10,866 |
| graph-12b | real-time | 0% | 96% | $1.24 | $1.29 | $0.0022 | $12.43 ($12.10–$12.78) | $124.32 ($120.99–$127.82) | $1,243 ($1,210–$1,278) | $14,918 |
| graph-12b | batch | 0% | 96% | $0.62 | $0.64 | $0.0011 | $6.22 ($6.05–$6.39) | $62.16 ($60.49–$63.91) | $621.58 ($604.94–$639.10) | $7,459 |
| graph-12b-lean | real-time | 0% | 97% | $0.83 | $0.86 | $0.0016 | $8.29 ($8.05–$8.52) | $82.87 ($80.46–$85.25) | $828.70 ($804.56–$852.49) | $9,944 |
| graph-12b-lean | batch | 0% | 97% | $0.41 | $0.43 | $0.0008 | $4.14 ($4.02–$4.26) | $41.44 ($40.23–$42.62) | $414.35 ($402.28–$426.25) | $4,972 |

Rates from https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-06. Cache replayed as Anthropic's: prefixes marked where a later request reuses them (the best case), from 512 tokens, 5-minute lifetime.

### Priced as gpt-6-luna (OpenAI)

What the run's tokens would cost at OpenAI's published prices for gpt-6-luna, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 6% | 96% | $0.92 | $0.96 | $0.0019 | $9.18 ($8.84–$9.52) | $91.81 ($88.41–$95.16) | $918.14 ($884.13–$951.63) | $11,018 |
| graph-12b | real-time | 0% | 96% | $1.24 | $1.29 | $0.0022 | $12.43 ($12.10–$12.78) | $124.32 ($120.99–$127.82) | $1,243 ($1,210–$1,278) | $14,918 |
| graph-12b | batch | 0% | 96% | $0.62 | $0.64 | $0.0011 | $6.22 ($6.05–$6.39) | $62.16 ($60.49–$63.91) | $621.58 ($604.94–$639.10) | $7,459 |
| graph-12b-lean | real-time | 0% | 97% | $0.83 | $0.86 | $0.0016 | $8.29 ($8.05–$8.52) | $82.87 ($80.46–$85.25) | $828.70 ($804.56–$852.49) | $9,944 |
| graph-12b-lean | batch | 0% | 97% | $0.41 | $0.43 | $0.0008 | $4.14 ($4.02–$4.26) | $41.44 ($40.23–$42.62) | $414.35 ($402.28–$426.25) | $4,972 |

Rates from https://openai.com/api/pricing/, checked 2026-10-28. Cache replayed as OpenAI's: every prefix it sees, from 1,024 tokens, 5-minute lifetime. **Unverified:** OpenAI's pricing page refuses automated fetches. Input and output are as recorded on getotium.ai's rate card (2026-10-28); the cached rate assumes OpenAI's usual 10% of input, and the cache rule (automatic from 1,024 tokens in 128-token steps, about 5 minutes idle) is from OpenAI's prompt caching guide as last read, not re-checked. Check both by hand before publishing.

### Priced as otium-small (Otium)

What the run's tokens would cost at Otium's published prices for otium-small, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| graph-12b | batch | 36% | 96% | $0.58 | $0.60 | $0.0010 | $5.79 ($5.63–$5.96) | $57.89 ($56.29–$59.56) | $578.86 ($562.88–$595.64) | $6,946 |
| graph-12b-lean | batch | 36% | 97% | $0.38 | $0.39 | $0.0008 | $3.80 ($3.68–$3.91) | $37.99 ($36.83–$39.13) | $379.91 ($368.31–$391.33) | $4,559 |

Rates from https://getotium.ai/pricing, checked 2026-10-28. Cache replayed as Otium's: every prefix it sees, from 16 tokens, 5-minute lifetime.

### Graph against agent, item by item

Each graph arm next to the agent on the same model, so the two differ only in shape, compared on the items both ran. Columns: [reading a report](../../docs/reading-reports.md#graph-against-agent-item-by-item).

| Graph | Agent | Items | Only graph right | Only agent right | Success, graph − agent | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| graph-12b | agent-12b | 500 | 6 | 2 | +0.8 pts (+0.0 pts to +1.8 pts) | 0.29 |
| graph-12b-lean | agent-12b | 500 | 7 | 2 | +1.0 pts (+0.0 pts to +2.0 pts) | 0.18 |

p is McNemar's exact test on the items where the arms disagree: how likely a split this
uneven would be if neither arm were better.

| Graph | Agent | Priced as | Graph mode | Graph − agent, per 1,000 items | Relative |
| --- | --- | --- | --- | ---: | ---: |
| graph-12b | agent-12b | claude-haiku-5-5 | real-time | +$0.34 (+$0.29 to +$0.38) | +37% |
| graph-12b | agent-12b | claude-haiku-5-5 | batch | −$0.28 (−$0.32 to −$0.25) | -31% |
| graph-12b | agent-12b | gpt-6-luna | real-time | +$0.33 (+$0.28 to +$0.37) | +35% |
| graph-12b | agent-12b | gpt-6-luna | batch | −$0.30 (−$0.33 to −$0.26) | -32% |
| graph-12b-lean | agent-12b | claude-haiku-5-5 | real-time | −$0.08 (−$0.11 to −$0.04) | -8% |
| graph-12b-lean | agent-12b | claude-haiku-5-5 | batch | −$0.49 (−$0.52 to −$0.46) | -54% |
| graph-12b-lean | agent-12b | gpt-6-luna | real-time | −$0.09 (−$0.12 to −$0.05) | -10% |
| graph-12b-lean | agent-12b | gpt-6-luna | batch | −$0.50 (−$0.54 to −$0.47) | -55% |

The agent is priced real-time throughout; negative means the graph costs less.

Arms shown at real-time rates only, because their requests wait on each other: agent-12b.

Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of
the average, not how much a real month will vary.
