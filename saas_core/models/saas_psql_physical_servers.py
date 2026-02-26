from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..utils import SSHConnection


class SaasPsqlPhysicalServer(models.Model):
    _name = 'saas.psql.physical.server'
    _description = 'PSQL physical Servers'
    _inherit = ['mail.thread']
    _order = 'sequence, name'

    sequence = fields.Integer(
        string='Sequence',
        default=10,
    )

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
        string='Public IP v4',
    )

    private_ip_v4 = fields.Char(
        string='Private IP v4',
        help='Private/internal IP address. Used by Odoo containers to connect to PostgreSQL.',
    )

    ssh_connect_using = fields.Selection(
        selection=[
            ('public_ip', 'Public IP'),
            ('private_ip', 'Private IP'),
        ],
        string='SSH Connect Using',
        default='public_ip',
        required=True,
        help='Choose which IP address to use for SSH connections.',
    )

    psql_port = fields.Integer(
        string='PSQL Port',
        default=5432,
    )

    def _get_ssh_ip(self):
        """Return the IP to use for SSH based on ssh_connect_using."""
        self.ensure_one()
        if self.ssh_connect_using == 'private_ip':
            if not self.private_ip_v4:
                raise ValidationError(
                    _("Private IP address is required on server '%s' when SSH is set to use Private IP.")
                    % self.name
                )
            return self.private_ip_v4
        if not self.ip_v4:
            raise ValidationError(
                _("Public IP address is required on server '%s'.") % self.name
            )
        return self.ip_v4

    def _get_ssh_connection(self):
        """Return an SSHConnection context manager for this server."""
        self.ensure_one()
        if not self.ssh_key_pair_id or not self.ssh_key_pair_id.private_key_file:
            raise ValidationError(
                _("SSH key pair with a private key file is required on server '%s'.")
                % self.name
            )
        ssh_ip = self._get_ssh_ip()
        return SSHConnection(
            host=ssh_ip,
            port=self.ssh_port or 22,
            user=self.ssh_user or 'root',
            private_key_b64=self.ssh_key_pair_id.private_key_file,
            key_type=self.ssh_key_pair_id.type or 'rsa',
        )

    def action_test_connection(self):
        """Test SSH connection to the server."""
        self.ensure_one()
        try:
            ssh_ip = self._get_ssh_ip()
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
                        ) % (ssh_ip, stdout.strip()),
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
