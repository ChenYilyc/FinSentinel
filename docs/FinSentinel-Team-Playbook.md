# FinSentinel 双人开发与 GitHub 协作手册

2026-11-19 · 适用于当前本地 PoC · A 为项目负责人，B 为数据工程负责人。本手册记录当前进度和建议分工，长期验收口径沿用 [分阶段验收标准](FinSentinel-Acceptance-v1.md)。

## 1　两个人共同交付什么

**近期目标**：让面试官上传一份有出处的公司公告和一份示例持仓，问“这条公告与我的哪些持仓有关？”，看到 Agent 调用了哪些工具，点开一条证据，并用同一份价格快照复算风险。这个演示用时目标为 3–5 分钟。**长期目标**：接入有来源和时间戳的日频行情、支持多账户私有文档与持仓，在满足订阅规则时生成一条可追溯的站内提醒。SPY 五日预测保留为独立研究页，本轮排期冻结训练工作。

### 11 月 19 日进度

| 模块       | 已有证据                                                                      | 距离验收还差什么                                        |
| -------- | ------------------------------------------------------------------------- | ----------------------------------------------- |
| 持仓与风险    | CSV 导入、行业权重、压力损失和模拟历史风险可运行。样例总额 100,000 美元，AMD 12,000，半导体 42,000          | 估值仍用模拟价。第一阶段的本机容器与完整持仓交互验收记录待补                  |
| 公告与引用    | 两条内置 AMD 摘录；支持自选 UTF-8 文本、按截止日和关键词检索、按原始行定位、逐字核对引文                        | 上传元数据由人填写，文件随请求传递。PDF 页码、复杂表格、扫描页、持久索引和检索评测待做   |
| Agent    | Local 固定工作流与 Live 模型选工具均有入口；有调用预算、轨迹与引用核对；已接 DeepSeek/OpenAI 配置           | 本轮回归使用模拟模型响应。需保留一次真实模型轨迹，补证据冲突、授权边界、中断恢复及真实行情联调 |
| SPY 五日预测 | 3 个窗口、756 个样本外预测。准确率 62.17%，基线 62.04%；模型与基线 Brier 分别为 0.237027 和 0.235663 | 研究快照已可演示。实时前瞻记录待积累，本轮不以提高准确率为交付条件               |
| 监控与上线    | FastAPI、React、Dockerfile 和单服务 Compose 已有                                  | 账户隔离、持久化、后台任务、提醒去重和公网端到端演示待做                    |

本次在当前工作区重跑 **37 项测试，全部通过**；TypeScript 检查及 Vite 生产构建通过；Compose 配置校验通过。容器启动、真实模型调用与公网访问分别保留独立验收记录。此目录初查时尚未初始化 Git。

## 2　分工



| 负责人                 | 日常可独立修改                                                                                                                                               | 第一批交付和验收                                                                                  |
| ------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| **A · Agent、产品与集成** | `backend/agent_lab.py`、`agent_api.py`、`agent_tools.py`、`filing_citations.py`，研究页 `frontend/src/AgentPanel.tsx`，对应 Agent 测试                            | 用固定工具结果跑通相关、无关、证据冲突、缺价四种输入。报告显示来源、截至日期、引用和调用轨迹。冲突时补查或标记待核实，缺价时暂停受影响的计算。留一条经脱敏的真实 Live 轨迹  |
| **B · 文档、行情与风险数据**  | `backend/filing_text.py`、`risk.py`；新增解析器建议放 `backend/filings/`，行情适配器放 `backend/market_data/`；样例放 `examples/filings/`、`examples/market_data/`，各自新增测试文件 | 首先交付一份可读 PDF 的页码、原文和版本定位，以及无法提取文本的状态。随后提供样例与真实日线读取器，记录来源、币种、交易日和缺价状态。用两只股票和一只 ETF 各核三个交易日 |
| **A 集成，B 复核**       | `backend/main.py`、依赖清单、Compose、README、全局样式、接口契约及最终演示                                                                                                  | B 如需新增解析依赖，在自己的 PR 说明包名、版本及理由，由 A 统一改依赖清单。B 的检索代码由 A 接入 `agent_tools.py`，避免两人在同一文件并行重写    |

**当前边界容易踩错的地方。** 公告检索和持仓敞口的工具入口目前都在 `agent_tools.py`。B 可以直接用单测验证自己的 Python 解析和行情模块。A 同时用固定返回值开发工具调度与界面。首次联调只替换 A 的调用入口，两个模块各自保留可重跑的测试。

## 3　第一批 Issues 与合并顺序

| Issue / 建议分支                           | 负责人           | 可以何时开工                 | 交付与合并条件                                                                             |
| -------------------------------------- | ------------- | ---------------------- | ----------------------------------------------------------------------------------- |
| 01 接口样例 · `feat/evidence-contract`     | A 主笔，B review | 首日                     | 先提交两个很小的 JSON 样例和字段说明，一份公告证据、一份带缺价状态的行情快照。注明日期含义、单位、可空值。双方同意后先合这个 PR                |
| 02 PDF 页级解析 · `feat/pdf-passages`      | B             | 首日即可准备材料和解析测试          | 一份可读 PDF 能返回文件版本、页码、摘录。一份扫描或不可读页返回待核实；原有 TXT 空行与行号回归通过                              |
| 03 报告与评测 · `feat/agent-evals`          | A             | 01 的样例写好即可，与 02 并行     | 固定输入覆盖四种情形，能打开样例来源、检查工具轨迹并复算示例组合。先用固定返回值，B 的模块就绪后再切换                                |
| 04 真实行情快照 · `feat/market-snapshot`     | B             | 01 字段确定后，可先保存获准使用的核对材料 | 固定样例价格和真实来源分别运行；提交三标的 × 三日的核对记录。模拟模式的 42% 与 3,360 美元仍可复现                            |
| 05 端到端演示 · `feat/research-integration` | A 主集成，B 独立验收  | 02–04 合入后              | 真实公告关联持仓，有一条可点回的原文；金额误差 ≤0.01 美元，权重误差 ≤0.01 个百分点。在 B 的干净克隆上复现，并记下 commit、输入、输出和启动命令 |

**接口约定草案（Issue 01 确认后采用）**。现有公告工具响应已有 `status`、`total_matches`、`documents`；文档中有 `ticker`、`quarter`、`published`、`excerpt`、`url`，TXT 另有 `line`。PDF 扩展可选的 `page` 与文档版本字段，页码从 1 开始，保留旧 TXT 定位符。行情样例建议包含 `ticker`、`trading_date`、`currency`、`close`、`source`、`as_of` 和 `status`；缺价时价格为空。公告发布日期和行情交易日可不同。字段改名或单位变化先发契约 PR，A 用旧样例回归，B 用新样例验证。

### 双人排期

按每人每周 **10–12 小时**估算。11 月 19 日至 12 月 9 日约有 60–72 人时，目标是先交可演示版本。下表为建议目标日期。

| 窗口          | A                      | B                               | 共同验收点                                                     |
| ----------- | ---------------------- | ------------------------------- | --------------------------------------------------------- |
| 11/19–11/25 | 首次入库、接口样例、报告四类评测       | 冻结小型材料集，完成可读 PDF 页级解析           | A、B 分别在自己的机器从同一 commit 启动 Local 模式                        |
| 11/26–12/02 | 接入页码引用、缺价展示、真实 Live 轨迹 | 真实行情适配与三标的核对；整理 10 份材料、20 个抽查字段 | 串通公告和持仓。材料集抽查至少 18/20 个字段正确，已输出的数值引用逐条可定位                 |
| 12/03–12/09 | 完成端到端报告、容器演示和讲解        | 按独立计算复核金额与权重，重跑 10 个检索题         | 记录前五条命中正确证据的题数，目标 ≥8/10。保留失败用例并注明当前检索方法；混合检索、重排序分别按实际实现验收 |
| 演示后         | 订阅与提醒逻辑、任务恢复、前端及公网联调   | 文档持久化、Supabase 数据与文件隔离、调度和数据质量  | 两账户隔离；同一事件重复投递三次仅一条提醒；Worker 重启后可恢复                       |

如行情权限审批延迟，A 可照常交演示和缺价用例，报告标记样例估值；真实行情一项继续留待验收。SPY 页面保留冻结结果，演示前的人力优先给公告、引用和报告。

## 4　你第一次上传 GitHub（Windows PowerShell）

**① 建一个空仓库。** 登录 GitHub，在 [新建仓库](https://github.com/new) 选择自己的账户，仓库名建议 `FinSentinel`，可见性建议先选 **Private**。README、.gitignore 和 License 都留空，本机已有项目历史的起点。创建后复制页面给出的 **HTTPS** 仓库地址。以下步骤仅首次由 A 操作。

**② 在本机核对目录和提交边界。** 在 PowerShell 逐段执行。

```powershell
Set-Location -LiteralPath 'C:\Users\CZ\Desktop\研究生\求职_预测项目'
git init -b main
git check-ignore -v -- .env FinSentinel-Agent-Research.zip examples/spy_adjusted_close.csv frontend/node_modules frontend/dist
git status --short --untracked-files=normal
```

上传前，`.gitignore` 应有以下规则，连同原有的 `node_modules/`、`dist/`、`.venv/`、`__pycache__/` 一起保留。本次已更新工作目录；若你从较早的 ZIP 起步，请先把缺少的行补进 `.gitignore`。本机 `.env` 可继续保存真实密钥，队友使用空模板。原始 SPY 报价依项目数据说明留在本机，冻结结果 `forecast/result.json` 可供项目页面使用。若以后改为公开仓库，先核对研究数据与演示材料的展示授权。

```gitignore
.env
.env.*
!.env.example
/FinSentinel-*.zip
/examples/spy_adjusted_close.csv
```

**③ 暂存并检查首个提交。** 下列命令只选项目源码、配置、说明、固定样例和已有离线演示。在最后一条命令的输出中，应该看得到 `.env.example` 和本手册。确认列表中没有 `.env`、历史 ZIP、真实账户持仓或原始 SPY 报价后，再执行提交。

```powershell
git add -- .gitignore .dockerignore .env.example README.md Dockerfile compose.yaml pyproject.toml backend frontend forecast examples docs tests FinSentinel-SPY-PoC.html
git diff --cached --stat
git diff --cached --name-only
```

```powershell
git commit -m "Import FinSentinel research agent baseline"
$repoUrl = Read-Host 'https://github.com/ChenYilyc/FinSentinel.git'
git remote add origin $repoUrl
git remote -v
git push -u origin main
git status -sb
git rev-parse --short HEAD
```

首次提交若提示 *Author identity unknown*，运行 `git config user.name "你的 Git 显示名"` 和 `git config user.email "你的 GitHub 提交邮箱"`，再重试 commit。推送时按 Git for Windows 的登录提示完成 GitHub 授权。若显示 *remote origin already exists*，先检查 `git remote -v`；确认要修正本项目地址后才执行 `git remote set-url origin $repoUrl`。若推送提示远端已有提交，先 `git fetch origin` 并看 `git log --oneline --all --graph`；远端已有独立内容时保留它，改用真正的空仓库做本次导入。

**成功标志**：刷新仓库页，默认分支为 `main`，能看到 README、`backend/` 和 `docs/`，最新提交短哈希与本机一致。此后 A、B 都从功能分支提 PR。[GitHub 官方导入说明](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)

已用临时仓库演练上述暂存范围：首个提交含 49 个文件。通过本地 Git bundle 克隆到空目录后，32 项核心测试全部通过，实际项目目录仍可由你亲手初始化。GitHub 上的创建、邀请及首次推送由仓库所有者操作。

## 5　队友加入并独立启动

A 打开仓库 **Settings → Collaborators → Add people**，按 B 的 GitHub 用户名邀请。B 接受后在自己机器的工作目录执行下面的命令。原项目使用 Python 3.11–3.13；以下示例选 Python 3.12，依赖管理用 uv，前端使用 Node 22.12+ 及 npm。[GitHub 协作者说明](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/repository-access-and-collaboration/inviting-collaborators-to-a-personal-repository)

```powershell
$repoUrl = Read-Host 'Paste the shared repository HTTPS URL'
git clone $repoUrl FinSentinel
Set-Location FinSentinel
uv sync --python 3.12 --extra research --no-install-project
npm.cmd --prefix frontend ci
npm.cmd --prefix frontend run build
uv run --no-sync python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

打开 `http://127.0.0.1:8000/#agent`，用 Local 模式跑一次默认 AMD 查询。预期能见到原文及 AMD 在半导体内部的占比 28.57%。首次克隆要构建前端，因为 Git 忽略 `frontend/dist/`。需要 Live 时，B 在自己的克隆里将 `.env.example` 复制为 `.env`，填入自己的密钥并重启服务。

**测试口径。** 在另一个终端进入项目根目录。干净克隆不含原始 SPY CSV，下面运行现有 32 项 Agent、公告、模型配置和持仓测试。拥有经授权的同版本研究 CSV 时，可再执行全量 37 项。

```powershell
Get-ChildItem tests/test_*.py | Where-Object Name -ne 'test_forecast.py' | ForEach-Object {
  uv run --no-sync python -m unittest discover -s tests -p $_.Name
  if ($LASTEXITCODE -ne 0) { throw "Failed: $($_.Name)" }
}
# 本机有归档研究输入时
# uv run --no-sync python -m unittest discover -s tests -v
```

## 6　两个人走完第一轮 PR

**每个 Issue 用一个短期分支。** 先确认工作目录干净，再更新 main。A 的第一个分支可用 `feat/evidence-contract`；B 将下面的分支名换成 `feat/pdf-passages`。两人各自在自己的克隆执行。

```powershell
git switch main
git pull --ff-only origin main
git switch -c feat/evidence-contract
# 完成该 Issue 的改动后
git status --short
git add -p
# 新文件单独用 git add -- 相对路径 加入
git diff --cached --stat
git commit -m "Define filing evidence and market snapshot examples"
git push -u origin HEAD
```

1. 在 GitHub 点 **Compare & pull request**，base 选 `main`。PR 正文写明关联 Issue、改了什么、怎样复现、预期与实际结果。A 和 B 互相担任 reviewer。
2. 审阅人挑一个容易“算对数、用错数”的案例：AMD 的分母是否为半导体总额，PDF 引用是否对应正确页，Q3 公告是否在发布日期前被检索到。通过后由一人点击 **Squash and merge**。
3. 若 GitHub 报冲突，作者先在自己的功能分支提交现有工作，再执行 `git fetch origin`、`git merge origin/main`。按文件所有权核对双方改动，解决后 `git add -- 文件路径`、`git commit`，重跑测试并 `git push`。这样原 PR 会自动更新。
4. 合并后两人都切回 `main`，执行 `git pull --ff-only origin main`；下一项从更新后的 main 开新分支。第一次合作验收以 **B 能独立启动、A 和 B 各有一个经对方审阅并合并的 PR** 为完成标志。[GitHub Flow 官方说明](https://docs.github.com/en/get-started/using-github/github-flow)
