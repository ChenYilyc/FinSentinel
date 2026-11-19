import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

type Filing = { ticker: string; quarter: string; published: string; excerpt: string; url: string; line?: number }
type Exposure = {
  status: 'ok'; ticker: string; industry: string; valuation_date: string
  direct_value_usd: number; industry_value_usd: number; portfolio_total_usd: number
  direct_weight_pct: number; industry_weight_pct: number; direct_share_of_industry_pct: number | null
}
type Result = Exposure | { status: 'found' | 'no_matching_evidence'; documents: Filing[]; total_matches: number }
  | { status: 'unsupported_ticker' | 'invalid_arguments' | 'unknown_tool' }
type Trace = { tool: string; arguments: unknown; result: Result }
const issueText = {
  invalid_format: 'A citation was incomplete.',
  source_not_retrieved: 'The cited source or its metadata did not match a filing returned in this run.',
  quote_mismatch: 'The quoted text differed from the retrieved excerpt.',
  missing_quote: 'The model retrieved a filing but supplied no checkable quote.',
}
type Run = { mode: string; provider?: string; model?: string; status?: string; answer?: string; trace: Trace[]
  filing_citations?: { matched: Filing[]; issues: (keyof typeof issueText)[] } }
type Props = { csv: string; source: string; tickers: string[]; snapshot: string }
const money = (n: number) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const pct = (n: number) => n.toFixed(2) + '%'

function SourceLink({ doc, open }: { doc: Filing; open: (line: number) => void }) {
  const label = `${doc.ticker} · ${doc.quarter} · Published ${doc.published}`
  const line = doc.line
  return line === undefined ? <a href={doc.url} target="_blank" rel="noreferrer">{label} ↗</a>
    : <button type="button" onClick={() => open(line)}>{label} · View line {line}</button>
}

function Evidence({ step, open }: { step: Trace; open: (line: number) => void }) {
  const r = step.result
  if (r.status === 'found') return <>{r.documents.map(d => <blockquote key={d.url}>
    <p>{d.excerpt}</p><SourceLink doc={d} open={open}/>
  </blockquote>)}{r.total_matches > r.documents.length && <p>Showing {r.documents.length} of {r.total_matches} passages. Use a more specific search term.</p>}</>
  if (r.status === 'no_matching_evidence') return <p>No matching passage in the active filing source for this selection.</p>
  if (r.status !== 'ok') return <p>Tool returned: {r.status}.</p>
  return <div><h3>{r.ticker} exposure</h3>
    <div className="scroll"><table><thead><tr><th>Measure</th><th>Holding value</th><th>Denominator</th><th>Share</th></tr></thead>
      <tbody><tr><td>{r.ticker} / portfolio</td><td>{money(r.direct_value_usd)}</td><td>{money(r.portfolio_total_usd)}</td><td>{pct(r.direct_weight_pct)}</td></tr>
        <tr><td>{r.industry} / portfolio</td><td>{money(r.industry_value_usd)}</td><td>{money(r.portfolio_total_usd)}</td><td>{pct(r.industry_weight_pct)}</td></tr>
        <tr><td>{r.ticker} / {r.industry}</td><td>{money(r.direct_value_usd)}</td><td>{money(r.industry_value_usd)}</td>
          <td>{r.direct_share_of_industry_pct === null ? 'N/A · no industry holding' : pct(r.direct_share_of_industry_pct)}</td></tr></tbody>
    </table></div><p className="muted">Industry totals include the company. Synthetic prices as of {r.valuation_date}.</p></div>
}

export function AgentPanel({ csv, source, tickers, snapshot }: Props) {
  const [liveAvailable, setLiveAvailable] = useState(false)
  const [live, setLive] = useState(false)
  const [ticker, setTicker] = useState('AMD')
  const [quarter, setQuarter] = useState('2025-Q3')
  const [through, setThrough] = useState(snapshot)
  const [file, setFile] = useState<File>()
  const fileInput = useRef<HTMLInputElement>(null)
  const [fileTicker, setFileTicker] = useState('')
  const [fileQuarter, setFileQuarter] = useState('')
  const [published, setPublished] = useState('')
  const [term, setTerm] = useState('')
  const [sourceLines, setSourceLines] = useState<string[]>([])
  const [line, setLine] = useState<number>()
  const dialog = useRef<HTMLDialogElement>(null)
  const selected = useRef<HTMLLIElement>(null)
  const [question, setQuestion] = useState('What did AMD report for Q3 2025, and what share of my semiconductor holdings is AMD?')
  const [result, setResult] = useState<Run>()
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const active = useRef<AbortController | null>(null)
  useEffect(() => {
    if (line !== undefined) {
      dialog.current?.showModal()
      selected.current?.scrollIntoView({ block: 'center' })
    }
  }, [line])
  useEffect(() => {
    const settings = new AbortController()
    fetch('/api/agent/settings', { signal: settings.signal })
      .then(r => r.ok ? r.json() : undefined).then(s => setLiveAvailable(s?.live_available === true))
      .catch(() => {})
    return () => { settings.abort(); active.current?.abort() }
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    active.current?.abort()
    const request = new AbortController()
    active.current = request
    setBusy(true); setError(''); setResult(undefined)
    try {
      let filing
      if (file) {
        if (file.size > 49152) throw Error('Choose a plain-text extract of at most 48 KiB.')
        let text: string
        try { text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()) }
        catch { throw Error('Could not read the file as UTF-8 text.') }
        filing = { text, ticker: fileTicker.trim().toUpperCase(), quarter: fileQuarter, published }
        setSourceLines(text.replace(/\r\n?/g, '\n').split('\n'))
      }
      const inputs = live ? { question: question.trim() } : {
        ticker: filing?.ticker ?? ticker, quarter: filing?.quarter ?? quarter,
        through_date: through, contains: term.trim() || undefined,
      }
      const response = await fetch('/api/agent/' + (live ? 'ask' : 'report'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: request.signal,
        body: JSON.stringify({ ...inputs, csv_text: csv, filing }),
      })
      const body = await response.json()
      if (!response.ok) throw Error(typeof body.detail === 'string' ? body.detail :
        body.detail?.[0]?.msg ?? 'Check the inputs and retry.')
      if (!request.signal.aborted) setResult(body)
    } catch (e) {
      if (!request.signal.aborted) setError(e instanceof Error ? e.message : 'Request failed.')
    } finally {
      if (!request.signal.aborted) setBusy(false)
    }
  }

  return <section className="panel research" id="agent">
    <h2>Filing &amp; portfolio research</h2>
    <p className="muted">Active holdings: {source}. Filing source: {file ? file.name : 'AMD Q2 and Q3 2025 sample excerpts'}.</p>
    <form onSubmit={submit} onChange={() => { setResult(undefined); setError('') }}>
      <fieldset disabled={busy}><label>Analysis mode<select value={live ? 'live' : 'local'} onChange={e => setLive(e.target.value === 'live')}>
        <option value="local">Local · fixed two-tool workflow</option><option value="live" disabled={!liveAvailable}>Live · model selects tools{liveAvailable ? '' : ' (API key required)'}</option>
      </select></label>
      <label>Use a filing extract (.txt, UTF-8, up to 48 KiB)
        <input ref={fileInput} type="file" accept=".txt,text/plain" onChange={e => {
          setFile(e.target.files?.[0]); setPublished(''); setFileQuarter(''); setFileTicker('')
        }}/></label>
      {file && <div><small>Supply the company, fiscal quarter and publication date from your document. This run searches only this file.</small>
        <button type="button" onClick={() => {
          if (fileInput.current) fileInput.current.value = ''
          setFile(undefined); setResult(undefined); setError('')
        }}>Use sample excerpts</button>
        <div className="research-fields">
          <label>Filing ticker<input required pattern="[A-Z0-9][A-Z0-9.\-]{0,11}" value={fileTicker} onChange={e => setFileTicker(e.target.value.toUpperCase())}/></label>
          <label>Filing quarter<input required pattern="[0-9]{4}-Q[1-4]" placeholder="2025-Q3" value={fileQuarter} onChange={e => setFileQuarter(e.target.value.toUpperCase())}/></label>
          <label>Published on<input required type="date" value={published} onChange={e => setPublished(e.target.value)}/></label>
        </div></div>}
      {live ? <label>Research question<textarea required maxLength={1200} value={question} onChange={e => setQuestion(e.target.value)}/>
        <small>Your question and requested tool results are sent to the configured model provider.</small></label>
      : <div className="research-fields">{!file && <><label>Company<select value={ticker} onChange={e => setTicker(e.target.value)}>
        {tickers.filter(t => t !== 'CASH').map(t => <option key={t}>{t}</option>)}</select></label>
        <label>Fiscal quarter<select value={quarter} onChange={e => setQuarter(e.target.value)}>
          <option>2025-Q2</option><option>2025-Q3</option></select></label></>}
        <label>Text contains (optional)<input maxLength={100} value={term} onChange={e => setTerm(e.target.value)}/></label>
        <label>Filings published through<input type="date" required value={through} onChange={e => setThrough(e.target.value)}/></label></div>}
      <button disabled={busy || (live && !question.trim())}>{busy ? 'Running…' : 'Run analysis'}</button></fieldset>
    </form>
    {error && <p className="error" role="alert">{error}</p>}
    {result && <div aria-live="polite">
      <h3>{result.mode === 'live' ? `Live model · ${result.provider} / ${result.model}` : 'Local fixed workflow'}</h3>
      <p>Tool calls completed: {result.trace.length}</p>
      {result.trace.map((step, idx) => <Evidence key={idx} step={step} open={setLine}/>)}
      {result.answer && <><h3>Model draft</h3><p className="draft-text">{result.answer}</p></>}
      {result.filing_citations && <div><h3>Filing quote check</h3>
        {result.filing_citations.matched.map(d => <p key={d.url}>Exact quote matched · <SourceLink doc={d} open={setLine}/> · “{d.excerpt}”</p>)}
        {result.filing_citations.issues.map((issue, i) => <p className="error" key={i}>{issueText[issue]}</p>)}
        {!result.filing_citations.matched.length && !result.filing_citations.issues.length &&
          <p>No filing quote was checked in this run.</p>}
        <small>This check covers the quoted passage only. Review the model’s interpretation separately.</small>
      </div>}
      {result.status === 'budget_exhausted' && <p>Tool-call budget reached. Only completed tool results are shown.</p>}
      {result.status === 'no_answer' && <p>The model returned no answer.</p>}
      <details><summary>Tool trace ({result.trace.length})</summary><pre>{JSON.stringify(result.trace, null, 2)}</pre></details>
    </div>}
    <dialog ref={dialog} onClose={() => setLine(undefined)} aria-labelledby="source-title" className="filing-source">
      <header><h3 id="source-title">{file?.name} · Line {line}</h3>
        <button type="button" onClick={() => dialog.current?.close()}>Close</button></header>
      {line !== undefined && <ol>{sourceLines.map((content, i) => <li key={i} ref={i + 1 === line ? selected : undefined}
        className={i + 1 === line ? 'selected' : ''}>{content || ' '}</li>)}</ol>}
    </dialog>
  </section>
}
