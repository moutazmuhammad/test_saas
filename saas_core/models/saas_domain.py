from odoo import fields, models


class SaasOdooServer(models.Model):
    _name = 'saas.based.domain'
    _description = 'Based domain'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
    )


