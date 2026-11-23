# Real-Document Sample Review

Validation date: 2026-10-16. The sample contains twelve official documents: ten HTML press releases and two text-based PDFs. Current successful extractions contain 185 chunks; historical versions and processing results remain in the database.

| Document | Publication date | Format | Current chunks |
|---|---|---|---:|
| [Granting of stablecoin issuer licences](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2026/04/20260410-4/) | 2026-04-10 | HTML | 2 |
| [Joint Statement by the HKMA and the SFC on Stablecoin-related Market Movements](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2025/08/20250814-8/) | 2025-08-14 | HTML | 3 |
| [Implementation of regulatory regime for stablecoin issuers](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2025/07/20250729-4/) | 2025-07-29 | HTML | 2 |
| [Government welcomes passage of the Stablecoins Bill](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2025/05/20250521-3/) | 2025-05-21 | HTML | 3 |
| [HKMA announces stablecoin issuer sandbox participants](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2024/07/20240718-4/) | 2024-07-18 | HTML | 2 |
| [Consultation conclusions for legislative proposal to implement regulatory regime for stablecoin issuers in Hong Kong released](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2024/07/20240717-3/) | 2024-07-17 | HTML | 2 |
| [HKMA launches the stablecoin issuer sandbox arrangement](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2024/03/20240312-4/) | 2024-03-12 | HTML | 1 |
| [Consultation on legislative proposal to implement regulatory regime for stablecoin issuers and announcement on introduction of sandbox arrangement](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2023/12/20231227-4/) | 2023-12-27 | HTML | 3 |
| [Conclusion of discussion paper on crypto-assets and stablecoins](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2023/01/20230131-9/) | 2023-01-31 | HTML | 2 |
| [Discussion Paper on Crypto-assets and Stablecoins](https://www.hkma.gov.hk/eng/news-and-media/press-releases/2022/01/20220112-3/) | 2022-01-12 | HTML | 1 |
| [Guideline on Supervision of Licensed Stablecoin Issuers](https://www.hkma.gov.hk/media/eng/doc/key-functions/ifc/stablecoin-issuers/Guideline_on_supervision_of_licensed_stablecoin_issuers_eng.pdf) | Unknown: month-only cover date | PDF | 113 |
| [Legislative Proposal to Implement the Regulatory Regime for Stablecoin Issuers in Hong Kong Consultation Conclusions](https://www.hkma.gov.hk/media/eng/doc/key-information/press-release/2024/20240717e3a1.pdf) | Unknown: month-only cover date | PDF | 51 |

Checks covered every document's title, source, publication-date evidence, original-byte hash, text and chunk coverage. All 417 historical chunk slices, HTML observation/evidence fingerprints, foreign keys and integrity_check passed. The beginning and end of each of the ten HTML bodies were also inspected for topic consistency and exclusion of sidebar news or footer navigation.

HTML dates come from article headers and were independently compared with topic-list dates. Month-only PDF dates remain NULL without borrowing announcement dates. Legal validity and full table structure were not assessed; is_table remains NULL. This review does not establish legal or business conclusions approved by a human legal reviewer.

Two live batches each processed ten articles. The second reused every evidence version and extraction. A third --new-only run had zero pending documents. Content/link changes and failure isolation were tested locally; no claim is made that the official website underwent a regulatory revision during testing.

Full hashes, metadata evidence, version IDs, chunk counts and validation results are in the local data/ingestion/discovery_validation_report.json. That report, the real database and runtime originals are excluded from this code submission. This list records completed local validation; see the [ingestion guide](ingestion.md) for reproduction.
