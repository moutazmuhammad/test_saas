from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError

from ..utils import SSHConnection


class SaasContainerPhysicalServer(models.Model):
    _name = 'saas.container.physical.server'
    _description = 'Container physical Servers'
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
        help='Private/internal IP address used for communication between servers on the same network.',
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

    docker_base_path = fields.Char(
        string='Docker Base Path',
        default='/home/odoo',
        help='Docker Base Path.',
    )

    docker_container_ids = fields.One2many(
        'saas.docker.container',
        'server_id',
        string='Docker Containers',
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

    def action_refresh_containers(self):
        """Fetch all Docker containers from the server via SSH and update the list."""
        self.ensure_one()
        separator = '|||'
        fmt = separator.join([
            '{{.ID}}', '{{.Image}}', '{{.Command}}',
            '{{.CreatedAt}}', '{{.Status}}', '{{.Ports}}', '{{.Names}}',
        ])
        cmd = "docker ps -a --format '%s' --no-trunc" % fmt

        try:
            with self._get_ssh_connection() as ssh:
                exit_code, stdout, stderr = ssh.execute(cmd)
                if exit_code != 0:
                    raise UserError(
                        _("Failed to list containers:\n%s") % stderr
                    )
        except (UserError, ValidationError):
            raise
        except Exception as e:
            raise UserError(
                _("SSH connection failed:\n%s") % str(e)
            )

        # Remove old container records for this server
        self.docker_container_ids.unlink()

        # Parse output and create new records
        container_model = self.env['saas.docker.container']
        for line in stdout.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            parts = line.split(separator)
            if len(parts) < 7:
                continue
            container_model.create({
                'server_id': self.id,
                'container_id': parts[0][:12],
                'image': parts[1],
                'command': parts[2],
                'created': parts[3],
                'status': parts[4],
                'ports': parts[5],
                'name': parts[6],
            })
