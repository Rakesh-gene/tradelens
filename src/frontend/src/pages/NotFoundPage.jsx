import SiteFooter from '../components/SiteFooter.jsx'
import useDocumentTitle from '../hooks/useDocumentTitle.js'

export default function NotFoundPage({ onNavigate, withFooter = false }) {
  useDocumentTitle('Page not found')
  const content = (
    <main className="standalone-state" aria-labelledby="not-found-title">
      <p className="eyebrow">404</p>
      <h1 id="not-found-title">Page not found</h1>
      <button className="primary-button" type="button" onClick={() => onNavigate('/overview')}>Return to overview</button>
    </main>
  )
  return withFooter ? <div className="public-shell">{content}<SiteFooter /></div> : content
}
