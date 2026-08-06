"""
DisGeNET tool — query gene-disease associations via the DisGeNET API.

API docs: https://disgenet.com/api
Requires DISGENET_API_KEY in the environment (register at https://disgenet.com).
"""

import os
import httpx

BASE_URL = "https://api.disgenet.com/api/v1"


def search_disgenet(
    query:       str,
    query_type:  str = "disease",   # "disease" | "gene"
    max_results: int = 50,
    api_key:     str | None = None,
) -> dict:
    """
    Search DisGeNET for gene-disease associations.

    query:       disease name or gene symbol (e.g. 'Parkinson disease', 'CFTR').
    query_type:  'disease' to find genes associated with a disease,
                 'gene' to find diseases associated with a gene.
    max_results: maximum number of associations to return.
    api_key:     DisGeNET API key. Falls back to DISGENET_API_KEY if not given.
    """
    api_key = api_key or os.getenv("DISGENET_API_KEY")
    if not api_key:
        return {
            "n_results": 0, "is_complete": False, "associations": [],
            "warnings": ["DISGENET_API_KEY not set. Register at https://disgenet.com"],
        }

    headers = {"Authorization": f"Bearer {api_key}"}

    if query_type == "disease":
        endpoint = f"{BASE_URL}/gda/disease"
        params   = {"disease_name": query, "limit": max_results}
    else:
        endpoint = f"{BASE_URL}/gda/gene"
        params   = {"gene_symbol": query, "limit": max_results}

    resp = httpx.get(endpoint, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data  = resp.json()
    items = data.get("payload", [])
    total = data.get("totalCount", len(items))

    associations = []
    for item in items:
        associations.append({
            "gene_symbol":    item.get("gene_symbol", ""),
            "disease_name":   item.get("disease_name", ""),
            "score":          item.get("score"),
            "ei":             item.get("ei"),       # evidence index
            "n_pmids":        item.get("pmid_count"),
            "url":            f"https://disgenet.com/gene/{item.get('geneid')}/diseases",
        })

    is_complete = total <= max_results
    warnings    = []
    if not is_complete:
        warnings.append(f"Query matched {total} associations; returning first {max_results}.")

    return {
        "n_results":    total,
        "is_complete":  is_complete,
        "associations": associations,
        "warnings":     warnings,
    }
