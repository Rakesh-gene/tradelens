import { useEffect, useState } from 'react'
import { ACTIONS, EVENTS, Joyride, STATUS } from 'react-joyride'

const steps = [
  { target: '.app-nav a[href="/overview"]', waitFor: '/overview', title: '1. Open Overview', content: 'Click Overview in the navigation. The tour will then show you what to check first on the real page.', hideFooter: true },
  { target: '.page-intro', title: 'Read market context', content: 'Start with the data date, then check market regime, breadth, and lifecycle counts below. Click a lifecycle count whenever you want to open matching setups.' },
  { target: '.app-nav a[href="/sector-rotation"]', waitFor: '/sector-rotation', title: '2. Open Sector rotation', content: 'Click Sector rotation to continue. You will use this page to find where relative strength is building.', hideFooter: true },
  { target: '.sector-rotation', title: 'Compare sector progression', content: 'Hover a five-session path to fade the other sectors and inspect its progression. Click a sector to reveal its strongest stocks. This is context, not a forecast.' },
  { target: '.app-nav a[href="/setups"]', waitFor: '/setups', title: '3. Open Setups', content: 'Click Setups to learn how to narrow the active-pattern list.', hideFooter: true },
  { target: '.filter-bar', title: 'Filter the setup list', content: 'Choose a lifecycle state, pattern type, score, or ranking and click Apply filters. The resulting URL keeps the exact view shareable and repeatable.' },
  { target: '.security-jump', title: 'Search a stock and add it', content: 'Type an NSE symbol or company name. Select a result to inspect the stock, or click Add beside it to place that equity on your Watchlist.' },
  { target: '.app-nav a[href="/watchlist"]', waitFor: '/watchlist', title: '4. Open Watchlist', content: 'Click Watchlist to see how saved stocks are monitored.', hideFooter: true },
  { target: '.watchlist-toolbar', title: 'Switch how you review names', content: 'Choose Cards, List, or Quadrant. The Quadrant view connects five sessions so you can see progression instead of only a current zone.' },
  { target: '.app-nav a[href="/indices"]', waitFor: '/indices', title: '5. Open Indices', content: 'Click Indices to compare broad-market, sectoral, and thematic benchmark behaviour.', hideFooter: true },
  { target: '.watchlist-toolbar', title: 'Read index rotation', content: 'Switch to Quadrant to compare index paths. Click an index to open its public index detail page—internal index identifiers are never used in the address bar.' },
  { target: '.app-nav a[href="/case-studies"]', waitFor: '/case-studies', title: '6. Open Case studies', content: 'Click Case studies to finish with historical evidence.', hideFooter: true },
  { target: '.case-study-catalog-toolbar', title: 'Inspect comparable history', content: 'Open a case to see why it qualified, its chart and entry rationale, then the stock’s 3M, 6M, and 1Y performance after entry. These are research examples, not predictions.' },
].map((step) => ({ ...step, skipBeacon: true, ...(step.waitFor ? { buttons: [] } : {}) }))

export default function ProductGuideTour({ active, stepIndex, pathname, onStepIndexChange, onFinish }) {
  const [targetReady, setTargetReady] = useState(false)
  const step = steps[stepIndex]
  useEffect(() => {
    setTargetReady(false)
    if (!active || !step) return undefined
    let timer
    const waitForTarget = () => {
      if (document.querySelector(step.target)) setTargetReady(true)
      else timer = window.setTimeout(waitForTarget, 60)
    }
    waitForTarget()
    return () => window.clearTimeout(timer)
  }, [active, step, pathname])
  useEffect(() => {
    if (active && step?.waitFor === pathname) onStepIndexChange(stepIndex + 1)
  }, [active, pathname, step, stepIndex, onStepIndexChange])
  const callback = ({ action, index, status, type }) => {
    if ([STATUS.FINISHED, STATUS.SKIPPED].includes(status)) { onFinish(); return }
    if (type !== EVENTS.STEP_AFTER || steps[index]?.waitFor) return
    const next = action === ACTIONS.PREV ? index - 1 : index + 1
    if (next < 0 || next >= steps.length) { onFinish(); return }
    onStepIndexChange(next)
  }
  return <Joyride continuous run={active && targetReady} stepIndex={stepIndex} steps={steps} onEvent={callback} options={{ arrowColor: 'rgb(20 17 12)', backgroundColor: 'rgb(20 17 12)', overlayColor: 'rgb(0 0 0 / 0.68)', primaryColor: '#ffdf84', textColor: '#f6ecd6', zIndex: 10000, showProgress: true, skipBeacon: true, scrollOffset: 96, locale: { back: 'Back', close: 'Close', last: 'Finish', next: 'Next', skip: 'Skip tour' } }} />
}
