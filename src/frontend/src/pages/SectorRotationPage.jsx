import React from 'react'
import SectorRotation from '../components/SectorRotation.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'
import { PageIntro } from '../components/PatternUi.jsx'

export default function SectorRotationPage({ onNavigate, onUnauthorized }) {
  useDocumentTitle('Sector rotation')
  return <>
    <PageIntro title="Sector rotation" />
    <SectorRotation onNavigate={onNavigate} onUnauthorized={onUnauthorized} />
  </>
}
