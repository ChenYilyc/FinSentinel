export type PortfolioHistory = {
  series: { date: string; value: number }[]
  return_pct: number
  daily_volatility_pct: number
  max_drawdown_pct: number
}

type Props = {
  history: PortfolioHistory
  money: (value: number) => string
  percent: (value: number) => string
}

export function HistoryPanel({ history, money, percent }: Props) {
  const { series } = history
  return <section className="panel history">
    <h2>Historical risk</h2>
    <p className="muted">Fixed holdings valued at {series.length} synthetic closes, {series[0].date} to {series[series.length - 1].date}. Cash stays at $1. Dividends, fees and trades are excluded.</p>
    <dl className="history-stats">
      <div><dt>Period return</dt><dd>{percent(history.return_pct)}</dd></div>
      <div><dt>Daily volatility</dt><dd>{percent(history.daily_volatility_pct)}</dd></div>
      <div><dt>Maximum drawdown</dt><dd>{percent(history.max_drawdown_pct)}</dd></div>
    </dl>
    <details><summary>Inspect closing values and calculations</summary>
      <p>Period return compares the last close with the first. Daily volatility is the sample standard deviation of the {series.length - 1} daily returns. Maximum drawdown measures the largest percentage loss from an earlier peak.</p>
      <table><thead><tr><th>Simulated close</th><th>Portfolio value</th></tr></thead>
        <tbody>{series.map(point => <tr key={point.date}><td>{point.date}</td><td>{money(point.value)}</td></tr>)}</tbody>
      </table>
    </details>
  </section>
}
