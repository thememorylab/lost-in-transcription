#!/usr/bin/env python3
"""
Audit underlining tags in NorHand PAGE XML files.

Scans every XML file in a given directory, finds all TextLine elements 
where the custom attribute contains 'underlined:true', and writes the 
results to a CSV file.

Output columns:
- file: XML filename
- line_id: TextLine element id
- offset: starting character offset of the underlined text
- length: length of the underlined text in characters
- full_line_text: the complete Unicode text of the line
- underlined_text: the substring that is marked as underlined
- whole_line: True if the underlining covers the entire line, else False
"""

import os
import re
import csv
import xml.etree.ElementTree as ET
from pathlib import Path

# --- CONFIGURE THESE TWO PATHS ---
XML_DIR = Path("letter-analyser/Letters")
OUTPUT_CSV = Path("underlining_audit.csv")
# ---------------------------------

# PAGE XML namespace
NS = {"pc": "http://schema.primaresearch.org/PAGE/gts/pagecontent/2013-07-15"}

# Regex to extract offset and length from the custom attribute
TEXTSTYLE_PATTERN = re.compile(
    r"textStyle\s*\{[^}]*offset:(\d+);\s*length:(\d+);[^}]*underlined:true"
)


def audit_file(xml_path: Path) -> list[dict]:
    """Return a list of underlining records found in one XML file."""
    records = []
    try:
        tree = ET.parse(xml_path)
    except ET.ParseError as e:
        print(f"  ! Could not parse {xml_path.name}: {e}")
        return records

    root = tree.getroot()

    for textline in root.iter("{%s}TextLine" % NS["pc"]):
        custom = textline.get("custom", "")
        if "underlined:true" not in custom:
            continue

        match = TEXTSTYLE_PATTERN.search(custom)
        if not match:
            offset = None
            length = None
        else:
            offset = int(match.group(1))
            length = int(match.group(2))

        unicode_elem = textline.find(".//pc:Unicode", NS)
        full_text = unicode_elem.text if unicode_elem is not None and unicode_elem.text else ""

        if offset is not None and length is not None:
            underlined_text = full_text[offset:offset + length]
            whole_line = (offset == 0 and length == len(full_text)) or \
                         (offset <= 1 and length >= len(full_text) - 2)
        else:
            underlined_text = ""
            whole_line = False

        records.append({
            "file": xml_path.name,
            "line_id": textline.get("id", ""),
            "offset": offset if offset is not None else "",
            "length": length if length is not None else "",
            "full_line_text": full_text,
            "underlined_text": underlined_text,
            "whole_line": whole_line,
        })

    return records


def main() -> None:
    if not XML_DIR.exists():
        print(f"Error: directory not found: {XML_DIR.resolve()}")
        print("Edit XML_DIR at the top of this script to point to your XML files.")
        return

    xml_files = sorted(XML_DIR.rglob("*.xml"))
    print(f"Found {len(xml_files)} XML files in {XML_DIR.resolve()}")
    print()

    all_records = []
    files_with_tags = 0

    for xml_path in xml_files:
        records = audit_file(xml_path)
        if records:
            files_with_tags += 1
            print(f"  {xml_path.name}: {len(records)} tagged line(s)")
        all_records.extend(records)

    if all_records:
        with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
            fieldnames = ["file", "line_id", "offset", "length",
                          "full_line_text", "underlined_text", "whole_line"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(all_records)

    print()
    print("--- Summary ---")
    print(f"Files scanned: {len(xml_files)}")
    print(f"Files with at least one tagged line: {files_with_tags}")
    print(f"Total tagged lines: {len(all_records)}")
    if all_records:
        whole = sum(1 for r in all_records if r["whole_line"])
        partial = len(all_records) - whole
        print(f"  Whole-line tagged: {whole}")
        print(f"  Partial-line tagged: {partial}")
        print(f"Output written to: {OUTPUT_CSV.resolve()}")
    else:
        print("No tagged lines found in any XML file.")


if __name__ == "__main__":
    main()
    