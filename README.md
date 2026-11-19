# FinSentinel

公告研究页支持导入 UTF-8 文本摘录，按发布时间和关键词检索，点击证据可打开原文件内容并高亮对应行。[导入演示和代码复盘](docs/Filing-Text-Stage.md)

公告与持仓分析页面位于 `/#agent`。先按下文启动本地服务，再打开 [阶段复盘](docs/Agent-Research-Stage.md) 查看运行方法、工具调用记录和测试结果。

## SPY 五交易日预测 PoC

打开项目根目录的 `FinSentinel-SPY-PoC.html` 查看离线演示，或启动本地 API 后访问 `http://127.0.0.1:8000/#forecast`。实验使用 2,513 个真实历史交易日，包含三个滚动测试窗口、校准图和逐日导出。数据口径、模型表现及重跑命令见 [实验记录](docs/SPY-PoC-Results.md)。新环境运行完整测试前请安装研究依赖 `uv sync --extra research --no-install-project`。

FinSentinel 的第一个可运行模块是持仓风险面板。导入美元多头持仓 CSV 后，FastAPI 用固定的模拟收盘价计算组合市值、行业权重、情景损失和历史风险，React 页面展示结果。所有计算都在本地完成，示例无需账户或 API 密钥。

## 启动面板

在项目根目录运行。当前工作区已装好依赖并构建前端，可直接启动。

```powershell
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

打开 [持仓风险面板](http://127.0.0.1:8000) 或 [FastAPI 接口文档](http://127.0.0.1:8000/docs)。Ctrl+C 停止服务。

在新环境中，准备 Python 3.11–3.13、uv 和 Node 22.12+，先构建前端，再启动后端。

```powershell
uv sync --no-install-project
npm --prefix frontend ci
npm --prefix frontend run build
uv run --no-sync python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

修改前端时，可在第二个终端运行 `npm --prefix frontend run dev`，访问 Vite 输出的地址。开发服务器会把 API 请求转给 8000 端口。修改后再次构建即可更新 FastAPI 提供的页面。

安装并启动 Docker Desktop 的 Linux 引擎后，也可以单独运行 `docker compose up --build`，访问相同地址。原生服务和容器共用 8000 端口，每次选择一种启动方式。

## 用模拟持仓验收

1. 打开面板，或点 **Import holdings** 上传 `examples/portfolio.csv`。默认组合有六项持仓，包括现金，总市值为 100,000 美元。
2. NVDA 的 200 股乘以 150 美元，AMD 的 100 股乘以 120 美元，合计 42,000 美元。半导体权重为 42%，超过默认 35% 阈值。把阈值改成 42 并点 **Apply scenario**，提醒数应变为零。
3. 保持其他价格不变，仅让半导体价格下跌 8%，压力损失应为 3,360 美元，占总市值 3.36%。改成 10%，损失应为 4,200 美元。
4. 展开 **Historical risk** 下的明细，核对六个模拟收盘日的组合市值。每日都按本次导入的相同数量估值，现金按每单位 1 美元计价。样例首日市值 98,100 美元，末日 100,000 美元，期间收益约 1.94%。日波动率取五个简单日收益率的样本标准差，最大回撤取历史峰值至其后低点的最大跌幅，以正数显示。该序列用于验证算法，无法代表真实持仓业绩。
5. 上传只含 `CASH,12000,USD` 的 CSV（保留表头）。总市值应为 12,000 美元，历史风险和情景损失都应为零。非法代码或币种会显示行号，并保留上一次成功的报告。

## 代码入口

| 文件 | 职责 |
|---|---|
| `examples/portfolio.csv` | UTF-8 示例持仓，字段为 ticker、quantity、currency，可从页面下载 |
| `examples/universe.csv`、`examples/prior_closes.csv` | 支持的十只股票及现金、行业、末日和前五日的模拟价格 |
| `backend/risk.py` | CSV 校验、重复代码合并、十进制估值、行业压力测试和历史风险计算 |
| `backend/main.py` | FastAPI 的样例、CSV 下载和持仓分析接口 |
| `frontend/src/main.tsx`、`frontend/src/HistoryPanel.tsx` | 导入和提交情景参数、呈现分析结果及逐日明细 |
| `tests/test_risk.py` | 可手算的参考组合与输入边界用例 |

在项目根目录运行 `python -m unittest discover -s tests -v` 复核计算，运行 `npm --prefix frontend run build` 检查 TypeScript 并构建页面。
