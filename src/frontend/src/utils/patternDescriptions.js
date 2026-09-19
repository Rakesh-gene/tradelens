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

const SUPPORTING_PATTERNS = {
  'BASE-TIGHT': ['tight base', 'A tight base is a short, narrow consolidation after an advance. Small price swings show that the stock is holding its gains while supply is limited.', 'Look for a decisive move above the top of the tight range while the lower edge remains intact.'],
  'TREND-HHHL': ['higher highs and higher lows', 'This trend structure shows successive advances reaching higher highs and pullbacks holding at higher lows.', 'The structure weakens if a meaningful prior higher low is lost.'],
  'TREND-S2': ['trend support', 'Price is repeatedly respecting a rising support area, suggesting buyers are continuing to defend the trend.', 'Review whether the next pullback holds support rather than assuming the trend will continue.'],
  'TREND-MA': ['moving-average trend', 'Price is holding above or recovering around key moving averages, which provides a simple view of trend alignment.', 'A moving average is context, not a trigger by itself; combine it with price structure and lifecycle evidence.'],
  'COMP-NR7': ['narrow-range contraction', 'The current session has an unusually narrow range compared with the preceding sessions, showing a temporary reduction in volatility.', 'A later expansion can be worth watching, but direction is not known from compression alone.'],
  'COMP-IB': ['inside-bar compression', 'An inside bar trades entirely within the prior session range, showing a short pause in price movement.', 'The break from the parent range provides the direction to investigate.'],
  'COMP-ATR': ['ATR contraction', 'Average true range has contracted, meaning typical daily movement has become smaller.', 'Compression is supporting evidence; wait for price structure and a trigger to establish direction.'],
  'COMP-RANGE': ['range compression', 'Price has remained in a constrained range, creating a visible boundary for later breakout or breakdown evidence.', 'Use the range edges with volume and lifecycle evidence rather than treating the range alone as a signal.'],
  'MOM-ACC': ['momentum acceleration', 'Relative-strength or price momentum is improving, indicating that the rate of outperformance is increasing.', 'Acceleration is strongest when it agrees with the price structure and market context.'],
  'MOM-RSL': ['relative-strength leadership', 'The stock is outperforming its benchmark over the measured horizon.', 'Leadership can change; compare its five-session progression and price structure before relying on it.'],
  'MOM-RSB': ['relative-strength breakout', 'Relative strength has pushed through a meaningful prior high, signalling renewed outperformance against the benchmark.', 'Confirm that price action and the broader context support the relative-strength move.'],
  'VOL-DRY': ['volume dry-up', 'Trading participation has contracted during a pause or pullback, which can indicate that selling pressure is becoming less active.', 'A dry-up is supporting evidence, not a standalone entry condition.'],
  'VOL-EXP': ['volume expansion', 'Trading participation has expanded meaningfully, often around a breakout or decisive price move.', 'Check whether price held the move; high volume alone does not validate direction.'],
  'FAIL-BRK': ['failed breakout', 'Price moved beyond a breakout level but quickly lost that level and returned to the prior range.', 'It is terminal evidence for that breakout instance and remains visible for research.'],
  'FAIL-BASE': ['failed base', 'A base structure lost the support or invalidation area that was holding its geometry together.', 'The original setup is no longer ranked as active evidence.'],
  'FAIL-EMA20': ['failed EMA pullback', 'A pullback around the 20-day EMA did not hold and price lost the expected support area.', 'Use it as evidence that the pullback thesis weakened, not as an automatic trade instruction.'],
  'FAIL-SMA50': ['failed SMA pullback', 'A pullback around the 50-day SMA lost medium-term support and no longer meets the intended structure.', 'The original setup is retained as terminal evidence for review.'],
  'FAIL-STRUCT': ['structural failure', 'A key geometric feature of the pattern was broken, so the stored structure can no longer be treated as valid.', 'Inspect the event timeline and invalidation level to understand what changed.'],
}

export function describePattern(patternType) {
  const key = String(patternType || '').toUpperCase()
  const supporting = SUPPORTING_PATTERNS[key]
  if (supporting) return { label: supporting[0], description: supporting[1], confirmation: supporting[2] }
  return PATTERNS[key] || {
    label: key ? key.replaceAll('-', ' ').toLowerCase() : 'chart pattern',
    description: 'This pattern was identified from the shape and behavior of price using information available on the detection date.',
    confirmation: 'Use the annotated chart, entry rationale, support, and invalidation levels to understand what qualified and what could weaken the pattern.',
  }
}
