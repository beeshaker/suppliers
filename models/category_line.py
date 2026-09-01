from odoo import fields, models


class SupplierCategoryLine(models.Model):
    _name = "supplier.category.line"
    _description = "Supplier Category Link"
    _order = "is_preferred desc, supplier_id"

    supplier_id = fields.Many2one(
        "supplier.supplier", required=True, ondelete="cascade", index=True
    )
    category_id = fields.Many2one(
        "supplier.category", required=True, ondelete="cascade", index=True
    )
    is_preferred = fields.Boolean(
        string="Preferred / Approved Panel",
        help="This supplier is on the vetted/approved vendor panel for this category.",
    )
    supplier_phone = fields.Char(related="supplier_id.phone", string="Telephone")
    supplier_mobile = fields.Char(related="supplier_id.mobile", string="Mobile")
    supplier_email = fields.Char(related="supplier_id.email", string="Email")

    _supplier_category_unique = models.Constraint(
        "unique(supplier_id, category_id)",
        "This supplier is already linked to this category.",
    )
