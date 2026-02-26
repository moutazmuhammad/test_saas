from odoo import fields, models


class SaasOdooProduct(models.Model):
    _name = 'saas.odoo.product'
    _description = 'Odoo Module Product (Bundle)'
    _inherit = ['image.mixin']
    _order = 'name'

    name = fields.Char(
        string='Product Name',
        required=True,
        help='Display name of the product bundle (e.g. CRM Package).',
    )
    description = fields.Text(
        string='Description',
        help='Description of what this product bundle provides.',
    )
    odoo_version_id = fields.Many2one(
        'saas.odoo.version',
        string='Odoo Version',
        required=True,
        ondelete='cascade',
    )
    module_ids = fields.Many2many(
        'saas.odoo.module',
        'saas_product_module_rel',
        'product_id',
        'module_id',
        string='Modules',
        help='Modules included in this product bundle.',
    )
    module_count = fields.Integer(
        string='Module Count',
        compute='_compute_module_count',
    )

    def _compute_module_count(self):
        for rec in self:
            rec.module_count = len(rec.module_ids)
