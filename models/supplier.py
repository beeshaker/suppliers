from odoo import api, fields, models


class SupplierSupplier(models.Model):
    _name = "supplier.supplier"
    _description = "Supplier"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "name"

    name = fields.Char(required=True, tracking=True, index=True)
    internal_code = fields.Char(string="Internal Code", tracking=True)
    tax_pin = fields.Char(string="Tax PIN", tracking=True)
    contact_person = fields.Char(tracking=True)
    phone = fields.Char(string="Telephone", tracking=True)
    mobile = fields.Char(tracking=True)
    fax = fields.Char()
    email = fields.Char(tracking=True)
    address = fields.Text()
    notes = fields.Text()
    active = fields.Boolean(default=True)

    category_line_ids = fields.One2many(
        "supplier.category.line", "supplier_id", string="Category Links"
    )
    category_names = fields.Char(compute="_compute_category_names", string="Categories")
    property_ids = fields.Many2many(
        "apricot.property",
        relation="supplier_property_rel",
        column1="supplier_id",
        column2="property_id",
        string="Properties",
        tracking=True,
    )

    _supplier_name_unique = models.Constraint(
        "unique(name)",
        "A supplier with this name already exists.",
    )

    @api.depends("category_line_ids.category_id.complete_name")
    def _compute_category_names(self):
        for record in self:
            record.category_names = ", ".join(
                record.category_line_ids.mapped("category_id.complete_name")
            )
