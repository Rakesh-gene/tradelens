import React, { useState } from 'react'
import { PageIntro } from '../components/PatternUi.jsx'
import NavigationLink from '../components/NavigationLink.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { describePattern } from '../utils/patternDescriptions.js'
import { SUPPORTED_PATTERN_TYPES } from '../utils/setupFilters.js'

const steps = [
  { target: 'body', placement: 'center', title: 'Welcome to TradeLens', content: 'TradeLens is an end-of-day research workspace for Indian equities. Use it to investigate market context and positional setups—not as an intraday terminal or a recommendation service.' },
  { target: '[data-guide="primary-navigation"]', title: 'Move through the research flow', content: 'Start with the market, narrow to sectors and setups, then investigate the stock or historical cases.' },
  { target: '.security-jump', title: 'Search a stock any time', content: 'Search by NSE symbol or company name. Open a stock to review its adjusted chart, trend, relative strength, levels, and active evidence.' },
  { target: '[data-guide="guide-workflow"]', title: 'Use this workflow', content: 'These four steps are the fastest way to turn the dashboard into a repeatable research routine.' },
  { target: '[data-guide="guide-reference"]', title: 'Use the screen reference', content: 'Open the screen that matches your question. Each section explains the job it does and the evidence to inspect.' },
  { target: '[data-guide="guide-interpretation"]', title: 'Keep evidence in context', content: 'Scores rank the current evidence; they are not probabilities, forecasts, or a substitute for your own risk process.' },
]

const screenGuide = [
  ['Overview', 'What is happening in the market?', 'Check the data-as-of date, pipeline status, market breadth, lifecycle counts, and top-ranked active setups. Start here before assessing an individual stock.'],
  ['Sector rotation', 'Where is relative strength improving?', 'Read the five-session paths before opening a sector. Then review the ranked stocks in that sector to find candidates with both leadership and active evidence.'],
  ['Setups', 'Which structures are active now?', 'Filter by the available pattern types, lifecycle state, timeframe, score, or sector. Results are server-ranked and reproducible from the page URL.'],
  ['Pattern inspection', 'Why did this setup appear?', 'Review the adjusted chart, detection and trigger dates, pivot, support, invalidation, scores, measurements, supporting signals, and lifecycle events.'],
  ['Stock overview', 'What does this one stock look like?', 'Search by symbol or company name. Review trend, moving averages, relative strength, volume, price location, sector context, active patterns, and the recent event timeline.'],
  ['Watchlist', 'How are my research names changing?', 'Add equities from search or investigation pages. Cards and the rotation view make it easy to revisit five-session relative-strength progression.'],
  ['Indices', 'How are market benchmarks behaving?', 'Compare broad-market, sectoral, and thematic NIFTY indices. Index pages use their public index code in the address bar, not an internal identifier.'],
  ['Case studies', 'How did comparable historical stocks perform?', 'Open a published case to see the pattern explanation, chart, entry rationale, and the stock’s forward 3-month, 6-month, and 1-year performance.'],
]

const glossary = [
  ['Adjusted price', 'A historical price adjusted for corporate actions so trend, levels, and return comparisons remain meaningful.'],
  ['Relative strength (RS)', 'How a stock, sector, or index performed compared with NIFTY 500 over the stated period. It is not the RSI oscillator.'],
  ['Momentum proxy', 'One-month RS minus one-third of three-month RS. It describes acceleration or deceleration in the rotation view.'],
  ['Pivot', 'The reference price level a structure must clear to trigger.'],
  ['Support', 'A nearby level used to judge whether the structure remains orderly.'],
  ['Invalidation', 'The price level where the stored setup evidence is no longer valid. It is evidence context, not a personalised exit instruction.'],
  ['Lifecycle', 'The persisted maturity of a pattern: from detected/forming through ready, triggered, and confirmed, or to a terminal outcome.'],
]

const PATTERN_EXAMPLES = {
  'BASE-VCP': { points: [[5,72],[17,30],[29,66],[41,40],[53,61],[65,47],[77,57],[87,51],[95,20]], level: 45, label: 'pivot', cue: 'Pullbacks narrow as price approaches the pivot.' },
  'BASE-FLAT': { points: [[5,68],[18,45],[31,60],[44,47],[57,58],[70,48],[83,55],[90,46],[95,22]], level: 43, label: 'range high', cue: 'A shallow sideways range follows an earlier advance.' },
  'BASE-52WH': { points: [[5,70],[18,36],[31,53],[44,40],[57,50],[70,41],[83,47],[91,39],[95,14]], level: 35, label: '52-week high', cue: 'Price consolidates close to the prior 52-week high.' },
  'BASE-TIGHT': { points: [[5,73],[18,28],[31,50],[44,46],[57,51],[70,47],[83,50],[91,46],[95,24]], level: 43, label: 'tight-range high', cue: 'The final swings are notably smaller than the preceding move.' },
  'BRK-RANGE': { points: [[5,65],[18,45],[31,62],[44,44],[57,61],[70,45],[83,59],[89,43],[95,18]], level: 42, label: 'range breakout', cue: 'Price leaves a clearly defined sideways range.' },
  'BRK-52WH': { points: [[5,72],[18,54],[31,39],[44,52],[57,43],[70,50],[83,40],[89,35],[95,12]], level: 34, label: 'prior 52-week high', cue: 'The final move clears the highest price from the prior year.' },
  'BRK-ATH': { points: [[5,76],[18,59],[31,43],[44,55],[57,38],[70,47],[83,31],[89,27],[95,8]], level: 25, label: 'all-time high', cue: 'The final push enters price territory with no prior recorded high.' },
  'BRK-MULTIY': { points: [[5,67],[18,35],[31,62],[44,38],[57,65],[70,41],[83,60],[90,36],[95,10]], level: 34, label: 'multi-year resistance', cue: 'Several long swings meet the same resistance before the break.' },
  'PB-BRKRET': { points: [[5,75],[18,57],[31,25],[44,15],[57,32],[70,49],[80,44],[88,32],[95,17]], level: 43, label: 'old resistance / new support', cue: 'Price returns to the breakout area, then starts to recover.' },
  'PB-EMA20': { points: [[5,75],[18,57],[31,35],[44,18],[57,31],[69,45],[78,54],[86,42],[95,22]], level: 52, label: '20-day EMA', cue: 'The pullback tests a rising short-term average before bouncing.' },
  'PB-SMA50': { points: [[5,78],[18,59],[31,33],[44,17],[57,30],[70,48],[79,65],[87,49],[95,25]], level: 64, label: '50-day SMA', cue: 'This is a deeper retracement into medium-term trend support.' },
  'TREND-HHHL': { points: [[5,78],[18,62],[29,68],[42,48],[53,56],[66,34],[77,43],[95,18]], level: 0, label: '', cue: 'Each advance reaches higher and each pullback holds above the prior low.' },
  'TREND-S2': { points: [[5,74],[18,50],[31,60],[44,42],[57,52],[70,35],[83,45],[95,27]], level: 61, label: 'rising support', cue: 'Several pullbacks respect an upward-sloping support area.' },
  'TREND-MA': { points: [[5,76],[18,54],[31,61],[44,39],[57,48],[70,28],[83,38],[95,17]], level: 55, label: 'moving average', cue: 'Price remains aligned with a rising trend average.' },
  'COMP-NR7': { points: [[5,69],[18,35],[31,65],[44,39],[57,61],[70,45],[82,56],[90,50],[95,49]], level: 0, label: '', cue: 'The final session has the narrowest range in the sequence.' },
  'COMP-IB': { points: [[5,70],[18,36],[31,64],[44,38],[57,58],[70,43],[82,54],[90,48],[95,51]], level: 0, label: '', cue: 'The final bar sits inside the range of the preceding bar.' },
  'COMP-ATR': { points: [[5,73],[18,31],[31,69],[44,40],[57,62],[70,47],[82,57],[90,51],[95,48]], level: 0, label: '', cue: 'Daily movement contracts progressively across the example.' },
  'COMP-RANGE': { points: [[5,66],[18,43],[31,62],[44,45],[57,60],[70,46],[83,58],[95,48]], level: 42, label: 'range ceiling', cue: 'Repeated swings define a compact range and its boundaries.' },
  'MOM-ACC': { points: [[5,78],[18,71],[31,65],[44,58],[57,49],[70,37],[83,23],[95,10]], level: 0, label: '', cue: 'The slope steepens, illustrating improving momentum rather than a price target.' },
  'MOM-RSL': { points: [[5,75],[18,66],[31,54],[44,47],[57,39],[70,32],[83,25],[95,18]], level: 0, label: '', cue: 'The steady upward path represents persistent relative outperformance.' },
  'MOM-RSB': { points: [[5,72],[18,51],[31,58],[44,44],[57,50],[70,40],[83,44],[90,35],[95,14]], level: 34, label: 'RS high', cue: 'Relative strength breaks above its own earlier high.' },
  'VOL-DRY': { points: [[5,72],[18,35],[31,63],[44,43],[57,57],[70,48],[83,54],[95,49]], level: 0, label: '', cue: 'Price pauses while participation contracts; volume is supporting evidence.' },
  'VOL-EXP': { points: [[5,70],[18,52],[31,58],[44,45],[57,55],[70,43],[83,49],[90,40],[95,16]], level: 39, label: 'breakout level', cue: 'A decisive move through the level is paired with expanded participation.' },
  'FAIL-BRK': { points: [[5,70],[18,54],[31,45],[44,30],[57,20],[69,42],[81,57],[95,70]], level: 43, label: 'lost breakout level', cue: 'Price first clears the level, then quickly falls back through it.' },
  'FAIL-BASE': { points: [[5,64],[18,43],[31,59],[44,46],[57,56],[70,47],[82,62],[95,80]], level: 62, label: 'lost base support', cue: 'The base breaks below the support that defined its structure.' },
  'FAIL-EMA20': { points: [[5,75],[18,49],[31,25],[44,34],[57,51],[70,63],[82,72],[95,84]], level: 55, label: 'lost 20-day EMA', cue: 'The pullback continues through the expected short-term support.' },
  'FAIL-SMA50': { points: [[5,76],[18,51],[31,23],[44,38],[57,55],[70,67],[82,76],[95,88]], level: 67, label: 'lost 50-day SMA', cue: 'The deeper pullback loses medium-term trend support.' },
  'FAIL-STRUCT': { points: [[5,68],[18,39],[31,61],[44,45],[57,56],[70,48],[82,69],[95,86]], level: 65, label: 'invalidation', cue: 'A decisive break invalidates a defining part of the structure.' },
}

function patternExample(patternType) {
  return PATTERN_EXAMPLES[patternType] || PATTERN_EXAMPLES['BASE-VCP']
}

function PatternExampleChart({ patternType }) {
  const example = patternExample(patternType)
  const points = example.points.map(([x, y]) => `${x},${y}`).join(' ')
  const isFailure = patternType.startsWith('FAIL-') || patternType === 'REV-DTOP'
  return <figure className="pattern-example-chart">
    <svg viewBox="0 0 100 100" role="img" aria-label={`Illustrative ${patternType} price shape`} preserveAspectRatio="none">
      {example.level > 0 && <><line x1="5" x2="95" y1={example.level} y2={example.level} className="pattern-example-chart__level" /><text x="6" y={example.level - 3} className="pattern-example-chart__label">{example.label}</text></>}
      <polyline points={points} className={isFailure ? 'pattern-example-chart__line is-failure' : 'pattern-example-chart__line'} />
      <circle cx="95" cy={example.points.at(-1)[1]} r="2.4" className="pattern-example-chart__end" />
    </svg>
    <p className="pattern-example-chart__cue"><strong>How to read it:</strong> {example.cue}</p>
    <figcaption>Illustrative price shape only — not live data, scale, or a trade signal.</figcaption>
  </figure>
}

const tourStyles = {
  options: {
    arrowColor: 'rgb(20 17 12)', backgroundColor: 'rgb(20 17 12)', overlayColor: 'rgb(0 0 0 / 0.68)',
    primaryColor: '#ffdf84', textColor: '#f6ecd6', zIndex: 10000,
  },
  buttonNext: { color: '#20170c', fontWeight: 800 },
  buttonBack: { color: '#f6ecd6' },
  buttonClose: { color: '#f6ecd6' },
}

export default function GuidePage({ onNavigate, onStartTour }) {
  useDocumentTitle('Guide')
  const [selectedPattern, setSelectedPattern] = useState('BASE-VCP')
  const selectedPatternInfo = describePattern(selectedPattern)
  const selectedPatternExample = patternExample(selectedPattern)
  return <section className="page-stack guide-page">
    <PageIntro eyebrow="Product guide" title="Research with a clear process" description="A practical guide to finding and investigating positional-stock evidence in TradeLens." />
    <section className="evidence-card guide-start" aria-labelledby="guide-start-title">
      <div><p className="eyebrow">Quick start</p><h2 id="guide-start-title">Take the guided tour</h2><p>Five short steps introduce the navigation, stock search, workflow, and the limits of the signals you see.</p></div>
      <button className="primary-button" type="button" onClick={onStartTour}>Start interactive tour</button>
    </section>

    <section className="evidence-card pattern-learning" aria-labelledby="pattern-learning-title">
      <div className="section-heading"><div><p className="eyebrow">Pattern guide</p><h2 id="pattern-learning-title">Learn each setup pattern</h2><p>Select a pattern type to see the same name used in Setups, an explanation, confirmation context, and an illustrative shape.</p></div></div>
      <label className="pattern-learning__select">Pattern type
        <select className="select-control" value={selectedPattern} onChange={(event) => setSelectedPattern(event.target.value)}>
          {SUPPORTED_PATTERN_TYPES.map((type) => <option value={type} key={type}>{type}</option>)}
        </select>
      </label>
      <div className="pattern-learning__content">
        <PatternExampleChart patternType={selectedPattern} />
        <div className="pattern-learning__copy">
          <p className="eyebrow">{selectedPattern}</p><h3>{selectedPatternInfo.label}</h3>
          <h4>Pattern structure</h4><p>{selectedPatternInfo.description}</p>
          <h4>What the illustration shows</h4><p>{selectedPatternExample.cue}</p>
          <h4>What to inspect next</h4><p>{selectedPatternInfo.confirmation}</p>
          <div className="pattern-learning__action"><NavigationLink className="secondary-button" to={`/setups?patternType=${encodeURIComponent(selectedPattern)}`} onNavigate={onNavigate}>View {selectedPattern} setups</NavigationLink></div>
        </div>
      </div>
    </section>

    {/* Archived guide reference material intentionally omitted from this focused page.
    <section className="guide-section" data-guide="guide-workflow" aria-labelledby="guide-workflow-title">
      <div className="section-heading"><div><p className="eyebrow">Core workflow</p><h2 id="guide-workflow-title">From market context to a stock decision</h2></div></div>
      <ol className="guide-workflow">
        <li><strong>1. Read the market</strong><p>Open <NavigationLink to="/overview" onNavigate={onNavigate}>Overview</NavigationLink> to check the data date, breadth, market regime, and the highest-ranked active setups.</p></li>
        <li><strong>2. Find leadership</strong><p>Use <NavigationLink to="/sector-rotation" onNavigate={onNavigate}>Sector rotation</NavigationLink> and <NavigationLink to="/indices" onNavigate={onNavigate}>Indices</NavigationLink> to see relative-strength progression. A path shows the last five sessions, not a forecast.</p></li>
        <li><strong>3. Inspect a setup</strong><p>Open <NavigationLink to="/setups" onNavigate={onNavigate}>Setups</NavigationLink>, filter the server-ranked list, then inspect its chart, pivot, support, invalidation, lifecycle, and evidence.</p></li>
        <li><strong>4. Follow the stock</strong><p>Search a stock or add it to <NavigationLink to="/watchlist" onNavigate={onNavigate}>Watchlist</NavigationLink> to track its own five-session rotation path and revisit the evidence.</p></li>
      </ol>
    </section>

    <section className="guide-grid" aria-label="Quick screen guide">
      <article className="evidence-card"><h2>Overview</h2><p>Use the data-as-of label and pipeline status first. The top setups are ranked evidence, not buy calls.</p></article>
      <article className="evidence-card"><h2>Rotation charts</h2><p>Leading and improving indicate stronger relative conditions; weakening and lagging indicate fading conditions. Hover a path to isolate that security, sector, or index.</p></article>
      <article className="evidence-card"><h2>Setup details</h2><p>Pattern state shows where the structure is in its lifecycle. The adjusted chart and measured levels explain why it was detected.</p></article>
      <article className="evidence-card"><h2>Case studies</h2><p>These show how the stock performed after a historical entry over roughly 3 months, 6 months, and 1 year. They are research examples, not profit claims.</p></article>
    </section>

    <section className="guide-section" data-guide="guide-reference" aria-labelledby="guide-reference-title">
      <div className="section-heading"><div><p className="eyebrow">Screen reference</p><h2 id="guide-reference-title">Choose the screen for the question you have</h2></div></div>
      <div className="guide-reference-table" role="region" aria-label="TradeLens screen reference" tabIndex="0">
        <table><thead><tr><th scope="col">Screen</th><th scope="col">Best question</th><th scope="col">How to use it</th></tr></thead><tbody>{screenGuide.map(([screen, question, guidance]) => <tr key={screen}><th scope="row">{screen}</th><td>{question}</td><td>{guidance}</td></tr>)}</tbody></table>
      </div>
    </section>

    <section className="guide-section" aria-labelledby="guide-rotation-title">
      <div className="section-heading"><div><p className="eyebrow">Rotation charts</p><h2 id="guide-rotation-title">How to read relative-strength progression</h2></div></div>
      <div className="guide-quadrants">
        <article><strong>Leading</strong><p>Relative strength is above zero and momentum is positive. Leadership is present; check the path and setup evidence before drawing a conclusion.</p></article>
        <article><strong>Improving</strong><p>Relative strength is below zero but momentum is improving. This can identify early recovery, but it is not confirmation on its own.</p></article>
        <article><strong>Weakening</strong><p>Relative strength is above zero but momentum is fading. Strength may still be positive while leadership loses pace.</p></article>
        <article><strong>Lagging</strong><p>Relative strength and momentum are below zero. Treat it as a context signal, not a prediction that price must fall.</p></article>
      </div>
      <p className="muted-copy">Each trail connects the most recent five sessions. Hover or focus a plotted item to fade the rest and inspect its path. The axes compare relative performance; they do not represent price or return targets.</p>
    </section>

    <section className="guide-section" aria-labelledby="guide-lifecycle-title">
      <div className="section-heading"><div><p className="eyebrow">Pattern lifecycle</p><h2 id="guide-lifecycle-title">Read the state before reading the score</h2></div></div>
      <div className="guide-lifecycle"><article><h3>Early evidence</h3><p><strong>Detected</strong>, <strong>Forming</strong>, and <strong>Mature</strong> mean geometry is emerging. It has not necessarily reached a trigger-ready state.</p></article><article><h3>Actionable evidence</h3><p><strong>Ready</strong> means the stored structure meets readiness criteria. <strong>Triggered</strong> and <strong>Confirmed</strong> record progressively stronger follow-through evidence.</p></article><article><h3>Closed evidence</h3><p><strong>Failed</strong>, <strong>Invalidated</strong>, and <strong>Expired</strong> are retained for research and explainability but excluded from active opportunity ranking.</p></article></div>
    </section>

    <section className="guide-section" aria-labelledby="guide-cases-title">
      <div className="section-heading"><div><p className="eyebrow">Case-study methodology</p><h2 id="guide-cases-title">Use historical cases to learn, not to infer a promise</h2></div></div>
      <div className="guide-grid"><article className="evidence-card"><h3>What is measured</h3><p>Forward stock performance starts from the next-session adjusted open after the historical entry and is centred on approximately 63, 126, and 252 trading sessions.</p></article><article className="evidence-card"><h3>What to compare</h3><p>Compare the pattern, lifecycle, entry rationale, market context, and completeness of each horizon—not only the eventual return.</p></article><article className="evidence-card"><h3>Why a horizon can be incomplete</h3><p>Newer cases may not yet have enough trading sessions for a full 3M, 6M, or 1Y observation. TradeLens labels this rather than inventing a result.</p></article><article className="evidence-card"><h3>What it is not</h3><p>A case study is not a live position, intraday trade log, personalised recommendation, or a claim of future profit.</p></article></div>
    </section>

    <section className="guide-section" aria-labelledby="guide-data-title">
      <div className="section-heading"><div><p className="eyebrow">Data and quality</p><h2 id="guide-data-title">Know what you are looking at</h2></div></div>
      <div className="guide-details"><details open><summary>Data freshness and incomplete work</summary><p>Every market result carries a data-as-of date. If a page says data is stale, partially processed, or unavailable, do not treat it as live. Wait for the next completed end-of-day update or inspect the date before comparing results.</p></details><details><summary>Scores and rankings</summary><p>Setup, quality, maturity, and context scores are separate. Rankings compare evidence within compatible lifecycle states; they are not expected-return estimates or probabilities of success.</p></details><details><summary>Point-in-time historical research</summary><p>Case studies and historical research are designed to use information available at the time. They preserve data, configuration, adjustment, feature, and engine lineage so the evidence can be reproduced.</p></details><details><summary>Filters and links</summary><p>Setups filters and sorting live in the URL so a view can be shared or revisited. The case-study catalog is intentionally a simple browse view; open a case to inspect the complete evidence.</p></details></div>
    </section>

    <section className="guide-section" aria-labelledby="guide-glossary-title">
      <div className="section-heading"><div><p className="eyebrow">Glossary</p><h2 id="guide-glossary-title">Terms used throughout TradeLens</h2></div></div>
      <dl className="guide-glossary">{glossary.map(([term, explanation]) => <div key={term}><dt>{term}</dt><dd>{explanation}</dd></div>)}</dl>
    </section>

    <section className="evidence-card guide-interpretation" data-guide="guide-interpretation" aria-labelledby="guide-interpretation-title">
      <p className="eyebrow">Reading the evidence</p><h2 id="guide-interpretation-title">What TradeLens does—and does not—tell you</h2>
      <ul>
        <li>All displayed market evidence is end-of-day and clearly dated. Treat stale or incomplete data cautiously.</li>
        <li>A setup score ranks evidence quality and alignment. It does not predict returns or probability of success.</li>
        <li>Patterns retain their lifecycle and supporting evidence so you can judge the structure rather than rely on a label alone.</li>
        <li>Case studies focus on forward stock performance after entry. Your position sizing, entry timing, exits, and risk decisions remain your responsibility.</li>
      </ul>
    </section>
    */}
  </section>
}
