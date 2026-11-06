"""Offline RDF/SHACL checks and explicitly opt-in Ontop integration checks."""
import importlib.util
import os
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent
HAS_RDF = importlib.util.find_spec("rdflib") is not None and importlib.util.find_spec("pyshacl") is not None


@unittest.skipUnless(HAS_RDF, "Install requirements-ontology.txt for RDF/SHACL validation")
class OntologyArtifactTests(unittest.TestCase):
    def setUp(self):
        from rdflib import Graph, Namespace
        self.tl = Namespace("urn:tradelens:ontology:")
        self.ontology = Graph().parse(ROOT / "ontology/tradelens.ttl")
        self.graph = Graph().parse(ROOT / "fixtures/ontology/equity_setup_today.ttl")
        self.graph.parse(ROOT / "ontology/facts.ttl")

    def test_real_rdf_query_requires_subclass_entailment(self):
        from owlrl import DeductiveClosure, RDFS_Semantics
        from repositories.knowledge_graph import current_setup_query
        query = current_setup_query("RELIANCE")
        without_inference = list(self.graph.query(query))
        self.assertEqual(1, len(without_inference))
        self.assertIsNone(without_inference[0].snapshot)
        self.graph += self.ontology
        DeductiveClosure(RDFS_Semantics).expand(self.graph)
        rows = list(self.graph.query(query))
        self.assertEqual(1, len(rows))
        self.assertEqual("BASE-VCP", str(rows[0].patternType))
        self.assertEqual("90", str(rows[0].quality))
        self.assertIsNone(rows[0].maturity)

    def test_shapes_accept_valid_and_reject_invalid_score_and_missing_date(self):
        from rdflib import Literal, URIRef
        from rdflib.namespace import XSD
        from pyshacl import validate
        shapes = str(ROOT / "ontology/shapes.ttl")
        def conforms():
            return validate(self.graph, shacl_graph=shapes, ont_graph=self.ontology, inference="rdfs")[0]
        self.assertTrue(conforms())
        score = URIRef("urn:tradelens:score:fixture:quality")
        self.graph.set((score, self.tl.numericValue, Literal("101", datatype=XSD.decimal)))
        self.assertFalse(conforms())
        self.graph.set((score, self.tl.numericValue, Literal("90", datatype=XSD.decimal)))
        self.graph.remove((URIRef("urn:tradelens:snapshot:fixture"), self.tl.asOfDate, None))
        self.assertFalse(conforms())

    def test_all_mappings_parse_and_no_score_probability_entailment(self):
        from rdflib import Graph, Namespace, RDF
        from rdflib.namespace import RDFS
        from owlrl import DeductiveClosure, RDFS_Semantics
        mapping = Graph().parse(ROOT / "repositories/semantic/tradelens.r2rml.ttl")
        rr = Namespace("http://www.w3.org/ns/r2rml#")
        self.assertGreaterEqual(len(list(mapping.subjects(RDF.type, rr.TriplesMap))), 10)
        self.graph += self.ontology
        DeductiveClosure(RDFS_Semantics).expand(self.graph)
        self.assertFalse(list(self.graph.subjects(RDF.type, self.tl.HistoricalProbabilityEstimate)))
        self.assertIn((self.tl.Equity, RDFS.subClassOf, self.tl.Security), self.ontology)

    def test_gemini_schema_context_matches_formal_ontology_definitions(self):
        from rdflib import Literal
        from rdflib.namespace import RDFS
        from chat.service import CAPABILITY
        self.assertEqual(set(CAPABILITY["terms"]), set(CAPABILITY["definitions"]))
        for term, definition in CAPABILITY["definitions"].items():
            self.assertIn((self.tl[term], RDFS.comment, Literal(definition)), self.ontology)


@unittest.skipUnless(os.getenv("TRADELENS_RUN_ONTOLOGY_TESTS") == "1", "Opt-in local PostgreSQL/Ontop verification")
class OntopIntegrationTests(unittest.TestCase):
    def test_populated_snapshot_and_scores_match_the_database(self):
        import server
        import psycopg
        from decimal import Decimal
        from repositories.knowledge_graph import OntopKnowledgeGraphRepository
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            connection.execute("SET statement_timeout = '5s'")
            candidate = connection.execute("SELECT e.symbol, s.isin FROM chat_current_setups s JOIN nse_equities e ON e.isin=s.isin LIMIT 1").fetchone()
            if not candidate:
                self.skipTest("No populated current primary setup exists in this local dataset")
            symbol, isin = candidate
            expected = connection.execute("SELECT pattern_id, quality_score, maturity_score, context_score, setup_score FROM chat_current_setups WHERE isin=%s ORDER BY pattern_id LIMIT 25", (isin,)).fetchall()
            rows = OntopKnowledgeGraphRepository(os.getenv("ONTOP_URL", "http://127.0.0.1:8088/sparql")).current_setups(symbol)
            self.assertEqual([row[0] for row in expected], [row["patternId"] for row in rows[:25]])
            for expected_row, actual in zip(expected, rows):
                for value, key in zip(expected_row[1:], ("quality", "maturity", "context", "setup")):
                    self.assertEqual(value, Decimal(actual[key]) if actual.get(key) else None)

    def test_live_mapping_query_matches_read_views_and_hides_superseded_rows(self):
        import server
        import psycopg
        from repositories.knowledge_graph import OntopKnowledgeGraphRepository
        endpoint = os.getenv("ONTOP_URL", "http://127.0.0.1:8088/sparql")
        with psycopg.connect(os.environ["DATABASE_URL"]) as connection:
            connection.execute("SET statement_timeout = '5s'")
            identities = connection.execute("SELECT isin, symbol FROM chat_security_context WHERE symbol = 'RELIANCE'").fetchall()
            self.assertEqual(1, len(identities))
            isin, symbol = identities[0]
            expected = connection.execute("SELECT pattern_id, state, setup_score, data_as_of FROM chat_current_setups WHERE isin = %s ORDER BY pattern_id LIMIT 26", (isin,)).fetchall()
            rows = OntopKnowledgeGraphRepository(endpoint).current_setups(symbol)
            self.assertTrue(rows, "Security context must remain queryable even without primary setups")
            actual = [row for row in rows if row.get("patternId")]
            self.assertEqual([row[0] for row in expected], [row["patternId"] for row in actual])
            for sql_row, rdf_row in zip(expected, actual):
                self.assertEqual("urn:tradelens:ontology:" + sql_row[1], rdf_row["state"])
                self.assertEqual(str(sql_row[3]), rdf_row["evidenceDate"])
            # Verify the semantic view preserves the existing latest-evidence predicate.
            from repositories.pattern_queries import _latest_evidence_clause
            count = connection.execute("SELECT count(*) FROM chat_current_setups c JOIN pattern_instances p ON p.id::text = c.pattern_id WHERE c.isin = %s AND NOT (" + _latest_evidence_clause("(CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Kolkata')::date") + ")", (isin,)).fetchone()[0]
            self.assertEqual(0, count)
