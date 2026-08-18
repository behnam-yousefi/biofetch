# SIDER — data reference notes

Source: https://sideeffects.embl.de/download/ (flat-file downloads, no API,
no key). Unlike `disgenet_api_reference.md`/`orphadata_api_reference.md`,
there's no live endpoint to hit — everything here is about the downloadable
`.tsv`/`.tsv.gz` files themselves and what each column actually contains.
Column formats confirmed live 2026-08-18 from the official README at
https://sideeffects.embl.de/media/download/README.

**Data currency**: this is **SIDER 4.1, released 2015-10-21** — the current
version as of writing, and (per SIDER's own site) the last release; there is
no newer version to switch to. Drugs approved after 2015 won't appear at
all, and side effect profiles for older drugs won't reflect anything learned
since. Worth surfacing to the end user when a `search_sider` result seems
thin or a drug isn't found — that's expected for anything recent, not a bug.

## Capability table

| File | Size | Used by `search_sider`? | Notes |
|---|---|---|---|
| `drug_names.tsv` | 34 KB | **Yes** | STITCH compound id → drug name. Required. |
| `meddra_all_se.tsv.gz` | 2.3 MB | **Yes** | Compound id → side effect. Required. **See bug below** — the code currently reads the wrong column. |
| `meddra_freq.tsv.gz` | 2.0 MB | No — candidate | Frequency ("common"/"rare"/a percentage range) per side effect. Standout candidate: `search_sider` currently returns an undifferentiated flat list with no sense of how common each side effect actually is. |
| `meddra_all_indications.tsv.gz` | 337 KB | No — candidate | What the drug is prescribed *for*, not its side effects — a different axis SIDER has that we don't touch. `search_drugbank` already covers indications to some degree, so this would be a complement, not a from-scratch gap. |
| `drug_atc.tsv` | 32 KB | No | ATC drug-classification codes — a taxonomy/browsing aid, not something a lookup tool needs. Low priority. |
| `meddra_all_label_indications.tsv.gz` | 5.6 MB | No | Same data as `meddra_all_indications.tsv.gz`, plus a leading column naming the source label. Raw/per-label, not deduplicated. Low priority. |
| `meddra_all_label_se.tsv.gz` | 41 MB | No | Same relationship to `meddra_all_se.tsv.gz` — per-label raw version. Low priority. |
| `meddra.tsv.gz` | 1.0 MB | No | Plain MedDRA term dictionary: `{UMLS concept id, MedDRA id, term kind (PT/LLT/...), side effect name}`. Not a joining table the other files need — each of them already carries its own MedDRA name column directly. |

## Column formats (verified against the official README, not guessed)

**`drug_names.tsv`** — 2 columns, no header: `stitch_id`, `drug_name`.

**`meddra_all_se.tsv.gz`** — 6 columns, no header:
1. STITCH compound id (flat)
2. STITCH compound id (stereo)
3. UMLS concept id as found on the label
4. MedDRA concept type (`LLT` = lowest level term, `PT` = preferred term)
5. UMLS concept id **for the MedDRA term** (a code, e.g. `C0235431` — not readable text)
6. **side effect name** (the actual human-readable text, e.g. `"Blood creatinine increased"`)

Every side effect appears as an `LLT` row; most also get a separate `PT` row
(same side effect, coarser-grained term — the README's own example: four
different `LLT`s like "Creatinine increased," "Plasma creatinine increased,"
etc. all roll up to one `PT`, "Blood creatinine increased"). Filtering to
`PT` rows only (column 4) avoids returning near-duplicate LLT variants of
the same underlying side effect.

**`meddra_freq.tsv.gz`** — 10 columns: columns 1-2 same STITCH ids, column 3
UMLS label concept id, column 4 `"placebo"` or empty (whether the frequency
came from placebo-arm data), column 5 a frequency description (free text:
`"postmarketing"`, `"rare"`, `"infrequent"`, `"frequent"`, `"common"`, or an
exact percentage), columns 6-7 lower/upper numeric bounds on that frequency
(equal if the exact value is known), columns 8-10 the same MedDRA
type/UMLS-id/name triple as `meddra_all_se.tsv.gz`'s columns 4-6. Note: a
single side effect can have more than one frequency row (different clinical
trials, different severity levels), so this is a one-to-many join against
`meddra_all_se.tsv.gz`, not one-to-one.

**`meddra_all_indications.tsv.gz`** — 7 columns: STITCH id (flat only, no
stereo column here), UMLS label concept id, detection method (`NLP_indication`
/ `NLP_precondition` / `text_mention`), the as-found concept name, then the
same MedDRA type/UMLS-id/name triple as the side-effect file.

## Bug: `search_sider` reads the wrong column for the side effect name

`biofetch/sider.py`'s parsing:
```python
stitch_id, _, _, _, se_name = parts[:5]
```
This unpacks only the first **5** columns (0-indexed 0-4), assigning
`se_name = parts[4]` — column **5**, which per the README above is *"UMLS
concept id for MedDRA term"*, a code like `C0235431`. The actual readable
side effect name is column **6** (`parts[5]`), never read at all. So today,
once `SIDER_DIR` is actually configured, `search_sider` returns UMLS concept
ID codes in its `side_effects` list instead of human-readable text like
"Blood creatinine increased" — silently wrong, no error, no warning. Caught
by reading the real column documentation before building on top of this file
for `meddra_freq` support, not by running the tool (nothing has exercised
this path yet since `SIDER_DIR` has never been set).

**Fix**: unpack 6 columns instead of 5, and optionally filter to `PT` rows
(column 4) to avoid returning near-duplicate `LLT` variants of the same
underlying side effect — see the `meddra_all_se.tsv.gz` column notes above
for why that matters.

## Fix status

**Implemented** in `biofetch/sider.py`:

1. `meddra_all_se.tsv.gz` parsing now reads all 6 columns and takes column 6
   (`parts[5]`) as the side effect name, not column 5. Also now filters to
   `PT` rows only (per the README's own recommendation — see the column
   notes above for why LLT rows are redundant near-duplicates).
2. `_load_frequencies()` reads `meddra_freq.tsv.gz` (optional — missing file
   returns `{}`, not an error) and joins by side effect name + `PT` type,
   collecting every frequency description seen (a side effect can have more
   than one, e.g. from different clinical trials).
3. `search_sider`'s `side_effects` list changed shape from a flat list of
   strings to a list of `{name, frequencies}` objects — a breaking change to
   the output shape, but the old shape had never actually worked correctly
   (returning codes, not names) and `SIDER_DIR` had never been configured
   until now, so there was nothing real depending on the old shape.

Live-verified against the real downloaded files (2026-08-18): `search_sider("ibuprofen")`
correctly returns readable names ("Abdominal pain", "Adrenal insufficiency", ...),
with frequency data attached where SIDER has it (e.g. "Adrenal insufficiency" →
`["7%", "1%"]`) and an empty list where it doesn't (frequency data is sparse —
most side effects have none).

Not implemented, lower priority: `meddra_all_indications.tsv.gz` as a
complement to `search_drugbank`'s existing indication data.
