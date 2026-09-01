{
    "name": "Suppliers",
    "summary": "Central supplier directory linked to categories and properties",
    "description": """
Maintains a supplier directory searchable by category, by property, or by
supplier, with each supplier linked to one or more categories and one or
more properties. Categories support a Main/Sub hierarchy and a
preferred/approved-panel flag per supplier-category link. Includes CSV/XLSX
bulk import.
    """,
    "version": "19.0.1.0.0",
    "category": "Services/Helpdesk",
    "author": "Abhishek Shah",
    "website": "https://www.apricotproperty.co.ke",
    "license": "LGPL-3",
    "depends": ["base", "mail", "apricot_ticketing"],
    "external_dependencies": {"python": ["openpyxl"]},
    "data": [
        "security/ir.model.access.csv",
        "views/supplier_views.xml",
        "views/category_views.xml",
        "views/apricot_property_views.xml",
        "wizards/import_wizard_views.xml",
        "views/menu_views.xml",
    ],
    "installable": True,
    "application": True,
}
