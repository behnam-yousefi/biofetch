"""
SIDER tool — query drug side effects from local SIDER flat files.

No live API. Requires:
  1. Download SIDER files from http://sideeffects.embl.de/
  2. Set SIDER_DIR in the environment to the directory containing the flat files

Key files used:
  meddra_all_se.tsv.gz   — compound CID -> side effect (MedDRA)
  drug_names.tsv         — compound CID -> drug name
"""

import gzip
import os


def _load_names(sider_dir: str) -> dict:
    """Return {stitch_id: drug_name} mapping from drug_names.tsv."""
    path = os.path.join(sider_dir, "drug_names.tsv")
    names = {}
    if not os.path.exists(path):
        return names
    with open(path) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) >= 2:
                names[parts[0]] = parts[1]
    return names


def search_sider(
    drug_name:   str,
    max_results: int = 100,
    sider_dir:   str | None = None,
) -> dict:
    """
    Search SIDER for known side effects of a drug.

    drug_name:   drug name to look up (e.g. 'ibuprofen', 'metformin').
    max_results: maximum number of side effects to return.
    sider_dir:   directory containing drug_names.tsv and meddra_all_se.tsv.gz.
                 Falls back to SIDER_DIR if not given.
    """
    sider_dir = sider_dir or os.getenv("SIDER_DIR")
    if not sider_dir or not os.path.isdir(sider_dir):
        return {
            "n_results": 0, "is_complete": False, "side_effects": [],
            "warnings": [
                "SIDER_DIR not set or directory not found. "
                "Download from http://sideeffects.embl.de/ and set SIDER_DIR in the environment."
            ],
        }

    names    = _load_names(sider_dir)
    query    = drug_name.lower()

    # Find STITCH IDs matching the drug name
    matching_ids = {k for k, v in names.items() if query in v.lower()}
    if not matching_ids:
        return {
            "n_results":    0,
            "is_complete":  True,
            "side_effects": [],
            "warnings":     [f"No drug matching '{drug_name}' found in SIDER."],
        }

    # Read side effects for matching IDs
    se_file  = os.path.join(sider_dir, "meddra_all_se.tsv.gz")
    side_effects = []
    seen     = set()

    opener = gzip.open if se_file.endswith(".gz") else open
    with opener(se_file, "rt") as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 5:
                continue
            stitch_id, _, _, _, se_name = parts[:5]
            if stitch_id in matching_ids and se_name not in seen:
                seen.add(se_name)
                side_effects.append(se_name)
            if len(side_effects) >= max_results:
                break

    return {
        "drug_name":    drug_name,
        "n_results":    len(side_effects),
        "is_complete":  len(side_effects) < max_results,
        "side_effects": side_effects,
        "warnings":     [],
    }
