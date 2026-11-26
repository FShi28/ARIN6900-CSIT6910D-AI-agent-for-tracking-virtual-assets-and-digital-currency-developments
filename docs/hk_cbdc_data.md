# 香港 CBDC 数据与续接说明

最新交付状态（2026-11-26）：66 份资料 / 1,158 片段；数据验收通过，在线刷新部分失败（7 份历史 PDF 超时，旧快照保留）。详见 `docs/hk_cbdc_handoff.md`、`docs/hk_cbdc_inventory.md`。运行 `python scripts/validate_hk_cbdc.py` 重验；综合状态仍会提示刷新问题。以下历史阶段数字仅供续接审计。

范围：香港 CBDC，以及香港参与的跨境 CBDC 项目。保持与香港 stablecoin 数据集独立。

## 当前资料结构

截至 2026-11-26，本地 66 份资料、1,158 个引用片段：HKMA 48、BIS 13、Charltons 1、香港政府新闻公报 3、Linklaters 1；19 PDF、47 HTML。这是已收集的文件数量，不是香港资料总量。BIS 是教授推荐的研究来源，Charltons、Linklaters 是辅助法律解读。当前只扩充 CBDC，代币化资产产品及参与机构名单暂缓。

项目包括 e-HKD/e-HKD+、Inthanon-LionRock/mBridge、Ensemble/EnsembleTX、Aurum、Sela、香港跨境 e-CNY 试点。Aurum/Sela 的国际合作研究不等于已上线跨境支付系统；e-CNY 也不等于香港发行的 CBDC。项目分类、货币、牵头机构、应用范围及历史阶段证据见 `config/hk_cbdc_projects.json`。

文件中的项目、地区、资产类型字段表示正文提及，不能据此把观察员当成正式参与方，或把代币化存款等同于央行货币。项目阶段未自动推断；14 条人工选定的阶段/政策/使用边界陈述绑定原文及引用片段，来源变化后需复核。未知法律效力保持 `not_assessed`。

## 运行与导出

在项目根目录运行：

```powershell
python scripts/collect_hk_cbdc.py
python scripts/collect_hk_cbdc.py --status
python scripts/collect_hk_cbdc.py --discover-only
python scripts/collect_hk_cbdc.py --export-only
python scripts/check_hk_cbdc_questions.py
```

完整运行刷新固定链接、扫描新文章、验证并导出。发现队列和每份成功文件立即落盘；中断后重新运行复用稳定 URL 身份，不重复增加文件。`--discover-only` 继续候选队列，不刷新所有旧文件。当前 CLI 没有按阶段跳过的 `--resume` 参数。

导出位于 `data/exports/hk_cbdc/`：

- `documents.jsonl`、`chunks.jsonl`：原文元数据、完整抽取文字分块及页码引用。
- `inventory.md`：所有文件的标题、类型、发布方、日期、项目和原文链接。
- `projects.json`、`evidence.json`：项目说明与审核过的历史证据。
- `summary.json`、`validation.json`：数量及原文哈希、引用检查。

原文在 `data/raw/`，共享资料快照在 `data/ingestion/research/`，历史版本在 `research_versions/`。现有应用的 Research Library 读取共享资料库，可用 CBDC 主题筛选；没有修改队友的 chatbot 或主监管图表。

## 自动更新的准确范围

66 个已收录链接均接入固定链接刷新。新文章发现有两个发布机构、五个入口：HKMA CBDC 专题页、HKMA CBDC 新闻列表、BIS mBridge、Aurum 2.0 和 Sela 项目页。通过正文和日期验证的 HTML 可以自动入库；新 PDF 先进入审核队列。CBDC 的 Charltons、Linklaters 和香港政府新闻公报当前仅支持已有文件刷新，不能套用 stablecoin 的发现能力。

这些入口不是全站历史搜索；HKMA 新闻入口当前只读取可见的最近一页。BIS 新项目如果未被现有入口链接，也不会自动发现。既有 Streamlit 采集线程按配置每 24 小时运行，必须保持主机和采集进程运行。没有安装独立系统服务；`enabled` 设置和旧成功记录均不能证明进程活跃。

日期不能由 URL、PDF 创建时间或抓取时间推测。12 份报告/简介的发布日期从已核实官方说明补齐，保留月精度，不补造具体日。四个持续更新项目页没有单一发布日期，另有一份季度文章的发布日期待核实。

## 已知缺口与下一步

1. e-HKD 第一阶段 PDF 限制文字提取，未收为全文；不能因已有第二阶段报告/项目概述而声称第一阶段全文完整。
2. HKMA 页面指向的两个旧 BIS PDF URL 实际跳转到 HTML，已采用核实的新官方 PDF URL，不重复计数。
3. 跨境碳信用 DvP、Ensemble 参与机构及代币化产品附件按用户 CBDC-only 要求暂缓，不作为本轮必补缺口。
4. 早期 LionRock 简介及三篇历史演讲已收录；e-HKD 行业论坛名单待审。项目匹配失败不等于文章没有 CBDC 内容。
5. 尚未证明历史发布完整；继续审计历史新闻、研究报告附件及教授推荐渠道。新增来源必须先验证页面和采集规则。

机器断点：`data/ingestion/hk_cbdc/work_checkpoint.json`；最近运行：`run_checkpoint.json`；候选：`candidates.json`；PDF 审核记录：`data/discovery/hk_cbdc/pdf_review.json`。继续前先读取这些文件。运行数据未随 Git 自动共享。


## 2026-11-24 较早刷新记录（56 份阶段）

上次完整刷新因进程中断停止，已归档其断点，不将旧 running 状态当作成功。25 份成功快照保留，剩余 31 份补跑全部成功；五个发现入口扫描完成，本轮新增文件 0。最终仍为 56 份文件 / 1,117 个片段，原文与引用检查通过，11 条审核证据有效。11 份报告日期已补齐并验证，未知发布日期剩余 5 份（四个持续更新项目页及一份季度文章）。

HKMA 部分网页原始字节变化，但六条审核证据对应的抽取正文与旧版一致；复核前后哈希与理由保存在 `data/ingestion/hk_cbdc/evidence_refresh_review.json`。日期证据保留审核时原始文件，并在最新说明中重查日期语句，避免导航等变化无故使日期失效；目标报告内容变化仍要求复核。

CBDC 文件下载增加 90 秒流式下载预算，在收到数据块或重试前检查，另保留 30 秒单次网络等待超时；不承诺精确的 90 秒墙钟截止。超时保留上次成功快照，下一次运行可重试。此设置不改变 stablecoin 的默认下载策略。

测试：本轮前全套 254 项通过；下载预算及相关采集回归 92 项通过；最后日期证据与导出检查 12 项通过。香港 stablecoin 的 68 份文件 / 1,553 个片段保持不变。

接续入口：`work_checkpoint.json` 标为 `initial_dataset_verified`。剩余内容属于覆盖扩充和已注明的文件缺口，不等于没有完成采集代码。数据位于本机，CBDC 未推送 GitHub，也未启动常驻采集服务。

## 2026-11-24 CBDC 专项补充与问题验收（59 份阶段）

新增第一阶段 e-HKD 官方结果新闻公报、Sela 启动公报、2019 年 11 月 LionRock-Inthanon 简介，共 59 份 / 1,124 片段。三份重新在线刷新均复用已有记录；原文、引用和 14 条证据检查通过，相关测试 15 项通过。第一阶段完整 PDF 再次核实仍限制提取；新增的是结果说明，不是完整报告。审核见 `phase1_permission_recheck.json`。

`config/hk_cbdc_questions.json` 定义 8 个问题及使用边界；运行检查可重新生成 `data/exports/hk_cbdc/question_acceptance.md` 和 JSON。6 个问题有对应审核证据，2 个明确缺证（第一阶段全文、确定的零售 e-HKD 公众发行日期）。这是资料可用性检查，不代表 chatbot 已成功回答。

`data/exports/hk_cbdc/keyword_probe.json` 保留中英文问题、命中文本引用和评分。复现简单空格分词与子串计数、仅搜 CBDC 子集的前 3 片段时，中英文各仅 1/6 个问题找齐指定来源。指标只比对人工选定的原文 URL；其他相关报告或等价证据未计入，因此不能称作答案准确率。检索排序及中文语义匹配需要接入方另外验收，本轮未修改 chatbot。

当前断点状态 `cbdc_data_and_question_evidence_verified`。继续优先复核历史 CBDC 演讲和相关教授渠道；不扩充代币化产品。数量、已完成事项、限制及下一步均保存在 `data/ingestion/hk_cbdc/work_checkpoint.json`。CBDC 仍为本地改动，未推送。

## 2026-11-24 历史与教授渠道补充（当前 64 份）

新增 HKMA 2019-11-06、2020-11-02、2023-08-24 三篇演讲、政府 2022-01-26 的 LCQ15 CBDC 答复，以及 Linklaters 2025-11-12 亚太金融科技通讯中的 e-HKD 段落。

三篇演讲有明确 CBDC 研究或互操作性背景，但未命名已配置项目，因此 `projects=[]`，不补造项目名称。人工 `context_scope_review` 记录理由及至少两段原文锚点；验证器检查 HKMA 来源、演讲类型、CBDC 文字和锚点仍存在。自动发现规则未放宽。清单注明「CBDC 历史背景」。

Linklaters 保留完整原始 HTML，但只索引 e-HKD 段落；`text_scope` 和 `scope_note` 说明这是通讯节选、辅助解读，不能视为香港法规全文。已配置固定链接刷新，未实现该渠道新文章发现。

IMF 2022 年亚太 CBDC 调研已核实官方落地页，但本机 PDF 请求返回 403。未绕过限制、未计入 64 份；缺口清单保留标题、落地页和错误。Ashurst 的本轮搜索未取得可核验的相关官网正文，这不代表该渠道没有 CBDC 资料，也不算已接入。

5 份新资料重复在线获取全部成功；4 份原始 HTML 字节变化导致保存新版本，但抽取文字全部一致，文件身份数仍为 64。对照记录：`data/ingestion/hk_cbdc/history_repeat_comparison_20261124.json`。相关测试 16 项通过；导出完整性与 14 条证据检查通过；问题验收仍为 6 个有证据、2 个明确缺证。先前关键词探测对应 59 份阶段，未冒充本轮 64 份的测试结果。

继续从 `work_checkpoint.json` 和 `config/hk_cbdc_gaps.json` 读取；数据仍仅在本机，未推送 CBDC，也未启动常驻服务。
