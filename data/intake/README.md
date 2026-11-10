# Catalog intake inputs: a supplier's feed with rejects

Built from the product catalog of the **Shopping Queries Dataset (ESCI)** by Amazon Science,
<https://github.com/amazon-science/esci-data>, licensed under the Apache License 2.0, by
`avg data <parquet> --intake data/intake` (seed 1). Why the task is built this way:
[docs/design.md](../../docs/design.md#catalog-intake).

> Reddy, C. K., Màrquez, L., Valero, F., Rao, N., Zaragoza, H., Bandyopadhyay, S., Biswas, A.,
> Xing, A., & Subbian, K. (2022). Shopping Queries Dataset: A Large-Scale ESCI Benchmark for
> Improving Product Search. arXiv:2206.06588.

| File | What it is |
| --- | --- |
| `items-20.jsonl`, `items-85.jsonl` | The feed: 500 listings, of which 20% or 85% should be rejected |
| `catalog-20.jsonl`, `catalog-85.jsonl` | The store's catalog for each feed: `sku`, `brand`, `title`, `color` |
| `policy.json` | The store's rules: its excluded brands, and no books |

Changes from the source, beyond task 1's (US listings, HTML removed, long text shortened, brand
and color moved into `gold`):

- **Ids replaced** by `p` and eight hex digits, so neither an ASIN nor an ISBN shows. The source id
  is kept in `gold.source`.
- **Re-listings** (catalog and feed duplicates) rewritten from the original by fixed rules in
  [`src/avg/data.py`](../../src/avg/data.py) (`relist`): title parts reordered with the brand
  moved, bullet points reversed, the description dropped when there are bullets and halved when
  there are not. No model wrote any of it.
- **Books** are listings whose ESCI product id is an ISBN-10 and whose text says it is a book,
  with no toy, game, kit or cards in the title, and the blocklist still applied.
- **New items** have no ISBN for an id and never mention anything that reads as a book or other
  media, nor an excluded brand, so excluding one is never the right call.

`gold.kind` is the answer: `new`, `catalog_duplicate`, `feed_duplicate`, `excluded_brand` or
`excluded_kind`; `gold.group` ties the listings of one product in the same feed together. No arm
sees `gold`.

Rebuild it with `task data:intake` (needs the source file `task data` downloads).
