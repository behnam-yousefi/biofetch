# DisGeNET REST API — reference notes

Source: https://disgenet.com/interactive-console (Swagger console, verified live
2026-08-11; endpoints below re-verified 2026-08-17 via the raw OpenAPI spec —
the console embeds an iframe at `https://api.disgenet.com/doc/swagger`, which
itself loads its spec from `https://api.disgenet.com/v2/api-docs`, a plain
JSON document — fetching that directly is far more reliable than scrolling the
console's custom React UI, and gives the exact request/response schema instead
of prose). Base URL: `https://api.disgenet.com/api/v1`. Auth: `Authorization:
Bearer <DISGENET_API_KEY>` header (register/generate key at disgenet.com).

`biofetch/disgenet.py`'s original implementation targeted `/gda/disease` and
`/gda/gene`, which **do not exist** — confirmed via a real authenticated call
(`404`, not `401`, meaning the key worked but the path didn't). This doc is
the ground truth to fix that, and a map of what else the API offers.

## Capability table

| Category | Endpoint | Method | Purpose | Key parameters | Status |
|---|---|---|---|---|---|
| 1_gda | `/gda/summary` | GET | Gene-disease associations — the correct replacement for the old `/gda/disease` and `/gda/gene` | `gene_symbol` (HGNC symbol, comma-sep, up to 100) **or** `disease` (vocab-prefixed ID, e.g. `UMLS_C0030567`, `OMIM_143890`; NOT a free-text name) — at least one of `gene_ncbi_id`/`gene_ensembl_id`/`gene_symbol`/`uniprot_id`/`disease`/`chemical_id` required. Plus optional filters: `source`, `evidence_level`, `min_score`/`max_score`, `min_ei`/`max_ei`, `disease_type`, `dis_class_list`, `order_by`, `order`. | **Verified** — confirmed correct via Swagger schema |
| 1_gda | `/gda/evidence` | GET | Evidence records (publications) supporting a gene-disease association | Same identifier params as `/gda/summary` | Not yet explored in detail |
| 1_gda | `/gda/shared` | GET | Shared genes between diseases | Disease identifiers | Not yet explored in detail |
| 2_vda | `/vda/summary`, `/vda/evidence`, `/vda/shared` | GET | Variant-disease associations (SNP/variant level, not gene level) | Variant identifiers (dbSNP etc.) | Not explored — likely lower priority; relevant only if the agent needs variant-level (not gene-level) precision-medicine queries |
| 3_dda | `/dda` | GET | Disease-disease associations (shared-gene based, Jaccard index) | Disease identifiers | Not explored — candidate for repurposing/comorbidity reasoning |
| 4_entity | `/entity/disease` | GET | Resolve/describe disease(s) — **this is the free-text name lookup DisGeNET-side queries need** | `disease` (ID) **or** `disease_free_text_search_string` (plain text, e.g. "systemic lupus erythematosus") — response includes a `search_rank` relevance score per match when using free-text search | **Verified** — confirmed `disease_free_text_search_string` param exists and is exactly what's needed |
| 4_entity | `/entity/gene` | GET | Resolve/describe gene(s) | `gene_free_text_search_string` (plain text, single-gene query only) **or** `gene_ncbi_id`/`gene_ensembl_id`/`gene_symbol`/`uniprot_id` | **Verified** — confirmed `gene_free_text_search_string` exists via the raw spec; response is `GeneDTO`, same `search_rank`-is-NaN issue as `/entity/disease` (confirmed live) — see response shape section below |
| 4_entity | `/entity/chemical` | GET | Resolve/describe chemical(s)/drug(s) | `chemical_name` (plain text, single-chemical query only) **or** `chemical_id` (formats: `DRUGBANK_<id>`, `CHEMBL_<id>`, `MESH_<id>`, `PUBCHEM_<id>`) | **Verified** — confirmed `chemical_name` free-text param exists via the raw spec; response is `ChemicalDTO` |
| 4_entity | `/entity/publication` | GET | Properties of publication(s) | Not explored | Not explored |
| 4_entity | `/entity/variant` | GET | Properties of variant(s) | Not explored | Not explored |
| 5_enrichment | `/enrichment/gene` | POST | Gene-set enrichment — given a **list** of genes, returns over-represented disease associations, ordered by ascending p-value | JSON body (`EnrichmentRequest`): one of `geneNCBIList`/`geneENSEMBLList`/`geneHGNCList`/`geneUniProtList` (comma-sep, up to 4000), optional `disList` (restrict to specific diseases), `source`, `minScore`/`maxScore`, `maxPvalue`, `commonGenes`, `pageNumber` | **Verified, live-tested** — confirmed working with a real gene list (CFTR/BRCA1/TP53 → 4843 disease associations, correctly ordered by p-value, correct `intersection` sets). Distinct capability from all current biofetch tools (set-level reasoning, not single-entity lookup) — the standout candidate for a new tool. |
| 5_enrichment | `/enrichment/variant` | POST | Variant-set enrichment | Not explored | Lower priority, same reasoning as vda |
| 6_embeddings | (not explored) | ? | "DISGENET normalization" — likely ML-embedding-based similarity | Not explored | Unclear value — flagged for future investigation, not evaluated |

## `/gda/summary` response shape (confirmed via Swagger `Model` view)

Response is a **raw JSON array** of `GeneDiseaseAssocSummaryDTO` objects — NOT
wrapped in `{"payload": [...], "totalCount": ...}` as the old `disgenet.py`
code assumed. Confirmed fields relevant to biofetch's current output shape:

- `diseaseName` (string), `diseaseUMLSCUI` (string), `diseaseType`, `diseaseVocabularies`
- `geneNcbiID` (int) — **no gene symbol/name field exists in the response**,
  only the numeric NCBI ID. If a human-readable symbol is wanted in the
  output, echo back the symbol that was searched by (already known to the
  caller) rather than expecting the API to return one.
- `score` (double, the DisGeNET GDA score), `normalized_score`
- `numPMIDs` (int), `ei` (evidence index), `el` (evidence level string)
- `geneDSI`, `geneDPI`, `genepLI` — gene-level metrics (disease specificity
  index, disease pleiotropy index, loss-of-function intolerance probability)

404 is a **documented** response code for `/gda/summary` (alongside 401/403),
meaning an unrecognized/malformed identifier can legitimately 404 even with
a correct endpoint path and a valid key — not just a routing error.

## `/entity/disease` response shape (confirmed via Swagger `Model` view)

Also a **bare JSON array**, of `DiseaseDTO` objects — same pattern as
`/gda/summary`, despite the same stale "payload field" wording in its prose
description. Confirmed fields relevant to name resolution:

- `name` (string) — the disease's name. **Not** `diseaseName` — that's the
  field name in `/gda/summary`'s *different* DTO
  (`GeneDiseaseAssocSummaryDTO`); easy to mix up since both DTOs describe
  "a disease" but were not designed with matching field names.
- `diseaseUMLSCUI` (string) — same field name as in `/gda/summary`'s DTO, used
  to build the `UMLS_<cui>` identifier `/gda/summary`'s `disease` param expects.
- `search_rank` (float) — documented as relevance score, populated only for
  free-text search. **In practice (confirmed via a live authenticated call
  searching "cystic fibrosis"), this came back `NaN` for every single
  candidate** — the field exists but isn't actually computed, at least not
  for this account/tier. Do not rank by it: Python's `max(..., key=...)`
  over all-NaN keys silently returns whichever item is first in the list
  (NaN comparisons are always `False`, so nothing ever beats the first
  candidate) — this produced a real wrong-disease match ("Fibrosis" instead
  of "Cystic Fibrosis") before it was caught. `biofetch/disgenet.py` ranks
  candidates by `difflib.SequenceMatcher` string similarity to the query
  instead, which correctly picks the exact/closest name match.
- `synonyms` (array) — not used currently, but available if fuzzy-name
  disambiguation ever needs alternate names to show the caller.

## `/enrichment/gene` request/response shape (confirmed via raw spec + a live test call)

Request body (`EnrichmentRequest`, JSON, not query params — this is a `POST`):
exactly one gene-list field is needed: `geneHGNCList` (symbols, e.g.
`"CFTR,BRCA1,TP53"`), `geneNCBIList`, `geneENSEMBLList`, or `geneUniProtList`.
Everything else is optional filtering (`disList` to restrict to specific
diseases, `source`, `minScore`/`maxScore`, `maxPvalue`, `commonGenes`,
`pageNumber`).

Response is a bare JSON array of `GeneEnrichmentDTO`, ordered by ascending
p-value — confirmed live with `geneHGNCList=CFTR,BRCA1,TP53` (4843 results,
no pagination cap hit despite the docs' TRIAL-tier "top-30" language, so
that limit apparently doesn't apply to this account/tier):

- `diseaseName`, `diseaseUMLSCUI` — same disease-identity fields as elsewhere
- `pvalue`, `oddsRatio`, `oddsRatioCI` (`[lower, upper]`) — statistical significance
- `intersection` (array of gene symbols actually shared with the disease),
  `intersectionSize`, `geneRatio`, `bgRatio`
- `numGenesAssociatedToDisease`, `totalGenesSource`, `source`

No pagination cap was hit in testing, but a biofetch wrapper should still
apply its own `max_results` truncation (same convention as every other
biofetch tool) — a broad gene list against `ALL` sources could plausibly
return thousands of rows, same as it did here for just 3 genes.

## `/entity/gene` and `/entity/chemical` response shape (confirmed via raw spec + a live test call)

`GeneDTO`'s name field is `symbolOfGene` (not `name`, not `geneSymbol` — yet
another DTO-specific name, same inconsistency pattern as `/entity/disease`
vs `/gda/summary`). It also has a `search_rank` field — **confirmed live to
be `NaN` for every candidate**, identical to `/entity/disease`'s issue. Any
gene free-text resolution must rank candidates the same way
`_resolve_disease_id` already does (string similarity via
`difflib.SequenceMatcher`), not by `search_rank`.

`ChemicalDTO`'s name field is `chemPrefName`. Not live-tested for the
`search_rank` issue, but given the identical pattern in both `DiseaseDTO` and
`GeneDTO`, assume it's broken there too until proven otherwise rather than
trusting it by default.

## Fix status

**Implemented** in `biofetch/disgenet.py` (see that file's own docstring/comments):

1. Both gene and disease queries go through `/gda/summary`.
2. Gene path: `gene_symbol=<query>` — unchanged, was already correct.
3. Disease path: resolves via `/entity/disease?disease_free_text_search_string=<query>`
   first (best string-similarity match — see `search_rank` note above for
   why not the API's own ranking — using its `diseaseUMLSCUI` field), then
   queries `/gda/summary?disease=UMLS_<cui>`. The matched disease name is
   surfaced back in a `warnings` entry when it differs from the query string,
   so the caller can tell if DisGeNET matched something other than intended.
4. Response parsing reads the bare top-level array via a small
   `_extract_list()` helper (defensive — also handles a `{"payload": [...]}`
   shape, in case that ever turns out to be real for some other endpoint or
   error case not yet seen), mapping `diseaseName`, `geneNcbiID`, `score`,
   `numPMIDs`, `ei` from `/gda/summary`'s actual field names.
5. `search_disgenet_enrichment(genes, id_type, max_results, api_key)` — new
   tool wrapping `POST /enrichment/gene`. `id_type` maps to the right
   `EnrichmentRequest` field (`symbol`→`geneHGNCList`, `ncbi`→`geneNCBIList`,
   `ensembl`→`geneENSEMBLList`, `uniprot`→`geneUniProtList`). Live-tested with
   `CFTR,BRCA1,TP53` — correct results, correct `intersection` sets, ordered
   by ascending p-value as documented.

Not yet implemented, but now verified and ready to build (see capability
table + response-shape sections above):

- `/entity/gene` and `/entity/chemical` free-text resolution — confirmed to
  exist and work the same way `/entity/disease` does, `search_rank`-is-NaN
  issue included. No current use case hitting this gap the way disease-name
  search did, so still lower priority.

Still unexplored, lower priority: `/gda/evidence`, `/gda/shared`, `dda`,
`vda/*`, `/enrichment/variant`, embeddings.
