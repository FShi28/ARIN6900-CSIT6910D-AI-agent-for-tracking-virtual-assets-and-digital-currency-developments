# 香港稳定币数据专项

## 六个重点的证据核对（2026-11-20）

当前增加了发行、储备、赎回、托管、牌照、合规要求的 39 项证据核对。完整可点击表见
[`data/exports/hk_stablecoins/coverage.md`](../data/exports/hk_stablecoins/coverage.md)，机器可读结果为同目录 `coverage.json`。
表内有适用机构、原文链接、章节、PDF 物理页码、引用段落 ID 和最后成功抓取时间。
核对配置为 `config/hk_stablecoin_coverage.json`。每次统一导出都会重新检查原文哈希和证据位置；内容变化会标记为 `source_changed_requires_review`，需要重新核验后才能更新审核哈希。

本轮补入四份官方原文：SFC 26EC26 稳定币服务通函、SFC 25EC44 平台托管通函、HKMA 2026-05-27 银行数字资产托管通函及标准附件。两个 SFC 原文是 HTML，不能把下载入口返回的网页冒充 PDF，也不能把正文中链接的咨询文件误认成通函本身。现有全文库增至 61 条、1,510 个段落。

39 项全部定位到证据，只代表这份预先选定的清单，不代表所有法规或所有合规责任已经覆盖。尤其应区分发行人储备资产保管、银行代客托管、交易平台托管的适用范围。

条例现行综合正文及原始宪报仍未取得：法例网站的加载／连接问题、立法会 PDF 的证书链问题，以及宪报新入口的交互验证均保留在缺口清单。SFC 26EC26 的全文缺口已关闭。不得将指南、咨询稿或新闻稿作为条例正文的替代。

新补入的四个链接已进入现有定时刷新，且可手动重跑；SFC 已接入当年通函查询；HKMA 专题页之外的通函归档仍未接通。即便固定链接每日检查，也不能据此宣称“六类全部最新法规已收齐”。

本轮范围：香港、稳定币、英文原文。以 2022 年基础讨论文件为起点，补充咨询、咨询总结、正式指引、发牌及过渡安排、通函及附件、政府公告与立法会答复、监管机构解释，以及教授推荐渠道的相关材料。收集的是有出处的文件全文与可引用段落，不是市场行情数据。

## 如何运行

在项目根目录安装 requirements-ingestion.txt 后运行：

```powershell
python scripts/collect_hk_stablecoins.py
```

这会刷新原有 HKMA SQLite 数据，以及已审核的香港稳定币扩展目录，导出统一数据，再检查 HKMA 主题页的直接链接。不会运行其他地区或市场数据采集。首次运行会建立 HKMA 数据库；下载失败保留此前成功版本并返回非零退出码。全文不存在的来源不会被计入成功数量。

只导出本机已有数据、不联网：

```powershell
python scripts/collect_hk_stablecoins.py --export-only
```

扩展目录也接入原有 collection worker；只有该进程运行时，原有定时刷新才会执行。没有建立独立的系统定时服务。2026-11-20 起，四个已验证入口支持自动发现和入库；无法通过正文、范围或格式检查的链接保留状态，不作为成功入库资料。

## 每日新文章发现（2026-11-20）

| 渠道 | 自动扫描入口 | 纳入方式与边界 |
|---|---|---|
| HKMA | 稳定币专题页 | 扫描直接链接；收录支持的文章和 PDF，不代表 HKMA 全站 |
| Charltons | 香港法律通讯列表 | 最多前三页；通过文章的 Download PDF 链接取得全文 |
| ASIFMA | 站内 stablecoin 搜索 | 列表标题须明确提及 HK／Hong Kong／HKMA；排除仅涉及 MAS 的回应 |
| Linklaters | Financial Regulation 博客的 Hong Kong stablecoin 搜索 | 检查正文中的香港稳定币相关内容；不等于 Linklaters 全站 |

每个入口每轮最多检查三页（HKMA 一页），每个渠道最多处理八个尚未入库候选；未处理候选持久保存并按最早尝试时间优先处理。超过页数限制的下一页会记录在报告中。分页限制意味着长时间停机或大量集中发布可能漏掉列表更深处的新文章，不能称作历史全量抓取。

已入库链接不会因每日扫描重复增加数量；每日原文刷新仍由已有刷新环节负责。带版本参数的 PDF 只有在原文件哈希完全一致时才合并。多地区简报中仅新加坡涉及稳定币的情况会被排除；包含香港稳定币讨论的跨地区文章仍明确属于背景解读。

自动发现与统一导出已接入 `CollectionService` 的每日执行路径，也接入香港专项 CLI。只运行新内容发现、不刷新所有旧文件，可使用：

```powershell
python src/hk_discovery.py
```

- `config/hk_discovery.json`：入口与扫描上限。
- `data/ingestion/hk_stablecoins/discovered_sources.json`：自动新增来源，现有 Research Library 和统一导出均会读取。
- `data/ingestion/hk_stablecoins/discovery_queue.json`：候选、首次发现时间、最近尝试、对应 PDF、排除／失败原因。
- `data/ingestion/hk_stablecoins/discovery_report.json`：每个渠道的扫描页数、已知链接、新增数量、待审核及截断分页。

初次扫描自动新增七条资料；修复下载链接带版本参数的识别问题后，再次扫描四个入口全部成功，新增零条，未产生重复记录。一个仅在新加坡部分讨论稳定币的 Linklaters 简报被排除。总库为 57 条资料、1,461 个段落。这个结果包含新发现的历史文件，不表示今天刚发布七篇新文章。

## 文件位置与交付

- `config/hk_stablecoin_sources.json`：本轮审核过的新增来源，包含标题、链接、格式、地区、类型、日期证据、抓取规则及部分关联文件链接。
- `config/hk_stablecoin_gaps.json`：已知全文缺口，以及教授推荐渠道的纳入／待审核状态。
- `data/ingestion/hkma.sqlite`：原有 HKMA 新闻稿及两份 PDF。
- `data/ingestion/research/`：扩展文件的最新全文分块快照；延续现有 Research Library 数据接口。
- `data/ingestion/research_versions/`：扩展文件的历史内容／元数据快照。
- `data/raw/`：按 SHA-256 保存的 PDF／HTML 原文。
- `data/exports/hk_stablecoins/documents.jsonl`：统一文件目录，每行一个文件。
- `data/exports/hk_stablecoins/chunks.jsonl`：统一可引用段落，每行一个段落，带来源、文件类型、primary/secondary、日期精度、PDF 页码或网页链接。
- `data/exports/hk_stablecoins/inventory.md`：可阅读的全部标题和原文链接清单。
- `data/exports/hk_stablecoins/summary.json`：本次导出的实际数量；不要使用历史报告数字作为实时统计。
- `data/ingestion/hk_stablecoins/last_run.json`：每个链接的最新刷新结果。
- `data/ingestion/hk_stablecoins/topic_audit.json`：HKMA 主题页直接链接的覆盖和待审核项。

新材料没有全部塞入两个旧 SQLite 数据库。因此只复制旧的 `hkma.sqlite` 和 `regional.sqlite`，不会带走本轮全部新增材料。需要交付数据时使用统一 JSONL 导出；本机已有原始文件并不等于 GitHub 已经包含这些数据。本轮未提交或推送 Git。

## 教授推荐渠道怎么用

已补入 Charltons、Linklaters、ASIFMA 和 EY 的相关全文。律所用于解释规则，ASIFMA 用于了解行业反馈，EY 用于比较不同地区的监管安排。EY 报告是跨地区研究，不能把整份报告都称作香港法规。ASIFMA 的建议也不代表监管机构采纳了这些建议。

BIS、FSB、IOSCO、IMF、GFMA 属于后续背景研究层；原有研究库保留此前条目，本次香港专项导出只纳入明确相关的文件。Ashurst、DLA Piper、其他四大渠道仍待做香港稳定币专项审核，不因为教授列过名称就声称它们已经全部接入。

## 日期、版本与引用规则

1. PDF 封面只写月份时，保留 `YYYY-MM`；网页或正文日期明确到日时才保留 `YYYY-MM-DD`。不从 URL、PDF 创建时间或旁边的新闻反推发布日期。
2. 发牌登记册等动态页面的抓取时间不等于发布日期。联系名单的更新时间也不等于发布日期。
3. PDF 保留实际页码；HTML 页码为空。原文、哈希、链接和分块一起保留。
4. `authority=primary` 说明来源是监管机构／政府，不表示每篇演讲、解释或公告都是有约束力的规定。
5. 所有文件默认 `legal_status=not_assessed`。本轮没有自动判断生效、失效、替代关系，也没有生成 HSBC 风险评级。
6. 文件之间可能引用或附载同一指引，文件数量不是独立规则数量。按链接去重，不把一次新闻稿与对应指引合并成一个法律来源。

## 覆盖边界与已知缺口

这是经过核验的一批材料，不是“香港稳定币所有内容”。主题页直接链接覆盖只说明该入口，不代表全站、所有历史版本、所有语言或所有监管机构完整覆盖。

《稳定币条例》的现行综合正文尚未成功下载：法例网站在此抓取方式下返回加载页；立法会原始条例 PDF 的证书链校验失败。旧宪报入口也已迁移。已收集的条例刊宪／生效政府公告不等于条例全文。其他已知缺口见配置文件。PDF 表格目前保留为文字，未验证为可直接计算的结构化表格。

后续应首先解决条例正文与宪报、SFC 配套通函，再系统审计 HKMA 咨询／通函归档及其余教授推荐渠道。EY 等其他渠道目前仍只刷新已收录文件，尚无自动发现适配器。

## 本轮验证（2026-11-19）

完整香港专项刷新：50 条资料，全部成功；其中 23 个 created（首次或内容／元数据更新），27 个 reused。总计 23 份 PDF、27 个网页、1,325 个段落。原有 12 条 HKMA 资料和 1 条 Charltons 资料，加上本轮新增 37 条，组成此专项导出。HKMA 主题页的 31 个直接资料链接中，30 个已收录，条例链接仍待取得正文。

`python -m pytest tests -q -p no:cacheprovider`：200 项测试通过。

`python scripts/validate_hk_stablecoins.py`：50 条资料原文哈希、段落出处、PDF 页码、扩展资料重新解析结果通过；发牌、储备与赎回、反洗钱、行业咨询回应、2026 年通函及发牌登记册六类证据检查通过。这验证数据可用性，不表示已经评估 chatbot 回答质量。

完整清单、最新实际数量和验证详情以 `data/exports/hk_stablecoins/` 的生成文件为准。

2026-11-20 自动发现验证：整套回归 210 项通过；随后新增的每日执行路径开关两种集成情况通过，相关模块共 27 项定向测试通过。57 条资料的原文哈希、引用页码和重新提取检查通过。HKMA 新闻稿继续由原有 SQLite 收集器处理，扩展发现器不另建重复副本。

## 条例官方开放数据复核（2026-11-20）

另外发现并实际下载了律政司通过 DATA.GOV.HK 发布的现行法例包中的第 656 章 XML 候选正文。该公开数据集标注每周更新。由于整个 ZIP 约 129 MB，使用服务器支持的标准 HTTP Range 读取目录及指定成员；每段校验一致的 ETag，成员 CRC 由 ZIP 读取器验证。没有绕过法例／宪报网站的验证界面。

文件名是 `cap_656_en_c/cap_656_20260910000000_en_c.xml`，正文短标题为 Stablecoins Ordinance，但 XML 的根 identifier、dc:identifier 和 docNumber 分别标成 cap155／155。此矛盾需要与官方核证 PDF 或更正后的 XML 复核；不能由程序擅自修改后当成已确认法律正文。

候选原文及 SHA-256 已保留，隔离记录在 `data/ingestion/hk_stablecoins/quarantine/cap656.json`，未加入 Research Library 或 chatbot 的检索库，也未计入 61 条全文记录。当前准确状态是“已取得官方 XML 候选，未通过身份一致性校验”，而不是“完全没有取得正文”，也不是“条例已完整核验”。

本轮整套回归 216 项通过；随后新增的 XML 编号冲突与实体拒绝校验 2 项通过。61 条入库资料的哈希、页码、原文重提取验证通过，39 个选定证据核对项均定位成功。新增四份官方文件再次刷新均为 reused，未重复入库。


## Official discovery extension — 2026-11-20

Six configured discovery channels now include HKSAR Government and SFC.

- Government: official English RSS `https://www.info.gov.hk/gia/rss/general_en.xml`; title and description stablecoin filter, followed by full article validation. The observed feed holds 100 releases spanning approximately two days. It is not a historical archive and downtime or high release volume can cause missed items. Print/ordinary URL variants share a publication identity for discovery.
- SFC: the public e-Distribution app exposes `POST https://apps.sfc.hk/edistributionWeb/api/circular/search`. The endpoint and payload were verified against its published JavaScript and live response. Each run scans the current calendar year, at most six pages of 20 results, with at most eight new bodies ingested. Title filter: stablecoin, or both virtual asset and custody. This does not discover every SFC news release, consultation, or broad AML circular. The RSS endpoint returned 403 and is not used. No access protections were bypassed.
- The live scan read three SFC pages (46 circulars), found one matching already-collected document, and added zero. The government feed contained zero matching releases. Production remains 61 documents and 1,510 chunks.
- Isolated live SFC ingestion checks first-time storage and repeated-run deduplication; government saved-body tests verify extraction, publication date, provenance and persistence.
- Both use the existing 24-hour collection worker. No always-on process or OS task was started. EY remains fixed-link refresh only.
- Run all configured discovery: `python src/hk_discovery.py`. Full HK refresh: `python scripts/collect_hk_stablecoins.py`.
- Implementation: `src/virtual_asset_agent/collectors/hk_official.py`, `src/hk_discovery.py`, `src/virtual_asset_agent/fetching.py`; config remains in `config/hk_discovery.json`, because the legacy YAML registry only accepts its fixed source schema.

Validation for this extension: full suite `python -m pytest -q` passed 229 tests. Government live article refresh returned `reused`; isolated SFC live ingestion created one record and a repeat created none. Production export remains 61 documents / 1,510 chunks.


## 2026-11-21 续接记录

先读 `data/ingestion/hk_stablecoins/work_checkpoint.json`。该文件记录最新状态、待办、阻碍和运行命令；不要仅依赖聊天历史或上方历史数量。

HKMA Banking Regulatory Document Repository 已接入自动发现，配置 ID 为 `hkma_brdr`。通过官网公开 JavaScript 验证的 POST `/restapi/doc-search` 查询 stablecoin，按发布日期降序每页 20 条、最多六页；只收录标题包含 stablecoin 的英文记录。正文提及稳定币、但标题未提及的广义银行规则仍需人工审核，不能声称归档全覆盖。实际扫描四页、65 个搜索结果，四个相关候选中三个已经存在，新增 Relevant Stablecoin-related Activities 通函。仓库标记 Current 只保留为发布者元数据，不据此自动判定法律效力。

现在是六个发布渠道、七个扫描入口（HKMA 有专题页和通函库两个入口）。新文件先检查落地页上实际 PDF 链接，原文与检索结果均保留；已有 PDF 不重复入库。

PwC《Stablecoins in Hong Kong》已下载，但 PDF 提取权限检查失败，未纳入全文库。条例 XML 身份冲突仍未解决，继续隔离；立法会原始条例 PDF 的 TLS 校验仍失败，未关闭证书验证。


本轮验收结果：63 条资料（30 PDF、33 HTML）、1,519 个段落。增加 HKMA Relevant Stablecoin-related Activities 和 SFC 25EC57（产品、服务及托管通函中的稳定币条款）。全量刷新无失败，七个扫描入口全部成功且第二轮无新增重复；232 项全套测试通过，63 条原文与引用验证通过。39 项预设证据检查仍可定位；这不代表法规全量覆盖。`work_checkpoint.json` 保持 in_progress，明确保留条例正文、宪报、修订关系审计、其余教授渠道审核和持续运行安排等待办。本轮没有启动常驻采集或安装系统定时任务。


2026-11-21 additional source review: corpus now 66 documents (30 PDFs, 36 HTML pages), 1,545 chunks. Added KPMG Digital payments, Deloitte Q3 2026 frontier-technology regulatory report, and government LCQ10 Regulation of digital assets (2025-09-10). KPMG and Deloitte remain secondary mixed-context sources, not Hong Kong-only rules; publication day unknown, never inferred from URL. They have fixed-link refresh but no new-article discovery. Duplicate saves returned reused. Eight relevant parser/export tests passed. Ashurst old article now resolves to a generic migrated Insights directory; DLA returned 429; neither admitted. PwC PDF extraction restrictions and statutory identity/TLS gaps remain. Full previous implementation suite: 232 passed; no pipeline code changed in this source-only extension.

Final validation for this source extension: all 66 documents passed raw/hash/citation checks, with no failures. Resume from work_checkpoint.json.


## 香港专项运行记录与续跑（2026-11-21）

- `python scripts/collect_hk_stablecoins.py`：新一轮香港专项刷新，只启用 legacy hkma 数据源，随后刷新香港扩展资料、自动发现、导出和核对专题页。
- `python scripts/collect_hk_stablecoins.py --status`：不联网查看专项断点、共享采集锁、现有 Streamlit 调度状态和资料数量。enabled=true 只表示设置开启，不证明后台进程正在运行；显示的旧调度记录也不是本次手动刷新结果。
- `python scripts/collect_hk_stablecoins.py --resume`：同一代码／配置且开始不足 24 小时的断点可继续。跳过成功阶段；遇到未完成／失败阶段时重跑该阶段及其下游。阶段中已保存的文件通过既有幂等逻辑复用。整轮已成功的断点不会再次联网，不能将 resume 当成新一轮刷新。
- `python scripts/collect_hk_stablecoins.py --export-only`：不联网重新生成导出，仍遵守共享写锁。

每个阶段执行前后保存 `data/ingestion/hk_stablecoins/run_checkpoint.json`，每轮历史保留在 `runs/<run_id>.json`。人为中断不会丢失此前保存的阶段结果和文件。进程退出后锁会由操作系统释放；状态查询会将遗留 running 断点标为 interrupted。不要通过删锁文件绕过正在工作的采集进程。

该改动增强香港专项 CLI 的可恢复性，未安装系统定时任务、未启动常驻后台，也不改变 Streamlit 原来的跨地区调度行为。法律正文和宪报缺口继续单独列出，不因采集运行成功而关闭。


2026-11-21 运行验证与历史补查：香港专项五个阶段均已真实成功完成，run_id 为 638e1e136e5443c39730926971ecde73；其导出为当时的 66 条。成功断点再次 resume 不做新请求，现已修正为不改写原完成时间，返回 resume_noop=true。代码或目录配置变更后必须新跑，不能重用旧断点。

另经 SFC 官方搜索接口补查 2025 年全部 48 条列表记录，按标题中的 virtual asset / stablecoin 选出 16 条候选，2 条已收录，对其余 14 条原始 HTML 检查稳定币段落。新增 25EC50 Supplemental joint circular on intermediaries’ virtual asset-related activities；它是历史背景通函，稳定币段落说明后续指引将另行发布，不代表所有虚拟资产要求适用于稳定币。其余候选无明确 stablecoin 文本，不强行纳入本专项。审计原始响应、请求参数、候选及正文结果保存于 data/discovery/hk_completion/sfc-2025-audit.json。这是一次有边界的历史补查，不是 SFC 全站完整性证明，也不是新增历史自动发现能力。

当前目录为 67 条（30 PDF、37 HTML）、1,550 个段落。新通函固定链接已接入后续刷新；重复保存为 reused。条例正文、宪报及系统性修订关系审计仍未完成。

Final verification: 239 full-suite tests passed; current 67-document / 1550-chunk corpus validation passed. No live collection process or scheduled service left running. Source/code changes after the previous live run require a fresh run, not --resume. Earlier no-op run timestamp was corrected from preserved per-stage timestamps with an audit annotation.


## 已审核的文件关系（2026-11-21）

现有 68 条资料（31 PDF、37 HTML）、1,553 个段落。新增 2024-02-20 HKMA Provision of Custodial Services for Digital Assets，作为被后续通函明确取代的历史原文。原旧域名链接跳转到已验证的官方 BRDR 地址，不放宽任意跨域抓取。

`config/hk_stablecoin_relationships.json` 保存人工核对的四条原文陈述：2026 托管通函取代 2024 通函、银行稳定币活动采用注册机构相同标准、HKMA 与 SFC 同日配套指引，以及 2025 通函补充 2023 联合通函。前三条 source/target 原文和证据均已定位；第四条目标来源返回 SFC 维护页，状态为 target_not_collected，不当成已验证关系。

每次导出检查来源及目标原文哈希、审核哈希和证据句。原文变化时转为 requires_review；损坏文件或缺失证据不标为验证通过。关系输出在 `data/exports/hk_stablecoins/relationships.json`；documents.jsonl 包含 relationship_evidence，chunks.jsonl 包含 relationship_evidence_ids。下游 agent 必须检查 status 和 applies_to，不得把整个历史文档默认当现行要求。现有 legal_status 仍为 not_assessed：这是有证据的文件关系，不是自动法律效力判断，也不是全量修订审计。

DoJ 官方 XML 归档的 ETag 仍与此前一致（最后修改 2026-11-16）；没有观察到修正版本，Cap656 身份冲突文件继续隔离。SFC23EC67维护页未入库。相关关系/导出/覆盖测试14项通过。
