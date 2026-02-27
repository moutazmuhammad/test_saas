from odoo import fields, models


class SaasBasedDomain(models.Model):
    _name = 'saas.based.domain'
    _description = 'Base Domain'

    name = fields.Char(
        string='Domain Name',
        required=True,
        tracking=True,
        help='The parent domain under which instance subdomains are created '
             '(e.g. "saas.example.com"). Instances will be reachable at '
             '<subdomain>.<domain>.',
    )
