# 公告证据与行情快照 v1

这份约定用于 [双人协作任务 01](FinSentinel-Team-Playbook.md)。A 根据下面两份 JSON 开发报告和评测，B 用同一约定验收 PDF 解析器和行情读取器。两个输入均为合成测试样例。

## 公告证据

[完整工具响应](../examples/contracts/filing-evidence.json) 可以从 [原始 TXT](../examples/filing-demo.txt) 重现：用 NVDA、2025-Q3、发布日期与检索截止日 2025-11-12、关键词 `125` 调用 `search_filings`，唯一命中应在第 3 行。

| 字段 | 约定 |
|---|---|
| `status`、`total_matches`、`documents` | 命中为 `found`，无匹配为 `no_matching_evidence`、0、空数组。计数包含所有命中，一次最多返回前 5 条。 |
| `corpus` | 数据集说明，供人阅读。上传文件的公司、财季与发布日期由导入者提供。 |
| `ticker`、`quarter`、`published` | 股票代码、形如 `2025-Q3` 的财政期间、公告对外发布日期（YYYY-MM-DD）。仅在发布日期不晚于截止日时返回。 |
| `excerpt`、`url` | 可逐字核对的单行摘录及其唯一定位符，均必填。内置公告使用原始 HTTPS 链接。引文核对只接受本次工具结果中的定位符和摘录。 |
| `source`、`line` | 上传 TXT 使用 `uploaded_text` 与从 1 开始的物理行号。空行也占行号。定位符沿用 `#filing-{规范化文本的 SHA-256}-L{line}`。内置公告可以省略这两个字段。 |

**给 PDF 解析器的交接。** 对可读片段沿用必填字段，增加 `source: uploaded_pdf`、`page`（从 1 开始的物理页）、`document_version`（原始 PDF 字节的 SHA-256 小写十六进制）。每页按稳定阅读顺序从 1 给可引用片段编号，定位符用 `#filing-{document_version}-P{page}-S{片段序号}`。例如第 2 页两条不同收入数据分别用后缀 `-P2-S1` 和 `-P2-S2`，模型可以分别引用。PDF 省略 `line`。不可读页由解析器记录页码和 `needs_review`，检索层只收可引用片段。若整份文档不可读，后续界面应读取解析状态提示用户。此处定义 B 的交付格式，实际 PDF 解析和打开原页由后续 PR 实现。

## 日收盘行情

[完整行情快照](../examples/contracts/market-snapshot.json) 表示同一来源、同一交易日、同一可用时点的一批价格。[MarketSnapshot](../backend/market_contract.py) 提供可复用的校验入口 `MarketSnapshot.model_validate_json(raw_json)`。

| 字段 | 约定 |
|---|---|
| `source` | 必填、非空的来源标识。此样例为 `synthetic-contract-fixture`。 |
| `trading_date`、`as_of` | 前者是交易所本地的交易日（YYYY-MM-DD）；后者是这版快照可供分析使用的时间（ISO 8601，含时区）。回放只能使用截至决策时刻已可用的版本。 |
| `currency`、`quotes` | v1 使用 USD；每条记录代表一只请求的股票或 ETF，每个代码只出现一次。读取器应显式列出请求到的每个代码，包括缺价项。 |
| `status`、`close` | `available` 配有限正数，单位是美元/股，口径为该交易日的未复权收盘价；`missing` 配 JSON `null`。`close` 在两种状态下都必须存在。 |

例如样例里 AMD 的价格为 120 美元，NVDA 缺价。持有 100 股 AMD 时，可以计算这笔持仓的市值为 12,000 美元。如果同时持有 NVDA，半导体持仓总额就无法确定，AMD 的行业内占比也应显示“待补行情”。如果 NVDA 的持仓数量是零，其缺价不会妨碍其他持仓估值。现有风险页使用独立、完整的模拟价；该样例供后续缺价评测使用。

## 验收

在项目根目录运行 `python -m unittest discover -s tests -p test_evidence_contract.py -v`。检查真实 TXT 工具输出与样例一致、原文校验通过，以及行情拒绝缺价填零、重复代码和无时区时间。改契约时同时提交样例与测试，由另一位开发者复核。
