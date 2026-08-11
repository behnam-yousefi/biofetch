# DisGeNET REST API — reference notes

Source: https://disgenet.com/interactive-console (Swagger console, verified live
2026-08-11). Base URL: `https://api.disgenet.com/api/v1`. Auth: `Authorization:
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
| 4_entity | `/entity/gene` | GET | Resolve/describe gene(s) | Presumed analogous to `/entity/disease` (ID or free-text) — not yet confirmed | Not yet verified — likely has a similar free-text param, worth checking before relying on it |
| 4_entity | `/entity/chemical` | GET | Resolve/describe chemical(s)/drug(s) | Presumed analogous — chemical ID formats include `DRUGBANK_<id>`, `CHEMBL_<id>`, `MESH_<id>`, `PUBCHEM_<id>` (per `/gda/summary`'s `chemical_id` param docs) — worth checking for a free-text drug-name param, which could help resolve drug names before cross-referencing DrugBank | Not yet verified |
| 4_entity | `/entity/publication` | GET | Properties of publication(s) | Not explored | Not explored |
| 4_entity | `/entity/variant` | GET | Properties of variant(s) | Not explored | Not explored |
| 5_enrichment | `/enrichment/gene` | POST | Gene-set enrichment — given a **list** of genes, returns over-represented disease/pathway associations | POST body, not yet inspected in detail | **Candidate new tool** — distinct capability from all current biofetch tools (set-level reasoning, not single-entity lookup). Useful for interpreting a gene signature/hit-list. |
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

Not implemented (deliberately out of scope for this pass — see capability
table above): `/enrichment/gene` (gene-set enrichment, a new tool rather than
a bug fix), `/entity/gene` and `/entity/chemical` free-text resolution (no
current use case hitting that gap the way disease-name search did), `dda`/`vda`
categories.
