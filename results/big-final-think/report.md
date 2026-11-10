# Run big-final-think

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
| code | b178820e6122 | the commit of this repo the run used |

## Scores

How often each arm's output was right, against the catalog's own fields. Columns: [reading a report](../../docs/reading-reports.md#scores).

| Arm | Items | Valid | Brand | Color | Success |
| --- | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 100% | 95% | 62% | 95% |
| graph-12b | 500 | 100% | 97% | 62% | 97% |
| graph-12b-lean | 500 | 100% | 97% | 61% | 97% |

## Task: enrich

### Tokens per item

What each arm sent to the model and got back, per item, counted at the wire. Columns: [reading a report](../../docs/reading-reports.md#tokens-per-item).

| Arm | Items | Requests / item | Prompt | Output | Of which thinking | Refused requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | 500 | 2.0 | 1,726 | 1,453 | – | 0 |
| graph-12b | 500 | 2.0 | 1,041 | 2,282 | – | 0 |
| graph-12b-lean | 500 | 2.0 | 1,049 | 1,483 | – | 0 |

Prompt counts every input token. What a provider would have served from its cache is
replayed from the recorded prompts under each price's own cache rule, below. Refused
requests are not priced: the server reports no usage for them.

### Priced as claude-haiku-5-5 (Anthropic)

What the run's tokens would cost at Anthropic's published prices for claude-haiku-5-5, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 27% | 95% | $0.88 | $0.92 | $0.0019 | $8.77 ($8.44–$9.09) | $87.68 ($84.41–$90.87) | $876.78 ($844.05–$908.70) | $10,521 |
| graph-12b | real-time | 0% | 97% | $1.25 | $1.29 | $0.0022 | $12.45 ($12.11–$12.81) | $124.53 ($121.14–$128.08) | $1,245 ($1,211–$1,281) | $14,943 |
| graph-12b | batch | 0% | 97% | $0.62 | $0.64 | $0.0011 | $6.23 ($6.06–$6.40) | $62.26 ($60.57–$64.04) | $622.64 ($605.69–$640.40) | $7,472 |
| graph-12b-lean | real-time | 0% | 97% | $0.85 | $0.88 | $0.0017 | $8.46 ($8.22–$8.74) | $84.64 ($82.17–$87.44) | $846.43 ($821.75–$874.37) | $10,157 |
| graph-12b-lean | batch | 0% | 97% | $0.42 | $0.44 | $0.0009 | $4.23 ($4.11–$4.37) | $42.32 ($41.09–$43.72) | $423.22 ($410.87–$437.18) | $5,079 |

Rates from https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-06. Cache replayed as Anthropic's: prefixes marked where a later request reuses them (the best case), from 512 tokens, 5-minute lifetime.

### Priced as gpt-6-luna (OpenAI)

What the run's tokens would cost at OpenAI's published prices for gpt-6-luna, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-12b | real-time | 7% | 95% | $0.89 | $0.94 | $0.0019 | $8.89 ($8.56–$9.21) | $88.91 ($85.65–$92.10) | $889.05 ($856.47–$921.03) | $10,669 |
| graph-12b | real-time | 0% | 97% | $1.25 | $1.29 | $0.0022 | $12.45 ($12.11–$12.81) | $124.53 ($121.14–$128.08) | $1,245 ($1,211–$1,281) | $14,943 |
| graph-12b | batch | 0% | 97% | $0.62 | $0.64 | $0.0011 | $6.23 ($6.06–$6.40) | $62.26 ($60.57–$64.04) | $622.64 ($605.69–$640.40) | $7,472 |
| graph-12b-lean | real-time | 0% | 97% | $0.85 | $0.88 | $0.0017 | $8.46 ($8.22–$8.74) | $84.64 ($82.17–$87.43) | $846.38 ($821.70–$874.31) | $10,157 |
| graph-12b-lean | batch | 0% | 97% | $0.42 | $0.44 | $0.0009 | $4.23 ($4.11–$4.37) | $42.32 ($41.08–$43.72) | $423.19 ($410.85–$437.16) | $5,078 |

Rates from https://openai.com/api/pricing/, checked 2026-10-28. Cache replayed as OpenAI's: every prefix it sees, from 1,024 tokens, 5-minute lifetime. **Unverified:** OpenAI's pricing page refuses automated fetches. Input and output are as recorded on getotium.ai's rate card (2026-10-28); the cached rate assumes OpenAI's usual 10% of input, and the cache rule (automatic from 1,024 tokens in 128-token steps, about 5 minutes idle) is from OpenAI's prompt caching guide as last read, not re-checked. Check both by hand before publishing.

### Priced as otium-small (Otium)

What the run's tokens would cost at Otium's published prices for otium-small, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| graph-12b | batch | 36% | 97% | $0.58 | $0.60 | $0.0010 | $5.80 ($5.64–$5.97) | $57.99 ($56.36–$59.69) | $579.89 ($563.58–$596.92) | $6,959 |
| graph-12b-lean | batch | 36% | 97% | $0.39 | $0.40 | $0.0008 | $3.88 ($3.77–$4.02) | $38.84 ($37.67–$40.18) | $388.40 ($376.73–$401.81) | $4,661 |

Rates from https://getotium.ai/pricing, checked 2026-10-28. Cache replayed as Otium's: every prefix it sees, from 16 tokens, 5-minute lifetime.

### Graph against agent, item by item

Each graph arm next to the agent on the same model, so the two differ only in shape, compared on the items both ran. Columns: [reading a report](../../docs/reading-reports.md#graph-against-agent-item-by-item).

| Graph | Agent | Items | Only graph right | Only agent right | Success, graph − agent | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| graph-12b | agent-12b | 500 | 10 | 1 | +1.8 pts (+0.8 pts to +3.0 pts) | 0.012 |
| graph-12b-lean | agent-12b | 500 | 10 | 1 | +1.8 pts (+0.8 pts to +3.0 pts) | 0.012 |

p is McNemar's exact test on the items where the arms disagree: how likely a split this
uneven would be if neither arm were better.

| Graph | Agent | Priced as | Graph mode | Graph − agent, per 1,000 items | Relative |
| --- | --- | --- | --- | ---: | ---: |
| graph-12b | agent-12b | claude-haiku-5-5 | real-time | +$0.37 (+$0.33 to +$0.41) | +42% |
| graph-12b | agent-12b | claude-haiku-5-5 | batch | −$0.25 (−$0.28 to −$0.22) | -29% |
| graph-12b | agent-12b | gpt-6-luna | real-time | +$0.36 (+$0.32 to +$0.40) | +40% |
| graph-12b | agent-12b | gpt-6-luna | batch | −$0.27 (−$0.30 to −$0.23) | -30% |
| graph-12b-lean | agent-12b | claude-haiku-5-5 | real-time | −$0.03 (−$0.07 to +$0.0063) | -3% |
| graph-12b-lean | agent-12b | claude-haiku-5-5 | batch | −$0.45 (−$0.48 to −$0.42) | -52% |
| graph-12b-lean | agent-12b | gpt-6-luna | real-time | −$0.04 (−$0.08 to −$0.0063) | -5% |
| graph-12b-lean | agent-12b | gpt-6-luna | batch | −$0.47 (−$0.50 to −$0.43) | -52% |

The agent is priced real-time throughout; negative means the graph costs less.

Arms shown at real-time rates only, because their requests wait on each other: agent-12b.

Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of
the average, not how much a real month will vary.
