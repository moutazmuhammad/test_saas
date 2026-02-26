import logging

from odoo import fields, models, _
from odoo.exceptions import UserError, ValidationError

_logger = logging.getLogger(__name__)


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

    module_ids = fields.One2many(
        'saas.odoo.module',
        'odoo_version_id',
        string='Available Modules',
    )

    product_ids = fields.One2many(
        'saas.odoo.product',
        'odoo_version_id',
        string='Products',
    )

    module_count = fields.Integer(
        string='Modules',
        compute='_compute_module_count',
    )

    def _compute_module_count(self):
        for rec in self:
            rec.module_count = len(rec.module_ids)

    def _get_container_server(self):
        """Return the first available container server or raise."""
        server = self.env['saas.container.physical.server'].search([], limit=1)
        if not server:
            raise UserError(
                _("No container physical server available to run the Docker image.")
            )
        return server

    def _get_docker_image(self):
        """Return the full docker image:tag string."""
        self.ensure_one()
        if not self.docker_image or not self.docker_image_tag:
            raise ValidationError(
                _("Docker image and tag are required to fetch modules.")
            )
        return '%s:%s' % (self.docker_image, self.docker_image_tag)

    def action_fetch_modules(self):
        """Fetch available modules from the Docker image by scanning addons manifests."""
        self.ensure_one()
        image = self._get_docker_image()
        server = self._get_container_server()

        # Python one-liner to scan all addons and output:
        # technical_name|||display_name|||summary|||category|||author
        scan_script = (
            "import ast, os, sys; "
            "paths = ['/usr/lib/python3/dist-packages/odoo/addons', '/mnt/extra-addons']; "
            "["
            "("
            "  lambda m: sys.stdout.write("
            "    d + '|||' + m.get('name', d) + '|||' "
            "    + m.get('summary', '').replace('\\\\n', ' ').replace('\\n', ' ') + '|||' "
            "    + m.get('category', '') + '|||' "
            "    + m.get('author', '') + '\\n'"
            "  )"
            ")(ast.literal_eval(open(os.path.join(p, d, '__manifest__.py')).read())) "
            "if os.path.isfile(os.path.join(p, d, '__manifest__.py')) else None "
            "for p in paths if os.path.isdir(p) "
            "for d in sorted(os.listdir(p)) "
            "if os.path.isdir(os.path.join(p, d))"
            "]"
        )

        cmd = "docker run --rm %s python3 -c \"%s\" 2>/dev/null" % (image, scan_script)

        with server._get_ssh_connection() as ssh:
            exit_code, stdout, stderr = ssh.execute(cmd, timeout=120)
            if exit_code != 0:
                raise UserError(
                    _("Failed to fetch modules from image '%s':\n%s")
                    % (image, stderr)
                )

        # Parse output and create/update module records
        existing = {m.technical_name: m for m in self.module_ids}
        found_names = set()

        for line in stdout.strip().splitlines():
            line = line.strip()
            if not line or '|||' not in line:
                continue
            parts = line.split('|||', 4)
            technical_name = parts[0].strip()
            display_name = parts[1].strip() if len(parts) > 1 else technical_name
            summary = parts[2].strip() if len(parts) > 2 else ''
            category = parts[3].strip() if len(parts) > 3 else ''
            author = parts[4].strip() if len(parts) > 4 else ''
            found_names.add(technical_name)

            vals = {
                'name': display_name,
                'summary': summary,
                'category': category,
                'author': author,
            }

            if technical_name in existing:
                existing[technical_name].write(vals)
            else:
                vals.update({
                    'technical_name': technical_name,
                    'odoo_version_id': self.id,
                })
                self.env['saas.odoo.module'].create(vals)

        # Remove modules that no longer exist in the image
        to_remove = self.module_ids.filtered(
            lambda m: m.technical_name not in found_names
        )
        if to_remove:
            to_remove.unlink()

        # Fetch icons for modules that don't have one yet
        self._fetch_module_icons(server, image)

        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': _("Modules Fetched"),
                'message': _("%d modules found for %s.") % (len(found_names), image),
                'type': 'success',
                'sticky': False,
            },
        }

    def _fetch_module_icons(self, server, image):
        """Fetch module icons from the Docker image for modules that don't have an image yet."""
        self.ensure_one()
        modules_needing_icons = self.module_ids.filtered(lambda m: not m.image_1920)
        if not modules_needing_icons:
            return

        tech_names = [m.technical_name for m in modules_needing_icons]

        # Process in batches of 100 to avoid overly large stdout
        batch_size = 100
        existing_map = {m.technical_name: m for m in modules_needing_icons}

        for i in range(0, len(tech_names), batch_size):
            batch = tech_names[i:i + batch_size]
            self._fetch_icon_batch(server, image, batch, existing_map)

    def _fetch_icon_batch(self, server, image, tech_names, existing_map):
        """Fetch icons for a batch of module technical names."""
        # Python script that reads icon.png for each module and outputs:
        # technical_name|||base64_encoded_icon_data
        icon_script = (
            "import base64, os, sys; "
            "paths = ['/usr/lib/python3/dist-packages/odoo/addons', '/mnt/extra-addons']; "
            "modules = %r; "
            "["
            "  sys.stdout.write(m + '|||' + base64.b64encode("
            "    open(os.path.join(p, m, 'static', 'description', 'icon.png'), 'rb').read()"
            "  ).decode() + '\\n') "
            "  for p in paths if os.path.isdir(p) "
            "  for m in modules "
            "  if os.path.isfile(os.path.join(p, m, 'static', 'description', 'icon.png'))"
            "]"
        ) % tech_names

        cmd = "docker run --rm %s python3 -c \"%s\" 2>/dev/null" % (image, icon_script)

        with server._get_ssh_connection() as ssh:
            exit_code, stdout, stderr = ssh.execute(cmd, timeout=300)

        if exit_code != 0:
            _logger.warning("Failed to fetch module icons: %s", stderr[:500])
            return

        for line in stdout.strip().splitlines():
            if '|||' not in line:
                continue
            tech_name, icon_b64 = line.split('|||', 1)
            tech_name = tech_name.strip()
            icon_b64 = icon_b64.strip()
            if tech_name in existing_map and icon_b64:
                try:
                    existing_map[tech_name].image_1920 = icon_b64
                except Exception:
                    _logger.warning(
                        "Failed to set icon for module %s", tech_name
                    )
