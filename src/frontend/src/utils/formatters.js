const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 3 })
const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 3 })

export const formatNumber = (value) => value == null ? 'Not available' : number.format(Number(value))
export const formatScore = (value) => value == null ? 'Not available' : number.format(Number(value))
export const formatPercent = (value, { signed = false } = {}) => value == null ? 'Not available' : `${signed && Number(value) > 0 ? '+' : ''}${number.format(Number(value))}%`
export const formatPrice = (value, currency = 'INR') => value == null ? 'Not available' : (currency === 'INR' ? money : new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 3 })).format(Number(value))
export const formatCompactNumber = (value) => value == null ? 'Not available' : new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 3 }).format(Number(value))
export const formatMarketDate = (value) => value ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(`${value}T00:00:00`)) : 'Not available'
export const labelize = (value) => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
export const formatMeasurementValue = (value) => typeof value === 'boolean' ? (value ? 'Yes' : 'No') : typeof value === 'number' ? formatNumber(value) : String(value)
export const roundStructuredNumbers = (value) => {
  if (typeof value === 'number') return Number(value.toFixed(3))
  if (Array.isArray(value)) return value.map(roundStructuredNumbers)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, roundStructuredNumbers(item)]))
  return value
}
