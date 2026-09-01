"""One-time migration utility. NOT part of the installed addon (nothing in
models/wizards imports this file, so it has zero effect on the running
module).

Reads the two legacy spreadsheets that shipped alongside this module:
  - SUPPLIERS' LIST PER MDA 1(Sheet1).csv   (1,349 suppliers, contact data,
    free-text "Service Type")
  - Vendor Categories(Vendor Panel).csv     (curated Main/Sub category
    taxonomy with up to 5 preferred contractors each)

and produces two review artifacts (does NOT touch any database):
  - suppliers_import.csv   -- in the supplier.import.wizard's exact template
                               shape, ready to upload through the real UI
                               once reviewed/edited
  - migration_report.txt   -- every raw "Service Type" fragment that had no
                               confident match to the canonical taxonomy
                               (kept as its own new top-level category
                               instead of being silently merged or dropped),
                               plus the list of vendor-panel contractors not
                               already present in the suppliers file.

Run manually:  python3 migrate_legacy_data.py
"""

import csv
import re
from pathlib import Path

BASE_DIR = Path(__file__).parent
SUPPLIERS_CSV = BASE_DIR / "SUPPLIERS' LIST PER MDA 1(Sheet1).csv"
PANEL_CSV = BASE_DIR / "Vendor Categories(Vendor Panel).csv"
OUT_CSV = BASE_DIR / "suppliers_import.csv"
OUT_REPORT = BASE_DIR / "migration_report.txt"

OUT_COLUMNS = [
    "Name",
    "Internal Code",
    "Tax PIN",
    "Address",
    "Contact Person",
    "Telephone",
    "Mobile",
    "Fax",
    "Email",
    "Notes",
    "Categories",
    "Preferred Categories",
]

# Junk / non-category values found in the raw "Service Type" column - dropped
# entirely, never turned into a category.
DROP_FRAGMENTS = {"xxxxx"}

# Fixes for values that were truncated in the source export (fixed-width
# column cut mid-word). Keyed by the raw (lowercased) fragment.
TRUNCATION_FIXES = {
    "environmenta audit nema l": "Environmental Audit (NEMA)",
    "garbage / refuse collecti": "Garbage / Refuse Collection",
    "general supply of materia": "General Supply of Materials",
    "glass & aluminium fabrica": "Glass & Aluminium Fabrication",
    "hardware & building mater": "Hardware & Building Materials",
    "solar water(heating exemp": "Solar Water (Heating Exemption)",
    "sports  equipment & suppl": "Sports Equipment & Supplies",
    "steel fabricators & bildi": "Steel Fabricators & Building Materials",
    "storage tanks and waste w": "Storage Tanks & Waste Water",
}

# Best-effort mapping from a raw file-1 "Service Type" fragment (lowercased)
# onto the canonical vendor-panel taxonomy (Main or "Main > Sub"). Anything
# NOT in this dict is kept as its own new top-level category instead of
# being force-merged - see migration_report.txt for that list on every run.
CATEGORY_MAPPING = {
    "advocacy": "Lawyers",
    "legal fees": "Lawyers",
    "airconditioning": "Air Conditioning & HVAC > Air conditioning",
    "electrical and structure": "Electrical",
    "ventilation": "Air Conditioning & HVAC > Mechanical ventilation",
    "alarm services": "Security Services",
    "security": "Security Services",
    "borehole water pumps": "Water Pumps",
    "domestic water pumps": "Water Pumps",
    "submersible water pumps": "Water Pumps",
    "bottled water": "Water Supply",
    "supply of bulk water": "Water Supply",
    "water": "Water Supply",
    "building repairs": "General Building Contractors",
    "constructions works": "General Building Contractors",
    "general contractor": "General Building Contractors",
    "retaining walls": "General Building Contractors",
    "building and civil works": "General Building Contractors > Civil works",
    "carpentry": "General Building Contractors > Carpentry & joinery",
    "joinery": "General Building Contractors > Carpentry & joinery",
    "roofing": "General Building Contractors > Roofing",
    "tiling": "General Building Contractors > Tiling",
    "cctv": "CCTV & Surveillance Systems",
    "carpet cleaning": "Cleaning Services",
    "window cleaning": "Cleaning Services",
    "cleaning services": "Cleaning Services",
    "electrical repairs": "Electrical",
    "electricity": "Electrical",
    "environmental audit (nema)": "Statutory Compliance Audits > NEMA",
    "fire equipments": "Fire Extinguisher Supply & Servicing",
    "fire pumps": "Fire Pump Maintenance",
    "fumigation / pest control": "Pest Control & Fumigation",
    "garbage / refuse collection": "Garbage Collectors",
    "gardening services": "Gardening & Landscaping",
    "landscaping": "Gardening & Landscaping",
    "generator fuel": "Generator Services > Fuel supply",
    "generator maintenance": "Generator Services > Annual maintenance",
    "laundry expense": "Laundry Services",
    "lifts inspection": "Lift & Escalator Services > Inspection",
    "lifts maintenance": "Lift & Escalator Services > Maintenance",
    "lifts repairs": "Lift & Escalator Services > Maintenance",
    "office furniture": "Office Items",
    "office supplies": "Office Items",
    "painting": "Painting",
    "plumbing": "Plumbing",
    "pool maintenance": "Pool Maintenance & Detergents",
    "swimming pool maintenance": "Pool Maintenance & Detergents",
    "swimming pool repairs": "Pool Maintenance & Detergents",
    "sewerage treatment plant": "STP Maintenance",
    "tissues / consumables": "Consumables",
    "water proofing": "Waterproofing",
}


def read_csv_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        return list(csv.reader(f))


def parse_panel(path):
    """Returns (preferred: {category_path: {contractor_name_upper, ...}},
    canonical_paths: set of every Main / Main>Sub path)."""
    rows = read_csv_rows(path)
    header_idx = next(i for i, r in enumerate(rows) if r and r[0].strip() == "Main category")
    preferred = {}
    canonical_paths = set()
    last_main = None
    for row in rows[header_idx + 1 :]:
        if not any(c.strip() for c in row):
            continue
        main = row[0].strip() if len(row) > 0 else ""
        sub = row[1].strip() if len(row) > 1 else ""
        if main.lower().startswith("note:"):
            continue
        if main:
            last_main = main
        main = last_main
        if not main:
            continue
        path = f"{main} > {sub}" if sub else main
        canonical_paths.add(path)
        contractors = {c.strip().upper() for c in row[2:7] if c and c.strip()}
        preferred.setdefault(path, set()).update(contractors)
    return preferred, canonical_paths


def resolve_category(fragment):
    """Returns a category path for a raw Service Type fragment, or None if
    it should be dropped (junk)."""
    key = fragment.strip().lower()
    if key in DROP_FRAGMENTS:
        return None
    fixed = TRUNCATION_FIXES.get(key)
    if fixed:
        key = fixed.lower()
        fragment = fixed
    mapped = CATEGORY_MAPPING.get(key)
    if mapped:
        return mapped
    # Unmapped: keep the (possibly truncation-fixed) label as its own new
    # top-level category rather than dropping or force-merging it.
    return fragment.strip()


def parse_suppliers(path):
    rows = read_csv_rows(path)
    header = rows[0]
    idx = {name: i for i, name in enumerate(header)}
    out = []
    for row in rows[1:]:
        if not any(c.strip() for c in row):
            continue
        # header has "Name" twice (company name, then contact person) - the
        # naive {name: index} dict comprehension above collapses to the
        # LAST occurrence, so company name is read positionally instead.
        name_cols = [i for i, h in enumerate(header) if h == "Name"]
        name = row[name_cols[0]].strip() if len(row) > name_cols[0] else ""
        if not name:
            continue
        ref_no = row[idx["Reference No"]].strip() if len(row) > idx["Reference No"] else ""
        vat = row[idx["Vat/GST No"]].strip() if len(row) > idx["Vat/GST No"] else ""
        contact_person = row[name_cols[1]].strip() if len(name_cols) > 1 and len(row) > name_cols[1] else ""
        out.append(
            {
                "name": name,
                "internal_code": row[idx["Code"]].strip() if len(row) > idx["Code"] else "",
                "tax_pin": ref_no or vat,
                "address": row[idx["Address"]].strip() if len(row) > idx["Address"] else "",
                "contact_person": contact_person,
                "phone": row[idx["Telephone"]].strip() if len(row) > idx["Telephone"] else "",
                "mobile": row[idx["Mobile"]].strip() if len(row) > idx["Mobile"] else "",
                "fax": row[idx["Fax"]].strip() if len(row) > idx["Fax"] else "",
                "email": row[idx["Email"]].strip() if len(row) > idx["Email"] else "",
                "service_type": row[idx["Service Type"]].strip() if len(row) > idx["Service Type"] else "",
            }
        )
    return out


def main():
    preferred_by_path, canonical_paths = parse_panel(PANEL_CSV)
    suppliers = parse_suppliers(SUPPLIERS_CSV)

    # Reverse index: contractor name -> every panel category path they're
    # listed as preferred for. A supplier's own file-1 Service Type text
    # doesn't always repeat what the panel already says about them (e.g.
    # JOSCO INVESTMENT's file-1 row only says "General Contractor", but the
    # panel separately lists them as preferred for Electrical, Waterproofing,
    # and two General Building Contractors sub-categories) - both signals
    # have to be merged in, not just intersected.
    paths_by_contractor = {}
    for path, names in preferred_by_path.items():
        for name in names:
            paths_by_contractor.setdefault(name, set()).add(path)

    unmapped_fragments = set()
    dropped_fragments = set()
    out_rows = []
    covered_names = set()

    for sup in suppliers:
        name_upper = sup["name"].strip().upper()
        covered_names.add(name_upper)
        fragments = [f.strip() for f in sup["service_type"].split(",") if f.strip()]
        category_paths = []
        for fragment in fragments:
            if fragment.strip().lower() in DROP_FRAGMENTS:
                dropped_fragments.add(fragment)
                continue
            path = resolve_category(fragment)
            if path is None:
                dropped_fragments.add(fragment)
                continue
            if path not in canonical_paths:
                unmapped_fragments.add(path)
            if path not in category_paths:
                category_paths.append(path)

        preferred_paths = [p for p in category_paths if name_upper in preferred_by_path.get(p, set())]

        # Merge in every panel path for this contractor, even ones their
        # own file-1 Service Type text never mentioned.
        for path in paths_by_contractor.get(name_upper, set()):
            if path not in category_paths:
                category_paths.append(path)
            if path not in preferred_paths:
                preferred_paths.append(path)

        out_rows.append(
            {
                "Name": sup["name"],
                "Internal Code": sup["internal_code"],
                "Tax PIN": sup["tax_pin"],
                "Address": sup["address"],
                "Contact Person": sup["contact_person"],
                "Telephone": sup["phone"],
                "Mobile": sup["mobile"],
                "Fax": sup["fax"],
                "Email": sup["email"],
                "Notes": "",
                "Categories": ", ".join(category_paths),
                "Preferred Categories": ", ".join(preferred_paths),
            }
        )

    # Panel contractors not already present in the suppliers file: add as
    # new rows with only what the panel file tells us (name + category,
    # marked preferred). No contact details available for these.
    new_from_panel = []
    for path, names in preferred_by_path.items():
        for name in names:
            if name not in covered_names:
                new_from_panel.append((name, path))
                covered_names.add(name)

    by_name = {}
    for name, path in new_from_panel:
        by_name.setdefault(name, []).append(path)

    for name, paths in sorted(by_name.items()):
        out_rows.append(
            {
                "Name": name.title(),
                "Internal Code": "",
                "Tax PIN": "",
                "Address": "",
                "Contact Person": "",
                "Telephone": "",
                "Mobile": "",
                "Fax": "",
                "Email": "",
                "Notes": "From Vendor Panel file only - no contact details available, please fill in.",
                "Categories": ", ".join(paths),
                "Preferred Categories": ", ".join(paths),
            }
        )

    with open(OUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(out_rows)

    report_lines = [
        f"Suppliers from registry file: {len(suppliers)}",
        f"New suppliers found only in the vendor panel file: {len(by_name)}",
        f"Total rows written to {OUT_CSV.name}: {len(out_rows)}",
        "",
        f"Service Type fragments dropped as junk ({len(dropped_fragments)}):",
        *sorted(f"  - {f}" for f in dropped_fragments),
        "",
        f"Fragments with NO confident match to the vendor-panel taxonomy "
        f"({len(unmapped_fragments)}) - kept as their own new top-level "
        f"category, review before importing:",
        *sorted(f"  - {f}" for f in unmapped_fragments),
    ]
    OUT_REPORT.write_text("\n".join(report_lines) + "\n")

    print(f"Wrote {len(out_rows)} rows to {OUT_CSV}")
    print(f"Wrote report to {OUT_REPORT}")
    print(f"{len(unmapped_fragments)} unmapped category fragments - see report")


if __name__ == "__main__":
    main()
