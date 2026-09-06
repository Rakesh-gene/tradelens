import React from 'react'
import { apiGet } from '../apiClient.js'
import useApiResource from '../useApiResource.js'
import { formatMarketDate, formatPrice } from '../formatters.js'
import {
  MeasurementGrid,
  PageIntro,
  ResourceState,
  Score,
  SetupCard,
  StateBadge,
} from '../components/PatternUi.jsx'

function SupportingEvidence({ title, items }) {
  return <article className="evidence-card">
    <h2>{title}</h2>
    {items.length
      ? <div className="tag-list">{items.map((item) => <span key={item.patternInstanceId}>{item.variant || item.patternType}</span>)}</div>
      : <p className="muted-copy">No active {title.toLowerCase()} evidence.</p>}
  </article>
}

export default function SecurityPage({ isin, onNavigate, onUnauthorized }) {
  const resource = useApiResource(
    isin,
    (signal) => apiGet(`/api/securities/${encodeURIComponent(isin)}/fingerprint`, { signal, onUnauthorized }),
  )

  return <ResourceState status={resource.status} error={resource.error} onRetry={resource.reload}>
    {resource.data && (() => {
      const fingerprint = resource.data
      const primary = fingerprint.primarySetup
      return <>
        <PageIntro
          eyebrow="Technical fingerprint"
          title={fingerprint.security.symbol || fingerprint.security.isin}
          description={`${fingerprint.security.name || 'NSE security'}${fingerprint.security.sectorName ? ` - ${fingerprint.security.sectorName}` : ''}`}
          date={fingerprint.dataAsOf}
        />

        <section className="detail-grid">
          <article className="evidence-card">
            <h2>Trend and moving averages</h2>
            <MeasurementGrid values={fingerprint.trend} />
          </article>
          <article className="evidence-card">
            <h2>Current scores</h2>
            <Score label="Setup" value={fingerprint.scores.setup} />
            <Score label="Quality" value={fingerprint.scores.quality} />
            <Score label="Maturity" value={fingerprint.scores.maturity} />
            <Score label="Context" value={fingerprint.scores.context} />
            <p className="ranking-note">Ranking score, not historical probability.</p>
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
          <button type="button" className="text-button" onClick={() => onNavigate(`/patterns/${primary.patternInstanceId}`)}>Inspect full evidence -&gt;</button>
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
          {fingerprint.recentEvents.length
            ? <ol className="timeline">{fingerprint.recentEvents.map((event) => <li key={event.eventId}><span>{formatMarketDate(event.effectiveDate)}</span><strong>{event.eventType}</strong><p>{event.previousState || 'Created'} to {event.newState}</p></li>)}</ol>
            : <p className="muted-copy">No lifecycle events recorded.</p>}
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
