"""
SIDER tool — query drug side effects (and their reported frequency) from
local SIDER flat files.

No live API. Data is SIDER 4.1, released 2015-10-21 — the current (and per
SIDER's own site, last) release as of writing; nothing approved after 2015
appears at all. Requires:
  1. Download SIDER files from http://sideeffects.embl.de/download/
  2. Set SIDER_DIR in the environment to the directory containing the flat files

Key files used:
  drug_names.tsv         — compound CID -> drug name
  meddra_all_se.tsv.gz   — compound CID -> side effect
  meddra_freq.tsv.gz     — compound CID -> side effect frequency (optional;
                            skipped gracefully if not present)

See docs/sider_data_reference.md in this repo for the verified column
formats this implementation is built from. Notably: meddra_all_se.tsv.gz has
6 columns, not 5 — an earlier version of this file read only the first 5
(`parts[:5]`), landing on column 5 ("UMLS concept id for the MedDRA term",
e.g. "C0235431") instead of column 6 (the actual readable name, e.g.
"Blood creatinine increased"). Confirmed live against the real downloaded
file before fixing — this was never caught by running the tool, since
SIDER_DIR had never been configured until now.
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


def _open(path: str):
    return gzip.open(path, "rt") if path.endswith(".gz") else open(path)


def _load_frequencies(sider_dir: str, matching_ids: set) -> dict:
    """
    Return {side_effect_name: [frequency_description, ...]} for the given
    STITCH ids, from meddra_freq.tsv.gz. A side effect can have more than
    one frequency row (e.g. from different clinical trials), hence the list.
    meddra_freq.tsv.gz is optional (not everyone downloads it) — a missing
    file returns an empty dict, not an error.
    """
    path = os.path.join(sider_dir, "meddra_freq.tsv.gz")
    if not os.path.exists(path):
        return {}

    frequencies: dict = {}
    with _open(path) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 10:
                continue
            stitch_id, term_type, se_name, freq_desc = parts[0], parts[7], parts[9], parts[4]
            if stitch_id in matching_ids and term_type == "PT":
                bucket = frequencies.setdefault(se_name, [])
                if freq_desc not in bucket:
                    bucket.append(freq_desc)
    return frequencies


def search_sider(
    drug_name:   str,
    max_results: int = 100,
    sider_dir:   str | None = None,
) -> dict:
    """
    Search SIDER for known side effects of a drug, with reported frequency
    where available (e.g. 'common', 'rare', or a percentage).

    drug_name:   drug name to look up (e.g. 'ibuprofen', 'metformin').
    max_results: maximum number of side effects to return.
    sider_dir:   directory containing drug_names.tsv, meddra_all_se.tsv.gz,
                 and (optionally) meddra_freq.tsv.gz. Falls back to SIDER_DIR
                 if not given.
    """
    sider_dir = sider_dir or os.getenv("SIDER_DIR")
    if not sider_dir or not os.path.isdir(sider_dir):
        return {
            "n_results": 0, "is_complete": False, "side_effects": [],
            "warnings": [
                "SIDER_DIR not set or directory not found. "
                "Download from http://sideeffects.embl.de/download/ and set SIDER_DIR in the environment."
            ],
        }

    names = _load_names(sider_dir)
    query = drug_name.lower()

    matching_ids = {k for k, v in names.items() if query in v.lower()}
    if not matching_ids:
        return {
            "n_results":    0,
            "is_complete":  True,
            "side_effects": [],
            "warnings":     [f"No drug matching '{drug_name}' found in SIDER."],
        }

    se_file = os.path.join(sider_dir, "meddra_all_se.tsv.gz")
    names_in_order = []
    seen = set()

    with _open(se_file) as f:
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            stitch_id, term_type, se_name = parts[0], parts[3], parts[5]
            # PT (preferred term) only — LLT rows are finer-grained near-
            # duplicates of the same underlying side effect (e.g. "Creatinine
            # increased" / "Plasma creatinine increased" / "Serum creatinine
            # increased" all roll up to one PT, "Blood creatinine increased")
            # and would otherwise clutter the result with redundant entries.
            if stitch_id in matching_ids and term_type == "PT" and se_name not in seen:
                seen.add(se_name)
                names_in_order.append(se_name)
            if len(names_in_order) >= max_results:
                break

    frequencies  = _load_frequencies(sider_dir, matching_ids)
    side_effects = [
        {"name": name, "frequencies": frequencies.get(name, [])}
        for name in names_in_order
    ]

    return {
        "drug_name":    drug_name,
        "n_results":    len(side_effects),
        "is_complete":  len(side_effects) < max_results,
        "side_effects": side_effects,
        "warnings":     [],
    }
