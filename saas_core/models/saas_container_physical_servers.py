from odoo import fields, models


class SaasContainerPhysicalServer(models.Model):
    _name = 'saas.container.physical.server'
    _description = 'Container physical Servers'
    _inherit = ['mail.thread']
    _order = 'name'

    name = fields.Char(
        string='Name',
        required=True,
        tracking=True,
    )
    ssh_key_pair_id = fields.Many2one(
        'saas.ssh.key.pair',
        string='SSH Key Pair',
    )

    ssh_user = fields.Char(
        string='SSH User',
        default='root',
        help='SSH User for connecting to this server.',
    )

    ssh_port = fields.Integer(
        string='SSH Port',
        default=22,
        help='SSH port for connecting to this server.',
    )

    ip_v4 = fields.Char(
        string='IP v4',
    )

    docker_base_path = fields.Char(
        string='Docker Base Path',
        default='/home/odoo',
        help='Docker Base Path.',
    )

    def action_test_connection(self):
        """Test SSH connection to the server."""
        return True

