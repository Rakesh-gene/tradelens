function hasValue(value) {
  return value !== undefined && value !== null && value !== ''
}

export function buildQuery(query = {}) {
  const parameters = new URLSearchParams()
  Object.entries(query).forEach(([name, rawValue]) => {
    const values = Array.isArray(rawValue) ? rawValue : [rawValue]
    values.filter(hasValue).forEach((value) => parameters.append(name, String(value)))
  })
  return parameters.toString()
}

export function withQuery(path, query) {
  const value = buildQuery(query)
  return value ? `${path}?${value}` : path
}
