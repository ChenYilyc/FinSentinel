# 阶段复盘　把公告和持仓工具接入网页

## 运行与展示

在项目根目录执行 `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`，打开 `http://127.0.0.1:8000/#agent`。前端已经构建。选 AMD、2025-Q3，保留默认公告截止日，点 Run analysis。来源链接、三种权重的分子分母，以及可展开的 Tool trace 会一起出现。要分析另一份持仓，先在同页 Import holdings 上传 CSV，再运行分析。

默认 Local 模式固定执行两次只读查询，可在无模型密钥时完整演示。配置服务端环境变量 OPENAI_API_KEY 并重启后可选 Live 模式；在此模式点击运行会将问题及已调用工具的结果发送给提供商，可能产生 API 费用。可用 FINSENTINEL_MODEL 指定支持工具调用的型号。页面分开呈现程序计算的证据和模型生成的草稿。

## 用真实请求理解实现

1. **浏览器提交上下文。** `frontend/src/AgentPanel.tsx::submit` 将当前成功导入的 CSV 和查询条件提交到 `POST /api/agent/report` 或 `/api/agent/ask`。更换持仓时，旧报告随组件重新挂载清空。单用户本地模式使用本次请求携带的持仓。
2. **API 确定执行边界。** `backend/agent_api.py::report` 校验 CSV，将它作为程序参数传入 `replay`。Local 模式按选项构造固定步骤。Live 模式的 `ask` 将自然语言问题交给 `backend/agent_lab.py::run_agent`。循环取得模型返回的工具名与参数，用 `execute` 检查名称和 Schema，再将结果用原始 tool_call_id 发回模型。服务端每次请求最多四轮模型调用、六次工具调用。
3. **工具计算结果。** `backend/agent_tools.py::search_filings` 同时检查公司、财季与发布日期。默认查询返回 AMD 2025-Q3 的公告摘录，发布日期为 2025-11-04。随后 `get_portfolio_exposure` 用本次持仓调用风险模块。示例的公司市值是 12,000 美元，行业市值 42,000 美元，组合总市值 100,000 美元。
4. **前端展示依据。** `frontend/src/AgentPanel.tsx::Evidence` 从结构化工具结果读取金额和百分比。公司的组合权重为 12%，行业的组合权重为 42%，公司在行业内部占 28.57%。最后一项取 `direct_share_of_industry_pct`。行业市值为零时该值为 JSON null，页面显示 N/A。行业有持仓但没有该公司时，该值为 0%。

公告截止日只限制可检索的公告；持仓估值独立标注模拟价格日期。把公告截止日改为 2025-10-31，Q3 公告查询会返回 no_matching_evidence，持仓工具依然能返回模拟估值。这条结果说明哪些数据可用，也防止用此后才发表的公告回答此前的问题。

## 已验证的范围

在项目根目录运行 `python -m unittest discover -s tests -p test_agent_report.py -v` 可重跑本阶段的 7 项测试，覆盖两种分母、已导入持仓、公告发布时间、零分母、请求校验、模型不可用及模拟多轮调用。整个项目共 26 项测试通过。另以进程内 ASGI 请求验证了报告接口和错误状态，React 类型检查与生产构建通过。

本阶段使用已核实的两段 AMD 摘录和模拟价格。当前环境没有配置真实模型密钥，模型自主选工具的实网表现仍待验证；本机回环端口连接受限，未执行浏览器端到端点击。本阶段不包含通用 PDF 上传或语义检索。
## 配置 DeepSeek

在项目根目录的 `.env` 文件中填写 `DEEPSEEK_API_KEY`，模型默认使用 `deepseek-flash`。全新解压的项目可将 `.env.example` 复制为 `.env`。此文件只保存在本机。配置完成后重新启动后端，刷新 `/#agent` 并选择 Live。可访问 `/api/agent/settings` 确认 provider 为 deepseek 且 live_available 为 true。此状态表示已读取密钥。若使用 Docker，运行 `docker compose up -d --build` 应用配置。

## 财报引用核对与运行模式验收

同一张 AMD 证据卡可以来自 Local 或 Live。查看本次结果顶部的运行模式。Live 会显示实际请求使用的提供方、模型名称和工具调用次数。展开 Tool trace 可以看到每次请求的工具、参数和结果。

用 Live 提问「截至 2025-11-04，AMD 2025 年第三季度营收是多少？请引用原文」。展开 search_filings，核对公司、财季、截止日和返回的摘录。Filing quote check 显示 Exact quote matched 时，表示后端在本次工具结果中找到了相同的公司、财季、发布日期、URL 和英文摘录。Model draft 中的翻译、推断和持仓解释仍需单独审阅。

**代码复盘。** 打开 `backend/filing_citations.py` 的 `check_filing_quotes`。它从本次 trace 建立索引，再逐条核对模型提交的引文。把 Q3 引文的金额从 $9.2 billion 改成 $92 billion，URL 保持正确，返回 `quote_mismatch`。把检索截止日改成 2025-11-03，并模拟模型仍给出正确的 Q3 原文，此时工具没有返回这份公告，校验返回 `source_not_retrieved`。该检查依据模型实际调用的参数；验收时还要核对参数是否符合用户问题。

在项目根目录运行 `python -m unittest discover -s tests -p test_filing_citations.py -v` 可重复这两种故障及正常路径。测试通过替身返回模型消息，两轮消息之间执行真实的本地检索工具。

