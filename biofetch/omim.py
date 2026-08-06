"""
OMIM tool — search genetic disease entries via the OMIM API.

API docs: https://www.omim.org/api
Requires OMIM_API_KEY in the environment (register at https://www.omim.org/api).
"""

import os
import httpx

BASE_URL = "https://api.omim.org/api"


def search_omim(
    query:       str,
    max_results: int = 50,
    api_key:     str | None = None,
) -> dict:
    """
    Search OMIM for genetic disease entries matching a query term.
    Returns OMIM IDs, titles, gene symbols, and URLs.

    query:       disease or gene name (e.g. 'phenylketonuria', 'CFTR').
    max_results: maximum number of entries to return.
    api_key:     OMIM API key. Falls back to OMIM_API_KEY if not given.
    """
    api_key = api_key or os.getenv("OMIM_API_KEY")
    if not api_key:
        return {
            "n_results": 0, "is_complete": False, "entries": [],
            "warnings": ["OMIM_API_KEY not set. Register at https://www.omim.org/api"],
        }

    resp = httpx.get(
        f"{BASE_URL}/entry/search",
        params={
            "search":    query,
            "limit":     max_results,
            "format":    "json",
            "apiKey":    api_key,
        },
        timeout=30,
    )
    resp.raise_for_status()
    data    = resp.json().get("omim", {}).get("searchResponse", {})
    entries_raw = data.get("entryList", [])
    total   = data.get("totalResults", len(entries_raw))

    entries = []
    for item in entries_raw:
        e = item.get("entry", {})
        entries.append({
            "mim_number": e.get("mimNumber"),
            "title":      e.get("titles", {}).get("preferredTitle", ""),
            "type":       e.get("mimType", ""),
            "url":        f"https://omim.org/entry/{e.get('mimNumber')}",
        })

    is_complete = total <= max_results
    warnings    = []
    if not is_complete:
        warnings.append(f"Query matched {total} entries; returning first {max_results}.")

    return {
        "n_results":   total,
        "is_complete": is_complete,
        "entries":     entries,
        "warnings":    warnings,
    }
