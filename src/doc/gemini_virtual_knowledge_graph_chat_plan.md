# Ontology-driven Gemini chat with a virtual knowledge graph

Status: roadmap with a first implementation slice. Only `equity_setup_today`
is enabled by the implementation; counts, history and other questions below
remain future work. The implemented runtime uses `urn:tradelens:ontology:` IRIs
and a constrained Gemini answer schema. See `infra/ontology/README.md` for the
actual file layout, setup, API and limitations; roadmap schemas are proposals.
Revision: 3, ontology-first architecture with an overlay widget, 2026-11-01. Supersedes the initial
service-adapter-only proposal. Canonical pattern specification and repository guide retain
precedence. All limits below are proposed chat defaults, not changes to engine
thresholds or existing API contracts.

Current accepted provider decision (2026-11-01): use Ollama via its local
`/api/chat` endpoint with `gemma4:31b-cloud`. Free-form prompts use model-based
equity identification; the fixed question wording gate is removed. The current
registered evidence capability remains latest daily setups. Ollama Cloud does
not enforce structured output schemas, so JSON is requested in instructions
and evidence/citations are validated by the backend. Gemini-specific roadmap
details below describe the earlier provider choice and optional adapter.

## 1. Recommended approach

Add an authenticated TradeLens assistant using **ontology-based data access
(OBDA)**. A versioned TradeLens ontology defines domain meaning independently
of SQL tables and prompts. R2RML mappings expose PostgreSQL records as virtual
RDF assertions. An Ontop service answers SPARQL by rewriting queries against
those mappings and the ontology into SQL. Gemini understands questions through
the ontology vocabulary, selects a validated semantic query plan, and explains
the returned evidence.

The ontology, mappings, constraints and competency questions are first-release
deliverables, not optional documentation added after chat. Typed tools are only
the controlled interface to this semantic layer; wrapping existing APIs alone
does not implement the proposed VKG.

Recommended stack: RDF 1.1/Turtle, RDFS + OWL 2 QL, R2RML, SPARQL 1.1,
SHACL validation, Ontop and the existing PostgreSQL/Python/React application.
Ontop is a justified additional runtime for ontology-mediated query answering,
not a replacement application framework or graph storage layer. Pin compatible
versions after the integration spike. No graph replica or vector database is
required. Existing server code retains calculations and operating conclusions.

```text
Authenticated shell chat widget -> window overlay
                 |
      authenticated /api/chat/messages
                 |
       ChatService: user, scope, budgets, history
                 |
   Gemini + retrieved ontology terms / query examples
                 |
    validated semantic plan -> registered SPARQL template
                 |
        private Ontop SPARQL endpoint
          |                  |
      OWL 2 QL ontology   R2RML mappings
                 |
       ontology/mapping query rewriting -> SQL
                 |
   PostgreSQL semantic read views over existing records
                 |
       bounded evidence with dates and lineage
                 |
       Gemini explanation -> server validation
                 |
       answer blocks + server-authored sources/cards
```

Read views and mappings belong to persistence infrastructure. Existing services
may enrich results with calculated decisions or ranking; those outputs must be
identified as service-derived facts with their methodology/version. They must
not become a parallel set of definitions hidden in prompts. The ontology enables
supported taxonomic inference, not new pattern detection or price prediction.

## 2. Findings from the current code

| Existing location | What can be reused / implication |
| --- | --- |
| `src/backend/server.py` | Dependency injection in `create_server`; add chat service and disabled/fake implementations here. |
| `server_http/api.py` | `ThreadingHTTPServer`, bearer validation, `_read_json`, `_send_json`; add thin handlers without SQL or model orchestration. |
| `pattern_engine/query_service.py` | Reuse domain validation and computed decision contracts. Use existing responses as parity oracles for ontology queries, not as a substitute for ontology mappings. |
| `repositories/pattern_queries.py` | Latest-evidence eligibility and ranking already exist; factor shared semantics into reviewed repository read views/helpers where needed so chat and existing APIs cannot drift. |
| `pattern_engine/decision_intelligence.py` | Owns operating conclusions and evidence confidence. Assistant must preserve this contract and name missing inputs. |
| `pattern_engine/case_study_service.py` | Catalog/detail and positional performance can support historical examples later. Examples are selected research evidence, not an unbiased probability estimate. |
| `watchlist/service.py`, `indices/service.py` | Future user-scoped watchlist and index tools. Index access must retain its entitlement checks. |
| Migrations `007`–`011`, `023`, `033`, `037` onward | Adjusted bars, features, effective-dated memberships, patterns/events, watchlists and research relationships already exist. No graph replica is needed. |
| `App.jsx`, `components/AppShell.jsx`, `routing/routes.js` | Mount the widget in the authenticated shell. Pass validated current-page context from App; reuse route builders for source links. No chat route or navigation item. |
| `api/apiClient.js`, `api/authenticatedApi.js`, `useApiResource.js` | Existing JSON transport, session expiry, and abortable reads. Message submission needs a focused mutation hook, not automatic submission from a read effect. |
| `topology.css`, `styles.css`, frontend test setup | Reuse themes, responsive tokens, accessible native controls and React Testing Library/Vitest. |
| `requirements.txt` | Currently only psycopg is declared; Gemini needs a deliberately chosen provider dependency or REST adapter. No existing chat/LLM integration was found. |

The older product plans describe an earlier baseline; the implementation is
substantially further along, including watchlists, indices and case studies.
Use actual code as the integration baseline. Existing unrelated working-tree
changes must remain intact.

### Data gaps to handle before exposing tools

- `list_security_patterns(isin, as_of)` filters detection date but returns mutable
  instances, including state/scores updated after the requested date. The current
  fingerprint therefore cannot establish historical pattern state by itself.
- `pattern(id)` is a stored setup snapshot at `last_updated_date`; it is not a
  request to reconstruct that pattern at an arbitrary earlier date.
- `get_latest_feature` selects the latest feature version and joins an adjusted
  close separately by generation time. Verify compatible feature/data/adjustment
  lineage before combining these as one evidence snapshot.
- Service responses have different freshness/lineage shapes. The chat evidence
  adapter must normalize metadata and preserve missing values rather than
  inventing a common date/version.
- Effective-dated memberships are available, but current NSE classification is
  not a complete historical classification feed.

V1 supports current evidence, dated stored setup snapshots, and methodology.
Arbitrary historical state questions return an explicit availability limitation
until a tested replay/snapshot tool exists. Do not silently fall back to today's
state. A requested past date must not be presented as the actual evidence date.

## 3. First release scope and UX

Support questions such as:

- “Explain RELIANCE's current setup and its missing evidence.”
- “Why is this pattern READY? What would invalidate it?”
- “Show the strongest READY setups in this sector.”
- “What does BASE-VCP mean, and how does setup score differ from probability?”
- “Explain the difference between these two setups.”
- “How many setups does this equity have?”
- “Show me past setups for this equity.”

Use a chat launcher widget on authenticated pages. Clicking it opens a window
overlay above the current page, without changing the URL or browser history.
There is no `/chat` route, chat page or primary-navigation item. The overlay
contains conversation history, suggested questions, composer, retry,
clear/delete conversation, evidence cards and source links.

Mount it once in AppShell so closing/reopening preserves the active conversation
and draft. Desktop uses a bounded window near the launcher with a backdrop;
mobile uses a viewport-fitting overlay window, still on the same route. Keep
the launcher clear of page actions and mobile safe areas. Page-level “Ask about
this setup/stock” buttons may open the same overlay with validated IDs/symbols;
they do not navigate or automatically submit a question.

Show the selected scope/date before sending and validate them server-side.
Opening a new conversation defaults to the current page's scope. Navigation
never silently changes an existing conversation's scope or mixes evidence:
retain its labelled context and offer “Start chat about this page.” Changing
scope/date starts a new conversation in V1 and preserves the previous history.
Pass context through explicit App/AppShell props, not scraping page text or
embedding prompts/evidence in URLs.

Treat the overlay as a modal dialog with an accessible title, close button,
Escape dismissal, focus containment, inert background and focus restoration
to its opener (or launcher if that opener has unmounted). Closing hides the
overlay without deleting history or implying an in-flight provider call was
cancelled. An active bounded request may finish while hidden; reopen to see its
result. Unmount/abort and clear widget state on sign-out or user change. Source
links use normal semantic anchors; a plain same-tab navigation closes the
overlay and restores focus appropriately without discarding the conversation.

Each answer displays evidence dates, stale/partial status, missing inputs and
links to supporting pages. Separate explanation, server-provided decision,
levels and sources. Use symbol-based public security links. Render plain text
blocks and native cards first; do not render model HTML or arbitrary links.

Do not support orders, account changes, watchlist writes, ingestion, pipeline
runs, new backtests, news/web search, or inferred portfolio ownership in V1.
Questions about buying/selling should explain the server's decision and risks;
they must not turn ranking into personalized advice or a promised return.

### Equity setup counts and recorded history: first-release requirements

Resolve “this equity” from the conversation's labelled security scope or its
pattern's security. If no single equity is selected, ask which equity. Do not
silently switch to a different underlying page after navigation.

**“How many setups does this equity have?”** defaults to current active setup
instances at the latest available eligible evaluation, using the same group,
timeframe and lifecycle eligibility as Setups (`SETUP`, `1D` by default).
Display these filters alongside the count and allow explicit changes. Count
distinct pattern-instance UUIDs, not pattern types, events, snapshots or rows
produced by joining multiple measurements. Return a breakdown by type and state
and a separate distinct-type count if requested. Identify supporting/failure
classes in the breakdown; do not silently redefine the existing SETUP group.
“Primary setups only” is an explicit BASE/BREAKOUT/PULLBACK filter.

Important code finding: `PostgresPatternQueryRepository.list_setups` collapses
matching patterns to one ranked winner per security (`security_rank = 1`). Its
`totalCount` counts displayed securities, not every setup for an equity. The
fingerprint also returns a bounded pattern list. Neither is a valid aggregate
for this question. Add a mapped per-instance eligible view before that collapse,
reuse the latest-evidence predicate, and execute an exact distinct aggregate in
the data layer. Count and list share filters and the same evidence cutoff.
Gemini must never count a page of results and present it as the total.

**“Show me past setups for this equity”** returns recorded setup instances,
including terminal states and older retained instances excluded from today's
opportunity ranking. Default to stored instances outside the current eligible
active set, explicitly labelled “Past recorded setups”; an older nonterminal
record is labelled superseded/not current, not falsely marked EXPIRED. Offer
“All recorded setups” and date/type/state/timeframe filters. Default date range
is all retained recorded history, displayed as such; actual coverage may be
incomplete. Filter date ranges by detection date unless the user specifies a
different date field. Do not claim the archive is a complete replay history.

Return newest detection first, with UUID as a deterministic tie-breaker and
opaque cursor pagination (25 items per page). Show pattern ID/type/variant,
timeframe, detection/trigger/confirmation/terminal dates where available,
latest retained state, evidence date, available scores/levels and a pattern
detail source link. Historical rows display their own snapshot dates rather
than today's stock prices. Terminal states are evidence, not current ranking
candidates. Display total matching instances and returned count separately.
“Show more” uses server-held validated filters/cursor, not a model-created cursor.

Recorded history is answerable now from retained records; “what state/score was
this setup in on date X?” remains a different, reconstruction-dependent query.
Historical outcomes are not implied by a past setup and require separately
available research evidence. No records yields “No recorded setups found” with
coverage information, not “This equity has never had a setup.” Missing/lagging
evaluations yield an incomplete/unavailable count rather than an unexplained
zero. Label a verified zero only when the evaluation coverage supports it.

## 4. Ontology design and governance

### 4.1 Competency questions define the ontology's scope

For each question, maintain a named fixture, expected bindings, evidence path,
temporal policy, SPARQL template and expected missing-data behavior:

| ID | Question | Required semantic path |
| --- | --- | --- |
| CQ01 | Which setup snapshot describes RELIANCE, and when? | Security <- aboutSecurity - PatternSnapshot -> PatternInstance |
| CQ02 | Why is this setup READY, and which evidence is missing? | PatternSnapshot -> lifecycleState, ScoreObservation, Measurement, DecisionEvidence |
| CQ03 | Which active READY setups belong to this sector? | Security -> Membership -> Sector; Security <- PatternSnapshot -> lifecycleState; shared latest-evidence eligibility |
| CQ04 | Which events led to this setup's current state? | PatternInstance <- eventOf - PatternEvent, bounded by snapshot date |
| CQ05 | What is a VCP, and how is quality different from maturity? | PatternType -> MethodologyDefinition; separate QualityScore and MaturityScore concepts |
| CQ06 | What did the application know on an earlier date? | valid/effective time AND recorded/available time; explicitly unavailable when historical versions are missing |
| CQ07 | How did reviewed similar setups behave historically? | CaseStudy -> PatternType, ResearchRun, OutcomeObservation; research-only extension |
| CQ08 | How many current setups does this equity have? | Security <- aboutSecurity - eligible PatternSnapshot -> PatternInstance; COUNT DISTINCT instance and grouped counts before best-fit collapse |
| CQ09 | Show past recorded setups for this equity | Security <- aboutSecurity - retained PatternSnapshot -> PatternInstance; historical archive outside current eligible set, dated evidence and cursor |

CQ01-CQ05 and CQ08-CQ09 are the first release. CQ06 must pass abstention tests before launch;
full historical answering follows only when source evidence supports it.

### 4.2 Modules and formal concepts

Use a project-owned stable vocabulary IRI, provisionally
`https://w3id.org/tradelens/ontology/` (`tl:`); registration/resolution is future
deployment work, not an assumption of ownership. Use `urn:tradelens:` resource
IRIs for internal individuals. Public application links still use symbols.

| Module | Classes | Object properties / meaning |
| --- | --- | --- |
| Security/classification | Security, Equity, Sector, Industry, BasicIndustry, Index, Membership | `memberSecurity`, `memberGroup`; membership is a dated entity, not a timeless edge. |
| Pattern taxonomy | PatternType, PatternVariant, PatternInstance, PatternSnapshot, BaseSnapshot, BreakoutSnapshot, PullbackSnapshot | `snapshotOf`, `aboutSecurity`, `hasPatternType`, `hasVariant`, `sourcePattern`; distinguish identity from evolving evidence. |
| Evidence | Observation, FeatureSnapshot, Measurement, ScoreObservation, PriceLevel, DecisionEvidence | `hasObservation`, `hasMeasurement`, `hasScore`, `hasLevel`, `hasDecision`, `usesMethodology`; a value belongs to dated evidence. |
| Scores | QualityScore, MaturityScore, ContextScore, SetupScore, HistoricalProbabilityEstimate | Separate score meanings; score is never a probability by equivalence or inference. |
| Lifecycle | LifecycleState, PatternEvent | `lifecycleState`, `eventOf`, `previousState`, `newState`; exact canonical state individuals. |
| Methodology/provenance | MethodologyDefinition, CalculationRun, DataVersion, SourceArtifact | `derivedFrom`, `generatedBy`, `usesDataVersion`, `definedBy`; links to actual lineage and canonical definitions. |
| Research extension | CaseStudy, ResearchRun, OutcomeObservation | `observesSetup`, `hasOutcome`; separate then-known evidence from subsequently observed outcomes. |

Datatype properties include `asOfDate`, `effectiveFrom`, `effectiveTo`,
`recordedAt`, `generatedAt`, `numericValue`, `unitCode`, `timeframeCode`,
`engineVersion`, `configurationVersion`, `featureVersion`, `adjustmentVersion`.
Units distinguish INR, percentage points, ratios, sessions and 0-100 score
points. A resource may omit a missing value; do not encode SQL NULL as zero,
empty string or the literal word "null".

Use OWL 2 QL subclass/property axioms for query expansion. Example:
`BreakoutSnapshot rdfs:subClassOf PatternSnapshot` allows a query for all
pattern snapshots to include breakout snapshots. Pattern family identifiers
such as `BASE-VCP`, variant `VCP-3C`, and lifecycle `READY` are controlled
individuals with canonical codes, not loosely generated labels. Mappings assert
snapshot subtypes from persisted class values. Do not infer readiness from a
score threshold or encode detector geometry as OWL restrictions.

OWL follows open-world semantics: a missing observation is unknown, not false.
OWL domain/range axioms describe semantics and can entail types; they are not
form validation. Cardinality, required values and unit checks belong to SHACL
and application/SQL validation. Declare incompatible concepts separately, but
verify all axioms against the chosen OWL 2 QL profile and Ontop implementation.
Do not depend on arbitrary OWL DL, SWRL, property-chain or temporal reasoning.

Illustrative Turtle, not a complete deployable ontology:

```turtle
@prefix tl: <https://w3id.org/tradelens/ontology/> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

tl:PatternSnapshot a owl:Class .
tl:BreakoutSnapshot a owl:Class ; rdfs:subClassOf tl:PatternSnapshot .
tl:PatternInstance a owl:Class .
tl:LifecycleState a owl:Class .
tl:READY a tl:LifecycleState ; tl:canonicalCode "READY" .
tl:snapshotOf a owl:ObjectProperty ;
    rdfs:domain tl:PatternSnapshot ; rdfs:range tl:PatternInstance .
tl:lifecycleState a owl:ObjectProperty ;
    rdfs:domain tl:PatternSnapshot ; rdfs:range tl:LifecycleState .
tl:asOfDate a owl:DatatypeProperty ; rdfs:range xsd:date .
```

Canonical enums must be checked against specification, migrations and
`pattern_engine/enums.py`, including the existing multi-timeframe extensions.
Do not silently redefine additional implemented families as one of the original
three primary classes. Preserve unknown codes and require a reviewed ontology
extension for new semantics.

### 4.3 Time, identity and provenance are modeled explicitly

- Security identity is ISIN, with symbol/name assertions dated where source
  history exists. Never use `owl:sameAs` to merge securities based on names.
- A pattern instance keeps its UUID. A snapshot IRI includes UUID + state
  version + evidence date. The current row exposes only its current retained
  snapshot; changing the IRI does not manufacture historical snapshots.
- Membership is an individual with effective interval, source and imported
  time. Queries must apply interval semantics matching the existing repository
  conventions. Missing historical classification remains unknown.
- Valid market time and recorded knowledge time are different. A historical
  question cannot use a correction or event recorded later and claim it was
  known earlier. Source tables without sufficient revision history cannot
  answer that stricter question; mark the capability unavailable.
- Every answer fact retains subject/predicate/object or literal, source row
  key, mapping ID, observation date and available lineage. Distinguish asserted
  facts, ontology-entailed types, and service-derived decisions. Provide an
  explanation trace for inferred types without presenting inference as a
  newly measured market fact.

### 4.4 Mapping PostgreSQL into virtual RDF

Maintain R2RML mappings in persistence infrastructure, next to semantic SQL
read views. Only approved views are granted to Ontop's read-only DB role.

| Existing source | Virtual assertions | Mapping requirement |
| --- | --- | --- |
| `nse_equities` | Equity identity, symbol, company label | Stable ISIN IRI; current label is not historical proof. |
| `pattern_instances` | PatternInstance and current retained PatternSnapshot | UUID/version/date identity; exact class/type/variant/state; no synthetic history. |
| Pattern score columns and measurement JSONB | Typed score/measurement observations and price levels | Unpivot named values in reviewed SQL views; preserve units, nulls, date and lineage. |
| `pattern_events` | Immutable PatternEvent | Include effective and recorded times; only supported fields, not full state reconstruction by assumption. |
| `technical_features`, `adjusted_daily_bars` | FeatureSnapshot / Observation | Join compatible calculation/data versions; do not pick unrelated latest versions. |
| Classification/membership tables | Membership, group hierarchy | Preserve effective intervals and source availability. |
| Existing decision/ranking services | DecisionEvidence / ranking evidence in answer bundle | Same authoritative service; mark provenance as service-derived. Do not implement a duplicate SPARQL scoring formula. |
| Canonical definitions/configuration | PatternType and MethodologyDefinition | Publish controlled reference assertions through mapped reference views/tables; ontology annotations alone are not assumed to be queryable instance data. |

Illustrative R2RML mapping for one retained snapshot:

```turtle
@prefix rr: <http://www.w3.org/ns/r2rml#> .
@prefix tl: <https://w3id.org/tradelens/ontology/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .
@prefix map: <urn:tradelens:mapping:> .

map:PatternSnapshot a rr:TriplesMap ;
  rr:logicalTable [ rr:sqlQuery """
    SELECT id::text AS pattern_id, state_version, last_updated_date, state
    FROM pattern_instances
  """ ] ;
  rr:subjectMap [
    rr:template "urn:tradelens:snapshot:{pattern_id}:{state_version}:{last_updated_date}" ;
    rr:class tl:PatternSnapshot
  ] ;
  rr:predicateObjectMap [ rr:predicate tl:snapshotOf ;
    rr:objectMap [ rr:template "urn:tradelens:pattern:{pattern_id}" ] ] ;
  rr:predicateObjectMap [ rr:predicate tl:lifecycleState ;
    rr:objectMap [ rr:template "https://w3id.org/tradelens/ontology/{state}" ] ] ;
  rr:predicateObjectMap [ rr:predicate tl:asOfDate ;
    rr:objectMap [ rr:column "last_updated_date" ; rr:datatype xsd:date ] ] .
```

Production mapping should use the approved view, include provenance fields and
separate mappings for linked individuals. Validate exact PostgreSQL date/IRI
serialization, JSONB projections and Ontop SQL support in the spike. RDF mapping
can collapse duplicate triples, so entity and observation keys must be tested.

### 4.5 Constraints and ontology lifecycle

SHACL shapes require one security, instance, date and canonical state for a
complete PatternSnapshot; one numeric value/unit/score kind for each available
ScoreObservation; valid datatype/range 0-100; and well-formed membership
intervals. Missing optional evidence is allowed and explicitly reported.
Temporal cross-record constraints use tested SQL/application checks or supported
SHACL-SPARQL checks, not unsupported OWL axioms.

Run a SHACL validator over exported bounded fixture graphs and release samples;
Ontop is not assumed to execute SHACL. Validate runtime evidence bundles with
equivalent focused application checks. Never export the entire universe for
validation on every question.

Version ontology, mapping, shapes and query catalog independently in a release
manifest; record hashes with every response. Add definitions/rationale and
canonical document anchors for each public term. Require competency-question
and mapping-parity review before releasing vocabulary changes. Stable IRIs are
never repurposed; deprecated terms retain a documented replacement/migration.
An ontology change must not silently alter historical evidence or detector rules.

## 5. Retrieval and answer workflow

1. Authenticate, check feature availability, validate payload and ownership,
   reserve a user-scoped idempotent request, and enforce quotas.
2. Resolve scope and symbols to stable security identity. Ask for clarification
   when a company name matches multiple securities; do not guess.
3. Retrieve relevant ontology terms, definitions, allowed relationship paths and
   competency-query examples from the versioned catalog. Give Gemini this schema
   context plus bounded conversation history, not SQL table descriptions as the
   domain model. Prior model text is not a source of market facts.
4. Gemini emits a structured semantic plan: registered query ID, bound entity
   IRIs, date policy, ontology terms, filters and limit. Validate every term,
   relationship path, permission and budget. Compile the plan into a registered
   SPARQL template and execute through Ontop. Bind values as RDF terms using
   safe serialization; never interpolate user text as SPARQL syntax. The server
   derives user identity and entitlement. No arbitrary model-written queries.
5. Build a normalized evidence bundle. Retain actual observation date per item,
   generated time, engine/configuration/feature/adjustment versions where known,
   completeness, warnings, and stable source references.
6. Ask Gemini to return structured explanation blocks citing evidence IDs.
   Tool selection and final structured synthesis can be separate calls to avoid
   depending on model-specific combinations of tools and JSON output.
7. Validate schema and citations; reject invented evidence IDs and unsupported
   values in structured factual fields. Assemble numeric cards, dates, levels,
   source URLs and server decisions from retrieved evidence, not model text.
8. Persist the completed turn and its cited evidence snapshot, then return JSON.
   On validation failure, attempt one bounded repair within the same budget;
   otherwise return a grounded evidence-only fallback or explicit unavailable
   response. Do not save a failed output as a completed answer.

Schema validation does not prove prose is true. Keep prose short, require
citations per factual block, test semantic failures, and place decision claims
and numeric comparisons in server-authored blocks. No fabricated LLM confidence
score; evidence confidence remains the existing domain contract.

### Initial tool allowlist

| Semantic operation | Ontology query / enrichment | Boundaries |
| --- | --- | --- |
| `resolve_security` | Security labels/identifiers via mapped equity view | At most 8 matches; disambiguation mandatory. |
| `security_evidence` | CQ01: Security -> feature and pattern snapshots | Current view only; compatible lineage; parity with fingerprint service. |
| `pattern_evidence` | CQ02: snapshot -> state, observations, levels and definitions; existing decision service enrichment | Snapshot date explicit; no inferred readiness or new decision formula. |
| `pattern_timeline` | CQ04: PatternInstance <- PatternEvent | Snapshot cutoff and recorded-time policy; bounded. |
| `sector_setups` | CQ03: Membership -> Security <- eligible PatternSnapshot; shared server rank enrichment | Active/latest eligibility in shared read model; same lifecycle peers; at most 25 rows. |
| `sector_evidence` | Dated sector observations and member coverage | Existing rotation methodology/service remains authoritative. |
| `methodology` | CQ05: canonical concept -> MethodologyDefinition | Definition, units, source anchor and ontology/content version. |
| `equity_setup_count` | CQ08: distinct eligible PatternInstance aggregate, with type/state breakdown | Exact total before per-security winner collapse; same filters/cutoff as current instance list; coverage required. |
| `equity_setup_history` | CQ09: retained per-instance archive joined to dated snapshots | No active/latest-only opportunity exclusion in archive; default past set excludes current eligible active IDs; bounded pagination and exact matching total. |

Example CQ04 template, with the pattern IRI/date bound by trusted code:

```sparql
PREFIX tl: <https://w3id.org/tradelens/ontology/>
SELECT ?event ?effectiveDate ?recordedAt ?newState WHERE {
  ?event a tl:PatternEvent ; tl:eventOf ?pattern ;
         tl:effectiveDate ?effectiveDate ; tl:recordedAt ?recordedAt ;
         tl:newState ?newState .
  FILTER (?effectiveDate <= ?snapshotDate)
}
ORDER BY DESC(?effectiveDate) DESC(?recordedAt) ?event
LIMIT 25
```

The production template must also bind every external variable and enforce the
selected knowledge-time cutoff. Private watchlists/conversation data are not
mapped into the shared market endpoint in V1. An internal endpoint is not by
itself an authorization boundary; entitlements must restrict retrieval before
facts reach Gemini.

For methodology, begin with reviewed compact extracts from the canonical spec
and current engine configuration, checked into a dedicated content file. Do not
send the whole repository to Gemini. Test extracts against canonical identifiers
and version/hash changes. Embeddings/full-text retrieval can follow only if
question coverage shows that deterministic lookup is insufficient.

For multi-security comparisons, choose a common available session or explicitly
show differing dates and decline an unsupported like-for-like ranking. Preserve
nulls and units; `Pct` values already contain percentage points.

## 6. Backend files and storage

Proposed focused modules:

```text
src/backend/chat/
  service.py           # orchestration, protocols, budgets, scoped history
  gemini_client.py     # provider boundary, timeouts, response/tool translation
  tools.py             # semantic-plan schema, authorization-aware dispatch
  knowledge_graph.py   # ontology catalog, term/path validation, evidence assembly
  evidence.py          # source registry, lineage and final-output validation
  prompts.py           # versioned policies and answer schema
  methodology.json     # reviewed specification extracts and provenance
src/backend/repositories/chat.py   # PostgreSQL + behaviorally matching fake
src/backend/repositories/knowledge_graph.py  # bounded Ontop client + protocol fake
src/backend/repositories/semantic/
  tradelens.r2rml.ttl   # SQL-to-RDF mappings; persistence ownership
  queries/             # registered SPARQL templates and parameter schemas
src/backend/ontology/
  tradelens.ttl         # OWL 2 QL domain vocabulary and annotations
  shapes.ttl            # SHACL constraints
  catalog.json          # controlled concepts, definitions, permitted paths
  competency_questions.json
  release.json          # ontology/mapping/shapes/query versions and hashes
src/backend/fixtures/ontology/     # RDF fixtures and expected query bindings
infra/ontology/                    # proposed Ontop image/config; no secrets
```

Define Gemini and conversation repository protocols near the consuming service.
Inject them in `create_server`; ordinary tests use fakes and never call Gemini.
Use the maintained `google-genai` Python SDK behind the provider boundary;
pin a tested compatible version when implementing. This dependency serves the
requested integration rather than introducing an agent framework. Add RDF
parsing/SHACL validation tooling deliberately (for example RDFLib/pySHACL after
compatibility checks); do not implement RDF term escaping with string replacement.

Ontop runs as a private separately managed service with a read-only PostgreSQL
credential, bounded connection pool and DB statement timeout. Expose no SPARQL
endpoint to browsers. Restrict network access to the backend, disable federation
through allowed templates, and permit no updates, arbitrary `SERVICE`, unbounded
property paths or arbitrary graph selection. Enforce query deadline/row/response
byte limits; LIMIT alone does not bound database work. Check EXPLAIN plans for
representative joins and make shared eligibility views preserve API semantics.
Do not log expanded SPARQL containing user text or connection properties.

Use a pinned Ontop/JDBC release and explicit configuration paths. Report its
health and ontology release manifest separately; Ontop failure makes chat
unavailable without preventing login, browsing or market processing. No silent
fallback to service-only answers claimed as ontology-grounded. A semantic query
spike must demonstrate subclass entailment, mappings and result parity before
the Gemini/UI phase. Fake adapters test orchestration, while integration tests
against disposable PostgreSQL + Ontop test the actual ontology semantics.

Use a new append-only migration after the highest number at implementation time
(currently `041`). Include semantic read views and controlled reference tables
in append-only migrations, separately from conversation tables where practical.
Views expose data, not new financial calculations. Proposed chat storage:

- `chat_conversations`: UUID, owner user FK, title, validated scope JSON,
  requested date, created/updated timestamps; owner + updated-time index.
- `chat_requests`: UUID, conversation FK, client request UUID, payload hash,
  status, deadline, safe error code, model/prompt/tool/content versions,
  usage and timings. Unique conversation + client request ID.
- `chat_messages`: UUID, conversation/request FK, sequence, role, content blocks,
  cited evidence snapshot JSON, timestamps; unique conversation sequence.

Only one active turn per conversation. Reserve and finalize requests in short
transactions; do not hold a DB transaction or lock during the network call.
Retry with the same client request ID returns the completed response, or a
pending conflict; a changed payload with that ID is rejected. Expire abandoned
requests after their deadline, including after process restart. Persist only
user-visible answers, bounded tool facts and provenance, never chain-of-thought.

All conversation/message queries include owner identity. Unknown and foreign
conversation IDs both return 404. Delete cascades through requests/messages.
Proposed retention: 30 days, configurable, cleaned by an operations command or
existing outer scheduler; deletion removes snapshots too. Exclude chat content
from routine operational logs and document normal backup retention separately.

## 7. Proposed API contract

All endpoints require bearer authentication. These are new contracts, not
changes to existing market APIs.

| Endpoint | Behavior |
| --- | --- |
| `GET /api/chat/capabilities` | Enabled status, supported scopes and limits; no provider secrets. |
| `POST /api/chat/conversations` | Create owned conversation with validated scope; 201. |
| `GET /api/chat/conversations?pageSize=25&cursor=...` | Owned paginated summaries. |
| `GET /api/chat/conversations/{id}/messages?pageSize=25&cursor=...` | Owned paginated messages, oldest-to-newest within page. |
| `POST /api/chat/messages` | Submit a bounded turn; completed JSON response, 200. |
| `DELETE /api/chat/conversations/{id}` | Delete owned history; JSON confirmation. |

Example message request:

```json
{
  "conversationId": "<uuid>",
  "clientRequestId": "<uuid>",
  "message": "Explain the evidence and invalidation for this setup."
}
```

Conversation scope is stored server-side, for example
`{"kind":"pattern","patternId":"<uuid>"}` or
`{"kind":"security","symbol":"RELIANCE"}` or `{"kind":"market"}`.
Resolve symbol internally and retain original validated scope. Client messages
cannot supply system prompts, tool results, roles, owner IDs or evidence.

Response includes `conversationId`, `messageId`, `requestId`, `status`
(`answered`, `needsClarification`, `insufficientEvidence`), `blocks`, `sources`,
`warnings`, `requestedAsOf`, nullable `dataAsOf`, `generatedAt`, nullable
`engineVersion` and `configurationVersion`, `isStale`, `isPartial`, and an
`assistantVersion` object with model/prompt/tool/ontology/mapping/shapes/query/
content versions. Sources include semantic resource IRIs, mapping IDs and
asserted/entailed/service-derived provenance where applicable. UI links must
not expose internal security IRIs containing ISINs.

Count/history responses additionally use server-authored `setupSummary` and
`setupList` block types. Their fixtures define `scope` (`currentActive`,
`pastRecorded`, `allRecorded`), `security`, `filters`, nullable `totalCount`,
`returnedCount`, `countsByType`, `countsByState`, `items`, nullable `nextCursor`,
`coverage` and `dataAsOf`/per-item evidence dates. Aggregates and cursors are
trusted server output, not Gemini-generated fields. A null total means the
server cannot establish a complete count and requires an explicit warning.

Each source has `id`, `kind`, `label`, server-generated same-origin `href`,
actual `dataAsOf`, version lineage, `isStale` and evidence fields. Each block
has a validated `type`, bounded text and `sourceIds`. Model output cannot set
source URLs. Allowlist page paths through existing route builders. Methodology
sources need an in-app guide anchor mapped to their canonical document section.

For a single dated evidence bundle, top-level `dataAsOf` is that date; mixed
dates use null plus a warning and per-source dates. Unknown versions remain null
and source versions remain explicit. Methodology-only answers have no market
date. `isStale` propagates stale evidence; incomplete/mixed evidence is also
labelled partial. Define these semantics in contract fixtures before coding.

Errors follow the existing client-compatible envelope
`{"error":{"code":"...","message":"...","requestId":"..."}}`.
Use 400 for validation, 401 for invalid session, 403 for permission denial,
404 for missing/foreign history, 409 for concurrent/idempotency conflicts,
429 for local quota, 503 for disabled/upstream unavailable, and 504 for timeout.
Rate-limit errors supply a bounded retry interval. Do not expose raw provider
exceptions, credentials, prompts or database details.

## 8. Gemini configuration, limits and failure behavior

Keep `GEMINI_API_KEY` in backend environment only. Add non-secret placeholders
to `.env.example`; never use a `VITE_` key. Configuration should include
`CHAT_ENABLED`, `GEMINI_MODEL`, timeout, per-user/global concurrency, rate/token
budgets, history limit and retention. Feature disabled or missing configuration
must not prevent the rest of TradeLens from starting.

Use a pinned stable model ID selected through a short evaluation of current
Gemini Flash-class options for function calls, JSON adherence, latency and cost.
Do not use a moving `latest` alias or hard-code a speculative model name in this
plan. Verify model availability and the exact SDK/API combination at integration.
Persist the actual model ID/version returned when available.

Proposed starting limits: 4,000-character question, 12 recent messages,
3 tool rounds, 8 total tool calls, 25 rows per collection, bounded evidence and
output tokens, 30-second whole-turn deadline, 1 active turn per conversation,
2 per user and 8 globally. Reject extra work before dispatch. Tune limits using
the evaluation suite and measured cost; provider quota is an additional bound.
Store rolling user/global usage so a process restart does not reset spend limits.

V1 uses ordinary JSON requests to fit the existing transport. Keep the widget
mounted across protected-page navigation and overlay close/reopen. Abort the
browser request on widget unmount/sign-out or explicit cancellation and ignore
late results. Browser abort alone
does not guarantee the provider stopped or incurred no cost; server deadlines
and budgets remain authoritative. A response lost after completion can be
retrieved with the same request ID. Retry transient provider failures only
within the same deadline/budget; avoid duplicate provider work after a timeout.

Streaming is a later phase: extending the single low-level API transport,
server cancellation, proxy buffering, disconnect handling and final citation
validation are prerequisites. A stream must not show unvalidated factual
claims as a finalized answer.

Only send required market evidence and minimal question/history text to Google.
Exclude JWTs, email addresses, passwords, DSNs, NSE cookies and unrelated user
records. Treat user text, company names and retrieved text as untrusted data,
including instructions embedded in it. Enforce restrictions in code even if a
prompt is ignored. Prefer a paid production Gemini project after checking
applicable data-use/retention settings and market-data redistribution rights;
adding chat does not itself grant rights to send exchange data to a provider.

## 9. Frontend implementation

Add `api/chatApi.js`, `hooks/useChatConversation.js`, and focused
`components/chat/ChatWidget.jsx`, `ChatLauncher.jsx`, `ChatOverlay.jsx`, composer,
transcript and evidence components. Mount ChatWidget once in AppShell; App
supplies current-page context and session identity. Add overlay/launcher styles
using existing tokens. Do not add a route, page component, History API entry or
chat navigation link. Keep the only fetch in
`apiClient.js`; reuse `authenticatedRequest` and `useApiResource` for reads.
Keep pending send state widget-owned and guard mutations against duplicate sends
and stale responses. Clear in-memory conversation data when session changes.

Provide keyboard submission and an explicit Send button, visible labels,
restrained completion announcements, multiline entry, focus restoration and
source links reachable by keyboard. Avoid announcing every generated token.
Do not force scroll when a reader has moved up the transcript.
Opening/closing the dialog must preserve background scroll position. Lock
background scrolling while open, contain transcript scrolling and keep the
composer/close action reachable when the mobile keyboard is visible. Test
focus trapping, Escape, reopen, source navigation and stale in-flight responses.

Cover initial/loading/empty, sending, clarification, missing evidence, partial,
stale, retryable failure, quota, disabled, forbidden and expired-session states.
Retain session on 403; clear it and replace navigation on 401. Verify desktop,
tablet, 390px and 320px, including wrapping long symbols/source labels and
keeping the composer visible without horizontal overflow.

## 10. Delivery order and completion gates

| Phase | Deliverable | Completion gate |
| --- | --- | --- |
| 1. Ontology and competency design | OWL 2 QL vocabulary, canonical concepts, temporal model, SHACL shapes, CQ01-CQ07 fixtures | Profile validation and domain review; distinct score/probability meanings; supported and unavailable questions explicit. |
| 2. Mapping and Ontop proof | Semantic SQL views, R2RML, reference assertions, private Ontop, SPARQL catalog | Real PostgreSQL/Ontop tests prove subclass entailment, joins, null handling, temporal filtering and parity with existing services; query plans reviewed. |
| 3. Ontology-grounded Gemini backend | Schema-context retrieval, semantic-plan validation, evidence provenance, provider adapter, owned storage/API and budgets | Fake-provider tests plus opt-in Gemini test pass; reject unknown terms/paths and demonstrate cited ontology-grounded answers. |
| 4. Chat widget UI | Authenticated shell launcher and overlay, history, contextual open actions, evidence and failure states; no new route | Frontend tests/build, auth checks, URL/history preservation, dialog focus behavior and responsive keyboard verification pass. |
| 5. Evaluation and rollout | Admin/test cohort first, usage dashboard/metrics and feature switch | Accuracy, latency and cost reviewed on representative prompts; existing product works when chat is disabled/unavailable. |
| 6. Extensions | Reviewed cases, owned watchlist, entitled indices, then historical replay and optional streaming | Separate authorization/point-in-time tests and explicit contracts for each new tool. |

Phase 1 should start with RELIANCE (`INE002A01018`) and the reviewed offline NSE
snapshot, plus stale/missing-data fixtures. Do not depend on live NSE in normal
tests. No work in chat may trigger a scan or alter pattern detection.

Concrete first vertical slice: ontology + mappings for Equity, PatternInstance,
PatternSnapshot, LifecycleState, ScoreObservation and PatternEvent; CQ01/CQ02/
CQ04 through Ontop; then one Gemini answer displaying a snapshot date and source
trace. Acceptance requires showing the SPARQL, expected bindings and mapping
provenance in developer artifacts, plus evidence cards in the UI. A successful
API-tool answer without ontology query execution does not pass this gate.

### Evaluation and regression coverage

- Golden questions: security explanation, specific setup, two-security comparison,
  sector filtering, lifecycle explanation, methodology and ambiguous identity.
- Ontology tests: syntax/profile compliance, canonical code coverage, class and
  property entailment, no inference of a probability from SetupScore, and unknown
  rather than false for missing evidence. Validate reference data is queryable.
- Mapping tests: stable IRIs, join identities, row/triple counts where relevant,
  decimal/date/unit fidelity, JSONB projections, null omission, version-compatible
  price/feature joins and SHACL reports on valid and deliberately invalid data.
- Semantic parity tests: same eligible security/pattern IDs, peer groups and
  ordering as existing APIs; prevent old retained patterns re-entering results
  through a different mapping. Query authorization must exclude unentitled index
  data before provider disclosure, not merely hide result links afterwards.
- Equity count/history tests: multiple instances of the same type count
  separately; repeated snapshots/events/measurements do not inflate totals;
  current aggregation does not collapse to one winner per equity; current-only
  exclusions do not erase archive records; terminal and superseded records retain
  exact states/dates; counts and pages agree for the same filters/cutoff;
  timeframe scope and deterministic cursor navigation are explicit; distinguish
  verified zero from missing coverage and recorded history from historical replay.
- Adversarial cases: prompt injection, unknown tool, SQL request, cross-user
  conversation IDs, spoofed tool results/owner IDs, arbitrary URLs and secret requests.
- Evidence cases: stale date, mixed sessions/versions, absent feature, missing
  score, newer data than setup snapshot, terminal pattern, insufficient history,
  unknown future enum and percentage-point formatting.
- Historical cases: past-date query must not expose later lifecycle state;
  historical case outcomes must not leak into a then-known explanation.
- Reliability: provider 429/timeout/malformed JSON/blocked response, tool failure,
  duplicate retry, concurrent send, restart after reservation, disconnected client,
  session expiry and deletion/retention of owned history.
- Track citation validity, numeric-card equality to source, unsupported-claim
  frequency, correct abstention, tool selection, p50/p95 latency, tokens and cost.
  Use human-reviewed prose samples; schema validation alone is insufficient.

Run narrow chat/backend tests first, then the complete backend suite and
frontend tests/build when implementing across both boundaries. Live Gemini
evaluation is opt-in and billed; keep ordinary CI fully offline. Do not claim
performance targets until measured.

## 11. Documentation changes when implementation is accepted

Update the server and client implementation plans and AGENTS.md with the
accepted ontology architecture, ontology/mapping ownership, chat API,
permission, inference and evidence rules. Update
README/environment examples with setup, disabled behavior, retention operations
and opt-in evaluation commands. This proposal deliberately leaves existing
canonical contracts unchanged.

## 12. Official integration references

Consulted for this proposal; recheck model capabilities, quotas and terms during
implementation:

- [Ontop concepts](https://ontop-vkg.org/guide/concepts.html) and
  [supported features](https://ontop-vkg.org/guide/): ontology-based virtual RDF
  queries, mapping support, PostgreSQL integration and entailment scope.
- [OWL 2 profiles](https://www.w3.org/TR/owl2-profiles/): OWL 2 QL is intended
  for relational query answering with lightweight ontology semantics.
- [R2RML](https://www.w3.org/TR/r2rml/): standard mapping of relational data to RDF.
- [SHACL](https://www.w3.org/TR/shacl/): graph validation constraints; distinct
  from OWL entailment.
- [SPARQL 1.1](https://www.w3.org/TR/sparql11-overview/): query language and
  result formats; verify the exact Ontop-supported subset in integration tests.

- [Gemini function calling](https://ai.google.dev/gemini-api/docs/function-calling):
  the model proposes function calls; the application controls execution.
- [Structured outputs](https://ai.google.dev/gemini-api/docs/structured-output):
  schema-constrained response support; still requires application validation.
- [Google Gen AI Python SDK](https://googleapis.github.io/python-genai/):
  provider integration and tool-call behavior; use explicit bounded dispatch.
- [Gemini models](https://ai.google.dev/gemini-api/docs/models): verify a stable
  model's availability and supported capabilities before choosing its exact ID.
- [Gemini API terms](https://ai.google.dev/gemini-api/terms): review applicable
  paid/unpaid data-use conditions before production traffic.
