"""
Orphanet tool — search rare/orphan diseases via the Orphanet ORPHAcodes API.

API docs / spec: https://api.orphacode.org/openapi.json
Requires an `apiKey` header, but per the API's own description this is just a
self-chosen identifier ("enter a user name of your choosing"), not a real
registered secret — any non-empty string works. Override with ORPHANET_API_KEY
if you want to identify your own usage.
"""

import os
import httpx

BASE_URL = "https://api.orphacode.org/EN"


def search_orphanet(
    query:       str,
    max_results: int = 50,
    api_key:     str | None = None,
) -> dict:
    """
    Search Orphanet for rare/orphan diseases matching a query term.
    Returns disease names, Orphanet IDs, and URLs.

    query:       disease name or keyword (e.g. 'phenylketonuria', 'cystic fibrosis').
    max_results: maximum number of diseases to return.
    api_key:     usage identifier for the apiKey header (not a real secret, see
                 module docstring). Falls back to ORPHANET_API_KEY, then "biofetch".
    """
    api_key = api_key or os.getenv("ORPHANET_API_KEY", "biofetch")
    resp = httpx.get(
        f"{BASE_URL}/ClinicalEntity/ApproximateName/{query}",
        headers={"apiKey": api_key},
        timeout=30,
    )

    if resp.status_code == 404:
        return {"n_results": 0, "is_complete": True, "diseases": [], "warnings": []}

    resp.raise_for_status()
    data = resp.json()

    diseases = []
    for item in data[:max_results]:
        diseases.append({
            "orphanet_id": item.get("ORPHAcode"),
            "name":        item.get("Preferred term", ""),
            "url":         f"https://www.orpha.net/en/disease/detail/{item.get('ORPHAcode')}",
        })

    total       = len(data)
    is_complete = total <= max_results
    warnings    = []
    if not is_complete:
        warnings.append(f"Query matched {total} diseases; returning first {max_results}.")

    return {
        "n_results":   total,
        "is_complete": is_complete,
        "diseases":    diseases,
        "warnings":    warnings,
    }
