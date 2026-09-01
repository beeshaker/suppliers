import base64
import csv
import io

import openpyxl

from odoo import fields, models
from odoo.exceptions import UserError

HEADER_MAP = {
    "name": "name",
    "internal code": "internal_code",
    "tax pin": "tax_pin",
    "address": "address",
    "contact person": "contact_person",
    "telephone": "phone",
    "mobile": "mobile",
    "fax": "fax",
    "email": "email",
    "notes": "notes",
    "categories": "categories",
    "preferred categories": "preferred_categories",
}

SUPPLIER_FIELDS = [
    "internal_code",
    "tax_pin",
    "contact_person",
    "phone",
    "mobile",
    "fax",
    "email",
    "address",
    "notes",
]


class SupplierImportWizard(models.TransientModel):
    _name = "supplier.import.wizard"
    _description = "Supplier Bulk Import"

    file = fields.Binary(string="File")
    filename = fields.Char()
    state = fields.Selection(
        [("upload", "Upload"), ("done", "Done")], default="upload", required=True
    )
    created_count = fields.Integer(readonly=True)
    updated_count = fields.Integer(readonly=True)
    error_count = fields.Integer(readonly=True)
    result_message = fields.Text(readonly=True)

    def action_import(self):
        self.ensure_one()
        if not self.file or not self.filename:
            raise UserError("Please choose a file to import.")
        if not self.filename.lower().endswith((".csv", ".xlsx")):
            raise UserError("Please upload a .csv or .xlsx file.")

        rows = self._parse_rows()

        Supplier = self.env["supplier.supplier"]
        Category = self.env["supplier.category"]

        supplier_map = {
            s.name.strip().lower(): s
            for s in Supplier.with_context(active_test=False).search([])
        }
        category_map = {
            (c.name.strip().lower(), c.parent_id.id): c
            for c in Category.with_context(active_test=False).search([])
        }

        created = updated = errors = 0
        error_lines = []

        for index, row in enumerate(rows, start=2):
            if not any(row.values()):
                continue
            name = (row.get("name") or "").strip()
            if not name:
                errors += 1
                error_lines.append(f"Row {index}: blank Name, skipped")
                continue

            with self.env.cr.savepoint():
                category_ids, preferred_ids = self._resolve_categories(row, category_map)
                supplier = supplier_map.get(name.lower())
                if supplier:
                    self._update_supplier(supplier, row)
                    updated += 1
                else:
                    supplier = self._create_supplier(name, row)
                    supplier_map[name.lower()] = supplier
                    created += 1
                self._sync_categories(supplier, category_ids, preferred_ids)

        self.write(
            {
                "state": "done",
                "created_count": created,
                "updated_count": updated,
                "error_count": errors,
                "result_message": "\n".join(error_lines) or "No errors.",
            }
        )
        return self._reload_action()

    def action_new_import(self):
        self.ensure_one()
        self.write(
            {
                "file": False,
                "filename": False,
                "state": "upload",
                "created_count": 0,
                "updated_count": 0,
                "error_count": 0,
                "result_message": False,
            }
        )
        return self._reload_action()

    def _reload_action(self):
        return {
            "type": "ir.actions.act_window",
            "res_model": "supplier.import.wizard",
            "res_id": self.id,
            "view_mode": "form",
            "target": "new",
        }

    def _parse_rows(self):
        content = base64.b64decode(self.file)
        if self.filename.lower().endswith(".csv"):
            return self._parse_csv(content)
        return self._parse_xlsx(content)

    def _parse_csv(self, content):
        text = content.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(text))
        return [self._normalize_row(row) for row in reader]

    def _parse_xlsx(self, content):
        workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.worksheets[0]
        rows_iter = sheet.iter_rows(values_only=True)
        try:
            headers = list(next(rows_iter))
        except StopIteration:
            return []
        rows = []
        for values in rows_iter:
            raw = dict(zip(headers, values))
            rows.append(self._normalize_row(raw, cast_numeric=True))
        return rows

    @staticmethod
    def _clean_header(value):
        return (str(value) if value is not None else "").strip().lower()

    @staticmethod
    def _cast_cell(value):
        if value is None:
            return ""
        if isinstance(value, float) and value.is_integer():
            return str(int(value))
        return str(value).strip()

    def _normalize_row(self, raw, cast_numeric=False):
        row = {}
        for header, value in raw.items():
            key = HEADER_MAP.get(self._clean_header(header))
            if not key:
                continue
            row[key] = self._cast_cell(value) if cast_numeric else (value or "").strip()
        return row

    @staticmethod
    def _split_list(value):
        if not value:
            return []
        return [v.strip() for v in value.split(",") if v.strip()]

    def _get_or_create_category(self, path, category_map):
        Category = self.env["supplier.category"]
        parent_id = False
        category = None
        for part in [p.strip() for p in path.split(">")]:
            if not part:
                continue
            key = (part.lower(), parent_id)
            category = category_map.get(key)
            if not category:
                category = Category.create({"name": part, "parent_id": parent_id})
                category_map[key] = category
            parent_id = category.id
        return category

    def _resolve_categories(self, row, category_map):
        category_ids = []
        for path in self._split_list(row.get("categories")):
            category = self._get_or_create_category(path, category_map)
            if category and category.id not in category_ids:
                category_ids.append(category.id)

        preferred_ids = set()
        for path in self._split_list(row.get("preferred_categories")):
            category = self._get_or_create_category(path, category_map)
            if category:
                preferred_ids.add(category.id)
                if category.id not in category_ids:
                    category_ids.append(category.id)

        return category_ids, preferred_ids

    def _update_supplier(self, supplier, row):
        values = {f: row[f] for f in SUPPLIER_FIELDS if row.get(f)}
        if values:
            supplier.write(values)

    def _create_supplier(self, name, row):
        values = {f: row[f] for f in SUPPLIER_FIELDS if row.get(f)}
        values["name"] = name
        return self.env["supplier.supplier"].create(values)

    def _sync_categories(self, supplier, category_ids, preferred_ids):
        Line = self.env["supplier.category.line"]
        existing = {line.category_id.id: line for line in supplier.category_line_ids}
        for category_id in category_ids:
            line = existing.get(category_id)
            is_preferred = category_id in preferred_ids
            if line:
                if is_preferred and not line.is_preferred:
                    line.is_preferred = True
            else:
                Line.create(
                    {
                        "supplier_id": supplier.id,
                        "category_id": category_id,
                        "is_preferred": is_preferred,
                    }
                )
