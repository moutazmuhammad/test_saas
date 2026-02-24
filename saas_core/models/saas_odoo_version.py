from odoo import fields, models


class SaasOdooVersion(models.Model):
    _name = 'saas.odoo.version'
    _description = 'Odoo Version'
    _order = 'name'

    name = fields.Char(
        string='Odoo Version',
        required=True,
    )

    docker_image = fields.Char(
        string='Docker Image',
    )

    docker_image_tag = fields.Char(
        string='Docker Image Tag',
    )
