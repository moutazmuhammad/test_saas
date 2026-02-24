from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    # ========== Section: SaaS Master ==========
    saas_default_instance_starting_port = fields.Integer(
        string='Default Instance Starting Port',
        config_parameter='saas_master.default_instance_starting_port',
        default=32000,
        help='Default starting port of odoo instance when create physical server',
    )
