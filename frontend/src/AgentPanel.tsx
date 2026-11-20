import { useEffect, useRef, useState } from 'react'
import type { FormEvent } from 'react'

type Filing = { ticker: string; quarter: string; published: string; excerpt: string; url: string; line?: number; page?: number; document_version?: string }
type PdfPreview = { url: string; version: string }
type Exposure = {
  status: 'ok'; ticker: string; industry: string; valuation_date: string
  held: boolean; other_industry_tickers: string[]
  direct_value_usd: number | null; industry_value_usd: number | null; portfolio_total_usd: number | null
  direct_weight_pct: number | null; industry_weight_pct: number | null; direct_share_of_industry_pct: number | null
  missing_prices: string[]; price_source: string; as_of: string | null
  industry_scenario: { industry: string; decline_pct: number; loss_usd: number | null; loss_pct_of_portfolio: number | null } | null
}
type Result = Exposure | { status: 'found' | 'no_matching_evidence'; documents: Filing[]; total_matches: number }
  | { status: 'unsupported_ticker' | 'invalid_arguments' | 'unknown_tool' | 'permission_denied' }
type Trace = { tool: string; arguments: unknown; result: Result }
const issueText = {
  invalid_format: 'A citation was incomplete.',
  source_not_retrieved: 'The cited source or its metadata did not match a filing returned in this run.',
  quote_mismatch: 'The quoted text differed from the retrieved excerpt.',
  missing_quote: 'The model retrieved a filing but supplied no checkable quote.',
}
type Run = { mode: string; provider?: string; model?: string; status?: string; answer?: string; trace: Trace[]
  resume_token?: string | null
  receipt: {run_id: string; model_rounds: number; elapsed_ms: number; resumptions: number}
  assessments?: {ticker: string; quarter: string; held: boolean | null; conflicting_revenue_sources: string[]}[]
  filing_citations?: { matched: Filing[]; issues: (keyof typeof issueText)[] } }
type Props = { csv: string; source: string; tickers: string[]; snapshot: string }
const money = (n: number | null) => n === null ? 'Awaiting price' : n.toLocaleString('en-US', { style: 'currency', currency: 'USD' })
const pct = (n: number | null) => n === null ? 'Awaiting price' : n.toFixed(2) + '%'

function SourceLink({ doc, open, pdf }: { doc: Filing; open: (line: number) => void; pdf?: PdfPreview }) {
  const label = `${doc.ticker} · ${doc.quarter} · Published ${doc.published}`
  if (doc.page !== undefined) {
    const location = `${label} · Page ${doc.page}, passage ${doc.url.split('-S').pop()}`
    return pdf && pdf.version === doc.document_version
      ? <a href={`${pdf.url}#page=${doc.page}`} target="_blank" rel="noreferrer">{location} ↗</a>
      : <span>{location}</span>
  }
  const line = doc.line
  return line === undefined ? <a href={doc.url} target="_blank" rel="noreferrer">{label} ↗</a>
    : <button type="button" onClick={() => open(line)}>{label} · View line {line}</button>
}

function Evidence({ step, open, pdf }: { step: Trace; open: (line: number) => void; pdf?: PdfPreview }) {
  const r = step.result
  if (r.status === 'found') return <>{r.documents.map(d => <blockquote key={d.url}>
    <p>{d.excerpt}</p><SourceLink doc={d} open={open} pdf={pdf}/>
  </blockquote>)}{r.total_matches > r.documents.length && <p>Showing {r.documents.length} of {r.total_matches} passages. Use a more specific search term.</p>}</>
  if (r.status === 'no_matching_evidence') return <p>No matching passage in the active filing source for this selection.</p>
  if (r.status === 'permission_denied') return <p>Holdings request blocked by the selected filing-only scope.</p>
  if (r.status !== 'ok') return <p>Tool returned: {r.status}.</p>
  const members = r.held ? [r.ticker, ...r.other_industry_tickers] : r.other_industry_tickers
  return <div><h3>{r.ticker} exposure</h3>
    <p>Holdings in {r.industry}: {members.length ? members.join(', ') : 'None'}.</p>
    <div className="scroll"><table><thead><tr><th>Measure</th><th>Holding value</th><th>Denominator</th><th>Share</th></tr></thead>
      <tbody><tr><td>{r.ticker} / portfolio</td><td>{money(r.direct_value_usd)}</td><td>{money(r.portfolio_total_usd)}</td><td>{pct(r.direct_weight_pct)}</td></tr>
        <tr><td>{r.industry} / portfolio</td><td>{money(r.industry_value_usd)}</td><td>{money(r.portfolio_total_usd)}</td><td>{pct(r.industry_weight_pct)}</td></tr>
        <tr><td>{r.ticker} / {r.industry}</td><td>{money(r.direct_value_usd)}</td><td>{money(r.industry_value_usd)}</td>
          <td>{r.industry_value_usd === 0 ? 'N/A · no industry holding' : pct(r.direct_share_of_industry_pct)}</td></tr></tbody>
    </table></div><p className="muted">Industry totals include the company. Price source: {r.price_source} · Trading date: {r.valuation_date}{r.as_of && ` · Available at: ${r.as_of}`}.</p>
    {r.industry_scenario && <div><h4>Industry stress scenario</h4>
      <p>Assume {r.industry_scenario.industry} prices fall {r.industry_scenario.decline_pct}% and all other prices stay fixed.</p>
      <p>Scenario loss: <strong>{money(r.industry_scenario.loss_usd)}</strong> · Share of portfolio lost: <strong>{pct(r.industry_scenario.loss_pct_of_portfolio)}</strong></p>
    </div>}
    {r.missing_prices.length > 0 && <p>Holdings awaiting prices: {r.missing_prices.join(', ')}.</p>}</div>
}

export function AgentPanel({ csv, source, tickers, snapshot }: Props) {
  const [liveAvailable, setLiveAvailable] = useState(false)
  const [live, setLive] = useState(false)
  const [scope, setScope] = useState('filings_only')
  const useHoldings = !live || scope === 'filings_and_holdings'
  const [ticker, setTicker] = useState('AMD')
  const [quarter, setQuarter] = useState('2025-Q3')
  const [through, setThrough] = useState(snapshot)
  const [file, setFile] = useState<File>()
  const isPdfEvidence = /\.json$/i.test(file?.name ?? '')
  const [originalPdf, setOriginalPdf] = useState<File>()
  const pdfPreview = useRef<PdfPreview | undefined>(undefined)
  const [priceFile, setPriceFile] = useState<File>()
  const [industryDecline, setIndustryDecline] = useState('8')
  const priceInput = useRef<HTMLInputElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const [fileTicker, setFileTicker] = useState('')
  const [fileQuarter, setFileQuarter] = useState('')
  const [published, setPublished] = useState('')
  const [term, setTerm] = useState('')
  const [sourceLines, setSourceLines] = useState<string[]>([])
  const [line, setLine] = useState<number>()
  const dialog = useRef<HTMLDialogElement>(null)
  const selected = useRef<HTMLLIElement>(null)
  const [question, setQuestion] = useState('What revenue did AMD report for Q3 2025? Cite the filing.')
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
    return () => {
      settings.abort(); active.current?.abort()
      if (pdfPreview.current) URL.revokeObjectURL(pdfPreview.current.url)
    }
  }, [])

  async function submit(event: FormEvent) {
    event.preventDefault()
    active.current?.abort()
    const request = new AbortController()
    active.current = request
    setBusy(true); setError(''); setResult(undefined)
    try {
      let filing
      let researchTicker = ticker, researchQuarter = quarter
      if (pdfPreview.current) URL.revokeObjectURL(pdfPreview.current.url)
      pdfPreview.current = undefined
      if (file && isPdfEvidence) {
        if (file.size > 524288) throw Error('Choose a PDF evidence JSON of at most 512 KiB.')
        const bundle = JSON.parse(await file.text())
        const first = bundle?.documents?.[0]
        if (!Array.isArray(bundle?.documents) || !first || first.source !== 'uploaded_pdf')
          throw Error('Choose a PDF evidence JSON with parsed passages in documents.')
        filing = bundle
        researchTicker = first.ticker; researchQuarter = first.quarter
        if (originalPdf) {
          if (originalPdf.size > 32 * 1024 * 1024) throw Error('Choose a PDF of at most 32 MiB for preview.')
          const bytes = await originalPdf.arrayBuffer()
          if (new TextDecoder().decode(bytes.slice(0, 5)) !== '%PDF-') throw Error('Choose an original PDF file.')
          const hash = new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))
          const version = Array.from(hash, b => b.toString(16).padStart(2, '0')).join('')
          if (first.document_version !== version) throw Error('The PDF does not match the version in this evidence file.')
          if (request.signal.aborted) return
          pdfPreview.current = { url: URL.createObjectURL(new Blob([originalPdf], {type: 'application/pdf'})), version }
        }
      } else if (file) {
        if (file.size > 49152) throw Error('Choose a plain-text extract of at most 48 KiB.')
        let text: string
        try { text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()) }
        catch { throw Error('Could not read the file as UTF-8 text.') }
        filing = { text, ticker: fileTicker.trim().toUpperCase(), quarter: fileQuarter, published }
        researchTicker = filing.ticker; researchQuarter = filing.quarter
        setSourceLines(text.replace(/\r\n?/g, '\n').split('\n'))
      }
      const inputs = live ? { question: question.trim(), scope } : {
        ticker: researchTicker, quarter: researchQuarter,
        through_date: through, contains: term.trim() || undefined,
      }
      let marketSnapshot
      if (useHoldings && priceFile) {
        if (priceFile.size > 65536) throw Error('Choose a market snapshot of at most 64 KiB.')
        try { marketSnapshot = JSON.parse(await priceFile.text()) }
        catch { throw Error('Could not read the market snapshot as JSON.') }
        if (!marketSnapshot || typeof marketSnapshot !== 'object' || Array.isArray(marketSnapshot))
          throw Error('The market snapshot must be a JSON object.')
      }
      const response = await fetch('/api/agent/' + (live ? 'ask' : 'report'), {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: request.signal,
        body: JSON.stringify({ ...inputs, csv_text: useHoldings ? csv : undefined, filing, market_snapshot: marketSnapshot,
          industry_decline_pct: useHoldings ? Number(industryDecline) : undefined }),
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

  async function resumeRun() {
    if (!result?.resume_token || busy) return
    const request = new AbortController()
    active.current = request
    setBusy(true); setError('')
    try {
      const response = await fetch('/api/agent/resume', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: request.signal,
        body: JSON.stringify({ token: result.resume_token }),
      })
      const body = await response.json()
      if (request.signal.aborted) return
      if (!response.ok) {
        if (response.status === 410) setResult({ ...result, resume_token: null })
        throw Error(typeof body.detail === 'string' ? body.detail : 'Could not resume the analysis.')
      }
      setResult(body)
    } catch (e) {
      if (!request.signal.aborted) setError(e instanceof Error ? e.message : 'Could not resume the analysis.')
    } finally {
      if (!request.signal.aborted) setBusy(false)
    }
  }

  return <section className="panel research" id="agent">
    <h2>Filing &amp; portfolio research</h2>
    <p className="muted">{useHoldings && `Active holdings: ${source}. `}Filing source: {file ? file.name : 'AMD Q2 and Q3 2025 sample excerpts'}.</p>
    <form onSubmit={submit} onChange={() => { setResult(undefined); setError('') }}>
      <fieldset disabled={busy}><label>Analysis mode<select value={live ? 'live' : 'local'} onChange={e => setLive(e.target.value === 'live')}>
        <option value="local">Local · fixed two-tool workflow</option><option value="live" disabled={!liveAvailable}>Live · model selects tools{liveAvailable ? '' : ' (API key required)'}</option>
      </select></label>
      {live && <label>Allowed tools<select value={scope} onChange={e => setScope(e.target.value)}>
        <option value="filings_only">Filing search only</option>
        <option value="filings_and_holdings">Filing search and portfolio exposure</option>
      </select></label>}
      <div hidden={!useHoldings}><label>Assumed decline in the researched company's industry (%)
        <input type="number" min="0" max="100" step="1" required disabled={!useHoldings} value={industryDecline}
          onChange={e => setIndustryDecline(e.target.value)}/></label>
      <label>Price snapshot (optional JSON)<input ref={priceInput} type="file" accept=".json,application/json"
        onChange={e => setPriceFile(e.target.files?.[0])}/></label>
      {priceFile && <button type="button" onClick={() => {
        if (priceInput.current) priceInput.current.value = ''
        setPriceFile(undefined); setResult(undefined); setError('')
      }}>Use demo prices</button>}</div>
      <label>Filing source (UTF-8 text or parsed PDF evidence JSON)
        <input ref={fileInput} type="file" accept=".txt,.json,text/plain,application/json" onChange={e => {
          setFile(e.target.files?.[0]); setOriginalPdf(undefined); setPublished(''); setFileQuarter(''); setFileTicker('')
        }}/></label>
      {file && <div>{isPdfEvidence
        ? <label>Original PDF for local page links (optional)<input key={file.name + file.lastModified} type="file" accept=".pdf,application/pdf"
            onChange={e => setOriginalPdf(e.target.files?.[0])}/></label>
        : <small>Supply the company, fiscal quarter and publication date from your document. This run searches only this file.</small>}
        <button type="button" onClick={() => {
          if (fileInput.current) fileInput.current.value = ''
          setFile(undefined); setResult(undefined); setError('')
        }}>Use sample excerpts</button>
        {!isPdfEvidence && <div className="research-fields">
          <label>Filing ticker<input required pattern="[A-Z0-9][A-Z0-9.\-]{0,11}" value={fileTicker} onChange={e => setFileTicker(e.target.value.toUpperCase())}/></label>
          <label>Filing quarter<input required pattern="[0-9]{4}-Q[1-4]" placeholder="2025-Q3" value={fileQuarter} onChange={e => setFileQuarter(e.target.value.toUpperCase())}/></label>
          <label>Published on<input required type="date" value={published} onChange={e => setPublished(e.target.value)}/></label>
        </div>}</div>}
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
      <p>Tool requests: {result.trace.length} · Model rounds: {result.receipt.model_rounds} · Elapsed: {result.receipt.elapsed_ms} ms</p>
      {result.receipt.resumptions > 0 && <p>Resumed {result.receipt.resumptions} time(s) · Original run {result.receipt.run_id}</p>}
      <a download={`finsentinel-run-${result.receipt.run_id}.json`}
        href={'data:application/json;charset=utf-8,' + encodeURIComponent(JSON.stringify(result.receipt, null, 2))}>
        Download run receipt</a>
      {result.assessments?.map(a => <div key={a.ticker + a.quarter}>
        <p>{a.ticker} · {a.quarter} · {a.held === null ? 'Direct holdings not checked' :
          a.held ? 'Issuer held directly' : 'No direct holding in this issuer'}.</p>
        {a.conflicting_revenue_sources.length > 0 && <p className="error">Needs review: retrieved passages report different current-quarter revenue amounts.
          {' '}{a.conflicting_revenue_sources.map(url => {
            const doc = result.trace.flatMap(s => s.result.status === 'found' ? s.result.documents : []).find(d => d.url === url)
            return doc && <SourceLink key={url} doc={doc} open={setLine} pdf={pdfPreview.current}/>
          })}</p>}
      </div>)}
      {result.trace.map((step, idx) => <Evidence key={idx} step={step} open={setLine} pdf={pdfPreview.current}/>)}
      {result.answer && <><h3>Model draft</h3><p className="draft-text">{result.answer}</p></>}
      {result.filing_citations && <div><h3>Filing quote check</h3>
        {result.filing_citations.matched.map(d => <p key={d.url}>Exact quote matched · <SourceLink doc={d} open={setLine} pdf={pdfPreview.current}/> · “{d.excerpt}”</p>)}
        {result.filing_citations.issues.map((issue, i) => <p className="error" key={i}>{issueText[issue]}</p>)}
        {!result.filing_citations.matched.length && !result.filing_citations.issues.length &&
          <p>No filing quote was checked in this run.</p>}
        <small>This check covers the quoted passage only. Review the model’s interpretation separately.</small>
      </div>}
      {result.status === 'budget_exhausted' && <p>Run budget reached. Completed tool results are shown.</p>}
      {result.status === 'no_answer' && <p>The model returned no answer.</p>}
      {result.status === 'needs_review' && <p>Model draft withheld pending review. See the tool results above.</p>}
      {result.status === 'provider_interrupted' && <div><p>The model connection was interrupted. Completed tool results are available above.</p>
        {result.resume_token && <button type="button" disabled={busy} onClick={resumeRun}>Resume from saved evidence</button>}
      </div>}
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
