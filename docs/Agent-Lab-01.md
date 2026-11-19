# 第一轮　检查金融 Agent 的工具调用

本轮只用示例持仓和两段核对过的 AMD 公告摘录。固定回放在本地执行两个只读函数，复用原有风险计算。交互模式让模型按提问选择工具，程序验证参数并回传结果，输出包含工具轨迹和模型草稿。所有估值都基于 2026-10-30 的模拟价格。公告检索日期按自然日日终解释，支持范围为已收录的两个财季。

在项目根目录的 PowerShell 运行：

```powershell
python -m backend.agent_lab
python -m unittest discover -s tests -p test_agent_lab.py -v
```

独立练习包需要 Python 3.11–3.13 和 Pydantic 2。在空环境可先运行 `python -m pip install pydantic==2.11.7`。在已有项目环境可直接运行。固定回放不需要 API 密钥。输出的 `trace` 依次列出调用的工具、参数和实际结果。

已在本机配置有效的 `OPENAI_API_KEY` 后，可自选执行下列命令。交互模式使用 Chat Completions，将输入的问题与所用工具的结果发送给模型提供商，按账户实际用量计费。默认使用 gpt-4.1-mini，可用 `FINSENTINEL_MODEL` 指定账户可用且支持工具调用的型号。

```powershell
python -m backend.agent_lab --ask "AMD 2025 年第三季度公布了多少营收？它在我的示例持仓中占多少？给出来源和估值日期。"
```

**读代码的顺序**　先看 `backend/agent_tools.py` 中两种权重分别取自哪里，再看 `backend/agent_lab.py` 中工具返回值如何对应到模型发出的调用 ID。最后在 `tests/test_agent_lab.py` 找一个可以反驳错误实现的例子。

**检查题**　某份报告写道：“AMD 占 12%，半导体行业占 42%，两项相加，组合共有 54% 的资金暴露在 AMD 及其所在行业。”如果你负责批准报告，请说明你的判断、要核查的两组持仓，以及你会补的一条测试。本轮先提交你的思路，再对照调用记录讨论。

公告依据：[AMD 2025 Q2](https://ir.amd.com/financial-information/sec-filings/content/0000002488-25-000106/q22025991.htm) · [AMD 2025 Q3](https://ir.amd.com/news-events/press-releases/detail/1265/amd-reports-third-quarter-2025-financial-results)
