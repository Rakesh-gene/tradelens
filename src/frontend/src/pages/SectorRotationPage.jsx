import React from 'react'
import SectorRotation from '../components/SectorRotation.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { PageIntro } from '../components/PatternUi.jsx'

export default function SectorRotationPage({ onNavigate, onUnauthorized }) {
  useDocumentTitle('Sector rotation')
  return <>
    <PageIntro eyebrow="Market leadership" title="Sector rotation" description="See which sectors are gaining or losing strength relative to the broader market." />
    <SectorRotation onNavigate={onNavigate} onUnauthorized={onUnauthorized} />
  </>
}
