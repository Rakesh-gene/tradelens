export function shouldHandleNavigation(event) {
  return !event.defaultPrevented
    && event.button === 0
    && !event.altKey
    && !event.ctrlKey
    && !event.metaKey
    && !event.shiftKey
}

export default function NavigationLink({ to, onNavigate, children, ...props }) {
  const handleClick = (event) => {
    if (!shouldHandleNavigation(event) || props.target === '_blank') return
    event.preventDefault()
    onNavigate(to)
  }
  return <a {...props} href={to} onClick={handleClick}>{children}</a>
}
