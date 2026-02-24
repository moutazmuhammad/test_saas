from odoo import fields, models


class SaasSshKeyPair(models.Model):
    _name = 'saas.ssh.key.pair'
    _description = 'SSH Key Pair'
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True,
    )
    private_key_filename = fields.Char(
        string='Private Key Filename',
        default='id_rsa',
        help='Filename of the private key.',
    )
    type = fields.Selection(
        selection=[
            ('rsa', 'RSA'),
            ('dsa', 'DSA'),
            ('ecdsa', 'ECDSA'),
            ('ed25519', 'ED25519'),
        ],
        string='Type',
        default='rsa',
    )
    private_key_file = fields.Binary(
        string='Private Key File',
        help='Upload the private key file.',
    )
    private_key_file_name = fields.Char(
        string='Private Key File Name',
    )
