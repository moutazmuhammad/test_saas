import datetime
import logging
import os
import secrets
import string

from jinja2 import Environment, FileSystemLoader

from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)

TEMPLATES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    'templates',
)


class SaasInstance(models.Model):
    _name = 'saas.instance'
    _description = 'Odoo Instance'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc'

    # ========== Title ==========
    subdomain = fields.Char(
        string='Subdomain',
        required=True,
        tracking=True,
    )
    based_domain_id = fields.Many2one(
        'saas.based.domain',
        string='Based Domain',
    )

    name = fields.Char(
        string='Instance Name',
        compute='_compute_name',
        store=True,
    )

    partner_id = fields.Many2one(
        'res.partner',
        string='Customer',
        tracking=True,
    )
    url = fields.Char(
        string='URL',
        compute='_compute_url',
        store=True,
    )

    odoo_version_id = fields.Many2one(
        'saas.odoo.version',
        string='Odoo Version',
        tracking=True,
    )

    container_physical_server_id = fields.Many2one(
        'saas.container.physical.server',
        string='Container Physical Server',
        tracking=True,
    )

    psql_physical_server_id = fields.Many2one(
        'saas.psql.physical.server',
        string='Psql Physical Server',
        tracking=True,
    )

    xmlrpc_port = fields.Char(
        string='Xmlrpc Port',
    )

    longpolling_port = fields.Char(
        string='Longpolling Port',
    )

    admin_passwd = fields.Char(
        string='Admin Password',
    )

    db_user = fields.Char(
        string='Conf DB User',
    )

    db_password = fields.Char(
        string='Conf DB Password',
    )

    # ========== New Fields ==========
    provisioning_log = fields.Text(
        string='Provisioning Log',
        readonly=True,
    )

    extra_config = fields.Text(
        string='Extra Configuration',
        help='Additional odoo.conf key=value pairs, one per line.',
    )

    # ========== State ==========
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('provisioning', 'Provisioning'),
            ('running', 'Running'),
            ('failed', 'Failed'),
            ('suspended', 'Suspended'),
            ('cancelled', 'Cancelled'),
        ],
        string='Status',
        default='draft',
        tracking=True,
        required=True,
        index=True,
    )
    company_id = fields.Many2one(
        'res.company',
        string='Company',
        default=lambda self: self.env.company,
    )

    # ========== Constraints ==========
    _sql_constraints = [
        (
            'unique_xmlrpc_port_per_server',
            'UNIQUE(container_physical_server_id, xmlrpc_port)',
            'XML-RPC port must be unique per container server.',
        ),
        (
            'unique_longpolling_port_per_server',
            'UNIQUE(container_physical_server_id, longpolling_port)',
            'Longpolling port must be unique per container server.',
        ),
    ]

    # ========== CRUD Overrides ==========

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        for rec in records:
            if not rec.db_user and rec.subdomain:
                rec.db_user = rec._generate_db_user()
            if not rec.db_password:
                rec.db_password = rec._generate_random_password()
            if not rec.admin_passwd:
                rec.admin_passwd = rec._generate_random_password()
            if rec.container_physical_server_id and (not rec.xmlrpc_port or not rec.longpolling_port):
                rec._auto_assign_ports()
        return records

    # ========== Computed ==========
    @api.depends('subdomain', 'based_domain_id.name')
    def _compute_name(self):
        for rec in self:
            if rec.subdomain and rec.based_domain_id:
                rec.name = '%s.%s' % (rec.subdomain, rec.based_domain_id.name)
            else:
                rec.name = rec.subdomain or ''

    @api.depends('subdomain', 'based_domain_id.name')
    def _compute_url(self):
        for rec in self:
            if rec.subdomain and rec.based_domain_id:
                rec.url = 'https://%s.%s' % (rec.subdomain, rec.based_domain_id.name)
            else:
                rec.url = ''

    # ========== Private Helpers ==========

    def _generate_random_password(self, length=24):
        """Generate a cryptographically secure random password."""
        alphabet = string.ascii_letters + string.digits + '-_.~+='
        return ''.join(secrets.choice(alphabet) for _ in range(length))

    def _generate_db_user(self):
        """Generate a db username based on subdomain."""
        self.ensure_one()
        safe_subdomain = self.subdomain.replace('-', '_').replace('.', '_')
        return 'saas_%s' % safe_subdomain

    def _get_partner_code(self):
        """Return partner code for folder naming: partnercode_partnername."""
        self.ensure_one()
        code = self.partner_id.ref or str(self.partner_id.id)
        name = self.partner_id.name or ''
        # Sanitize name for use as directory: lowercase, replace spaces/special chars
        safe_name = name.strip().lower().replace(' ', '_')
        safe_name = ''.join(c for c in safe_name if c.isalnum() or c == '_')
        return '%s_%s' % (code, safe_name)

    def _get_instance_path(self):
        """Return the full remote path for this instance."""
        self.ensure_one()
        server = self.container_physical_server_id
        return '%s/%s/%s' % (
            server.docker_base_path.rstrip('/'),
            self._get_partner_code(),
            self.subdomain,
        )

    def _get_container_name(self):
        """Return the Docker container name for this instance."""
        self.ensure_one()
        return 'odoo_%s' % self.subdomain

    def _append_log(self, message):
        """Append a timestamped message to provisioning_log."""
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        line = '[%s] %s\n' % (timestamp, message)
        current = self.provisioning_log or ''
        self.provisioning_log = current + line

    def _render_template(self, template_name, context):
        """Render a Jinja2 template from the templates/ directory."""
        env = Environment(
            loader=FileSystemLoader(TEMPLATES_PATH),
            keep_trailing_newline=True,
        )
        template = env.get_template(template_name)
        return template.render(context)

    def _parse_extra_config(self):
        """Parse the extra_config text field into a dict."""
        self.ensure_one()
        result = {}
        if self.extra_config:
            for line in self.extra_config.strip().splitlines():
                line = line.strip()
                if '=' in line and not line.startswith('#'):
                    key, _, value = line.partition('=')
                    result[key.strip()] = value.strip()
        return result or None

    def _provision_postgresql(self):
        """Create the PostgreSQL role and database on the PSQL server via SSH."""
        self.ensure_one()
        psql_server = self.psql_physical_server_id
        if not psql_server:
            raise UserError(_("No PSQL physical server configured on this instance."))

        db_user = self.db_user
        db_password = self.db_password
        db_name = self.subdomain

        # Escape single quotes for SQL string literals
        sql_password = db_password.replace("'", "''")

        # Build a single SQL script and pipe it via heredoc to avoid
        # all shell escaping issues with passwords.
        sql_script = (
            "DO $body$\n"
            "BEGIN\n"
            "  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '%(user)s') THEN\n"
            "    CREATE ROLE %(user)s WITH LOGIN PASSWORD '%(password)s';\n"
            "  ELSE\n"
            "    ALTER ROLE %(user)s WITH LOGIN PASSWORD '%(password)s';\n"
            "  END IF;\n"
            "END $body$;\n"
        ) % {'user': db_user, 'password': sql_password}

        # Use a heredoc with a quoted delimiter to prevent any shell expansion
        ensure_role_cmd = "sudo -u postgres psql <<'SAAS_END_SQL'\n%s\nSAAS_END_SQL" % sql_script

        create_db_cmd = (
            "sudo -u postgres psql -tc "
            "\"SELECT 1 FROM pg_database WHERE datname='%(db)s'\" "
            "| grep -q 1 "
            "|| sudo -u postgres createdb -O %(user)s %(db)s"
        ) % {'db': db_name, 'user': db_user}

        with psql_server._get_ssh_connection() as ssh:
            self._append_log("Ensuring PostgreSQL role '%s'..." % db_user)
            exit_code, stdout, stderr = ssh.execute(ensure_role_cmd)
            self._append_log(
                "Role command result: exit=%s stdout=%s stderr=%s"
                % (exit_code, stdout.strip(), stderr.strip())
            )
            if exit_code != 0:
                raise UserError(
                    _("Failed to create/update PostgreSQL role '%s':\n%s")
                    % (db_user, stderr)
                )

            self._append_log("Ensuring database '%s'..." % db_name)
            exit_code, stdout, stderr = ssh.execute(create_db_cmd)
            self._append_log(
                "DB command result: exit=%s stdout=%s stderr=%s"
                % (exit_code, stdout.strip(), stderr.strip())
            )
            if exit_code != 0:
                raise UserError(
                    _("Failed to create database '%s':\n%s")
                    % (db_name, stderr)
                )

    def _ensure_can_ssh(self):
        """Validate that the instance has the necessary server config for SSH."""
        self.ensure_one()
        if not self.container_physical_server_id:
            raise ValidationError(_("No container physical server configured."))
        server = self.container_physical_server_id
        if not server.ssh_key_pair_id or not server.ssh_key_pair_id.private_key_file:
            raise ValidationError(
                _("SSH key pair with private key is required on server '%s'.")
                % server.name
            )
        if not server.ip_v4:
            raise ValidationError(
                _("IP address is required on server '%s'.") % server.name
            )

    def _auto_assign_ports(self):
        """Auto-assign xmlrpc_port and longpolling_port if not already set."""
        self.ensure_one()
        if self.xmlrpc_port and self.longpolling_port:
            return

        starting_port = int(self.env['ir.config_parameter'].sudo().get_param(
            'saas_master.default_instance_starting_port', '32000',
        ))

        siblings = self.env['saas.instance'].search([
            ('container_physical_server_id', '=', self.container_physical_server_id.id),
            ('id', '!=', self.id),
            ('xmlrpc_port', '!=', False),
        ])

        used_ports = set()
        for sibling in siblings:
            if sibling.xmlrpc_port:
                try:
                    used_ports.add(int(sibling.xmlrpc_port))
                except (ValueError, TypeError):
                    pass
            if sibling.longpolling_port:
                try:
                    used_ports.add(int(sibling.longpolling_port))
                except (ValueError, TypeError):
                    pass

        candidate = starting_port
        while candidate < 65535:
            if candidate not in used_ports and (candidate + 1) not in used_ports:
                break
            candidate += 2

        if candidate >= 65535:
            raise ValidationError(
                _("No available port pair found on server '%s'.")
                % self.container_physical_server_id.name
            )

        self.xmlrpc_port = str(candidate)
        self.longpolling_port = str(candidate + 1)

    def _validate_deploy_fields(self):
        """Validate all required fields before deployment."""
        self.ensure_one()
        errors = []
        if not self.subdomain:
            errors.append(_("Subdomain is required."))
        if not self.container_physical_server_id:
            errors.append(_("Container Physical Server is required."))
        if not self.psql_physical_server_id:
            errors.append(_("PSQL Physical Server is required."))
        if not self.odoo_version_id:
            errors.append(_("Odoo Version is required."))
        if not self.partner_id:
            errors.append(_("Customer (Partner) is required."))
        if not self.odoo_version_id or not self.odoo_version_id.docker_image:
            errors.append(_("Docker image is not set on the selected Odoo version."))
        if not self.odoo_version_id or not self.odoo_version_id.docker_image_tag:
            errors.append(_("Docker image tag is not set on the selected Odoo version."))
        server = self.container_physical_server_id
        if server and (not server.ssh_key_pair_id or not server.ssh_key_pair_id.private_key_file):
            errors.append(_("Container server SSH key pair with private key is required."))
        if server and not server.ip_v4:
            errors.append(_("Container server IP address is required."))
        psql = self.psql_physical_server_id
        if psql and (not psql.ssh_key_pair_id or not psql.ssh_key_pair_id.private_key_file):
            errors.append(_("PSQL server SSH key pair with private key is required."))
        if psql and not psql.ip_v4:
            errors.append(_("PSQL server IP address is required."))
        if errors:
            raise ValidationError('\n'.join(str(e) for e in errors))

    # ========== Deploy Flow ==========

    def action_deploy(self):
        """Full deployment flow: provision Docker container over SSH."""
        for rec in self:
            rec._do_deploy()

    def _do_deploy(self):
        """Internal deploy logic for a single record."""
        self.ensure_one()

        # Step 1: Validate
        self._validate_deploy_fields()

        # Step 2: Auto-generate credentials if empty
        if not self.db_user:
            self.db_user = self._generate_db_user()
        if not self.db_password:
            self.db_password = self._generate_random_password()
        if not self.admin_passwd:
            self.admin_passwd = self._generate_random_password()

        # Step 3: Auto-assign ports
        self._auto_assign_ports()

        # Step 4: Set state to provisioning, clear old log
        self.provisioning_log = ''
        self.state = 'provisioning'

        server = self.container_physical_server_id
        instance_path = self._get_instance_path()
        container_name = self._get_container_name()

        try:
            with server._get_ssh_connection() as ssh:

                # Step 5: Create folder structure
                self._append_log("Creating directory structure at %s" % instance_path)
                mkdir_cmd = (
                    'mkdir -p %(path)s/addons '
                    '%(path)s/config '
                    '%(path)s/data/odoo'
                ) % {'path': instance_path}
                exit_code, stdout, stderr = ssh.execute(mkdir_cmd)
                if exit_code != 0:
                    raise UserError(
                        _("Failed to create directories:\n%s") % stderr
                    )
                self._append_log("Directory structure created.")

                # Step 6: Set permissions
                self._append_log("Setting permissions...")
                perms_cmd = (
                    'chown -R 1000:1000 %(path)s/data/odoo %(path)s/config %(path)s/addons && '
                    'chmod -R 777 %(path)s/data/odoo %(path)s/config %(path)s/addons'
                ) % {'path': instance_path}
                exit_code, stdout, stderr = ssh.execute(perms_cmd)
                if exit_code != 0:
                    raise UserError(
                        _("Failed to set permissions:\n%s") % stderr
                    )
                self._append_log("Permissions set.")

                # Step 7: Render and write docker-compose.yml
                self._append_log("Writing docker-compose.yml...")
                dc_context = {
                    'odoo_image': self.odoo_version_id.docker_image,
                    'odoo_version': self.odoo_version_id.docker_image_tag,
                    'subdomain': self.subdomain,
                    'host_ip': '0.0.0.0',
                    'xmlrpc_port': self.xmlrpc_port,
                    'longpolling_port': self.longpolling_port,
                    'network_name': 'net_%s' % self.subdomain,
                }
                dc_content = self._render_template(
                    'docker-compose.yml.jinja', dc_context,
                )
                ssh.write_file(
                    '%s/docker-compose.yml' % instance_path, dc_content,
                )
                self._append_log("docker-compose.yml written.")

                # Step 8: Render and write odoo.conf
                self._append_log("Writing odoo.conf...")
                psql_server = self.psql_physical_server_id
                conf_context = {
                    'master_pass': self.admin_passwd,
                    'db_host': psql_server.ip_v4,
                    'db_port': psql_server.psql_port or 5432,
                    'db_user': self.db_user,
                    'db_password': self.db_password,
                    'proxy_mode': True,
                    'extra_config': self._parse_extra_config(),
                }
                conf_content = self._render_template(
                    'odoo.conf.jinja', conf_context,
                )
                ssh.write_file(
                    '%s/config/odoo.conf' % instance_path, conf_content,
                )
                self._append_log("odoo.conf written.")

                # Step 8b: Create PostgreSQL user and database on PSQL server
                self._append_log("Creating PostgreSQL role and database...")
                self._provision_postgresql()
                self._append_log("PostgreSQL role and database ready.")

                # Step 9: Initialize Odoo database (before starting server)
                self._append_log("Initializing Odoo database...")
                init_cmd = (
                    'cd %(path)s && docker compose run --rm -T odoo '
                    'odoo -d %(db_name)s '
                    '-i base '
                    '--without-demo=all '
                    '--stop-after-init '
                    '--no-http 2>&1'
                ) % {
                    'path': instance_path,
                    'db_name': self.subdomain,
                }
                exit_code, stdout, stderr = ssh.execute(init_cmd, timeout=600)
                self._append_log(
                    "DB init output (last 1000 chars):\n%s"
                    % stdout[-1000:]
                )
                if exit_code != 0:
                    raise UserError(
                        _("Database initialization failed:\n%s\n%s")
                        % (stdout[-500:], stderr[-500:])
                    )
                self._append_log("Database initialized successfully.")

                # Step 10: Start the server
                self._append_log("Starting container with docker compose up -d...")
                up_cmd = 'cd %s && docker compose up -d 2>&1' % instance_path
                exit_code, stdout, stderr = ssh.execute(up_cmd)
                self._append_log(
                    "docker compose up output:\n%s\n%s" % (stdout, stderr)
                )
                if exit_code != 0:
                    raise UserError(
                        _("docker compose up failed:\n%s\n%s") % (stdout, stderr)
                    )
                self._append_log("Container started.")

                # Step 11: Wait for container to be ready
                self._append_log("Waiting for container to be ready...")
                wait_cmd = (
                    'for i in $(seq 1 30); do '
                    '  STATUS=$(docker inspect -f "{{.State.Status}}" %s 2>/dev/null); '
                    '  if [ "$STATUS" = "running" ]; then echo "READY"; exit 0; fi; '
                    '  if [ "$STATUS" = "exited" ] || [ "$STATUS" = "dead" ]; then '
                    '    echo "FAILED:$STATUS"; exit 1; '
                    '  fi; '
                    '  sleep 2; '
                    'done; '
                    'echo "TIMEOUT"; exit 1'
                ) % container_name
                exit_code, stdout, stderr = ssh.execute(wait_cmd)
                if exit_code != 0 or 'READY' not in stdout:
                    _ec, logs_out, _err = ssh.execute(
                        'docker logs --tail 50 %s 2>&1' % container_name
                    )
                    self._append_log(
                        "Container failed to start.\n"
                        "Container logs:\n%s"
                        % logs_out
                    )
                    raise UserError(
                        _("Container did not become ready within 60 seconds.\n"
                          "Container logs:\n%s")
                        % logs_out
                    )
                self._append_log("Container is running.")

            # Success
            self.state = 'running'
            self._append_log("Deployment completed successfully. State: running.")

        except Exception as e:
            self.state = 'failed'
            self._append_log("DEPLOYMENT FAILED: %s" % str(e))
            _logger.exception(
                "Deployment failed for instance %s (id=%s)",
                self.subdomain, self.id,
            )
            if not isinstance(e, (UserError, ValidationError)):
                raise UserError(
                    _("Deployment failed for '%s':\n%s") % (self.subdomain, str(e))
                )
            raise

    # ========== Lifecycle Actions ==========

    def action_stop(self):
        """Stop the Docker container via SSH."""
        for rec in self:
            rec._ensure_can_ssh()
            server = rec.container_physical_server_id
            container_name = rec._get_container_name()
            with server._get_ssh_connection() as ssh:
                exit_code, stdout, stderr = ssh.execute(
                    'docker stop %s' % container_name,
                )
                if exit_code != 0:
                    raise UserError(
                        _("Failed to stop container '%s':\n%s")
                        % (container_name, stderr)
                    )
        return True

    def action_restart(self):
        """Restart the Docker container via SSH."""
        for rec in self:
            rec._ensure_can_ssh()
            server = rec.container_physical_server_id
            container_name = rec._get_container_name()
            with server._get_ssh_connection() as ssh:
                exit_code, stdout, stderr = ssh.execute(
                    'docker restart %s' % container_name,
                )
                if exit_code != 0:
                    raise UserError(
                        _("Failed to restart container '%s':\n%s")
                        % (container_name, stderr)
                    )
        return True

    def action_redeploy(self):
        """Redeploy: docker compose down + up in the instance folder."""
        for rec in self:
            rec._ensure_can_ssh()
            server = rec.container_physical_server_id
            instance_path = rec._get_instance_path()
            with server._get_ssh_connection() as ssh:
                down_cmd = 'cd %s && docker compose down' % instance_path
                exit_code, stdout, stderr = ssh.execute(down_cmd)
                if exit_code != 0:
                    raise UserError(
                        _("docker compose down failed:\n%s") % stderr
                    )
                up_cmd = 'cd %s && docker compose up -d' % instance_path
                exit_code, stdout, stderr = ssh.execute(up_cmd)
                if exit_code != 0:
                    raise UserError(
                        _("docker compose up -d failed:\n%s") % stderr
                    )
        return True

    def action_suspend(self):
        """Stop container and set state to suspended."""
        for rec in self:
            rec._ensure_can_ssh()
            server = rec.container_physical_server_id
            container_name = rec._get_container_name()
            with server._get_ssh_connection() as ssh:
                exit_code, stdout, stderr = ssh.execute(
                    'docker stop %s' % container_name,
                )
                if exit_code != 0:
                    raise UserError(
                        _("Failed to stop container '%s':\n%s")
                        % (container_name, stderr)
                    )
            rec.state = 'suspended'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'

    def action_draft(self):
        """Reset to draft state (only from failed or cancelled)."""
        for rec in self:
            if rec.state not in ('failed', 'cancelled'):
                raise UserError(
                    _("Can only reset to draft from 'Failed' or 'Cancelled' state.")
                )
            rec.state = 'draft'

    def action_delete_instance(self):
        """Remove container and delete instance folder."""
        for rec in self:
            rec._ensure_can_ssh()
            server = rec.container_physical_server_id
            container_name = rec._get_container_name()
            instance_path = rec._get_instance_path()
            with server._get_ssh_connection() as ssh:
                ssh.execute('docker rm -f %s' % container_name)
                exit_code, stdout, stderr = ssh.execute(
                    'rm -rf %s' % instance_path,
                )
                if exit_code != 0:
                    raise UserError(
                        _("Failed to remove instance directory '%s':\n%s")
                        % (instance_path, stderr)
                    )
            rec.state = 'cancelled'
        return True

    def action_config(self):
        return True

    def action_create_backup(self):
        return True

    def action_update_install_module(self):
        return True

    def action_get_users(self):
        return True

    def action_get_apps(self):
        return True
