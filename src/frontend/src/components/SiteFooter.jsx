export default function SiteFooter() {
  return <footer className="site-footer">
    <div className="site-footer__inner">
      <span>© {new Date().getFullYear()} TradeLens</span>
      <p><strong>Disclaimer:</strong> TradeLens provides market research and screening tools, not investment advice. Trading and investing involve risk, including loss of capital. Verify the data and make decisions based on your own circumstances.</p>
    </div>
  </footer>
}
