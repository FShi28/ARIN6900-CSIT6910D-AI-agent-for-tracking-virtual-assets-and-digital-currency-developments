# 香港 CBDC 数据交接

范围限于香港 CBDC，以及香港参与的跨境 CBDC 研究与使用。包括 e-HKD、mBridge、Aurum、Sela、香港跨境 e-CNY，以及 Ensemble 的央行货币结算部分。不继续扩展其他代币化产品。

2026-11-26 验收：66 份资料、1,158 片段（19 PDF、47 HTML）。六个项目均有官方资料与审核证据；14 条陈述有效，6 个问题有证据，2 个明确缺证。全套 257 项测试通过，随后新增交付检查的相关 17 项测试通过。

数据验收 `data_status=passed`；在线运行 `refresh_status=partial_failure`，综合状态 `needs_review`。原有 64 个链接中 57 个刷新成功，7 个 PDF 超时保留旧版；五个发现入口成功运行，新增两份历史公告。来源配置已包含全部 66 个 URL。失败清单位于导出目录 `refresh_failures.json`。这批数据可用于 MVP 交接，但不能声称全部文件已于当天更新。

## 数据与运行

本机快照清单见 `docs/hk_cbdc_inventory.md`；数量、原文及引用完整性检查见 `data/exports/hk_cbdc/handoff_validation.json`。项目源配置是可迁移的，全文和运行数据不随 Git 自动共享。

```powershell
python -m pip install -r requirements-app.txt
python scripts/collect_hk_cbdc.py
python scripts/validate_hk_cbdc.py
python scripts/collect_hk_cbdc.py --status
```

已有本机数据可用 `--export-only` 重新导出；`--discover-only` 继续候选发现而不刷新旧文件。每份成功文件立即保存，中断后可重新执行；当前没有逐份跳过的 `--resume` 参数。完整采集与验收应串行运行，避免共享锁冲突。

## 给下游使用的数据

- `data/exports/hk_cbdc/documents.jsonl`：标题、发布方、日期、原文链接、来源性质、项目及范围说明。
- `data/exports/hk_cbdc/chunks.jsonl`：引用片段、文档身份、来源链接及物理 PDF 页码；网页没有虚构页码。
- `projects.json`、`evidence.json`：六个项目的说明和经过原文审核的历史陈述。
- `question_acceptance.json` / `.md`：支持的问题及明确不能回答的问题。
- `config/hk_cbdc_gaps.json`：未取得全文、替代链接、暂缓范围等记录。

需要现有精确快照时，应传递完整导出目录；需要在另一台电脑继续采集时，还需共享来源配置以及 `data/ingestion/research/`、`research_versions/`、`hk_cbdc/` 和引用的 `data/raw/` 文件。当前 CBDC 全文保存在共享 research JSON 快照中，不能只复制两个早期 SQLite 库就认为包含 CBDC。

重新抓取可能遇到网页变化和访问限制，因此从 Git 安装并运行不保证重建同一份历史快照。该交接说明不代表已经向 GitHub 推送或向队友传送数据。

## 与 stablecoin 的验收标准对照

| 项目 | CBDC 交付标准与边界 |
|---|---|
| 明确收集范围 | 六个相关项目有说明；CBDC、稳定币和代币化存款不混为一谈 |
| 官方与教授来源 | HKMA、政府为主要依据；BIS 研究及 Charltons、Linklaters 辅助解读；IMF 访问缺口单列 |
| 可引用全文 | 保留原文和片段；Linklaters 仅索引标明的 CBDC 段落；第一阶段 e-HKD 官方结果说明不冒充完整报告 |
| 固定链接刷新 | 所有已收录链接进入刷新配置；失败保留旧快照，不能将旧快照当成刷新成功 |
| 新文章发现 | HKMA、BIS 两个发布机构、五个入口；比 stablecoin 的六机构七入口窄；新 PDF 需审核 |
| 历史阶段与证据 | 人工证据绑定原文；页面变化要求复核；研究原型不等于已发行或已上线 |
| 重复采集与恢复 | URL 身份去重、版本保留、发现队列持久化、共享运行锁 |
| 数据验收 | 统一命令检查六项目、证据、问题、引用、来源配置及最近完整采集结果 |
| Chatbot 验收 | 不属于本轮数据交付；简单关键词检索存在已记录限制 |

## 已知缺口及停止条件

第一阶段 e-HKD 完整 PDF 提取受限；IMF 调研 PDF 下载返回 403；资料库未证明覆盖全部历史发布。未知日期保持未知，不从 URL 猜日期。相关历史资料可用于总结和比较，但不能据此给出公众零售发行的确定日期。

日常调度仍依赖运行中的 Streamlit 采集线程与电脑；没有安装常驻系统服务。成功的检查点不证明进程正在运行。

本轮停止标准是「所选范围可用于数据交接、引用、定期采集和续接，且验收通过、缺口明确」，而不是凑齐与 stablecoin 相同的文件数或宣称全覆盖。后续仅优先处理采集故障、来源实质更新和会影响核心问答的缺口。更多研究渠道、历史档案穷举、独立常驻部署作为后续增强。

续接首先读取 `data/ingestion/hk_cbdc/work_checkpoint.json`、本说明和 `docs/hk_cbdc_data.md`。
