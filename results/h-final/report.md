# Run h-final

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
| claude-code-haiku | Agent harness handed the whole input file | claude-haiku-5-5 |
| claude-code-skill-haiku | Agent harness handed the whole input file, with a skill for the task | claude-haiku-5-5 |
| graph-haiku | Workflow graph; every step on one model | claude-haiku-5-5 |
| graph-haiku-lean | Workflow graph; every step on one model, the description written without thinking | claude-haiku-5-5 |

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
| code | b178820e6122 | the commit of this repo the run used |

## Scores

How often each arm's output was right, against the catalog's own fields. Columns: [reading a report](../../docs/reading-reports.md#scores).

| Arm | Items | Valid | Brand | Color | Success |
| --- | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | 500 | 100% | 96% | 60% | 96% |
| claude-code-haiku | 500 | 100% | 96% | 59% | 96% |
| claude-code-skill-haiku | 500 | 100% | 94% | 59% | 94% |
| graph-haiku | 500 | 100% | 97% | 60% | 97% |
| graph-haiku-lean | 500 | 100% | 97% | 60% | 97% |

## Task: enrich

### Tokens per item

What each arm sent to the model and got back, per item, counted at the wire. Columns: [reading a report](../../docs/reading-reports.md#tokens-per-item).

| Arm | Items | Requests / item | Prompt | Output | Of which thinking | Refused requests |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | 500 | 2.1 | 3,371 | 779 | 199 | 0 |
| claude-code-haiku | 500 | 0.1 | 5,148 | 1,050 | 800 | 0 |
| claude-code-skill-haiku | 500 | 0.1 | 20,463 | 796 | 555 | 0 |
| graph-haiku | 500 | 2.1 | 1,785 | 968 | 591 | 0 |
| graph-haiku-lean | 500 | 2.3 | 1,936 | 745 | 342 | 0 |

Prompt counts every input token. What a provider would have served from its cache is
replayed from the recorded prompts under each price's own cache rule, below. Refused
requests are not priced: the server reports no usage for them.

### Priced as claude-haiku-5-5 (Anthropic)

What the run's tokens would cost at Anthropic's published prices for claude-haiku-5-5, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | 73% | 96% | $0.53 | $0.55 | $0.0009 | $5.26 ($5.12–$5.42) | $52.64 ($51.16–$54.18) | $526.44 ($511.63–$541.82) | $6,317 |
| claude-code-haiku | real-time | 65% | 96% | $1.01 | $1.05 | $0.0010 | $10.06 | $100.58 | $1,006 | $12,069 |
| claude-code-skill-haiku | real-time | 94% | 94% | $3.27 | $3.48 | $0.0033 | $32.71 | $327.15 | $3,271 | $39,257 |
| graph-haiku | real-time | 0% | 97% | $0.66 | $0.69 | $0.0012 | $6.62 ($6.41–$6.85) | $66.24 ($64.14–$68.54) | $662.43 ($641.45–$685.44) | $7,949 |
| graph-haiku | batch | 0% | 97% | $0.33 | $0.34 | $0.0006 | $3.31 ($3.21–$3.43) | $33.12 ($32.07–$34.27) | $331.21 ($320.72–$342.72) | $3,975 |
| graph-haiku-lean | real-time | 0% | 97% | $0.57 | $0.59 | $0.0010 | $5.66 ($5.51–$5.83) | $56.61 ($55.07–$58.28) | $566.06 ($550.74–$582.75) | $6,793 |
| graph-haiku-lean | batch | 0% | 97% | $0.28 | $0.29 | $0.0005 | $2.83 ($2.75–$2.91) | $28.30 ($27.54–$29.14) | $283.03 ($275.37–$291.38) | $3,396 |

Rates from https://platform.claude.com/docs/en/about-claude/pricing, checked 2026-11-06. Cache replayed as Anthropic's: prefixes marked where a later request reuses them (the best case), from 512 tokens, 5-minute lifetime. 3,356 requests were answered by claude-haiku-5-5 itself and are priced as Anthropic counted them, cache included, not replayed.

### Priced as gpt-6-luna (OpenAI)

What the run's tokens would cost at OpenAI's published prices for gpt-6-luna, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| agent-haiku | real-time | 24% | 96% | $0.65 | $0.68 | $0.0011 | $6.54 ($6.39–$6.70) | $65.40 ($63.88–$67.01) | $653.98 ($638.76–$670.11) | $7,848 |
| claude-code-haiku | real-time | 63% | 96% | $0.75 | $0.78 | $0.0007 | $7.48 | $74.77 | $747.73 | $8,973 |
| claude-code-skill-haiku | real-time | 94% | 94% | $0.71 | $0.75 | $0.0007 | $7.09 | $70.88 | $708.82 | $8,506 |
| graph-haiku | real-time | 0% | 97% | $0.66 | $0.69 | $0.0012 | $6.62 ($6.41–$6.85) | $66.24 ($64.14–$68.54) | $662.43 ($641.45–$685.44) | $7,949 |
| graph-haiku | batch | 0% | 97% | $0.33 | $0.34 | $0.0006 | $3.31 ($3.21–$3.43) | $33.12 ($32.07–$34.27) | $331.21 ($320.72–$342.72) | $3,975 |
| graph-haiku-lean | real-time | 0% | 97% | $0.57 | $0.59 | $0.0010 | $5.66 ($5.51–$5.83) | $56.61 ($55.07–$58.28) | $566.06 ($550.74–$582.75) | $6,793 |
| graph-haiku-lean | batch | 0% | 97% | $0.28 | $0.29 | $0.0005 | $2.83 ($2.75–$2.91) | $28.30 ($27.54–$29.14) | $283.03 ($275.37–$291.38) | $3,396 |

Rates from https://openai.com/api/pricing/, checked 2026-10-28. Cache replayed as OpenAI's: every prefix it sees, from 1,024 tokens, 5-minute lifetime. **Unverified:** OpenAI's pricing page refuses automated fetches. Input and output are as recorded on getotium.ai's rate card (2026-10-28); the cached rate assumes OpenAI's usual 10% of input, and the cache rule (automatic from 1,024 tokens in 128-token steps, about 5 minutes idle) is from OpenAI's prompt caching guide as last read, not re-checked. Check both by hand before publishing.

### Priced as otium-small (Otium)

What the run's tokens would cost at Otium's published prices for otium-small, per item and projected to monthly volumes. Columns: [reading a report](../../docs/reading-reports.md#price-tables).

| Arm | Mode | Cached | Success | Per 1,000 items | Per 1,000 successes | p95 item | 10,000 / month | 100,000 / month | 1,000,000 / month | Year at 1,000,000 / month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| graph-haiku | batch | 34% | 97% | $0.29 | $0.30 | $0.0006 | $2.89 ($2.79–$3.00) | $28.89 ($27.90–$29.97) | $288.91 ($279.00–$299.68) | $3,467 |
| graph-haiku-lean | batch | 32% | 97% | $0.24 | $0.25 | $0.0004 | $2.42 ($2.35–$2.49) | $24.18 ($23.48–$24.95) | $241.80 ($234.81–$249.48) | $2,902 |

Rates from https://getotium.ai/pricing, checked 2026-10-28. Cache replayed as Otium's: every prefix it sees, from 16 tokens, 5-minute lifetime.

### Graph against agent, item by item

Each graph arm next to the agent on the same model, so the two differ only in shape, compared on the items both ran. Columns: [reading a report](../../docs/reading-reports.md#graph-against-agent-item-by-item).

| Graph | Agent | Items | Only graph right | Only agent right | Success, graph − agent | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| graph-haiku | agent-haiku | 500 | 3 | 1 | +0.4 pts (-0.2 pts to +1.0 pts) | 0.62 |
| graph-haiku-lean | agent-haiku | 500 | 5 | 3 | +0.4 pts (-0.6 pts to +1.4 pts) | 0.73 |

p is McNemar's exact test on the items where the arms disagree: how likely a split this
uneven would be if neither arm were better.

| Graph | Agent | Priced as | Graph mode | Graph − agent, per 1,000 items | Relative |
| --- | --- | --- | --- | ---: | ---: |
| graph-haiku | agent-haiku | claude-haiku-5-5 | real-time | +$0.14 (+$0.11 to +$0.16) | +26% |
| graph-haiku | agent-haiku | claude-haiku-5-5 | batch | −$0.20 (−$0.21 to −$0.18) | -37% |
| graph-haiku | agent-haiku | gpt-6-luna | real-time | +$0.0084 (−$0.02 to +$0.03) | +1% |
| graph-haiku | agent-haiku | gpt-6-luna | batch | −$0.32 (−$0.34 to −$0.31) | -49% |
| graph-haiku-lean | agent-haiku | claude-haiku-5-5 | real-time | +$0.04 (+$0.02 to +$0.06) | +8% |
| graph-haiku-lean | agent-haiku | claude-haiku-5-5 | batch | −$0.24 (−$0.26 to −$0.23) | -46% |
| graph-haiku-lean | agent-haiku | gpt-6-luna | real-time | −$0.09 (−$0.11 to −$0.07) | -13% |
| graph-haiku-lean | agent-haiku | gpt-6-luna | batch | −$0.37 (−$0.39 to −$0.36) | -57% |

The agent is priced real-time throughout; negative means the graph costs less.

Arms shown at real-time rates only, because their requests wait on each other: agent-haiku, claude-code-haiku, claude-code-skill-haiku.

Ranges are a 90% bootstrap interval on the mean cost per item: how sure the sample makes us of
the average, not how much a real month will vary.
