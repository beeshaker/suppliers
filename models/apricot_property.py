from odoo import api, fields, models


class ApricotProperty(models.Model):
    _inherit = "apricot.property"

    supplier_ids = fields.Many2many(
        "supplier.supplier",
        relation="supplier_property_rel",
        column1="property_id",
        column2="supplier_id",
        string="Suppliers",
    )
    supplier_count = fields.Integer(compute="_compute_supplier_count")

    @api.depends("supplier_ids")
    def _compute_supplier_count(self):
        for record in self:
            record.supplier_count = len(record.supplier_ids)

    def action_view_suppliers(self):
        self.ensure_one()
        return {
            "type": "ir.actions.act_window",
            "name": "Suppliers",
            "res_model": "supplier.supplier",
            "view_mode": "list,form",
            "domain": [("property_ids", "in", self.id)],
            "context": {"default_property_ids": [(4, self.id)]},
        }
