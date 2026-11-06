"""Dated chart geometry from persisted pattern evidence and adjusted bars.

This describes recorded structures; it never runs a detector or infers a trade.
"""
from datetime import date
from decimal import Decimal, InvalidOperation


def _date(value):
    try:
        return value if isinstance(value, date) else date.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None


def _price(value):
    try:
        result = Decimal(str(value))
        return result if result.is_finite() and result > 0 else None
    except (TypeError, ValueError, InvalidOperation):
        return None


def pattern_annotations(patterns, bars, as_of, adjustment_version, selected_id=None):
    as_of = _date(as_of)
    dated = {_date(bar.get('trading_date')): bar for bar in bars if _date(bar.get('trading_date')) is not None}
    dates = sorted(day for day in dated if as_of and day <= as_of)
    if not dates:
        return []
    result = []
    for row in patterns:
        identifier, kind = str(row.get('id')), row.get('pattern_type') or ''
        if not kind.startswith(('BASE-', 'BRK-', 'PB-', 'REV-', 'HARM-')):
            continue
        if row.get('adjustment_version') != adjustment_version:
            continue
        confirmation = _date(row.get('confirmation_date'))
        known_dates = [_date(row.get(key)) for key in ('detected_date', 'trigger_date')]
        if confirmation and (confirmation > as_of or any(day and day > confirmation for day in known_dates)):
            confirmation = None
        selected = selected_id is not None and identifier == str(selected_id)
        if not confirmation and not selected:
            continue
        measurements = row.get('measurements') or {}
        pivot = _price(row.get('pivot_price'))
        start = _date(row.get('start_date'))
        end = _date(row.get('trigger_date')) or confirmation or _date(row.get('last_updated_date'))
        shapes = []
        # A later snapshot's geometry cannot describe an earlier evidence date.
        snapshot_date = _date(row.get('last_updated_date'))
        if start and end and start <= end <= as_of and snapshot_date and snapshot_date <= as_of:
            window = [day for day in dates if start <= day <= end]
            if len(window) >= 2:
                first, last = window[0], window[-1]

                def line(label, value):
                    if value is not None:
                        shapes.append({'kind': 'line', 'label': label, 'points': [
                            {'date': first, 'price': value}, {'date': last, 'price': value}]})

                def box(label, upper, lower):
                    if upper is not None and lower is not None and upper > lower:
                        shapes.append({'kind': 'box', 'label': label, 'startDate': first, 'endDate': last,
                                       'upperPrice': upper, 'lowerPrice': lower})
                    else:
                        line(label, upper)

                if kind.startswith('BASE-'):
                    box('Base range', pivot, _price(row.get('support_price')))
                elif kind.startswith('BRK-'):
                    line('Breakout resistance', pivot)
                elif kind == 'PB-BRKRET':
                    box('Breakout retest zone', _price(measurements.get('retest_zone_upper')),
                        _price(measurements.get('retest_zone_lower')))
                    line('Reclaim trigger', pivot)
                elif kind in {'PB-EMA20', 'PB-SMA50'}:
                    field = 'ema_20' if kind == 'PB-EMA20' else 'sma_50'
                    points = [{'date': day, 'price': _price(dated[day].get(field))} for day in window]
                    points = [point for point in points if point['price'] is not None]
                    if len(points) >= 2 and row.get('timeframe', '1D') == '1D':
                        shapes.append({'kind': 'line', 'label': 'EMA20 pullback' if field == 'ema_20' else 'SMA50 pullback', 'points': points})
                    line('Pullback trigger', pivot)
                elif kind in {'REV-DBOT', 'REV-DTOP', 'HARM-ABCD'}:
                    # Daily pivot candles reproduce the persisted pivot dates.
                    # Do not substitute daily extrema for weekly/monthly pivots.
                    if row.get('timeframe', '1D') == '1D':
                        if kind == 'HARM-ABCD':
                            keys = ['a_date', 'b_date', 'c_date', 'd_date']
                            fields = ['high_price', 'low_price', 'high_price', 'low_price'] if row.get('direction') == 'BULLISH' else ['low_price', 'high_price', 'low_price', 'high_price']
                        else:
                            keys = ['first_pivot_date', 'neckline_pivot_date', 'second_pivot_date']
                            fields = ['low_price', 'high_price', 'low_price'] if kind == 'REV-DBOT' else ['high_price', 'low_price', 'high_price']
                        points = [{'date': _date(measurements.get(key)),
                                   'price': _price(dated.get(_date(measurements.get(key)), {}).get(field))} for key, field in zip(keys, fields)]
                        if all(point['date'] in window and point['price'] is not None for point in points) and all(points[i]['date'] < points[i + 1]['date'] for i in range(len(points) - 1)):
                            shapes.append({'kind': 'line', 'label': row.get('variant') or kind, 'points': points})
                    line('Neckline' if kind.startswith('REV-') else 'Point C trigger', pivot)
        result.append({'patternInstanceId': identifier, 'patternType': kind, 'variant': row.get('variant'),
                       'state': row.get('state'), 'direction': row.get('direction'), 'confirmationDate': confirmation,
                       'confirmationPrice': _price(dated.get(confirmation, {}).get('close_price')) if confirmation else None,
                       'startDate': start, 'structureEndDate': end, 'shapes': shapes,
                       'geometryAvailable': bool(shapes), 'adjustmentVersion': adjustment_version})
    return sorted(result, key=lambda item: (item['confirmationDate'] or date.min, item['patternInstanceId']))
