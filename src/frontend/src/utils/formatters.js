const number = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 1 })
const money = new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 })

export const formatScore = (value) => value == null ? 'Not available' : number.format(Number(value))
export const formatPercent = (value, { signed = false } = {}) => value == null ? 'Not available' : `${signed && Number(value) > 0 ? '+' : ''}${number.format(Number(value))}%`
export const formatPrice = (value, currency = 'INR') => value == null ? 'Not available' : (currency === 'INR' ? money : new Intl.NumberFormat('en-IN', { style: 'currency', currency, maximumFractionDigits: 2 })).format(Number(value))
export const formatCompactNumber = (value) => value == null ? 'Not available' : new Intl.NumberFormat('en-IN', { notation: 'compact', maximumFractionDigits: 1 }).format(Number(value))
export const formatMarketDate = (value) => value ? new Intl.DateTimeFormat('en-IN', { dateStyle: 'medium' }).format(new Date(`${value}T00:00:00`)) : 'Not available'
export const labelize = (value) => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, (letter) => letter.toUpperCase())
