# Orphadata API — reference notes

Source: https://api.orphadata.com/ (verified live 2026-08-17, via its raw
OpenAPI spec at `https://api.orphadata.com/openapi.json` — same efficient
approach as `disgenet_api_reference.md`: fetch the spec directly instead of
navigating a rendered API-docs page). No auth required at all (`security` is
absent from the spec, confirmed by successful unauthenticated calls) — a step
even simpler than DisGeNET or OMIM.

**This is a different, separate Orphanet API from the one `biofetch/orphanet.py`
currently uses** (`api.orphacode.org`, the ORPHAcode nomenclature lookup only).
Orphadata is Orphanet's full structured-data product: cross-referencing to
other terminologies, classifications, HPO clinical signs, gene associations,
epidemiology, natural history, and medical specialty — 32 endpoints across 7
categories, all `GET`, all free.

## Capability table

| Category | Endpoint | Purpose | Key parameters | Status |
|---|---|---|---|---|
| rd-cross-referencing | `/rd-cross-referencing/orphacodes/names/{name}` | Resolve a disease name to its ORPHAcode plus cross-references (ICD-10, ICD-11, OMIM, MONDO, MeSH, MedDRA, UMLS, GARD) | `name` (path), `lang` (query, default `en`) | **Verified, live-tested** — see gotcha below: fuzzy-matching is unreliable, don't trust a single result blindly |
| rd-cross-referencing | `/rd-cross-referencing/omims/{omim}` | Reverse lookup: OMIM code → Orphanet disease + cross-references | `omim` (path), `lang` | **Verified, live-tested** (CF's OMIM `219700` → 200 OK) — nice bridge to the existing `search_omim` tool |
| rd-cross-referencing | `/rd-cross-referencing/icd-10s/{icd}`, `/icd-11s/{icd}` | Reverse lookup by ICD-10/ICD-11 code | `icd` (path), `lang` | Not live-tested, same shape as the OMIM reverse lookup — low risk |
| rd-phenotypes | `/rd-phenotypes/orphacodes/{orphacode}` | Clinical signs/symptoms — HPO phenotype associations with frequency | `orphacode` (path, int), `lang` | **Verified, live-tested** — genuinely new capability, nothing in current `biofetch` covers this |
| rd-epidemiology | `/rd-epidemiology/orphacodes/{orphacode}` | Prevalence/incidence data, per-country, with PMID sources | `orphacode` (path, int), `lang` | **Verified, live-tested** — genuinely new capability |
| rd-natural_history | `/rd-natural_history/orphacodes/{orphacode}` | Disease course/prognosis data | `orphacode` (path, int), `lang` | Not live-tested, same shape as epidemiology/phenotypes — low risk |
| rd-associated-genes | `/rd-associated-genes/genes/symbols/{symbol}` | Diseases associated with a gene, by symbol | `symbol` (path) | **Verified, live-tested — case-sensitive, lowercase only** (`cftr` → 200, `CFTR` → 404). See gotcha below. |
| rd-associated-genes | `/rd-associated-genes/genes/names/{name}` | Diseases associated with a gene, by (partial) gene name | `name` (path) | Live-tested with a full gene name, 404'd — needs more investigation before relying on it (case-sensitivity may apply here too) |
| rd-associated-genes | `/rd-associated-genes/orphacodes/{orphacode}` | Genes associated with a disease, by ORPHAcode | `orphacode` (path) | Not live-tested, same category as the gene-symbol endpoint |
| rd-classification | `/rd-classification/orphacodes/{orphacode}/hchids` | Where a disease sits in Orphanet's classification hierarchy (parents/children) | `orphacode` (path) | Not live-tested — lower priority, useful mainly for browsing/taxonomy UIs |
| rd-medical-specialties | `/rd-medical-specialties/orphacodes/{orphacode}` | Medical specialty linearisation for a disease | `orphacode` (path) | Not explored |

## `/rd-cross-referencing/orphacodes/names/{name}` — gotcha: unreliable fuzzy matching

**Confirmed live**: querying `"PAH deficiency"` returns a confident `200 OK`
match for **"Myeloperoxidase deficiency"** (ORPHAcode 2587) — completely
wrong; PAH (phenylalanine hydroxylase) deficiency is an unrelated disease.
Meanwhile a clean substring like `"phenylketon"` (of "Phenylketonuria")
returns a plain `404`, not a ranked list of candidates. So this endpoint's
matching is inconsistent: sometimes it silently guesses wrong with no
uncertainty signal, sometimes it fails outright on a query a human would find
obviously resolvable.

**Do not use this endpoint alone for name resolution.** The currently-used
`api.orphacode.org` `ApproximateName` endpoint (`biofetch/orphanet.py`'s
`search_orphanet`) already returns a **ranked list** of candidates instead of
one silent guess — safer, since the caller (or an LLM) can see there were
multiple matches and pick or ask, the same reasoning that led to fixing
DisGeNET's disease resolution. The sensible combination: keep
`search_orphanet` (via `api.orphacode.org`) as the name → ORPHAcode
resolution step, then use Orphadata's richer endpoints (cross-referencing,
phenotypes, epidemiology, genes) for the detail lookups once an ORPHAcode is
already known/confirmed — two complementary APIs joined by ORPHAcode, not a
replacement of one by the other.

## `/rd-associated-genes/genes/symbols/{symbol}` — gotcha: lowercase only

Confirmed live: `cftr` → `200`, `CFTR` → `404`, `BRCA1` → `404`. HGNC gene
symbols are conventionally uppercase (as DisGeNET's own `gene_symbol` param
expects them) — a wrapper around this endpoint must lowercase the symbol
before querying, or every standard-cased gene symbol will silently 404.

## Response shape notes (confirmed via live calls)

All successful responses share the same envelope:
```json
{"data": {"__count": <int>, "__licence": {...}, "results": <object or array>}}
```
`results` is a **single object** (not a list) for by-ID/by-exact-name lookups
(e.g. `.../names/{name}`, `.../orphacodes/{orphacode}`) — there is no
multi-candidate response shape in this API the way DisGeNET's `/entity/*`
free-text search returns a list; that's exactly why the fuzzy-match gotcha
above matters so much (nowhere for the API to express "here are 3 possible
matches, you choose").

- `/rd-cross-referencing/orphacodes/names/{name}` → `results.ORPHAcode`,
  `results["Preferred term"]`, `results.Synonym` (array), `results.ExternalReference`
  (array of `{Source, Reference, DisorderMappingRelation, ...}` — `Source` values
  seen live: `GARD`, `ICD-10` (multiple), `ICD-11`, `MONDO`, `MeSH`, `MedDRA`,
  `OMIM`, `UMLS`).
- `/rd-phenotypes/orphacodes/{orphacode}` → nested one level deeper than the
  others: `results.Disorder.HPODisorderAssociation`, each item
  `{HPO: {HPOId, HPOTerm}, HPOFrequency}` (frequency as a text band, e.g.
  `"Occasional (29-5%)"`, not a number).
- `/rd-epidemiology/orphacodes/{orphacode}` → `results.Prevalence` (array),
  each item `{PrevalenceType, PrevalenceClass, PrevalenceGeographic,
  PrevalenceQualification, PrevalenceValidationStatus, ValMoy, Source}` — CF
  (ORPHAcode 586) returned dozens of per-country entries with PMID sources,
  genuinely rich data.

## Fix status

**Implemented**: `get_orphanet_disease_details(orphanet_id, lang)` in
`biofetch/orphanet.py` — a new function, not a change to `search_orphanet`'s
signature, deliberately taking only an already-resolved `orphanet_id` (see
the fuzzy-matching gotcha above for why). Makes three independent Orphadata
calls (cross-referencing, phenotypes, epidemiology), each handled on its own
so one dataset having no data for a given disease (a plain 404) doesn't blank
out the other two. `search_orphanet`'s own result gained a `next_steps` hint
pointing at it. Live-tested end to end with Cystic fibrosis (ORPHAcode 586):
correct name/synonyms, 11 cross-references (GARD/ICD-10 x4/ICD-11/MONDO/MeSH/
MedDRA/OMIM/UMLS) with mapping-relation detail, real HPO phenotype data with
frequency bands, and per-country prevalence data with sources.

Not implemented, lower priority: gene-association lookup
(`/rd-associated-genes/*`) as an Orphanet-native complement to DisGeNET's own
gene-disease tool — DisGeNET already covers this ground, and the name-search
variant here needs more investigation (case-sensitivity, reliability) before
it's trustworthy.
