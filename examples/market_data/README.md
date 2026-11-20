# 日收盘行情快照

`synthetic_daily_closes.csv` 是人造测试数据。用它验证同一标的的不同交易日不会混用，以及价格留空或整行缺失时会返回 `missing`。原风险页的固定参考组合仍使用项目已有的模拟价格。

真实来源可先导出为 UTF-8 CSV，表头为 `ticker,trading_date,currency,close`。每行对应一个标的在指定美东交易日的未复权 USD 收盘价。缺价留空，日期使用 `YYYY-MM-DD`。调用方传入供应商标识和带时区的可用时间 `as_of`，并在验收记录保留来源、抓取时间和原文件版本。API 密钥和原始报价留在获准使用的环境。

在项目根目录可用下面的 Python 代码读取固定样例并估值：

```python
from datetime import date, datetime, timezone
from pathlib import Path

from backend.market_data.snapshots import read_daily_close_csv
from backend.risk import analyze

snapshot = read_daily_close_csv(
    Path("examples/market_data/synthetic_daily_closes.csv"),
    ["AMD", "NVDA"],
    trading_date=date(2026, 10, 30),
    as_of=datetime(2026, 10, 30, 20, 15, tzinfo=timezone.utc),
    source="synthetic-test-csv",
)
holdings = "ticker,quantity,currency\nAMD,100,USD\nNVDA,200,USD\nCASH,12000,USD"
report = analyze(holdings, 35, "Semiconductors", 8, snapshot=snapshot)
assert report["total"] == 59_525
assert report["loss"] == 3_802
```

缺少已持有标的的报价时，报告列出 `missing_tickers`，保留可估值持仓的金额，并将组合总值和权重留空。缺价影响选定行业时，该行业的压力损失金额也留空。损失占组合比例需要完整组合总值。传入单日快照时，历史风险留空。标准示例路径继续使用固定模拟历史。
