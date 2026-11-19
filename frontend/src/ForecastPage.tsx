import { useEffect, useState } from 'react'

type Scores = {
  n: number; up_rate: number; model_accuracy: number; baseline_accuracy: number
  model_brier: number; baseline_brier: number; delta_brier: number
}
type Window = Scores & { fold: number; start: string; end: string; train_n: number; last_train_label: string }
type Prediction = { date: string; maturity: string; model: number; baseline: number }
type Snapshot = {
  first: string; cutoff: string; rows: number; version: string; source: string
  pending: Prediction; settled: Prediction & { realized: number; up: number }
  windows: Window[]; overall: Scores; calibration_png: string
}
const pct = (value: number) => (value * 100).toFixed(2) + '%'
const score = (value: number) => value.toFixed(6)

function ScoreRow({ label, data }: { label: string; data: Scores }) {
  return <tr><td>{label}</td><td>{data.n}</td><td>{pct(data.up_rate)}</td>
    <td>{pct(data.model_accuracy)}</td><td>{pct(data.baseline_accuracy)}</td>
    <td>{score(data.model_brier)}</td><td>{score(data.baseline_brier)}</td></tr>
}

export function ForecastPage({ snapshot, csvUrl = '/api/forecast/history.csv' }: { snapshot?: Snapshot; csvUrl?: string }) {
  const [data, setData] = useState<Snapshot | undefined>(snapshot)
  const [error, setError] = useState('')
  useEffect(() => {
    if (snapshot) return
    const controller = new AbortController()
    async function load() {
      try {
        const response = await fetch('/api/forecast', { signal: controller.signal })
        if (!response.ok) throw Error('Forecast unavailable. Check the API and the trained snapshot.')
        setData(await response.json())
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : 'Unable to load snapshot.')
      }
    }
    void load()
    return () => controller.abort()
  }, [snapshot])
  return <>
    <header><div className="brand"><i aria-hidden="true">F</i> FinSentinel</div>
      {snapshot ? <span>Offline research report</span> : <a className="nav-link" href="#portfolio">← Portfolio risk</a>}</header>
    <main><section className="intro"><div><h1>SPY five-session outlook</h1>
      <p className="muted">Probability of a positive adjusted-close return over the next five US trading sessions.</p></div></section>
      {error && <p className="error" role="alert">{error}</p>}
      {!data && !error && <p role="status">Loading forecast…</p>}
      {data && <>
        <p><b>Historical snapshot</b> · Data through {data.cutoff} · Target close {data.pending.maturity}</p>
        <section className="metrics">
          <article><p>Logistic regression</p><strong>{pct(data.pending.model)}</strong><small>Estimate at the snapshot close</small></article>
          <article><p>Historical up frequency</p><strong>{pct(data.pending.baseline)}</strong><small>Baseline from matured training labels</small></article>
          <article><p>Out-of-sample predictions</p><strong>{data.overall.n}</strong><small>{data.windows.length} chronological test windows</small></article>
        </section>
        <section className="panel history"><h2>Walk-forward evaluation</h2>
          <p className="muted">Lower Brier scores indicate smaller probability errors. Accuracy uses a 50% cutoff. Adjacent five-session outcomes overlap.</p>
          <div className="scroll"><table><thead><tr>{['Test dates', 'Days', 'Up rate', 'Model acc.', 'Base acc.', 'Model Brier', 'Base Brier'].map(v => <th key={v}>{v}</th>)}</tr></thead>
            <tbody>{data.windows.map(w => <ScoreRow key={w.fold} label={w.start + ' → ' + w.end} data={w}/>)}
              <ScoreRow label="All test dates" data={data.overall}/></tbody></table></div>
          <p>Across all windows, the model’s Brier score was {score(Math.abs(data.overall.delta_brier))} {data.overall.delta_brier > 0 ? 'higher than' : data.overall.delta_brier < 0 ? 'lower than' : 'away from'} the baseline.</p>
          <a href={csvUrl} download="spy-five-session-backtest.csv">Download daily out-of-sample predictions</a>
        </section>
        <div className="columns"><section className="panel"><h2>Probability calibration</h2>
          <img className="calibration-chart" src={'data:image/png;base64,' + data.calibration_png}
            alt="Observed up frequency against average predicted probability, grouped in ten equal-width bins."/>
          <small>Each point represents a populated probability bin. The diagonal represents perfect calibration.</small>
        </section><section className="panel"><h2>Last settled replay</h2>
          <p>Prediction at the close of <b>{data.settled.date}</b>, settled on <b>{data.settled.maturity}</b>.</p>
          <dl className="history-stats"><div><dt>Model estimate</dt><dd>{pct(data.settled.model)}</dd></div>
            <div><dt>Baseline</dt><dd>{pct(data.settled.baseline)}</dd></div>
            <div><dt>Realized return</dt><dd>{pct(data.settled.realized)}</dd></div>
            <div><dt>Outcome</dt><dd>{data.settled.up ? 'Up' : 'Flat / down'}</dd></div></dl>
          <p className="muted">The estimate dated {data.cutoff} remains unscored within this frozen dataset.</p>
        </section></div>
        <p className="muted">{data.rows.toLocaleString('en-US')} daily observations · {data.first} to {data.cutoff} · Model {data.version} · <a href={data.source}>Data provenance</a></p>
      </>}
    </main>
  </>
}
