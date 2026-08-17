# biofetch

Biomedical database search tools for BioChemAIgent and Drug Discovery Platform.

## Install

```bash
micromamba env create -f environment.yml -y
micromamba env create -f environment.yml -y --prefix ~/env/bcai
pip install -e .
```

## Configuration

Only `search_orphanet` works out of the box with no setup. Everything else needs credentials or a local dataset — pass it directly as a function argument, or set the matching environment variable as a fallback (argument wins if both are given):

| Argument | Env var fallback | Required by | How to get it |
|---|---|---|---|
| `api_key` | `OMIM_API_KEY` | `search_omim` | Free registration at [omim.org/api](https://www.omim.org/api) |
| `api_key` | `DISGENET_API_KEY` | `search_disgenet` | Free registration at [disgenet.com](https://disgenet.com) |
| `xml_path` | `DRUGBANK_XML_PATH` | `search_drugbank` | Path to `drugbank_all_full_database.xml`, requires a DrugBank account/license at [go.drugbank.com/releases/latest](https://go.drugbank.com/releases/latest) |
| `sider_dir` | `SIDER_DIR` | `search_sider` | Path to a directory containing `drug_names.tsv` and `meddra_all_se.tsv.gz`, freely downloadable from [sideeffects.embl.de](http://sideeffects.embl.de/) |

Every function follows the same fallback, e.g.:

```python
api_key = api_key or os.getenv("OMIM_API_KEY")
```

Without either the argument or the env var set, a tool returns an empty result with a `warnings` entry explaining what's missing — it doesn't raise.

`biofetch` doesn't load `.env` itself — it just reads whatever's already in the process environment via `os.getenv`. Copy `.env.example` to `.env`, fill in the values you have, then get them into the process one of these ways:

- **Shell:** `export $(grep -v '^#' .env | xargs)` before running your script, or add the `export VAR=...` lines to your shell profile.
- **python-dotenv:** `pip install python-dotenv`, then `from dotenv import load_dotenv; load_dotenv()` before `import biofetch` in your script/notebook.
- **Already inside `bcai` or `pharma-search`:** those projects load their own `env` file at startup — add these 4 lines there instead of keeping a separate `.env` for biofetch.

`.env` is gitignored; only commit `.env.example`.

## Key tools

- `search_orphanet` — [Orphanet](https://www.orpha.net) is the reference portal for rare/orphan disease nomenclature and classification (the "ORPHAcode" system). `search_orphanet` looks up rare diseases by name and returns their ORPHAcode and canonical term. No real registration needed — the API requires an `apiKey` header, but per its own docs this is just a self-chosen usage identifier, not a real secret.
- `get_orphanet_disease_details` — given an ORPHAcode from `search_orphanet`, fetches richer detail from the separate [Orphadata](https://api.orphadata.com) API (no key needed at all): cross-references to ICD-10/ICD-11/OMIM/MONDO/MeSH/MedDRA/UMLS/GARD, HPO clinical signs/symptoms with frequency, and prevalence data by geographic area. Deliberately takes only an already-resolved ORPHAcode rather than a name — Orphadata's own name-search is unreliable, see `docs/orphadata_api_reference.md`.
- `search_omim` — [OMIM](https://www.omim.org) (Online Mendelian Inheritance in Man) catalogs genetic diseases and the genes known to cause them. `search_omim` looks up genetic disease entries by disease or gene name. Requires `OMIM_API_KEY` (register at [omim.org/api](https://www.omim.org/api)).
- `search_disgenet` — [DisGeNET](https://disgenet.com) is a curated database of gene-disease associations aggregated from expert curation, GWAS, animal models, and literature mining, each scored by evidence strength. `search_disgenet` looks up genes associated with a disease (or vice versa). Requires `DISGENET_API_KEY` (register at [disgenet.com](https://disgenet.com)).
- `search_disgenet_enrichment` — gene-set enrichment analysis via DisGeNET: given a list of genes, finds diseases whose known gene sets significantly overlap with it (set-level reasoning, not a single gene/disease lookup) — useful for interpreting a gene signature or hit-list. Same `DISGENET_API_KEY` as `search_disgenet`.
- `search_drugbank` — [DrugBank](https://go.drugbank.com) is a comprehensive drug reference combining detailed drug data (mechanism, targets, groups/approval status) with drug-target information. `search_drugbank` searches a local DrugBank XML dump by drug name, target, or indication keyword. Requires a DrugBank account/license and `DRUGBANK_XML_PATH` pointing at the extracted `drugbank_all_full_database.xml` ([go.drugbank.com/releases/latest](https://go.drugbank.com/releases/latest)).
- `search_sider` — [SIDER](http://sideeffects.embl.de/) (Side Effect Resource) catalogs marketed drugs and their recorded adverse effects, extracted from public documents and package inserts. `search_sider` looks up known side effects for a drug name. Requires `SIDER_DIR` pointing at a directory containing `drug_names.tsv` and `meddra_all_se.tsv.gz` (freely downloadable from [sideeffects.embl.de](http://sideeffects.embl.de/)).

## Notes

- All search functions return a uniform `{n_results, is_complete, <items>, warnings}` shape, so a calling agent can tell at a glance whether it saw the full result set and why not if it didn't.
- Functions that need credentials or local data degrade gracefully — if neither the function argument nor the fallback env var is set, they return an empty result with an explanatory `warnings` entry rather than raising.
- These tools don't cover UniProt, ChEMBL, PDB, PubMed, Reactome, or Open Targets — those are served by existing third-party MCP servers rather than reimplemented here.

## License

This software is licensed under the PolyForm Noncommercial License 1.0.0 — see `LICENSE`.

Free for academic, research, and other noncommercial use. Commercial use — including
use in proprietary pipelines, SaaS products, or any revenue-generating activity —
requires a separate commercial license. Contact: yousefi.bme@gmail.com, sbonn@uke.de

SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
