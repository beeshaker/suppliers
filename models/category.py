from odoo import api, fields, models


class SupplierCategory(models.Model):
    _name = "supplier.category"
    _description = "Supplier Category"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "complete_name"

    name = fields.Char(required=True, tracking=True, index=True)
    parent_id = fields.Many2one(
        "supplier.category",
        string="Parent Category",
        index=True,
        ondelete="restrict",
        tracking=True,
    )
    child_ids = fields.One2many("supplier.category", "parent_id", string="Sub-Categories")
    complete_name = fields.Char(compute="_compute_complete_name", store=True, recursive=True)
    active = fields.Boolean(default=True)
    category_line_ids = fields.One2many(
        "supplier.category.line", "category_id", string="Supplier Links"
    )
    supplier_count = fields.Integer(compute="_compute_supplier_count")

    _category_name_parent_unique = models.Constraint(
        "unique(name, parent_id)",
        "A category with this name already exists under the same parent.",
    )

    @api.depends("name", "parent_id.complete_name")
    def _compute_complete_name(self):
        for category in self:
            if category.parent_id:
                category.complete_name = f"{category.parent_id.complete_name} / {category.name}"
            else:
                category.complete_name = category.name

    @api.depends("category_line_ids")
    def _compute_supplier_count(self):
        for record in self:
            record.supplier_count = len(record.category_line_ids)

    def action_view_suppliers(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Suppliers",
            "res_model": "supplier.supplier",
            "view_mode": "list,form",
            "domain": [("category_line_ids.category_id", "=", self.id)],
        }
