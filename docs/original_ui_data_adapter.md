# Original UI with real data

Four-region extension: the adapter now combines `hkma.sqlite` and
`regional.sqlite`. The existing collection cycle also checks the three approved
MAS, ESMA and FCA publications. Multi-class records match individual asset
filter selections without duplicating rows. See the [four-region pilot](four_region_pilot.md)
for the separate schema, live coverage and repeat-run limitations. The original
CSS and layout remain unchanged; the earlier no-schema-change statement below
describes the initial UI restoration only.

As of 2026-10-28, `src/app.py` uses the teammate's original frontend again.
`src/app_original.py` remains an exact copy of commit `27b8b04:src/app.py`.
CSS, page navigation, column layouts, cards, bar chart, treemap, tables and
keyword-search interactions are retained. The previous redesigned dashboard
modules remain in the repository but are no longer called by `app.py`.

`src/app_data.py` adapts the existing SQLite reader and public market clients to
the original four DataFrames: `documents`, `developments`, `chunks`, `markets`.
No canonical demo file is modified or loaded by the current app.

## Necessary compatibility changes

- Publication previews populate the original development interface. Their
  `obligation_summary` is explicitly prefixed `Publication:` and contains the
  source title, not an inferred obligation or impact assessment.
- `risk_rating` is `unknown`, `confidence` is null, and `review_status` is
  `not_reviewed`. The UI displays `Not assessed` for null confidence, includes
  `unknown` in the original risk filter and uses a neutral bar color for it.
- Incorrect demo and completed-review claims are replaced with factual wording.
  The jurisdiction count reflects collected records; no model is added.
- Chunk references resolve to current real evidence. Text and citation attributes
  are HTML-escaped because the original renderer uses HTML cards.
- The three market cards show BTC market cap, USDC circulating amount at USD peg,
  and the largest currently available individual RWA protocol TVL. The real
  protocol name replaces the fictional Treasury basket. This selection is not a
  market-wide RWA total. The original treemap remains, with a note that unlike
  metrics cannot be interpreted as market shares.
- Unavailable market values stay missing and display `Unavailable`; invalid or
  nonpositive values are excluded from the treemap. Source errors and stale
  snapshots are explicitly identified rather than replaced with fixtures.

## Refresh behavior

Opening the app starts the existing app-owned HKMA collection service, using its
persisted schedule (default 24 hours). No new collection controls are added to
the original interface. The server and computer must remain running.

The original frontend has no timed rerender. Navigation, widget actions or a
browser reload read refreshed frames after the 60-second adapter cache expires.
The market provider cache still limits successful HTTP fetches to once per
15 minutes, with the existing failure cooldown. A static browser page alone does
not trigger market refresh. The earlier dashboard's fragment refresh intervals
do not apply to this original frontend.

Run the current app with `python -m streamlit run src/app.py --server.port 8501`.
Run the preserved original separately with
`python -m streamlit run src/app_original.py --server.port 8502`.

Validation covers exact CSS equality, retained layout constructs, null analysis
fields, unknown-risk filtering, real citation access, all four original pages,
empty datasets and unavailable market sources. No database schema or ingestion
algorithm was changed.
