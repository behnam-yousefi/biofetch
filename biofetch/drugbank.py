"""
DrugBank tool — search a local DrugBank XML dump.

No public API. Requires:
  1. A DrugBank account (https://go.drugbank.com/releases/latest)
  2. Download the full database XML: drugbank_all_full_database.xml.zip
  3. Set DRUGBANK_XML_PATH in the environment to the extracted .xml file path
"""

import os
import xml.etree.ElementTree as ET
from typing import Iterator

NS = "http://www.drugbank.ca"   # DrugBank XML namespace


def _iter_drugs(xml_path: str) -> Iterator[ET.Element]:
    """Stream <drug> elements one at a time instead of loading the whole file
    into memory. The full DrugBank dump is ~1.9GB, and a full ET.parse() of it
    can need several times that in RAM as a DOM tree — confirmed to OOM-kill
    the process in a memory-constrained environment (a Docker container with
    ~7.5GB available). iterparse() builds the tree incrementally as it reads,
    so calling .clear() on each <drug> right after use keeps peak memory
    roughly constant regardless of file size, instead of scaling with it.
    """
    for event, elem in ET.iterparse(xml_path, events=("end",)):
        if elem.tag == f"{{{NS}}}drug":
            yield elem
            elem.clear()


def search_drugbank(
    query:       str,
    max_results: int = 50,
    xml_path:    str | None = None,
) -> dict:
    """
    Search the local DrugBank XML dump for drugs matching a name, target, or indication.

    query:       drug name, target gene symbol, or indication keyword.
    max_results: maximum number of drugs to return.
    xml_path:    path to drugbank_all_full_database.xml. Falls back to
                 DRUGBANK_XML_PATH if not given.
    """
    xml_path = xml_path or os.getenv("DRUGBANK_XML_PATH")
    if not xml_path or not os.path.exists(xml_path):
        return {
            "n_results": 0, "is_complete": False, "drugs": [],
            "warnings": [
                "DRUGBANK_XML_PATH not set or file not found. "
                "Download from https://go.drugbank.com/releases/latest and set the path in the environment."
            ],
        }

    query = query.lower()
    drugs = []

    for drug in _iter_drugs(xml_path):
        name = drug.findtext(f"{{{NS}}}name", "") or ""
        if query not in name.lower():
            continue

        db_id = drug.findtext(f"{{{NS}}}drugbank-id[@primary='true']", "")
        groups = [g.text for g in drug.findall(f"{{{NS}}}groups/{{{NS}}}group") if g.text]
        targets = [
            t.findtext(f"{{{NS}}}name", "")
            for t in drug.findall(f"{{{NS}}}targets/{{{NS}}}target")
        ]

        drugs.append({
            "drugbank_id": db_id,
            "name":        name,
            "groups":      groups,       # approved, experimental, withdrawn, ...
            "targets":     targets[:10],
            "url":         f"https://go.drugbank.com/drugs/{db_id}",
        })

        if len(drugs) >= max_results:
            break

    return {
        "n_results":   len(drugs),
        "is_complete": len(drugs) < max_results,
        "drugs":       drugs,
        "warnings":    [],
    }
