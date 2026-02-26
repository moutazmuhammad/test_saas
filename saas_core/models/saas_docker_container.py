from odoo import fields, models, _
from odoo.exceptions import UserError


class SaasDockerContainer(models.Model):
    _name = 'saas.docker.container'
    _description = 'Docker Container'
    _order = 'name'

    server_id = fields.Many2one(
        'saas.container.physical.server',
        string='Server',
        required=True,
        ondelete='cascade',
    )
    container_id = fields.Char(
        string='Container ID',
        readonly=True,
    )
    name = fields.Char(
        string='Name',
        readonly=True,
    )
    image = fields.Char(
        string='Image',
        readonly=True,
    )
    command = fields.Char(
        string='Command',
        readonly=True,
    )
    created = fields.Char(
        string='Created',
        readonly=True,
    )
    status = fields.Char(
        string='Status',
        readonly=True,
    )
    ports = fields.Char(
        string='Ports',
        readonly=True,
    )

    def action_stop_container(self):
        """Stop this Docker container via SSH."""
        self.ensure_one()
        server = self.server_id
        with server._get_ssh_connection() as ssh:
            exit_code, stdout, stderr = ssh.execute(
                'docker stop %s' % self.name,
            )
            if exit_code != 0:
                raise UserError(
                    _("Failed to stop container '%s':\n%s") % (self.name, stderr)
                )
        return server.action_refresh_containers()

    def action_restart_container(self):
        """Restart this Docker container via SSH."""
        self.ensure_one()
        server = self.server_id
        with server._get_ssh_connection() as ssh:
            exit_code, stdout, stderr = ssh.execute(
                'docker restart %s' % self.name,
            )
            if exit_code != 0:
                raise UserError(
                    _("Failed to restart container '%s':\n%s") % (self.name, stderr)
                )
        return server.action_refresh_containers()
