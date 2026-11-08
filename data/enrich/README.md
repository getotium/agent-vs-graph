# Task 1 inputs: product listings

`items.jsonl` is 1,000 product listings from the product catalog of the **Shopping Queries
Dataset (ESCI)** by Amazon Science, <https://github.com/amazon-science/esci-data>, licensed under
the Apache License 2.0. Changes from the source: a seeded sample of the US listings only, HTML
removed and long text shortened, and the `product_brand` and `product_color` fields moved into
`gold`.

> Reddy, C. K., Màrquez, L., Valero, F., Rao, N., Zaragoza, H., Bandyopadhyay, S., Biswas, A.,
> Xing, A., & Subbian, K. (2022). Shopping Queries Dataset: A Large-Scale ESCI Benchmark for
> Improving Product Search. arXiv:2206.06588.

A listing is kept when it has a title, a brand, a color and some bullet points or description;
when its brand is named somewhere in its own text (so every arm can find it) and is not a
placeholder such as "Unknown"; and when nothing in it matches the blocklist in
[`src/avg/data.py`](../../src/avg/data.py): weapons, adult products, tobacco and drugs. The sample
is the 1,000 qualifying listings with the lowest SHA-256 of `seed:product_id` (seed 1), so it does
not depend on file order, and the first N items of the file are the sample of size N.

Rebuild it with `task data` (downloads the 1.1 GB source file).
