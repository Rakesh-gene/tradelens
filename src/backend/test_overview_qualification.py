"""Qualification boundaries and repository behavior; normal tests stay offline."""
from copy import deepcopy
from dataclasses import replace
from datetime import timedelta
from decimal import Decimal
import os
from pathlib import Path
import tempfile
import unittest

from pattern_engine.overview_qualification import load_overview_qualification
from pattern_engine.query_service import PatternQueryService, _default_filters
from repositories.overview_queries import OVERVIEW_SETUPS_SQL
from repositories.pattern_queries import InMemoryPatternQueryRepository, PostgresPatternQueryRepository, _latest_evidence_clause
from test_pattern_queries import _pattern, _DATE


def repository(patterns=None):
    patterns = patterns or [_pattern()]
    return InMemoryPatternQueryRepository(patterns=patterns,
        securities=[{"isin": item["isin"], "symbol": item["isin"], "series": "EQ"} for item in patterns],
        features=[{"isin": item["isin"], "trading_date": _DATE, "feature_version": "fv1", "data_version": "av1"} for item in patterns],
        bars=[{"isin": item["isin"], "trading_date": _DATE, "adjustment_version": "av1", "close_price": Decimal(98)} for item in patterns])


class OverviewQualificationTests(unittest.TestCase):
    def setUp(self):
        self.policy = load_overview_qualification()

    def selection(self, repo):
        return repo.overview_setups(_DATE, self.policy, 6, 0)

    def test_exact_boundaries_and_rejection_of_missing_nonfinite_or_lower_values(self):
        row = {**_pattern(), "best_fit_percentile_raw": Decimal(80), "best_fit_score": Decimal(70),
               "quality_score": Decimal(70), "context_score": Decimal(40), "liquidity_score": Decimal(100),
               "feature_date": _DATE, "price_date": _DATE, "last_close": Decimal(98)}
        self.assertTrue(self.policy.accepts(row, _DATE))
        for key in ("best_fit_percentile_raw", "best_fit_score", "quality_score", "context_score", "liquidity_score"):
            for value in (None, Decimal('NaN'), Decimal('Infinity'), row[key] - Decimal('0.001')):
                with self.subTest(key=key, value=value):
                    self.assertFalse(self.policy.accepts({**row, key: value}, _DATE))
        for key in ("last_close", "pivot_price", "invalidation_price", "setup_score"):
            for value in (None, Decimal('NaN'), Decimal('Infinity'), Decimal(-1)):
                with self.subTest(key=key, value=value):
                    self.assertFalse(self.policy.accepts({**row, key: value}, _DATE))
        # The unrounded 79.96 must not pass even though it displays as 80.0.
        self.assertFalse(self.policy.accepts({**row, "best_fit_percentile_raw": Decimal('79.96')}, _DATE))
        self.assertTrue(self.policy.accepts({**row, "maturity_score": None, "relative_strength_percentile": None}, _DATE))

    def test_current_dates_price_risk_and_required_lineage(self):
        repo = repository()
        self.assertEqual(1, self.selection(repo)["qualifiedCount"])
        for target, key, value in (
            ('patterns', 'last_updated_date', _DATE - timedelta(days=1)),
            ('features', 'trading_date', _DATE - timedelta(days=1)),
            ('features', 'feature_version', 'wrong'), ('features', 'data_version', 'wrong'),
            ('bars', 'trading_date', _DATE - timedelta(days=1)), ('bars', 'adjustment_version', 'wrong'),
            ('bars', 'close_price', Decimal(88)), ('bars', 'close_price', Decimal(87)),
            ('patterns', 'configuration_version', ''), ('patterns', 'engine_version', None)):
            candidate = deepcopy(repo)
            getattr(candidate, target)[0][key] = value
            with self.subTest(target=target, key=key, value=value):
                self.assertEqual(0, self.selection(candidate)["qualifiedCount"])
        # Invalidation can equal a breakout pivot; it need not be below it.
        repo.patterns[0]['pivot_price'] = Decimal(88)
        self.assertEqual(1, self.selection(repo)["qualifiedCount"])

    def test_liquidity_75_is_not_a_full_pass_and_no_weak_results_fill_empty_list(self):
        repo = repository()
        repo.patterns[0]['measurements']['scoring']['context_inputs']['liquidity'] = Decimal(75)
        page = PatternQueryService(repo).overview({"asOf": [_DATE.isoformat()]})
        self.assertEqual(1, page['qualification']['candidateCount'])
        self.assertEqual(0, page['qualification']['qualifiedCount'])
        self.assertEqual([], page['topSetups'])
        self.assertIsNone(page['nextCursor'])
        self.assertEqual(1, len(PatternQueryService(repo).setups({"asOf": [_DATE.isoformat()]})['items']))

    def test_ties_and_singleton_percentiles_use_complete_cohort_before_quality_gate(self):
        patterns = [{**_pattern(f'p{i}', 'READY', score), 'isin': f'EQ{i}'} for i, score in enumerate(('99', '99', '70', '60', '50', '40'))]
        repo = repository(patterns)
        first = self.selection(repo)
        self.assertEqual(6, first['candidateCount'])
        self.assertEqual(2, first['qualifiedCount'])
        self.assertEqual([Decimal(80), Decimal(80)], [row['best_fit_percentile_raw'] for row in first['items']])
        repo.patterns[0]['quality_score'] = Decimal(69)
        second = self.selection(repo)
        self.assertEqual(1, second['qualifiedCount'])
        self.assertEqual(Decimal(80), second['items'][0]['best_fit_percentile_raw'])
        self.assertEqual(100, self.selection(repository())['items'][0]['best_fit_percentile_raw'])

    def test_lifecycle_terminal_identity_and_one_representative(self):
        for change in ({'state': 'MATURE'}, {'terminal_date': _DATE}, {'timeframe': '1W'}, {'pattern_group': 'REVERSAL'}):
            with self.subTest(change=change):
                self.assertEqual(0, self.selection(repository([{**_pattern(), **change}]))['candidateCount'])
        repo = repository([_pattern('ready'), _pattern('confirmed', 'CONFIRMED', '20')])
        page = self.selection(repo)
        self.assertEqual(1, page['candidateCount'])
        self.assertEqual(0, page['qualifiedCount'])  # Do not replace with another pattern just to fill the shortlist.
        repo.securities['INE000000001']['series'] = 'BE'
        self.assertEqual(0, self.selection(repo)['candidateCount'])

    def test_policy_is_separately_configurable_and_rejects_invalid_configuration(self):
        self.assertEqual(0, repository().overview_setups(_DATE, replace(self.policy, minimum_best_fit=Decimal(99)), 6, 0)['qualifiedCount'])
        path = Path(__file__).parent / 'configuration/overview.toml'
        for text in (path.read_text().replace('minimum_quality = 70', 'minimum_quality = 101'),
                     path.read_text().replace('required_liquidity = 100', 'required_liquidity = 75')):
            with tempfile.TemporaryDirectory() as directory:
                config = Path(directory) / 'overview.toml'; config.write_text(text)
                with self.assertRaises(ValueError): load_overview_qualification(config)


class OverviewSqlTests(unittest.TestCase):
    def test_qualification_precedes_limit_but_not_peer_ranking_and_counts_survive_empty_page(self):
        class Capture(PostgresPatternQueryRepository):
            def __init__(self): pass
            def _fetch_all(self, sql, parameters):
                self.sql, self.parameters = sql, parameters
                return [{'id': None, 'candidate_count': 100, 'qualified_count': 0}]
        repo = Capture(); page = repo.overview_setups(_DATE, load_overview_qualification(), 6, 0)
        self.assertEqual({'items': [], 'candidateCount': 100, 'qualifiedCount': 0}, page)
        self.assertLess(repo.sql.index('), peers AS'), repo.sql.index('), qualified AS'))
        self.assertLess(repo.sql.index('), qualified AS'), repo.sql.index('LIMIT %(limit)s'))
        self.assertIn('feature.data_version = p.adjustment_version', repo.sql)
        self.assertEqual(7, repo.parameters['limit'])
        self.assertEqual(Decimal(70), repo.parameters['minimum_quality'])

    @unittest.skipUnless(os.getenv('TRADELENS_RUN_OVERVIEW_DB_TESTS') == '1', 'opt-in read-only database parity')
    def test_current_postgres_and_memory_qualification_parity(self):
        import server  # Load local settings without printing credentials.
        repo = PostgresPatternQueryRepository(os.environ['DATABASE_URL'], apply_migrations=False)
        policy = load_overview_qualification()
        as_of = repo.overview_summary(None)['data_as_of']
        filters = _default_filters(as_of); filters.update(states=('READY','TRIGGERED','CONFIRMED'), equities_only=True, latest_only=True)
        candidates = []
        for offset in range(0, 10000, 100):
            batch = repo.list_setups(filters, 100, offset); candidates.extend(batch[:100])
            if len(batch) <= 100: break
        identities = list({item['isin'] for item in candidates})
        memory = InMemoryPatternQueryRepository(patterns=candidates,
            securities=repo._fetch_all('SELECT * FROM nse_equities WHERE isin = ANY(%s)', (identities,)),
            features=repo._fetch_all('SELECT * FROM technical_features WHERE isin = ANY(%s) AND trading_date = %s', (identities, as_of)),
            bars=repo._fetch_all('SELECT * FROM adjusted_daily_bars WHERE isin = ANY(%s) AND trading_date = %s', (identities, as_of)))
        for offset in (0, 6, 12, 10000):
            actual = repo.overview_setups(as_of, policy, 6, offset)
            expected = memory.overview_setups(as_of, policy, 6, offset)
            self.assertEqual(expected['candidateCount'], actual['candidateCount'])
            self.assertEqual(expected['qualifiedCount'], actual['qualifiedCount'])
            self.assertEqual([str(item['id']) for item in expected['items']], [str(item['id']) for item in actual['items']])
            self.assertEqual([item['best_fit_percentile'] for item in expected['items']], [item['best_fit_percentile'] for item in actual['items']])
