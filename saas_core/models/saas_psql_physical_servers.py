from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..utils import SSHConnection


class SaasPsqlPhysicalServer(models.Model):
    _name = 'saas.psql.physical.server'
    _description = 'PSQL physical Servers'
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

    psql_port = fields.Integer(
        string='PSQL Port',
        default=5432,
    )

    def _get_ssh_connection(self):
        """Return an SSHConnection context manager for this server."""
        self.ensure_one()
        if not self.ssh_key_pair_id or not self.ssh_key_pair_id.private_key_file:
            raise ValidationError(
                _("SSH key pair with a private key file is required on server '%s'.")
                % self.name
            )
        if not self.ip_v4:
            raise ValidationError(
                _("IP address (IPv4) is required on server '%s'.") % self.name
            )
        return SSHConnection(
            host=self.ip_v4,
            port=self.ssh_port or 22,
            user=self.ssh_user or 'root',
            private_key_b64=self.ssh_key_pair_id.private_key_file,
            key_type=self.ssh_key_pair_id.type or 'rsa',
        )

    def action_test_connection(self):
        """Test SSH connection to the server."""
        self.ensure_one()
        try:
            with self._get_ssh_connection() as ssh:
                exit_code, stdout, stderr = ssh.execute(
                    'echo "Connection OK" && hostname'
                )
            if exit_code == 0:
                return {
                    'type': 'ir.actions.client',
                    'tag': 'display_notification',
                    'params': {
                        'title': _("Connection Successful"),
                        'message': _(
                            "SSH connection to %s succeeded. Hostname: %s"
                        ) % (self.ip_v4, stdout.strip()),
                        'type': 'success',
                        'sticky': False,
                    },
                }
            else:
                raise UserError(
                    _("Connection test command failed:\n%s") % stderr
                )
        except (UserError, ValidationError):
            raise
        except Exception as e:
            raise UserError(
                _("SSH connection failed:\n%s") % str(e)
            )
