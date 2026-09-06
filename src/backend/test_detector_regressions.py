"""Acceptance fixtures for the Phase 8/9 review findings."""
from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta
from decimal import Decimal as D
import unittest

from pattern_engine.configuration import load_pattern_engine_configuration
from pattern_engine.features import assign_relative_strength_percentiles
from pattern_engine.models import DetectionContext, SwingPoint, PriceZone
from pattern_engine.enums import SwingType, ZoneType, PatternState
from pattern_engine.supporting_detectors import detect_supporting_patterns
from pattern_engine.base_detectors import detect_primary_bases, _zone_dispersion, _nearest_resistance, _ols_movement
from test_supporting_detectors import _snapshot


class SupportingReviewTests(unittest.TestCase):
    def setUp(self):
        self.config = load_pattern_engine_configuration()

    def run_snapshot(self, b, f, s, c):
        return detect_supporting_patterns({"isin": "INE000000001"}, b, f, s, (), c, self.config)

    def test_each_identifier_false_case(self):
        # Each mutation targets a required rule, independently of all other rules.
        mutations = {
            "BASE-TIGHT": lambda b, f: f[-1].update(range_10=D(99)),
            "TREND-HHHL": lambda b, f: None,
            "TREND-S2": lambda b, f: f[-1].update(sma_50_slope=D(-1)),
            "TREND-MA": lambda b, f: f[-1].update(ema_20=D(600), sma_50=D(700), sma_100=D(800), sma_200=D(900), ema_20_slope=D(-1), sma_50_slope=D(-1), sma_200_slope=D(-1)),
            "COMP-NR7": lambda b, f: b[-1].update(high_price=D(1000)),
            "COMP-IB": lambda b, f: b[-1].update(high_price=D(1000)),
            "COMP-ATR": lambda b, f: f[-1].update(atr_5=D(100)),
            "COMP-RANGE": lambda b, f: f[-1].update(range_5=D(100)),
            "MOM-ACC": lambda b, f: f[-1].update(return_1_month=D(-1), return_3_month=D(0), return_6_month=D(6), return_12_month=D(24)),
            "MOM-RSL": lambda b, f: f[-1].update(secondary_metrics={f"rs_{h}_percentile": D(0) for h in ("1m", "3m", "6m", "12m")}),
            "MOM-RSB": lambda b, f: b[-1].update(close_price=D(1)),
            "VOL-DRY": lambda b, f: f[-1].update(median_volume_5=D(1000)),
            "VOL-EXP": lambda b, f: b[-1].update(volume=1),
        }
        for identifier, mutate in mutations.items():
            with self.subTest(identifier=identifier):
                b, f, s, c = _snapshot()
                mutate(b, f)
                if identifier == "TREND-HHHL": s = [replace(x, price=D(100)) for x in s]
                self.assertNotIn(identifier, {x.pattern_type for x in self.run_snapshot(b, f, s, c)})

    def test_each_identifier_missing_data_on_correct_asof(self):
        b, f, s, c = _snapshot()
        # Same as-of date; bypasses the old test's accidental date-mismatch exit.
        row = {"isin": b[-1]["isin"], "trading_date": c.as_of_date}
        result = self.run_snapshot(b[-1:], [row], (), replace(c, benchmark_snapshot={}))
        self.assertEqual(result, [])

    def test_threshold_equality_for_supporting_rules(self):
        b, f, s, c = _snapshot()
        f[-1].update(range_10=D(5), atr_5=D('1.5'), range_5=D(3), range_50=D(20)/3,
                     median_volume_5=D(70), sma_200_slope=D(0),
                     secondary_metrics={f"rs_{h}_percentile": D(70) for h in ("1m", "3m", "6m", "12m")})
        b[-1]['volume'] = 120
        identifiers = {x.pattern_type for x in self.run_snapshot(b, f, s, c)}
        self.assertTrue({"BASE-TIGHT", "COMP-ATR", "COMP-RANGE", "MOM-RSL", "VOL-DRY", "VOL-EXP", "TREND-S2", "TREND-MA"} <= identifiers)

    def test_nr7_and_inside_bar_equality_and_minimum_history(self):
        b, f, s, c = _snapshot()
        for row in b[-7:]: row.update(high_price=D(301), low_price=D(299), close_price=D(300))
        result = self.run_snapshot(b[-7:], f[-7:], (), c)
        self.assertIn("COMP-NR7", {x.pattern_type for x in result})
        self.assertIn("COMP-IB3", {x.variant for x in result})
        self.assertNotIn("COMP-NR7", {x.pattern_type for x in self.run_snapshot(b[-6:], f[-6:], (), c)})

    def test_rsb_short_stock_history_and_missing_benchmark_sessions(self):
        b, f, s, c = _snapshot()
        result = self.run_snapshot(b[-20:], f[-20:], (), c)
        self.assertEqual([x.variant for x in result if x.pattern_type == "MOM-RSB"], ["RS-20D-HIGH"])
        c = replace(c, benchmark_snapshot={"bars": c.benchmark_snapshot['bars'][:-1]})
        self.assertNotIn("MOM-RSB", {x.pattern_type for x in self.run_snapshot(b, f, s, c)})

    def test_hhhl_counts_sessions_and_pairs_forward_pullbacks(self):
        b, f, s, c = _snapshot()
        dates = [date(2020, 1, 1) + timedelta(days=2*i) for i in range(len(b))]
        mapping = {row['trading_date']: dates[i] for i, row in enumerate(b)}
        for row in b + f: row['trading_date'] = mapping[row['trading_date']]
        s = [replace(x, pivot_date=mapping[x.pivot_date], confirmation_date=mapping[x.confirmation_date]) for x in s]
        c = replace(c, as_of_date=dates[-1], benchmark_snapshot={})
        result = next(x for x in self.run_snapshot(b, f, s, c) if x.pattern_type == "TREND-HHHL")
        self.assertEqual(result.measurements['trend_duration_sessions'], 50)
        self.assertEqual(result.measurements['average_pullback_duration_sessions'], 10)
        self.assertEqual(result.measurements['average_pullback_depth_pct'], (D(5)/110*100 + D(5)/115*100)/2)

    def test_ranked_horizons_and_weighted_composite(self):
        rows = [{"isin": str(i), "trading_date": date(2020, 1, 1), **{f"relative_strength_{h}": D(i) for h in ('1m', '3m', '6m', '12m')}} for i in range(3)]
        assign_relative_strength_percentiles(rows, {'0', '1'})
        self.assertEqual(rows[1]['secondary_metrics']['rs_6m_percentile'], 100)
        self.assertEqual(rows[2]['secondary_metrics'], {})
        b, f, s, c = _snapshot()
        f[-1]['secondary_metrics'] = dict(zip(('rs_1m_percentile','rs_3m_percentile','rs_6m_percentile','rs_12m_percentile'), map(D, (10, 80, 90, 100))))
        candidate = next(x for x in self.run_snapshot(b, f, s, c) if x.pattern_type == 'MOM-RSL')
        self.assertEqual(candidate.measurements['relative_strength_composite'], D('82.5'))

    def test_replay_ignores_future_inputs(self):
        b, f, s, c = _snapshot()
        expected = self.run_snapshot(b, f, s, c)
        b.append({**b[-1], 'trading_date': c.as_of_date + timedelta(days=1)})
        f.append({**f[-1], 'trading_date': c.as_of_date + timedelta(days=1)})
        self.assertEqual(expected, self.run_snapshot(b, f, s, c))

    def test_momentum_continuous_score_and_equal_pace_boundary(self):
        b,f,s,c = _snapshot()
        scores = []
        for pace in (D(10), D('10.01'), D(11)):
            f[-1].update(return_1_month=pace,return_3_month=D(30),return_6_month=D(60),return_12_month=D(120))
            candidate = next((x for x in self.run_snapshot(b,f,s,c) if x.pattern_type=='MOM-ACC'),None)
            scores.append(candidate.quality_score if candidate else D(0))
        self.assertEqual(scores[0],0)
        self.assertTrue(scores[0] < scores[1] < scores[2])

    def test_independent_rs_horizon_boundaries_and_ties(self):
        b,f,s,c = _snapshot()
        c = replace(c,benchmark_snapshot={'bars':tuple({'trading_date':row['trading_date'],'close_price':row['close_price']} for row in b)})
        for length, expected in ((19,0),(20,1),(49,1),(50,2),(251,2),(252,3)):
            with self.subTest(length=length):
                result = self.run_snapshot(b[-length:],f[-length:],(),c)
                self.assertEqual(len([x for x in result if x.pattern_type=='MOM-RSB']),expected)


def vcp_fixture(count=3, duration=30, depth=D(20)):
    start = date(2020, 1, 1)
    b = [{'isin': 'X', 'trading_date': start + timedelta(days=i), 'open_price': D(99), 'close_price': D(99),
          'high_price': D(100), 'low_price': D(100)-depth, 'volume': 1000 if i < duration//2 else 100} for i in range(duration)]
    f = [{'trading_date': x['trading_date'], 'atr_10': D(2) if i < duration//2 else D('.2'), 'atr_14': D(2),
          'sma_50': D(90), 'sma_200': D(80), 'sma_50_slope': D(1), 'relative_strength_percentile': D(90)} for i,x in enumerate(b)]
    s = []
    for i in range(count):
        high_day = start + timedelta(days=i*3)
        low_day = high_day + timedelta(days=1)
        s.extend([SwingPoint(f'h{i}', 'X', high_day, high_day+timedelta(days=3), SwingType.HIGH, D(100), D(1), None, True),
                  SwingPoint(f'l{i}', 'X', low_day, low_day+timedelta(days=3), SwingType.LOW, D(100)-depth*D('.6')**i, D(1), None, True)])
    c = DetectionContext(b[-1]['trading_date'], {}, None, (), 'v1')
    return b,f,s,c


class BaseReviewTests(unittest.TestCase):
    def setUp(self): self.config = load_pattern_engine_configuration()

    def detect(self, b,f,s,c,z=()):
        return next((x for x in detect_primary_bases({'isin':'X'},b,f,s,z,c,self.config) if x.pattern_type=='BASE-VCP'), None)

    def test_all_contraction_counts_and_duration_depth_boundaries(self):
        for count in range(2,6):
            for duration in (20,90):
                for depth in (D(8),D(35)):
                    with self.subTest(count=count,duration=duration,depth=depth):
                        b,f,s,c=vcp_fixture(count,duration,depth)
                        candidate=self.detect(b,f,s,c)
                        self.assertIsNotNone(candidate)
                        self.assertEqual(candidate.variant,f'VCP-{count}C')
        for duration,depth in ((19,D(20)),(30,D('7.99')),(30,D('35.01'))):
            b,f,s,c=vcp_fixture(2,duration,depth)
            self.assertIsNone(self.detect(b,f,s,c))

    def test_old_contraction_does_not_hide_recent_base(self):
        b,f,s,c=vcp_fixture(3,30)
        old=replace(s[0],swing_id='oldh',pivot_date=date(2019,1,1),confirmation_date=date(2019,1,4))
        oldlow=replace(s[1],swing_id='oldl',pivot_date=date(2019,1,2),confirmation_date=date(2019,1,5))
        self.assertEqual(self.detect(b,f,[old,oldlow]+s,c).variant,'VCP-3C')

    def test_expansion_invalidation_and_nearby_zone_requirement(self):
        b,f,s,c=vcp_fixture()
        s[-1]=replace(s[-1],price=D(80))
        self.assertEqual(self.detect(b,f,s,c).state,PatternState.INVALIDATED)
        zone=PriceZone('far','X',ZoneType.RESISTANCE,s[0].pivot_date,s[1].pivot_date,D(1000),D(1),D(0),(),2)
        self.assertIsNone(_nearest_resistance(s[-2],[zone]))
        zone=replace(zone,median_price=D(101))
        self.assertIsNotNone(_nearest_resistance(s[-2],[zone]))

    def test_successive_sessions_ready_triggered_confirmed_and_invalidated(self):
        b,f,s,c=vcp_fixture(3,30)
        self.assertEqual(self.detect(b,f,s,c).state,PatternState.READY)
        for price,state in ((D('100.6'),PatternState.TRIGGERED),(D('100.7'),PatternState.CONFIRMED),(D(79),PatternState.INVALIDATED)):
            day=b[-1]['trading_date']+timedelta(days=1)
            b.append({**b[-1],'trading_date':day,'open_price':price,'close_price':price,'high_price':max(D(100),price),'low_price':min(D(80),price)})
            f.append({**f[-1],'trading_date':day})
            c=replace(c,as_of_date=day)
            self.assertEqual(self.detect(b,f,s,c).state,state)

    def test_unconfirmed_swings_and_stddev_dispersion(self):
        b,f,s,c=vcp_fixture(2)
        s[-1]=replace(s[-1],confirmation_date=c.as_of_date+timedelta(days=1))
        self.assertIsNone(self.detect(b,f,s,c))
        zone=PriceZone('r','X',ZoneType.RESISTANCE,s[0].pivot_date,s[2].pivot_date,D(100),D(1),D(9),('h0','h1'),2)
        s[0]=replace(s[0],price=D(99)); s[2]=replace(s[2],price=D(101))
        self.assertEqual(_zone_dispersion(zone,s),D(1))

    def flat_fixture(self,duration,depth=D(15)):
        b,f,_,c=vcp_fixture(2,duration,depth)
        s=[]
        for key,index,kind,price in (('h0',0,SwingType.HIGH,D(100)),('h1',5,SwingType.HIGH,D(100)),('l0',1,SwingType.LOW,D(100)-depth),('l1',6,SwingType.LOW,D(100)-depth)):
            day=b[index]['trading_date']
            s.append(SwingPoint(key,'X',day,day+timedelta(days=3),kind,price,D(1),None,True))
        z=[PriceZone('r','X',ZoneType.RESISTANCE,s[0].pivot_date,s[1].pivot_date,D(100),D(1),D(0),('h0','h1'),2,D('.5'),s[1].pivot_date,s[1].confirmation_date),
           PriceZone('s','X',ZoneType.SUPPORT,s[2].pivot_date,s[3].pivot_date,D(100)-depth,D(1),D(0),('l0','l1'),2,D('.5'),s[3].pivot_date,s[3].confirmation_date)]
        return b,f,s,z,c

    def flat(self,b,f,s,z,c):
        return next((x for x in detect_primary_bases({'isin':'X'},b,f,s,z,c,self.config) if x.pattern_type=='BASE-FLAT'),None)

    def test_flat_duration_depth_and_interaction_boundaries(self):
        for duration,exists in ((19,False),(20,True),(60,True),(61,False)):
            b,f,s,z,c=self.flat_fixture(duration)
            result=self.flat(b,f,s,z,c)
            self.assertEqual(result is not None,exists)
            if result: self.assertEqual(result.measurements['duration_sessions'],duration)
        b,f,s,z,c=self.flat_fixture(20,D('15.01'))
        self.assertIsNone(self.flat(b,f,s,z,c))
        b,f,s,z,c=self.flat_fixture(20)
        self.assertIsNone(self.flat(b,f,s,[replace(x,test_count=1) for x in z],c))

    def test_flat_retains_depth_and_flatness_break_evidence(self):
        for kind in ('depth','flatness'):
            b,f,s,z,c=self.flat_fixture(20,D(10))
            if kind=='flatness':
                for i,row in enumerate(b):
                    price=D(92)+D('.22')*i
                    row.update(open_price=price,close_price=price)
            self.assertIsNotNone(self.flat(b,f,s,z,c))
            day=c.as_of_date+timedelta(days=1)
            price=D(80) if kind=='depth' else D(100)
            b.append({**b[-1],'trading_date':day,'open_price':price,'close_price':price,'low_price':min(D(90),price)})
            f.append({**f[-1],'trading_date':day})
            result=self.flat(b,f,s,z,replace(c,as_of_date=day))
            self.assertIsNotNone(result)
            self.assertEqual(result.state,PatternState.INVALIDATED)

    def test_52wh_persistence_and_window_boundaries(self):
        sections={name:dict(values) for name,values in self.config.sections.items()}
        for duration in (20,80):
            sections['base_52wh'].update(min_duration_sessions=duration,max_duration_sessions=duration)
            config=replace(self.config,sections=sections)
            for near_count,exists in ((int(duration*.6),True),(int(duration*.6)-1,False)):
                b,f,s,c=vcp_fixture(2,253,D(20))
                for i,row in enumerate(b[-duration:]):
                    price=D(90) if i >= duration-near_count else D(85)
                    row.update(open_price=price,close_price=price)
                candidates=detect_primary_bases({'isin':'X'},b,f,(),(),c,config)
                candidate=next((x for x in candidates if x.pattern_type=='BASE-52WH'),None)
                self.assertEqual(candidate is not None,exists)
                if candidate:
                    self.assertEqual(candidate.measurements['persistence_ratio'],D('.6'))
                    self.assertEqual(candidate.measurements['duration_sessions'],duration)

    def test_progression_and_trigger_threshold_equality(self):
        b,f,s,c=vcp_fixture(2,30)
        s[-1]=replace(s[-1],price=D(82)) # 18/20 = 0.90, inclusive
        self.assertIsNotNone(self.detect(b,f,s,c))
        s[-1]=replace(s[-1],price=D('81.99'))
        self.assertIsNone(self.detect(b,f,s,c))
        b,f,s,c=vcp_fixture(3,30)
        b[-1].update(close_price=D('100.5'),high_price=D('100.5'))
        candidate=self.detect(b,f,s,c)
        self.assertFalse(candidate.measurements['lifecycle_evidence']['triggered'])
