from odoo import fields, models


class SaasOdooModule(models.Model):
    _name = 'saas.odoo.module'
    _description = 'Odoo Module'
    _inherit = ['image.mixin']
    _order = 'name'

    name = fields.Char(
        string='Module Name',
        required=True,
        help='Display name of the module (e.g. Sales, Invoicing, Purchase).',
    )
    technical_name = fields.Char(
        string='Technical Name',
        required=True,
        help='Technical module name used in odoo CLI (e.g. sale, account, purchase).',
    )
    summary = fields.Char(
        string='Summary',
        help='One-line summary from the module manifest.',
    )
    category = fields.Char(
        string='Category',
        help='Module category (e.g. Sales, Accounting, Inventory).',
    )
    author = fields.Char(
        string='Author',
        help='Module author from the manifest.',
    )
    description = fields.Text(
        string='Description',
        help='Detailed description of the module.',
    )
    odoo_version_id = fields.Many2one(
        'saas.odoo.version',
        string='Odoo Version',
        required=True,
        ondelete='cascade',
    )
    dependency_ids = fields.Many2many(
        'saas.odoo.module',
        'saas_module_dependency_rel',
        'module_id',
        'dependency_id',
        string='Dependencies',
        help='Modules that will be automatically installed with this module.',
    )

    _sql_constraints = [
        (
            'unique_technical_name_per_version',
            'UNIQUE(technical_name, odoo_version_id)',
            'Technical name must be unique per Odoo version.',
        ),
    ]

    def name_get(self):
        return [(rec.id, '%s (%s)' % (rec.name, rec.technical_name)) for rec in self]
