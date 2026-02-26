from odoo import fields, models


class SaasInstanceModuleLine(models.Model):
    _name = 'saas.instance.module.line'
    _description = 'Instance Module Installation Line'
    _order = 'sequence, id'

    sequence = fields.Integer(default=10)
    instance_id = fields.Many2one(
        'saas.instance',
        string='Instance',
        required=True,
        ondelete='cascade',
    )
    odoo_version_id = fields.Many2one(
        related='instance_id.odoo_version_id',
        store=True,
    )
    product_id = fields.Many2one(
        'saas.odoo.product',
        string='Product',
        domain="[('odoo_version_id', '=', odoo_version_id)]",
    )
    module_id = fields.Many2one(
        'saas.odoo.module',
        string='Module',
        domain="[('odoo_version_id', '=', odoo_version_id)]",
    )
    product_image = fields.Image(
        related='product_id.image_128',
        string='Product Image',
    )
    module_image = fields.Image(
        related='module_id.image_128',
        string='Module Image',
    )
    state = fields.Selection(
        selection=[
            ('pending', 'Pending'),
            ('installed', 'Installed'),
            ('failed', 'Failed'),
        ],
        string='Status',
        default='pending',
        readonly=True,
    )
    log = fields.Text(
        string='Log',
        readonly=True,
    )

    def _get_all_technical_names(self):
        """Return a set of all technical module names for this line including dependencies."""
        self.ensure_one()
        names = set()
        modules = self.env['saas.odoo.module']

        if self.product_id:
            modules = self.product_id.module_ids
        elif self.module_id:
            modules = self.module_id

        for mod in modules:
            names.add(mod.technical_name)
            for dep in mod.dependency_ids:
                names.add(dep.technical_name)

        return names
