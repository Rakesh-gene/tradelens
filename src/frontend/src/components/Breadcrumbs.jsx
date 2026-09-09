import NavigationLink from './NavigationLink.jsx'

export default function Breadcrumbs({ items, onNavigate }) {
  return <nav className="breadcrumbs" aria-label="Breadcrumb"><ol>{items.map((item, index) => <li key={item.label}>{item.to && index < items.length - 1 ? <NavigationLink to={item.to} onNavigate={onNavigate}>{item.label}</NavigationLink> : <span aria-current={index === items.length - 1 ? 'page' : undefined}>{item.label}</span>}</li>)}</ol></nav>
}
