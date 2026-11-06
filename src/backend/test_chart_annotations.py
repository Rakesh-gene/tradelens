from datetime import date, timedelta
from decimal import Decimal
import unittest

from pattern_engine.chart_annotations import pattern_annotations
from repositories.pattern_queries import InMemoryPatternQueryRepository
from pattern_engine.query_service import PatternQueryService, browser_payload
from test_pattern_queries import _pattern

START = date(2026, 10, 1)
BARS = [{'trading_date': START + timedelta(days=i), 'close_price': Decimal(110),
         'high_price': Decimal(115), 'low_price': Decimal(95), 'ema_20': Decimal(102), 'sma_50': Decimal(99)} for i in range(8)]
END = BARS[-1]['trading_date']


def pattern(kind='BASE-FLAT', **changes):
    return {**_pattern(), 'start_date': START, 'detected_date': START,
            'trigger_date': START + timedelta(days=4), 'confirmation_date': START + timedelta(days=5),
            'last_updated_date': END, 'state': 'CONFIRMED', 'pattern_type': kind, **changes}


class ChartAnnotationTests(unittest.TestCase):
    def annotations(self, row, **options):
        return pattern_annotations([row], BARS, END, 'av1', **options)

    def test_base_box_and_confirmation_use_stored_geometry_and_actual_confirmation_date(self):
        row = self.annotations(pattern())[0]
        self.assertEqual(START + timedelta(days=5), row['confirmationDate'])
        self.assertEqual(Decimal(110), row['confirmationPrice'])
        self.assertEqual({'kind': 'box', 'label': 'Base range', 'startDate': START, 'endDate': START + timedelta(days=4),
                          'upperPrice': Decimal(100), 'lowerPrice': Decimal(90)}, row['shapes'][0])

    def test_breakout_retest_and_ma_pullbacks_have_distinct_shapes(self):
        breakout = self.annotations(pattern('BRK-RANGE'))[0]
        self.assertEqual('Breakout resistance', breakout['shapes'][0]['label'])
        retest = self.annotations(pattern('PB-BRKRET', measurements={'retest_zone_lower': 97, 'retest_zone_upper': 103}))[0]
        self.assertEqual('box', retest['shapes'][0]['kind'])
        self.assertEqual('Reclaim trigger', retest['shapes'][1]['label'])
        for kind, label in (('PB-EMA20', 'EMA20 pullback'), ('PB-SMA50', 'SMA50 pullback')):
            self.assertEqual(label, self.annotations(pattern(kind))[0]['shapes'][0]['label'])

    def test_unconfirmed_state_never_infers_confirmation_from_detection_trigger_or_score(self):
        for state in ('DETECTED', 'READY', 'TRIGGERED', 'CONFIRMED'):
            row = pattern(state=state, confirmation_date=None)
            self.assertEqual([], self.annotations(row))
            selected = self.annotations(row, selected_id=row['id'])[0]
            self.assertIsNone(selected['confirmationDate'])
            self.assertTrue(selected['shapes'])

    def test_rejects_future_confirmation_future_geometry_and_wrong_adjustment_version(self):
        self.assertEqual([], self.annotations(pattern(confirmation_date=END + timedelta(days=1))))
        self.assertEqual([], self.annotations(pattern(adjustment_version='wrong')))
        newer = self.annotations(pattern(last_updated_date=END + timedelta(days=1)))[0]
        self.assertEqual([], newer['shapes'])
        self.assertIsNotNone(newer['confirmationDate'])
        self.assertEqual([], self.annotations(pattern('TREND-MA')))

    def test_historical_confirmation_survives_terminal_state_with_current_state_label(self):
        result = self.annotations(pattern(state='FAILED', terminal_date=END))[0]
        self.assertEqual('FAILED', result['state'])
        self.assertEqual(START + timedelta(days=5), result['confirmationDate'])

    def test_reversal_points_are_server_supplied_and_partial_geometry_is_not_invented(self):
        measurements = {'first_pivot_date': START, 'neckline_pivot_date': START + timedelta(days=1), 'second_pivot_date': START + timedelta(days=2)}
        result = self.annotations(pattern('REV-DBOT', measurements=measurements))[0]
        self.assertEqual([Decimal(95), Decimal(115), Decimal(95)], [point['price'] for point in result['shapes'][0]['points']])
        weekly = self.annotations(pattern('REV-DBOT', measurements=measurements, timeframe='1W'))[0]
        self.assertEqual(['Neckline'], [shape['label'] for shape in weekly['shapes']])

    def test_missing_or_invalid_bounds_do_not_draw_a_fabricated_box(self):
        for value in (None, Decimal('NaN'), Decimal('Infinity')):
            result = self.annotations(pattern(support_price=value))[0]
            self.assertEqual('line', result['shapes'][0]['kind'])
        result = self.annotations(pattern(pivot_price=None, support_price=None))[0]
        self.assertFalse(result['geometryAvailable'])

    def test_old_detection_with_confirmation_in_range_is_included(self):
        row = pattern(detected_date=START - timedelta(days=90))
        repo = InMemoryPatternQueryRepository(patterns=[row])
        self.assertEqual([row['id']], [item['id'] for item in repo.list_chart_patterns(row['isin'], END, START)])

    def test_chart_apis_serialize_confirmations_and_shapes_from_the_matching_adjustment(self):
        row = pattern()
        repo = InMemoryPatternQueryRepository(patterns=[row], securities=[{'isin': row['isin'], 'symbol': 'EXAMPLE'}],
            bars=[{**bar, 'isin': row['isin'], 'adjustment_version': 'av1'} for bar in BARS])
        service = PatternQueryService(repo)
        for chart in (service.chart(row['id'], {}), service.security_chart(row['isin'], {'asOf': [END.isoformat()]})):
            payload = browser_payload(chart)
            self.assertEqual('2026-10-06', payload['patternAnnotations'][0]['confirmationDate'])
            self.assertEqual('box', payload['patternAnnotations'][0]['shapes'][0]['kind'])
            self.assertEqual(100.0, payload['patternAnnotations'][0]['shapes'][0]['upperPrice'])
            self.assertEqual('2026-10-06', payload['evidence'][0]['confirmationDate'])

    def test_security_focuses_ready_52_week_base_instead_of_an_older_confirmed_breakout(self):
        base = pattern('BASE-52WH', id='bosch-base', state='READY', trigger_date=None, confirmation_date=None)
        breakout = pattern('BRK-RANGE', id='old-breakout', pattern_class='BREAKOUT')
        repo = InMemoryPatternQueryRepository(patterns=[base, breakout],
            securities=[{'isin': base['isin'], 'symbol': 'BOSCHLTD'}],
            bars=[{**bar, 'isin': base['isin'], 'adjustment_version': 'av1'} for bar in BARS])
        service = PatternQueryService(repo)
        chart = service.security_chart(base['isin'], {'asOf': [END.isoformat()]})
        self.assertEqual('bosch-base', service.fingerprint(base['isin'], {'asOf': [END.isoformat()]})['primarySetup']['patternInstanceId'])
        self.assertEqual('bosch-base', chart['focusedPatternId'])
        annotation = next(item for item in chart['patternAnnotations'] if item['patternInstanceId'] == chart['focusedPatternId'])
        self.assertIsNone(annotation['confirmationDate'])
        self.assertEqual('box', annotation['shapes'][0]['kind'])
        self.assertEqual(START, annotation['shapes'][0]['startDate'])
        self.assertEqual(END, annotation['shapes'][0]['endDate'])
        self.assertEqual(base['pivot_price'], chart['levels']['pivot'])

    def test_current_base_is_included_when_detection_predates_the_chart_range(self):
        base = pattern('BASE-52WH', id='long-base', state='READY', trigger_date=None, confirmation_date=None,
                       start_date=START - timedelta(days=200), detected_date=START - timedelta(days=190))
        repo = InMemoryPatternQueryRepository(patterns=[base], securities=[{'isin': base['isin'], 'symbol': 'BOSCHLTD'}],
            bars=[{**bar, 'isin': base['isin'], 'adjustment_version': 'av1'} for bar in BARS])
        chart = PatternQueryService(repo).security_chart(base['isin'], {'asOf': [END.isoformat()], 'range': ['3m']})
        self.assertEqual('long-base', chart['focusedPatternId'])
        self.assertEqual(START, chart['patternAnnotations'][0]['shapes'][0]['startDate'])
