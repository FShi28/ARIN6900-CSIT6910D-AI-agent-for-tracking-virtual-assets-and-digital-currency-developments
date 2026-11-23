# Real-data workspace integration

**2026-10-28 update:** `app.py` now preserves the original frontend through
`app_data.py`; see [the current adapter](original_ui_data_adapter.md). Source
endpoints and provenance below still apply. The redesigned UI's separate plots,
document reader and automatic fragment refresh are no longer used by `app.py`.

## Behavior and migration

The four original `app.py` pages now use actual regulatory records and public
market APIs. There is no demo mode and no runtime read from `data/canonical/`.
Those teammate-authored files are preserved, as are `requirements.txt`,
`README.md`, `proposal.txt` and `.gitignore`. The existing regulatory schema and
collector are unchanged. No canonical database migration is required.

| Original placeholder | Real replacement |
| --- | --- |
| `documents.jsonl` | Current documents from `data/ingestion/hkma.sqlite` through `Reader` |
| `chunks.jsonl` | Current successful extraction chunks, exact offsets and stored citations |
| `developments.jsonl` | Actual publications, source titles and verbatim excerpts; not invented legal developments |
| Risk chart | Publication counts by jurisdiction and document type |
| `risk_rating`, `confidence`, `review_status`, `obligation_summary` | Not assessed; removed fabricated values and approval claims; source excerpts remain verbatim |
| Fixed four-market coverage label | Actual jurisdiction count from the database |
| BTC market-cap fixture | CoinGecko Bitcoin market capitalization in USD |
| USDC circulating-supply fixture | DefiLlama USD-pegged circulating amount; available prices shown separately |
| Fictional tokenized Treasury basket | Individual protocols categorized `RWA` by DefiLlama, with their reported TVL |
| Treemap combining unlike metrics | Separate stablecoin circulating-amount and RWA TVL plots |
| Fixture keyword answers | English word matching over current real evidence, with exact citations |

Regulatory filtering applies to the monitor table and its document reader.
The reader retains full text, verified original downloads, PDF page numbers,
source links, hashes and fixed extraction/chunk identifiers. Current-version
selection uses the existing `Reader`; historical or failed latest versions are
not silently replaced with old successful text. Unknown dates remain null.

The analyst returns evidence excerpts, not generated conclusions. Matching word
counts are not confidence scores. Coverage is displayed explicitly: currently
Hong Kong / HKMA. A question about an uncollected jurisdiction cannot establish
its regulatory position. No local/cloud model, embeddings or new agent workflow
has been added in this change.

## Verified market sources

Configuration: `config/market_sources.json`. All three configured endpoints were
successfully fetched from this machine on 2026-10-26 without API keys.

| Source | Endpoint | Fields used |
| --- | --- | --- |
| DefiLlama stablecoins | `https://stablecoins.llama.fi/stablecoins?includePrices=true` | `peggedAssets[].id/symbol/pegType`, `circulating.peggedUSD`, optional `price` |
| CoinGecko Bitcoin | `https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids=bitcoin` | `market_cap`, `current_price`, `total_volume`, `last_updated` |
| DefiLlama RWA | `https://api.llama.fi/protocols` | `id`, `name`, `category == RWA`, `tvl` |

References: [DefiLlama API documentation](https://api-docs.defillama.com/llms-free.txt)
and [CoinGecko market endpoint](https://coingecko-api-v3.readme.io/v3.0.1/reference/coins-markets).
The DefiLlama documentation currently lists `api.llama.fi/stablecoins`, which
returned HTTP 404 during verification. The configured stablecoin service URL
above returned HTTP 200 with the documented `peggedAssets` shape. CoinGecko uses
the machine's configured proxy environment; DefiLlama uses direct connections.
TLS certificate verification remains enabled for both. No automatic provider
substitution is performed when an endpoint fails.

These are secondary market aggregators, not regulator evidence. USD-at-peg
circulation is not a price-adjusted capitalization. RWA protocol TVL is not a
tokenized Treasury basket, outstanding issuance, or a deduplicated RWA total.
The app does not sum BTC market cap, stablecoin circulation and protocol TVL.
Only USD-pegged stablecoins are included; other pegs are intentionally excluded.

## Market cache and provenance

The Overview and Market Signals pages check snapshots every minute while open.
An endpoint is fetched at most once per 15 minutes after success. Failures have
a 60-second retry cooldown. Requests use a declared User-Agent, 5-second connect
and 20-second read timeouts, a 20 MiB response limit, at most one retry for
connection/timeouts or HTTP 5xx, and no redirect following. HTTP 429 is not retried
inside the request. This is not an independent always-on market scheduler.

Responses are validated before replacing the current snapshot. Invalid numbers,
missing observations or failed requests never become zero-valued fixtures.
Provider failures are isolated. A previous valid snapshot remains visible as
**stale** with an error and retrieval time; an initial failure is **unavailable**.

`data/market/raw/<sha256>.json` preserves exact response bytes. Per-source JSON
state files contain the current snapshot reference, hash, retrieval time and
last attempt/error. OS locks prevent duplicate simultaneous refreshes. The raw
hash is checked before a saved snapshot is read. Runtime files are local artifacts
and should not be included in a source-only commit.

Normalized observation fields:

| Field | Meaning / provenance |
| --- | --- |
| `asset_id`, `instrument` | Provider identifier and symbol/name; source-derived |
| `asset_class` | Deterministic adapter mapping; `stablecoin`, `cryptocurrency`, `rwa` |
| `metric`, `unit` | Explicit adapter mapping; market cap, price and volume use USD; circulating amount uses USD at peg; protocol TVL uses USD |
| `value` | Finite nonnegative source number; invalid/missing values omitted, never synthesized |
| `observed_at` | Provider update timestamp where supplied; otherwise null |
| `collected_at` | UTC retrieval time; never substituted for provider update time |
| `provider`, `source_id`, `source_url` | Configuration-derived source attribution |
| `json_pointer` | Deterministic position of the numeric value in the saved response |
| `content_sha256`, `raw_path` | Exact-byte integrity and local provenance |
| `data_status` | Display status derived from cache age and refresh errors |

DefiLlama does not expose per-record update timestamps in these responses. A
successful recent fetch cannot establish the age of the underlying measurement.
CoinGecko update times older than one hour produce an additional warning.

## Validation

Local tests cover current-version evidence, filters, all four pages, missing
data, source metric mapping, non-USD exclusion, bad values, duplicate identities,
cache reuse, stale/error recovery, byte tampering and HTTP 429 handling.
No network calls or real data writes occur in those tests.
The full local suite passed: **180 tests** on 2026-10-26.

The initial live market fetch yielded 588 stablecoin observations, 3 Bitcoin
observations and 119 individual RWA protocol TVL observations. These are counts
of metrics, not counts of documents or distinct tokens. The local report is
`data/market/validation_report.json`; runtime provider coverage can change.
The existing regulatory corpus has 12 real documents and 185 current chunks.

Run from the repository root:

```powershell
python -m pip install -r requirements-app.txt
$env:PYTHONPATH = Join-Path (Get-Location) 'src'
python -m pytest tests -q -p no:cacheprovider
python -m streamlit run src/app.py --server.address 127.0.0.1
```
