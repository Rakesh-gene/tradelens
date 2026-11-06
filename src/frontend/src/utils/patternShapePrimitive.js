// Only maps server-supplied dates/prices to pixels. Chart lifecycle redraws
// primitives when scrolling, zooming, resizing or changing the price scale.
export default class PatternShapePrimitive {
  constructor(shapes) {
    this.shapes = shapes
    this.paths = []
    this.view = { zOrder: () => 'normal', renderer: () => ({ draw: (target) => this.draw(target) }) }
  }

  attached({ chart, series, requestUpdate }) {
    this.chart = chart
    this.series = series
    requestUpdate()
  }

  detached() { this.chart = null; this.series = null; this.paths = [] }
  paneViews() { return [this.view] }

  updateAllViews() {
    if (!this.chart || !this.series) return
    const x = (date) => this.chart.timeScale().timeToCoordinate(date)
    const y = (price) => this.series.priceToCoordinate(price)
    this.paths = this.shapes.map((shape) => {
      if (shape.kind === 'box') {
        const coordinates = [x(shape.startDate), x(shape.endDate), y(shape.upperPrice), y(shape.lowerPrice)]
        return coordinates.every((value) => value != null && Number.isFinite(value)) ? { ...shape, coordinates } : null
      }
      const coordinates = (shape.points || []).map((point) => [x(point.date), y(point.price)])
      return coordinates.length >= 2 && coordinates.every((point) => point.every((value) => value != null && Number.isFinite(value))) ? { ...shape, coordinates } : null
    }).filter(Boolean)
  }

  draw(target) {
    target.useMediaCoordinateSpace(({ context }) => {
      context.save()
      context.strokeStyle = '#77d9d0'
      context.fillStyle = 'rgba(119, 217, 208, 0.10)'
      context.lineWidth = 2
      this.paths.forEach((shape) => {
        if (shape.kind === 'box') {
          const [left, right, top, bottom] = shape.coordinates
          context.fillRect(left, top, right - left, bottom - top)
          context.strokeRect(left, top, right - left, bottom - top)
        } else {
          context.beginPath()
          shape.coordinates.forEach(([x, y], index) => { if (index === 0) context.moveTo(x, y); else context.lineTo(x, y) })
          context.stroke()
        }
      })
      context.restore()
    })
  }
}
