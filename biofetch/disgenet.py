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
    disease ID). Takes the highest-search_rank match. Returns
    (disease_id, matched_name), or (None, None) if nothing matched.
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

    best = max(candidates, key=lambda c: c.get("search_rank") or 0)
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
