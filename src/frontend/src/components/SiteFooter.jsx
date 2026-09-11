import { FULL_DISCLAIMER } from '../disclaimerCopy'

export default function SiteFooter() {
  return <footer className="site-footer">
    <div className="site-footer__inner">
      <span>© {new Date().getFullYear()} TradeLens</span>
      <p><strong>Important disclaimer:</strong> {FULL_DISCLAIMER}</p>
    </div>
  </footer>
}
