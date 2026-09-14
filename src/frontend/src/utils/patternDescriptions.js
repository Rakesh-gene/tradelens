const PATTERNS = {
  'REV-DBOT': {
    label: 'double bottom',
    description: 'A double bottom forms when price falls to a similar low twice, with a meaningful rebound between the two lows. It can show that selling pressure is weakening and buyers are defending the same area.',
    confirmation: 'The pattern becomes more meaningful when price moves above the rebound high, often called the neckline. That breakout is the level to compare with support and invalidation on the chart.',
  },
  'REV-DTOP': {
    label: 'double top',
    description: 'A double top forms when price reaches a similar high twice and pulls back between the two attempts. It can show that buying pressure is fading near resistance.',
    confirmation: 'The pattern becomes more meaningful when price falls below the pullback low, often called the neckline. The chart shows where that break occurred and which levels would invalidate the pattern.',
  },
  'HARM-ABCD': {
    label: 'AB=CD pattern',
    description: 'An AB=CD pattern is a four-point price swing in which the final move is similar in size and rhythm to the first move. Traders use the completion area to watch for a possible change in direction.',
    confirmation: 'The shape alone is not enough. Price reaction, supporting signals, and the invalidation level show whether the expected reversal actually began.',
  },
  'BASE-VCP': {
    label: 'volatility contraction pattern',
    description: 'A volatility contraction pattern forms when successive pullbacks become smaller and price movement tightens. This can indicate that available supply is being absorbed near a potential breakout level.',
    confirmation: 'A decisive move above the pivot, ideally with stronger participation, is the key confirmation to inspect on the chart.',
  },
  'BASE-FLAT': {
    label: 'flat base',
    description: 'A flat base is a relatively tight sideways pause after an earlier advance. Price repeatedly holds within a shallow range while buyers and sellers reach a temporary balance.',
    confirmation: 'The upper edge of the range acts as the pivot. A strong close above it signals that demand may be taking control again.',
  },
  'BASE-52WH': {
    label: '52-week-high base',
    description: 'A 52-week-high base is a consolidation that develops close to the stock’s highest price of the past year. Holding near the high can signal persistent demand despite earlier gains.',
    confirmation: 'The chart shows whether price cleared the base pivot while the nearby support and invalidation levels continued to hold.',
  },
  'BRK-RANGE': {
    label: 'range breakout',
    description: 'A range breakout occurs when price closes beyond the upper boundary of a clearly defined trading range after spending time moving sideways.',
    confirmation: 'The breakout level should remain visible because a quick move back into the old range can weaken the signal.',
  },
  'BRK-52WH': {
    label: '52-week-high breakout',
    description: 'A 52-week-high breakout occurs when price moves above its highest level of the previous year. It shows that the stock has cleared a widely watched area of resistance.',
    confirmation: 'Follow-through above the old high and continued support around the breakout level help distinguish a sustained move from a brief spike.',
  },
  'BRK-ATH': {
    label: 'all-time-high breakout',
    description: 'An all-time-high breakout occurs when price moves above every previously recorded high. With no historical overhead resistance, the focus shifts to whether the breakout can hold.',
    confirmation: 'The chart highlights the breakout level, subsequent price action, and the support area that would weaken the pattern if lost.',
  },
  'BRK-MULTIY': {
    label: 'multi-year breakout',
    description: 'A multi-year breakout occurs when price clears resistance that has contained it for several years. Breaking such a long-standing ceiling can mark a major change in market perception.',
    confirmation: 'Sustained trading above the old resistance and healthy participation provide stronger evidence than a single close above it.',
  },
  'PB-BRKRET': {
    label: 'breakout retest',
    description: 'A breakout retest happens when price returns to a recently cleared resistance level and begins to hold it as support. It offers a second look at the original breakout.',
    confirmation: 'The important evidence is whether buyers defend the old breakout level and price resumes its move without losing the invalidation area.',
  },
  'PB-EMA20': {
    label: '20-day EMA pullback',
    description: 'A 20-day EMA pullback is a short-term retreat toward the stock’s 20-day exponential moving average while the broader uptrend remains intact.',
    confirmation: 'A constructive rebound from the average, supported by price and volume evidence, suggests that buyers are returning after the pause.',
  },
  'PB-SMA50': {
    label: '50-day SMA pullback',
    description: 'A 50-day SMA pullback occurs when price retreats toward its 50-day simple moving average within a broader trend. This is a deeper test of medium-term support.',
    confirmation: 'The case is stronger when price holds the average, avoids the invalidation level, and begins to recover with improving evidence.',
  },
}

export function describePattern(patternType) {
  const key = String(patternType || '').toUpperCase()
  return PATTERNS[key] || {
    label: key ? key.replaceAll('-', ' ').toLowerCase() : 'chart pattern',
    description: 'This pattern was identified from the shape and behavior of price using information available on the detection date.',
    confirmation: 'Use the annotated chart, entry rationale, support, and invalidation levels to understand what qualified and what could weaken the pattern.',
  }
}
