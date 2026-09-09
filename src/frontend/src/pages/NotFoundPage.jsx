export default function NotFoundPage({ onNavigate }) {
  return (
    <main className="standalone-state" aria-labelledby="not-found-title">
      <p className="eyebrow">404 · Page not found</p>
      <h1 id="not-found-title">This route does not exist.</h1>
      <p>The address may be incomplete, expired, or copied incorrectly.</p>
      <button className="primary-button" type="button" onClick={() => onNavigate('/overview')}>Return to overview</button>
    </main>
  )
}
