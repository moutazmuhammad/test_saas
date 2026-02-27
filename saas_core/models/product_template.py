from odoo import api, fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    saas_type = fields.Selection(
        selection=[
            ('module', 'Module'),
            ('bundle', 'Bundle'),
        ],
        string='SaaS Type',
        help='Identifies this product as part of the SaaS platform. '
             '"Module" represents an individual Odoo module; '
             '"Bundle" represents a package of modules sold together.',
    )
    technical_name = fields.Char(
        string='Technical Name',
        help='Odoo technical module name as used in the CLI and manifest '
             '(e.g. "sale", "account", "purchase").',
    )
    saas_odoo_version_id = fields.Many2one(
        'saas.odoo.version',
        string='Odoo Version',
        ondelete='cascade',
        help='The Odoo version this module or bundle belongs to.',
    )
    saas_dependency_ids = fields.Many2many(
        'product.template',
        'saas_product_dependency_rel',
        'product_id',
        'dependency_id',
        string='Dependencies',
        domain="[('saas_type', '=', 'module')]",
        help='Other modules that are automatically installed as dependencies of this module.',
    )
    saas_module_ids = fields.Many2many(
        'product.template',
        'saas_bundle_module_rel',
        'bundle_id',
        'module_id',
        string='Included Modules',
        domain="[('saas_type', '=', 'module')]",
        help='Modules included in this bundle. All listed modules will be '
             'installed when a customer purchases this bundle.',
    )
    saas_author = fields.Char(
        string='Module Author',
        help='Author of the module as declared in the Odoo manifest file.',
    )
    saas_module_count = fields.Integer(
        string='Module Count',
        compute='_compute_saas_module_count',
        help='Number of modules included in this bundle.',
    )

    _sql_constraints = [
        (
            'unique_technical_name_per_version',
            'UNIQUE(technical_name, saas_odoo_version_id)',
            'Technical name must be unique per Odoo version.',
        ),
    ]

    @api.depends('saas_module_ids')
    def _compute_saas_module_count(self):
        for rec in self:
            rec.saas_module_count = len(rec.saas_module_ids)
