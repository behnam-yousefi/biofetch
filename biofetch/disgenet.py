"""
DisGeNET tool — query gene-disease associations via the DisGeNET API.

API docs: https://disgenet.com/api (interactive console:
https://disgenet.com/interactive-console). Requires DISGENET_API_KEY in the
environment (register at https://disgenet.com).

See docs/disgenet_api_reference.md in this repo for the verified endpoint,
parameter, and response reference this implementation is built from. Notably:
"/gda/disease" and "/gda/gene" (used by an earlier version of this file) do
not exist — the real endpoint is "/gda/summary" for both directions, and a
disease query needs a DisGeNET disease ID, not a free-text name, which is why
this module resolves one via "/entity/disease" first.
"""

import difflib
import os
import httpx

BASE_URL = "https://api.disgenet.com/api/v1"


def _extract_list(data) -> list:
    """Both /gda/summary and /entity/disease return a bare JSON array as their
    actual 200 response (verified live against the Swagger schema), despite
    their prose descriptions mentioning a "payload" wrapper — that wording
    appears to be stale/boilerplate, not the real shape. Handled defensively
    anyway in case a differently-shaped error body ever comes through here."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("payload") or []
    return []


def _resolve_disease_id(query: str, headers: dict) -> tuple[str | None, str | None]:
    """Resolve a free-text disease name to a DisGeNET disease ID via
    /entity/disease's disease_free_text_search_string param (the only way to
    query DisGeNET by name — /gda/summary itself only accepts a structured
    disease ID).

    Ranks candidates by string similarity to the query, NOT the API's own
    documented `search_rank` field — a live test call (searching "cystic
    fibrosis") showed `search_rank` comes back NaN for every candidate
    despite the docs saying it's populated for free-text search, and Python's
    max() over all-NaN keys silently returns whichever candidate happened to
    be listed first rather than the best match (comparisons against NaN are
    always False, so nothing ever looks "better" than the first). That
    produced a real wrong-disease match ("Fibrosis" instead of "Cystic
    Fibrosis") in testing, hence the client-side ranking here instead.

    Returns (disease_id, matched_name), or (None, None) if nothing matched.
    """
    resp = httpx.get(
        f"{BASE_URL}/entity/disease",
        params={"disease_free_text_search_string": query},
        headers=headers, timeout=30,
    )
    if resp.status_code == 404:
        return None, None
    resp.raise_for_status()
    candidates = _extract_list(resp.json())
    if not candidates:
        return None, None

    def similarity(c: dict) -> float:
        name = c.get("name") or ""
        return difflib.SequenceMatcher(None, query.lower(), name.lower()).ratio()

    best = max(candidates, key=similarity)
    disease_umls_cui = best.get("diseaseUMLSCUI")
    if not disease_umls_cui:
        return None, None
    return f"UMLS_{disease_umls_cui}", best.get("name", query)


def search_disgenet(
    query:       str,
    query_type:  str = "disease",   # "disease" | "gene"
    max_results: int = 50,
    api_key:     str | None = None,
) -> dict:
    """
    Search DisGeNET for gene-disease associations.

    query:       disease name or gene symbol (e.g. 'Parkinson disease', 'CFTR').
    query_type:  'disease' to find genes associated with a disease — resolved
                 to a DisGeNET disease ID internally via free-text search first,
                 since the underlying API has no plain-name disease parameter.
                 'gene' to find diseases associated with a gene (HGNC symbol,
                 accepted directly by the API, no resolution step needed).
    max_results: maximum number of associations to return. DisGeNET returns up
                 to 100 results per page and pagination beyond that isn't
                 implemented here (max_results above 100 has no extra effect).
    api_key:     DisGeNET API key. Falls back to DISGENET_API_KEY if not given.
    """
    api_key = api_key or os.getenv("DISGENET_API_KEY")
    if not api_key:
        return {
            "n_results": 0, "is_complete": False, "associations": [],
            "warnings": ["DISGENET_API_KEY not set. Register at https://disgenet.com"],
        }

    headers = {"Authorization": f"Bearer {api_key}"}
    matched_disease_name = None

    if query_type == "disease":
        disease_id, matched_disease_name = _resolve_disease_id(query, headers)
        if not disease_id:
            return {
                "n_results": 0, "is_complete": True, "associations": [],
                "warnings": [f"No DisGeNET disease matching '{query}' found."],
            }
        params = {"disease": disease_id}
    else:
        params = {"gene_symbol": query}

    resp = httpx.get(f"{BASE_URL}/gda/summary", params=params, headers=headers, timeout=30)
    if resp.status_code == 404:
        return {
            "n_results": 0, "is_complete": True, "associations": [],
            "warnings": [f"No gene-disease associations found for '{query}'."],
        }
    resp.raise_for_status()
    items = _extract_list(resp.json())

    associations = []
    for item in items[:max_results]:
        associations.append({
            "gene_symbol":   query if query_type == "gene" else "",
            "gene_ncbi_id":  item.get("geneNcbiID"),
            "disease_name":  item.get("diseaseName", matched_disease_name or ""),
            "score":         item.get("score"),
            "ei":            item.get("ei"),       # evidence index
            "n_pmids":       item.get("numPMIDs"),
        })

    is_complete = len(items) <= max_results
    warnings    = []
    if not is_complete:
        warnings.append(f"Query matched {len(items)} associations; returning first {max_results}.")
    if query_type == "disease" and matched_disease_name and matched_disease_name.lower() != query.lower():
        warnings.append(f"Matched DisGeNET disease '{matched_disease_name}' for query '{query}'.")

    return {
        "n_results":    len(items),
        "is_complete":  is_complete,
        "associations": associations,
        "warnings":     warnings,
    }


_ENRICHMENT_ID_FIELDS = {
    "symbol":  "geneHGNCList",
    "ncbi":    "geneNCBIList",
    "ensembl": "geneENSEMBLList",
    "uniprot": "geneUniProtList",
}


def search_disgenet_enrichment(
    genes:       str,
    id_type:     str = "symbol",   # "symbol" | "ncbi" | "ensembl" | "uniprot"
    max_results: int = 50,
    api_key:     str | None = None,
) -> dict:
    """
    Gene-set enrichment analysis via DisGeNET: given a list of genes, finds
    diseases whose known associated genes significantly overlap with it —
    set-level reasoning, distinct from search_disgenet's single gene/disease
    lookups. Useful for interpreting a gene signature or hit-list rather than
    asking about one gene at a time.

    genes:       comma-separated gene identifiers, matching id_type (e.g.
                 'CFTR,BRCA1,TP53' for symbols), up to 4000.
    id_type:     'symbol' (HGNC, default) | 'ncbi' | 'ensembl' | 'uniprot' —
                 must match the format of `genes`.
    max_results: maximum number of disease associations to return, ordered
                 by ascending p-value (most significant first). DisGeNET can
                 return thousands of rows for a broad gene set; this is a
                 client-side cap, not a real pagination limit (no server-side
                 pagination was hit in testing even at ~5000 results).
    api_key:     DisGeNET API key. Falls back to DISGENET_API_KEY if not given.
    """
    api_key = api_key or os.getenv("DISGENET_API_KEY")
    if not api_key:
        return {
            "n_results": 0, "is_complete": False, "associations": [],
            "warnings": ["DISGENET_API_KEY not set. Register at https://disgenet.com"],
        }

    field = _ENRICHMENT_ID_FIELDS.get(id_type)
    if field is None:
        return {
            "n_results": 0, "is_complete": False, "associations": [],
            "warnings": [f"Unknown id_type '{id_type}'. Use one of: {', '.join(_ENRICHMENT_ID_FIELDS)}."],
        }

    headers = {"Authorization": f"Bearer {api_key}"}
    resp = httpx.post(f"{BASE_URL}/enrichment/gene", json={field: genes}, headers=headers, timeout=30)
    if resp.status_code == 404:
        return {
            "n_results": 0, "is_complete": True, "associations": [],
            "warnings": [f"No enrichment results found for genes '{genes}'."],
        }
    resp.raise_for_status()
    items = _extract_list(resp.json())

    associations = []
    for item in items[:max_results]:
        associations.append({
            "disease_name":                  item.get("diseaseName"),
            "disease_umls_cui":              item.get("diseaseUMLSCUI"),
            "pvalue":                        item.get("pvalue"),
            "odds_ratio":                    item.get("oddsRatio"),
            "odds_ratio_ci":                 item.get("oddsRatioCI"),
            "intersection":                  item.get("intersection"),
            "intersection_size":             item.get("intersectionSize"),
            "n_genes_associated_to_disease": item.get("numGenesAssociatedToDisease"),
            "source":                        item.get("source"),
        })

    is_complete = len(items) <= max_results
    warnings    = []
    if not is_complete:
        warnings.append(f"Query matched {len(items)} disease associations; returning first {max_results} (ordered by ascending p-value).")

    return {
        "n_results":    len(items),
        "is_complete":  is_complete,
        "associations": associations,
        "warnings":     warnings,
    }
