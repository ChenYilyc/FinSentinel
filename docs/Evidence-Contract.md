# 公告证据与行情快照 v1

这份约定用于 [双人协作任务 01](FinSentinel-Team-Playbook.md)。A 根据下面两份 JSON 开发报告和评测，B 用同一约定验收 PDF 解析器和行情读取器。两个输入均为合成测试样例。

## Agent 报告中的行业压力情景

在 Filing research 选择 AMD，使用示例持仓和默认跌幅 8%，运行本地分析。半导体持仓为 42,000 美元，组合总值为 100,000 美元。报告应显示情景损失 3,360 美元，占组合 3.36%。把跌幅改为 25% 后重新运行，结果应为 10,500 美元和 10.50%。

研究面板的跌幅独立于首页看板，作用于所查询公司所属行业的全部持仓。计算采用报告标明的同一份行情快照，保持持仓数量及其他行业价格不变。公司已计入行业市值一次。报告接口和允许查询持仓的问答接口接受整数字段 `industry_decline_pct`（0 到 100，默认 8）。问答恢复时沿用原始跌幅。纯公告请求应省略此字段。

工具结果 `industry_scenario` 中的 `loss_usd` 为损失金额，`loss_pct_of_portfolio` 的分母为冲击前组合总值。行业内缺价且跌幅大于零时，两项均为 `null`。仅行业外缺价时，金额仍可计算，占比为 `null`。跌幅为零时金额为零，占比仍按分母是否可用返回。行业无持仓时损失为零；查询 CASH 本身时不生成行业情景。

## 公告证据

### AMD 公告与持仓联合验收

在项目根目录运行以下命令，使用已配置的模型、内置公告摘录和示例持仓发起一次 Live 研究。每次模型调用按供应商账户计费规则处理。

```powershell
python -m examples.verify_amd_live
```

程序会检查模型是否给出正文、两类工具是否均返回证据、财季和逐字引文是否匹配，以及工具返回的持仓与压力损失是否符合样例。任一检查失败时退出码为 1。取得运行结果后，程序在当前目录保存带运行 ID 的脱敏回执，同时在终端显示模型正文供人工核对。请核对正文中的 92 亿美元营收、AMD 与 NVDA 两个持仓、42,000 美元行业市值及 8% 情景下的 3,360 美元损失（占组合 3.36%）。检查模型是否将公告发布日期与持仓估值日期分别表述。

2026-11-20 的[本机 HTTP 回执](../examples/contracts/amd-local-http.json)记录了 8% 和 25% 两次独立请求，均按预期返回，两次损失分别为 3,360 和 10,500 美元。回执中的 `engine=local` 和 `model_rounds=0` 标明执行路径。当前环境到 DeepSeek 的网络访问受限，真实模型回执待补。浏览器渲染进程启动异常，页面改值仍待点验。

[完整工具响应](../examples/contracts/filing-evidence.json) 可以从 [原始 TXT](../examples/filing-demo.txt) 重现：用 NVDA、2025-Q3、发布日期与检索截止日 2025-11-12、关键词 `125` 调用 `search_filings`，唯一命中应在第 3 行。

| 字段 | 约定 |
|---|---|
| `status`、`total_matches`、`documents` | 命中为 `found`，无匹配为 `no_matching_evidence`、0、空数组。计数包含所有命中，一次最多返回前 5 条。 |
| `corpus` | 数据集说明，供人阅读。上传文件的公司、财季与发布日期由导入者提供。 |
| `ticker`、`quarter`、`published` | 股票代码、形如 `2025-Q3` 的财政期间、公告对外发布日期（YYYY-MM-DD）。仅在发布日期不晚于截止日时返回。 |
| `excerpt`、`url` | 可逐字核对的单行摘录及其唯一定位符，均必填。内置公告使用原始 HTTPS 链接。引文核对只接受本次工具结果中的定位符和摘录。 |
| `source`、`line` | 上传 TXT 使用 `uploaded_text` 与从 1 开始的物理行号。空行也占行号。定位符沿用 `#filing-{规范化文本的 SHA-256}-L{line}`。内置公告可以省略这两个字段。 |

**给 PDF 解析器的交接。** 对可读片段沿用必填字段，增加 `source: uploaded_pdf`、`page`（从 1 开始的物理页）、`document_version`（原始 PDF 字节的 SHA-256 小写十六进制）。每页按稳定阅读顺序从 1 给可引用片段编号，定位符用 `#filing-{document_version}-P{page}-S{片段序号}`。例如第 2 页两条不同数据分别用后缀 `-P2-S1` 和 `-P2-S2`。PDF 省略 `line`。不可读页由解析器记录页码和 `needs_review`，检索层只收可引用片段。整份文档不可读时，解析器仍需报告解析状态。

**报告端验收。** 在 Filing research 选择[片段 JSON](../examples/contracts/filing-pages-demo.json)，然后选择配套的[两页合成 PDF](../examples/contracts/filing-pages-demo.pdf)。在 Local 模式输入关键词 `125`，将公告截止日设为 2025-11-12，运行后应命中第 2 页第 1 段。第 2 页第 2 段是现金数据。页面先校对所选 PDF 的 SHA-256，再提供指向对应物理页的链接，实际跳页由浏览器的 PDF 阅读器处理。单独导入 JSON 时仍可查看页号、段号和摘录。原始 PDF 只在浏览器本地预览。

`POST /api/agent/report` 和 `/api/agent/ask` 的 `filing` 均可直接使用该 JSON，即含 `documents` 数组的对象。每次导入同一份公告的 1–1000 个片段，每段至多 1200 个字符，保持单行并去除首尾空白。浏览器接受至多 512 KiB 的片段 JSON 和 32 MiB 的可选预览 PDF。校验覆盖定位符、元数据一致性与引用是否来自本次检索。片段文字和物理页是否确实对应原件，仍由解析器与原页抽查验收。

## 日收盘行情

[完整行情快照](../examples/contracts/market-snapshot.json) 表示同一来源、同一交易日、同一可用时点的一批价格。[MarketSnapshot](../backend/market_contract.py) 提供可复用的校验入口 `MarketSnapshot.model_validate_json(raw_json)`。

| 字段 | 约定 |
|---|---|
| `source` | 必填、非空的来源标识。此样例为 `synthetic-contract-fixture`。 |
| `trading_date`、`as_of` | 前者是交易所本地的交易日（YYYY-MM-DD）；后者是这版快照可供分析使用的时间（ISO 8601，含时区）。回放只能使用截至决策时刻已可用的版本。 |
| `currency`、`quotes` | v1 使用 USD；每条记录代表一只请求的股票或 ETF，每个代码只出现一次。读取器应显式列出请求到的每个代码，包括缺价项。 |
| `status`、`close` | `available` 配有限正数，单位是美元/股，口径为该交易日的未复权收盘价；`missing` 配 JSON `null`。`close` 在两种状态下都必须存在。 |

例如样例里 AMD 的价格为 120 美元，NVDA 缺价。持有 100 股 AMD 时，可以计算这笔持仓的市值为 12,000 美元。如果同时持有 NVDA，半导体持仓总额就无法确定，AMD 的行业内占比也应显示“待补行情”。如果 NVDA 的持仓数量是零，其缺价不会妨碍其他持仓估值。现有风险页使用独立、完整的模拟价；研究页可导入该样例验证缺价报告。

## 验收

### 报告联调与四种回放

在研究页 `/#agent` 选择 Local，使用默认 AMD、2025-Q3 与示例持仓。所有案例均可离线运行。

| 情形 | 输入 | 页面预期 |
|---|---|---|
| 直接相关 | 默认输入 | 显示发行人被直接持有，AMD 市值 12,000 美元，行业内占比 28.57%，公告链接可打开 |
| 无直接持仓 | 上传只有 NVDA 的持仓 CSV，查询 AMD 公告 | 仍可查看公告，报告说明未直接持有 AMD；与 NVDA 同行业不等于持有 AMD |
| 证据冲突 | 导入 [冲突文本](../examples/filing-conflict.txt)，填写 AMD、2025-Q3、2025-11-04，检索词留空 | 两个不同金额对应同一财季的本季营收，提示待复核，可分别打开第 2、3 行 |
| 缺价 | 恢复示例公告和持仓，在 Price snapshot 选择 [行情样例](../examples/contracts/market-snapshot.json) | AMD 市值仍为 12,000 美元；NVDA 缺价导致行业内占比待补。界面同时列出其他缺价持仓、行情来源和可用时间 |

范围：关联性按发行人是否直接持有判断。冲突规则检查本次已取回的同公司、同财季、符合英文模板 `Revenue for the quarter was USD … million/billion.` 的单行摘录，先统一单位再比较。上一年、比较季度、分部及其他表述需要另行审阅。报告不从财报推断股价涨跌。Live 运行如果工具返回缺价或检出冲突，页面保留可复算的指标和证据，隐藏模型自由文本。公告筛选截止日与持仓估值日分别展示。

重跑四类报告评测与边界用例：`python -m unittest discover -s tests -p test_report_evals.py -v`。Live 回归用固定模型回复调用真实本地工具，不消耗模型额度。

### Live 工具权限和运行回执

在研究页选 Live，默认权限为 **Filing search only**。询问 AMD 的 2025-Q3 营收，完成后点 **Download run receipt**。要回答持仓占比，在 **Allowed tools** 中主动选择 **Filing search and portfolio exposure**。本地固定工作流仍执行两项工具。

| 检查位置 | 预期 |
|---|---|
| 浏览器 → API | 只查公告的请求仅传问题、权限和可选公告。已经选过的持仓 CSV 和行情快照也会省略。直接向这个模式提交持仓字段，API 返回 422。 |
| 后端 → 模型 | 只向模型声明此次可用的工具。即使回复中出现对持仓工具的请求，执行器也会先返回 `permission_denied`，不会进入估值函数。 |
| 运行回执 | JSON 包含版本、本次运行 ID、UTC 完成时间、总耗时、执行方式、权限、结局、模型轮数，以及按顺序排列的工具名和状态。Local 的模型轮数为 0。拒绝操作也会记录，未知工具名统一显示为 `unknown_tool`。 |
| 模型连接中断 | 已有工具结果且还剩模型轮数时，状态为 `provider_interrupted`。点击 **Resume from saved evidence** 会从该次运行继续；点击 **Run analysis** 会开始新运行。首次模型请求即失败时返回 HTTP 502。 |

**复盘。** `backend/agent_tools.py` 的 `definitions(scope)` 决定模型能看到的工具，`execute(..., scope=...)` 决定后端实际执行的工具。权限由本次请求传入，检索结果或模型生成的工具参数无法改写它。它适用于单用户工作台；多账户文件归属和访问隔离属于后续阶段。已有 API 客户端省略 `scope` 时沿用原组合模式，新客户端建议显式传入。

运行 `python -m unittest discover -s tests -p test_live_scope.py -v` 复现权限、导出与部分失败用例。运行 `python -m backend.agent_lab --receipt-only` 可以离线查看回执。配置真实模型后，使用页面或下面的 PowerShell 命令留存一次真实调用的回执。命令只查询公共公告，产生正常的模型调用费用。

```powershell
python -m backend.agent_lab --scope filings_only --ask "What revenue did AMD report for Q3 2025? Cite the filing." --receipt-only | Out-File -Encoding utf8 live-receipt.json
```

完整 Tool trace 保留工具参数和结果，可能含持仓；对外复盘请使用下载的回执。回执供核对运行过程，引用原文和金额仍须在本地报告单独验收。

在项目根目录运行 `python -m unittest discover -s tests -p test_evidence_contract.py -v`。检查真实 TXT 工具输出与样例一致、原文校验通过，以及行情拒绝缺价填零、重复代码和无时区时间。改契约时同时提交样例与测试，由另一位开发者复核。

### 从已取得的证据恢复

恢复入口为 `POST /api/agent/resume`，请求体仅含 `token`。服务端保留原始问题、消息历史（含工具调用 ID 和结果）、工具轨迹、权限以及这次分析使用的持仓和文档输入。恢复后的模型继续接收原工具结果。如果模型提出新的工具请求，执行器照常检查权限并计入原有预算。

| 故障或操作 | 预期 |
|---|---|
| 第 1 轮取到公告，第 2 轮连接失败，第 3 轮恢复成功 | 同一运行 ID、3 次模型尝试、1 次恢复、1 条检索轨迹。失败尝试也占一轮。回执耗时包含等待用户恢复的时间。 |
| 同一恢复请求并发到达，或完成响应在网络中丢失 | 在途请求返回 409；完成后用同一个令牌重试，在缓存有效期间返回相同结果。 |
| 恢复时试图改权限、换模型 | 额外请求字段返回 422。服务端模型配置与原运行不匹配时返回 409，恢复原配置后可再试。 |
| 恢复后再次断线或超过预算 | 仍有剩余轮数可获得新的恢复令牌。整次运行最多 4 次模型尝试、6 次工具请求。预算用尽时保留已取得的证据。 |

当前实现用于单进程本地工作台。令牌代表继续该次运行的权限，留在当前页面，脱敏回执只保存运行 ID。服务端内存最多缓存 64 项，令牌有效期为 15 分钟；容量满时可提前淘汰未执行的条目。服务重启、令牌过期或被淘汰后返回 410。刷新页面会丢失当前页面的令牌。跨服务重启和跨实例恢复留给持久化阶段。

运行 `python -m unittest discover -s tests -p test_resume.py -v` 复现恢复、并发和预算用例。[本机 HTTP 故障演练回执](../examples/contracts/resume-receipts.json) 使用模拟模型传输和真实公告工具，包含中断和恢复两份回执。
