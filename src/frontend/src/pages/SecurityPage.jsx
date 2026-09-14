import React, { useState } from 'react'
import { getSecurityChart, getSecurityFingerprint } from '../api/securityApi.js'
import useApiResource from '../useApiResource.js'
import { formatPrice } from '../utils/formatters.js'
import {
  MeasurementGrid,
  PageIntro,
  Score,
  SetupCard,
  StateBadge,
} from '../components/PatternUi.jsx'
import PatternCandlestickChart from '../components/PatternCandlestickChart.jsx'
import PatternTimeline from '../components/PatternTimeline.jsx'
import { ResourceState } from '../components/ResourceStates.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import NavigationLink from '../components/NavigationLink.jsx'
import { buildPatternPath } from '../routing/routes.js'
import DecisionSummary from '../components/DecisionSummary.jsx'
import WatchlistButton from '../components/WatchlistButton.jsx'

function SupportingEvidence({ title, items }) {
  return <article className="evidence-card">
    <h2>{title}</h2>
    {items.length
      ? <div className="tag-list">{items.map((item) => <span key={item.patternInstanceId}>{item.variant || item.patternType}</span>)}</div>
      : <p className="muted-copy">No active {title.toLowerCase()} evidence.</p>}
  </article>
}

export default function SecurityPage({ isin, onNavigate, onUnauthorized }) {
  useDocumentTitle('Security fingerprint')
  const [chartRange, setChartRange] = useState('6m')
  const resource = useApiResource(
    `${isin}:${chartRange}`,
    async (signal) => {
      const [fingerprint, chart] = await Promise.all([
        getSecurityFingerprint(isin, { signal, onUnauthorized }),
        getSecurityChart(isin, { range: chartRange }, { signal, onUnauthorized }),
      ])
      return { fingerprint, chart }
    },
  )

  return <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
    {resource.data && (() => {
      const { fingerprint, chart } = resource.data
      const primary = fingerprint.primarySetup
      const scoreSource = fingerprint.scoreSource || fingerprint.activePatterns.find(
        (item) => item.patternClass !== 'FAILURE' && item.setupScore != null,
      )
      const currentScores = Object.values(fingerprint.scores || {}).some((value) => value != null)
        ? fingerprint.scores
        : {
          setup: scoreSource?.setupScore,
          quality: scoreSource?.qualityScore,
          maturity: scoreSource?.maturityScore,
          context: scoreSource?.contextScore,
        }
      const scoreEntries = [
        ['Setup', currentScores.setup],
        ['Quality', currentScores.quality],
        ['Maturity', currentScores.maturity],
        ['Context', currentScores.context],
      ].filter(([, value]) => value != null)
      const classification = fingerprint.classification || {}
      const classificationValues = {
        macroSector: classification.macroSector?.name,
        sector: classification.sector?.name,
        industry: classification.industry?.name,
        basicIndustry: classification.basicIndustry?.name,
        status: classification.status,
      }
      return <>
        <PageIntro
          eyebrow="Stock overview"
          title={fingerprint.security.symbol || fingerprint.security.isin}
          description={`${fingerprint.security.name || 'NSE security'}${fingerprint.security.sectorName ? ` · ${fingerprint.security.sectorName}` : ''}. Review its trend, price levels, relative strength, and active patterns.`}
          date={fingerprint.dataAsOf}
        />
        <WatchlistButton isin={isin} onUnauthorized={onUnauthorized} />

        {primary?.decision && <section className="evidence-card security-decision"><div className="card-title"><div><p className="eyebrow">Decision intelligence</p><h2>Current operating view</h2></div><StateBadge state={primary.state} /></div><DecisionSummary decision={primary.decision} /></section>}

        <section className="evidence-card"><PatternCandlestickChart candles={chart.candles} levels={chart.levels} evidence={chart.evidence} corporateActions={chart.corporateActions} range={chartRange} onRangeChange={setChartRange} /></section>

        <section className="detail-grid">
          <article className="evidence-card"><h2>Company classification</h2><MeasurementGrid values={classificationValues} /></article>
          <article className="evidence-card"><h2>Sector strength</h2><MeasurementGrid values={fingerprint.sectorStrength || {}} /></article>
        </section>

        <section className="detail-grid">
          <article className="evidence-card">
            <h2>Trend and moving averages</h2>
            <MeasurementGrid values={fingerprint.trend} />
          </article>
          <article className="evidence-card">
            <h2>Current scores</h2>
            {scoreEntries.length
              ? <>
                {scoreSource && <p className="muted-copy">Best active signal: {scoreSource.variant || scoreSource.patternType}</p>}
                {scoreEntries.map(([label, value]) => <Score key={label} label={label} value={value} />)}
              </>
              : <p className="muted-copy">No active scored signal is available for this equity.</p>}
          </article>
        </section>

        {primary && <section className="evidence-card">
          <div className="card-title">
            <div><p className="eyebrow">Primary setup</p><h2>{primary.variant || primary.patternType}</h2></div>
            <StateBadge state={primary.state} />
          </div>
          <div className="level-grid">
            <div><span>Maturity</span><strong>{primary.maturityBand || '-'}</strong></div>
            <div><span>Pivot</span><strong>{formatPrice(primary.pivotPrice)}</strong></div>
            <div><span>Support</span><strong>{formatPrice(primary.supportPrice)}</strong></div>
            <div><span>Invalidation</span><strong>{formatPrice(primary.invalidationPrice)}</strong></div>
          </div>
          <div className="tag-list">{primary.supportingPatterns.map((pattern) => <span key={pattern}>{pattern}</span>)}</div>
          <NavigationLink className="text-button" to={buildPatternPath(primary.patternInstanceId)} onNavigate={onNavigate}>Inspect full evidence →</NavigationLink>
        </section>}

        <section className="detail-grid">
          <article className="evidence-card"><h2>Relative strength</h2><MeasurementGrid values={fingerprint.relativeStrength} /></article>
          <article className="evidence-card"><h2>Volume and liquidity</h2><MeasurementGrid values={fingerprint.volume} /></article>
          <article className="evidence-card"><h2>Price location</h2><MeasurementGrid values={fingerprint.location} /></article>
        </section>

        <section className="detail-grid">
          <SupportingEvidence title="Compression" items={fingerprint.compression} />
          <SupportingEvidence title="Momentum" items={fingerprint.momentum} />
          <article className="evidence-card"><h2>Market context</h2><MeasurementGrid values={fingerprint.context} /></article>
        </section>

        <section className="section-heading"><div><p className="eyebrow">Active evidence</p><h2>Patterns</h2></div></section>
        {fingerprint.activePatterns.length
          ? <div className="setup-grid">{fingerprint.activePatterns.map((setup) => <SetupCard key={setup.patternInstanceId} setup={setup} onNavigate={onNavigate} />)}</div>
          : <div className="empty-panel"><h2>No primary setup right now</h2><p>The trend, relative-strength, volume, and location evidence remains available above.</p></div>}

        <section className="evidence-card">
          <h2>Recent lifecycle events</h2>
          <PatternTimeline events={fingerprint.recentEvents} />
        </section>

        <section className="lineage" aria-label="Data lineage">
          <span>Engine {fingerprint.lineage.engineVersion || '-'}</span>
          <span>Configuration {fingerprint.lineage.configurationVersion || '-'}</span>
          <span>Features {fingerprint.lineage.featureVersion || '-'}</span>
          <span>Adjustments {fingerprint.lineage.adjustmentVersion || '-'}</span>
        </section>
      </>
    })()}
  </ResourceState>
}
