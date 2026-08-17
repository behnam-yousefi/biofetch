"""
Orphanet tools — search rare/orphan diseases and fetch rich disease detail,
via two separate Orphanet APIs.

search_orphanet uses https://api.orphacode.org/openapi.json (name -> ORPHAcode
resolution). get_orphanet_disease_details uses the separate, newer
https://api.orphadata.com (cross-references, HPO clinical signs, prevalence)
— no key needed there at all. See docs/orphadata_api_reference.md in this
repo for why these stay two functions instead of one: Orphadata's own
name-search endpoint gave a confidently WRONG match in live testing
("PAH deficiency" -> "Myeloperoxidase deficiency"), with no ranked-candidates
shape to hedge against it the way search_orphanet already does. So name
resolution stays here, and get_orphanet_disease_details only ever takes an
already-resolved orphanet_id.

api.orphacode.org requires an `apiKey` header, but per the API's own
description this is just a self-chosen identifier ("enter a user name of your
choosing"), not a real registered secret — any non-empty string works.
Override with ORPHANET_API_KEY if you want to identify your own usage.
"""

import os
import httpx

BASE_URL           = "https://api.orphacode.org/EN"
ORPHADATA_BASE_URL = "https://api.orphadata.com"


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

    result = {
        "n_results":   total,
        "is_complete": is_complete,
        "diseases":    diseases,
        "warnings":    warnings,
    }
    if diseases:
        result["next_steps"] = ["get_orphanet_disease_details(orphanet_id) for cross-references, clinical signs, and prevalence data"]
    return result


def get_orphanet_disease_details(
    orphanet_id: int,
    lang:        str = "en",
) -> dict:
    """
    Get rich detail for a specific Orphanet disease: cross-references to
    other terminologies (ICD-10, ICD-11, OMIM, MONDO, MeSH, MedDRA, UMLS,
    GARD), HPO clinical signs/symptoms with frequency, and prevalence data
    by geographic area. No API key needed.

    Call this AFTER search_orphanet has already resolved a name to an
    orphanet_id — this only takes an ID, deliberately, because Orphadata's
    own name-search is unreliable (see module docstring). Don't try to skip
    search_orphanet and guess an orphanet_id from memory.

    orphanet_id: ORPHAcode from search_orphanet's result (e.g. 586 for
                 Cystic fibrosis).
    lang:        ISO 639-1 language code (default 'en'); not every dataset
                 supports every language — falls back gracefully per-section
                 if a given language isn't available for that dataset.
    """
    warnings = []
    name, synonyms, external_references = None, [], []
    phenotypes, prevalence = [], []

    # Three independent calls, one per Orphadata dataset — a failure in one
    # (e.g. no phenotype data curated for this disease, a plain 404, not a
    # real error) shouldn't blank out the other two, so each is handled on
    # its own rather than raising on the first non-200.
    resp = httpx.get(f"{ORPHADATA_BASE_URL}/rd-cross-referencing/orphacodes/{orphanet_id}",
                     params={"lang": lang}, timeout=30)
    if resp.status_code == 200:
        r = resp.json()["data"]["results"]
        name      = r.get("Preferred term")
        synonyms  = r.get("Synonym") or []
        external_references = [
            {
                "source":          x.get("Source"),
                "reference":       x.get("Reference"),
                "mapping_relation": x.get("DisorderMappingRelation"),
            }
            for x in (r.get("ExternalReference") or [])
        ]
    elif resp.status_code != 404:
        warnings.append(f"Cross-referencing lookup failed for ORPHAcode {orphanet_id} (status {resp.status_code}).")

    resp = httpx.get(f"{ORPHADATA_BASE_URL}/rd-phenotypes/orphacodes/{orphanet_id}",
                     params={"lang": lang}, timeout=30)
    if resp.status_code == 200:
        disorder = resp.json()["data"]["results"].get("Disorder") or {}
        for assoc in disorder.get("HPODisorderAssociation") or []:
            hpo = assoc.get("HPO") or {}
            phenotypes.append({
                "hpo_id":    hpo.get("HPOId"),
                "hpo_term":  hpo.get("HPOTerm"),
                "frequency": assoc.get("HPOFrequency"),
            })
    elif resp.status_code != 404:
        warnings.append(f"Phenotype lookup failed for ORPHAcode {orphanet_id} (status {resp.status_code}).")

    resp = httpx.get(f"{ORPHADATA_BASE_URL}/rd-epidemiology/orphacodes/{orphanet_id}",
                     params={"lang": lang}, timeout=30)
    if resp.status_code == 200:
        for p in resp.json()["data"]["results"].get("Prevalence") or []:
            prevalence.append({
                "type":              p.get("PrevalenceType"),
                "prevalence_class":  p.get("PrevalenceClass"),
                "geographic_area":   p.get("PrevalenceGeographic"),
                "validation_status": p.get("PrevalenceValidationStatus"),
                "source":            p.get("Source"),
            })
    elif resp.status_code != 404:
        warnings.append(f"Epidemiology lookup failed for ORPHAcode {orphanet_id} (status {resp.status_code}).")

    if name is None and not phenotypes and not prevalence and not warnings:
        warnings.append(f"No Orphadata entry found for ORPHAcode {orphanet_id}.")

    return {
        "orphanet_id":          orphanet_id,
        "name":                 name,
        "synonyms":             synonyms,
        "external_references":  external_references,
        "phenotypes":           phenotypes,
        "prevalence":           prevalence,
        "warnings":             warnings,
    }
