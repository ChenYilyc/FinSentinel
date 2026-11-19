import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import './style.css'
import { HistoryPanel, type PortfolioHistory } from './HistoryPanel'
import { ForecastPage } from './ForecastPage'
import { AgentPanel } from './AgentPanel'

type Group = { name: string; weight: number; value: number; alert: boolean }
type Position = { ticker: string; name: string; quantity: number; price: number; value: number; weight: number }
type Report = { total: number; groups: Group[]; positions: Position[]; threshold: number; industry: string; decline: number; loss: number; loss_pct: number; history: PortfolioHistory }
type Demo = { csv_text: string; industries: string[]; tickers: string[]; snapshot: string; report: Report }
const money = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 })
const percent = (n: number) => n.toLocaleString('en-US', { maximumFractionDigits: 2 }) + '%'

function App() {
  const [demo, setDemo] = useState<Demo>()
  const [report, setReport] = useState<Report>()
  const [csv, setCsv] = useState('')
  const [source, setSource] = useState('Sample portfolio')
  const [industry, setIndustry] = useState('Semiconductors')
  const [threshold, setThreshold] = useState(35)
  const [decline, setDecline] = useState(8)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const file = useRef<HTMLInputElement>(null)

  useEffect(() => {
    if (demo && window.location.hash === '#agent') document.getElementById('agent')?.scrollIntoView()
  }, [demo])

  useEffect(() => {
    fetch('/api/demo').then(async res => {
      if (!res.ok) throw Error()
      const data: Demo = await res.json()
      setDemo(data); setReport(data.report); setCsv(data.csv_text)
    }).catch(() => setError('Could not load the sample portfolio. Check the API and refresh.'))
  }, [])

  async function run(upload?: File, reset = false) {
    if (!demo) return
    setBusy(true); setError('')
    try {
      if (upload && upload.size > 65536) throw Error('CSV uploads must be 64 KB or smaller.')
      const text = upload ? await upload.text() : reset ? demo.csv_text : csv
      const res = await fetch('/api/analyze', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ csv_text: text, threshold, industry, decline })
      })
      const body = await res.json()
      if (!res.ok) throw Error(typeof body.detail === 'string' ? body.detail : 'Check the CSV and scenario inputs.')
      setReport(body); setCsv(text)
      if (upload || reset) setSource(upload?.name ?? 'Sample portfolio')
    } catch (e) { setError(e instanceof Error ? e.message : 'Analysis failed. Please retry.') }
    finally { setBusy(false); if (file.current) file.current.value = '' }
  }
  const alerts = report?.groups.filter(g => g.alert) ?? []
  const changed = report && (report.industry !== industry || report.threshold !== threshold || report.decline !== decline)
  return <>
    <header><div className="brand"><i aria-hidden="true">F</i> FinSentinel</div><nav className="research-nav">
      <a className="nav-link" href="#agent">Filing research</a><a className="nav-link" href="#forecast">SPY forecast →</a>
    </nav></header>
    <main>
      <section className="intro"><div><p className="eyebrow">PORTFOLIO ANALYTICS</p><h1>Portfolio risk</h1>
        <p className="muted">Synthetic USD prices · Snapshot {demo?.snapshot ?? '…'}</p></div>
        <div className="actions"><a href="/api/template.csv" download>Download CSV template</a>
        <button disabled={!demo || busy} onClick={() => file.current?.click()}>Import holdings</button>
        <input hidden ref={file} type="file" accept=".csv,text/csv" onChange={e => { const f=e.target.files?.[0]; if(f) void run(f) }}/></div>
      </section>
      {error && <p className="error" role="alert">{error}</p>}
      {busy && <p role="status">Calculating portfolio risk…</p>}
      {report && demo ? <>
        <div className="metrics">
          <article><p>Portfolio value</p><strong>{money(report.total)}</strong><small>{source} · {report.positions.length} positions</small></article>
          <article><p>Concentration alerts</p><strong>{alerts.length}</strong><small>Industries above {percent(report.threshold)} weight</small></article>
          <article><p>Scenario loss</p><strong>{money(report.loss)}</strong><small>{percent(report.loss_pct)} of portfolio · {report.industry} −{report.decline}%</small></article>
        </div>
        <div className="columns"><section className="panel"><h2>Industry exposure</h2>
          {report.groups.map(g => <div className="row" key={g.name}><div><span>{g.name} {g.alert && <b className="flag">Above limit</b>}</span><b>{percent(g.weight)}</b></div>
            <div className="track"><i className={g.alert ? 'hot' : ''} style={{width:g.weight+'%'}}/></div></div>)}
        </section>
        <section className="panel"><h2>Stress test</h2><form onSubmit={e => {e.preventDefault(); void run()}}>
          <label>Affected industry<select disabled={busy} value={industry} onChange={e=>setIndustry(e.target.value)}>{demo.industries.map(s=><option key={s}>{s}</option>)}</select></label>
          <div className="pair"><label>Price decline (%)<input disabled={busy} type="number" min="0" max="100" required value={Number.isNaN(decline)?'':decline} onChange={e=>setDecline(e.target.valueAsNumber)}/></label>
          <label>Alert above (%)<input disabled={busy} type="number" min="1" max="100" required value={Number.isNaN(threshold)?'':threshold} onChange={e=>setThreshold(e.target.valueAsNumber)}/></label></div>
          <p className="muted">Other prices stay fixed. Cash counts toward total value and is excluded from concentration alerts.</p>
          <button disabled={busy || !changed}>Apply scenario</button>
        </form></section></div>
        <HistoryPanel history={report.history} money={money} percent={percent}/>
        <AgentPanel key={csv} csv={csv} source={source} tickers={demo.tickers} snapshot={demo.snapshot}/>
        <section className="panel holdings"><div className="heading"><h2>Holdings</h2>
          {source!=='Sample portfolio' && <button className="plain" disabled={busy} onClick={()=>void run(undefined,true)}>Reload sample</button>}</div>
          <div className="scroll"><table><thead><tr><th>Asset</th><th>Quantity</th><th>Unit price</th><th>Market value</th><th>Weight</th></tr></thead>
          <tbody>{report.positions.map(p=><tr key={p.ticker}><td><b>{p.ticker}</b><small>{p.name}</small></td><td>{p.quantity.toLocaleString('en-US',{maximumFractionDigits:6})}</td><td>{money(p.price)}</td><td>{money(p.value)}</td><td>{percent(p.weight)}</td></tr>)}</tbody></table></div>
          <details><summary>Supported tickers and CSV format</summary><p>{demo.tickers.join(', ')}. Use ticker, quantity and currency (USD). Repeated tickers are combined. CASH represents US dollars.</p></details>
        </section>
      </> : !error && <p role="status">Loading portfolio…</p>}
    </main>
  </>
}
function Workspace() {
  const [hash, setHash] = useState(window.location.hash)
  useEffect(() => {
    const navigate = () => {
      setHash(window.location.hash)
      if (window.location.hash !== '#agent') window.scrollTo(0, 0)
    }
    window.addEventListener('hashchange', navigate)
    return () => window.removeEventListener('hashchange', navigate)
  }, [])
  // Preserve the imported holdings when switching between research views.
  return <><div hidden={hash === '#forecast'}><App/></div>{hash === '#forecast' && <ForecastPage/>}</>
}
const embedded = document.getElementById('forecast-snapshot')?.textContent
const root = createRoot(document.getElementById('root')!)
if (embedded) {
  const { snapshot, csvUrl } = JSON.parse(embedded)
  root.render(<ForecastPage snapshot={snapshot} csvUrl={csvUrl}/>)
} else {
  root.render(<Workspace/>)
}
