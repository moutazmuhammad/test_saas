import base64
import datetime
import logging

from odoo import api, fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)

BACKUP_RETENTION_DAYS = 7
PRESIGNED_URL_EXPIRY = 7 * 24 * 3600


class SaasInstanceBackup(models.Model):
    _name = 'saas.instance.backup'
    _description = 'SaaS Instance Backup'
    _order = 'create_date desc'

    instance_id = fields.Many2one(
        'saas.instance', string='Instance',
        required=True, ondelete='cascade', index=True,
    )
    name = fields.Char(string='Backup Name', required=True)
    bucket_path = fields.Char(
        string='Bucket Path', readonly=True,
        help='Full object key inside the cloud bucket.',
    )
    size_mb = fields.Float(string='Size (MB)', readonly=True)
    state = fields.Selection([
        ('running', 'In Progress'),
        ('done', 'Done'),
        ('failed', 'Failed'),
    ], string='Status', default='running', required=True)
    error_message = fields.Text(string='Error', readonly=True)
    download_url = fields.Char(
        string='Download URL', readonly=True,
        help='Presigned download link valid for 7 days.',
    )
    download_url_expiry = fields.Datetime(
        string='Link Expires', readonly=True,
    )

    def _refresh_download_url(self):
        """Regenerate presigned URL if expired or missing."""
        now = fields.Datetime.now()
        for rec in self:
            if rec.state != 'done' or not rec.bucket_path:
                continue
            if rec.download_url and rec.download_url_expiry and rec.download_url_expiry > now:
                continue
            try:
                url = rec._generate_presigned_url()
                rec.write({
                    'download_url': url,
                    'download_url_expiry': now + datetime.timedelta(seconds=PRESIGNED_URL_EXPIRY),
                })
            except Exception as e:
                _logger.warning("Failed to refresh download URL for backup %s: %s", rec.id, e)

    def action_download(self):
        self.ensure_one()
        self._refresh_download_url()
        if not self.download_url:
            raise UserError(_("Could not generate download link."))
        return {
            'type': 'ir.actions.act_url',
            'url': self.download_url,
            'target': 'new',
        }

    def action_delete_backup(self):
        self.ensure_one()
        if self.state == 'done' and self.bucket_path:
            self._delete_from_bucket()
        self.unlink()
        return True

    # ------------------------------------------------------------------
    # Cloud storage helpers
    # ------------------------------------------------------------------
    def _get_s3_client(self):
        """Return a boto3 S3-compatible client configured from settings."""
        try:
            import boto3
            from botocore.config import Config as BotoConfig
        except ImportError:
            raise UserError(_("The 'boto3' Python package is required. Install it with: pip install boto3"))

        ICP = self.env['ir.config_parameter'].sudo()
        provider = ICP.get_param('saas_backup.provider', '')
        access_key = ICP.get_param('saas_backup.access_key', '')
        secret_key = ICP.get_param('saas_backup.secret_key', '')
        region = ICP.get_param('saas_backup.region', '')
        endpoint = ICP.get_param('saas_backup.endpoint', '')
        bucket = ICP.get_param('saas_backup.bucket_name', '')

        if not all([provider, access_key, secret_key, bucket]):
            raise UserError(_(
                "Cloud backup is not configured. Go to SaaS Manager > Configuration > Settings "
                "and fill in the Backup Storage section."
            ))

        kwargs = {
            'aws_access_key_id': access_key,
            'aws_secret_access_key': secret_key,
            'region_name': region or None,
        }
        if endpoint:
            kwargs['endpoint_url'] = endpoint
        if provider == 'digitalocean':
            kwargs['config'] = BotoConfig(s3={'addressing_style': 'path'})

        return boto3.client('s3', **kwargs), bucket

    def _upload_to_bucket(self, object_key, data_bytes):
        client, bucket = self._get_s3_client()
        client.put_object(Bucket=bucket, Key=object_key, Body=data_bytes)

    def _generate_presigned_url(self):
        client, bucket = self._get_s3_client()
        return client.generate_presigned_url(
            'get_object',
            Params={'Bucket': bucket, 'Key': self.bucket_path},
            ExpiresIn=PRESIGNED_URL_EXPIRY,
        )

    def _delete_from_bucket(self):
        try:
            client, bucket = self._get_s3_client()
            client.delete_object(Bucket=bucket, Key=self.bucket_path)
        except Exception as e:
            _logger.warning("Failed to delete backup object %s: %s", self.bucket_path, e)

    # ------------------------------------------------------------------
    # Backup creation — all done on the docker server via SSH
    # ------------------------------------------------------------------
    def _create_backup_zip(self, instance):
        """SSH to the docker server, dump DB + copy filestore + manifest, zip, return bytes."""
        instance._ensure_can_ssh()
        docker_server = instance.docker_server_id
        container_name = instance._get_container_name()
        instance_path = instance._get_instance_path()
        db_name = instance.subdomain
        db_server = instance.db_server_id
        db_host = db_server.private_ip_v4 or db_server.ip_v4
        db_port = db_server.psql_port or 5432
        ts = fields.Datetime.now().strftime('%Y%m%d%H%M%S')
        tmp_dir = '/tmp/saas_backup_%s_%s' % (db_name, ts)
        zip_path = '%s.zip' % tmp_dir
        script_path = '/tmp/saas_backup_script_%s_%s.sh' % (db_name, ts)

        import json
        manifest = json.dumps({
            'odoo_version': instance.odoo_version_id.name or '',
            'database': db_name,
            'partner': instance.partner_id.name or '',
            'timestamp': fields.Datetime.now().isoformat(),
            'instance': instance.name or '',
        }, indent=2)

        script = """#!/bin/bash
set -e

TMP_DIR="{tmp_dir}"
ZIP_PATH="{zip_path}"
CONTAINER="{container}"
DB_NAME="{db_name}"
DB_HOST="{db_host}"
DB_PORT="{db_port}"
DB_USER="{db_user}"
DB_PASS="{db_pass}"

mkdir -p "$TMP_DIR/filestore"

# 1) pg_dump via docker exec (pass PGPASSWORD into the container env)
docker exec -e PGPASSWORD="$DB_PASS" "$CONTAINER" pg_dump -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" --no-owner > "$TMP_DIR/dump.sql"

# 2) Copy filestore from inside the container using docker cp
#    Check both the explicit data_dir path and the Odoo default fallback
if docker exec "$CONTAINER" test -d "/var/lib/odoo/filestore/$DB_NAME" 2>/dev/null; then
    docker cp "$CONTAINER:/var/lib/odoo/filestore/$DB_NAME/." "$TMP_DIR/filestore/" 2>/dev/null || true
elif docker exec "$CONTAINER" test -d "/var/lib/odoo/.local/share/Odoo/filestore/$DB_NAME" 2>/dev/null; then
    docker cp "$CONTAINER:/var/lib/odoo/.local/share/Odoo/filestore/$DB_NAME/." "$TMP_DIR/filestore/" 2>/dev/null || true
fi

# 3) Write manifest.json
cat > "$TMP_DIR/manifest.json" << 'MANIFEST_EOF'
{manifest}
MANIFEST_EOF

# 4) Zip
cd "$TMP_DIR"
zip -r -q "$ZIP_PATH" dump.sql filestore manifest.json

# 5) Base64 to stdout
base64 "$ZIP_PATH"

# 6) Cleanup
rm -rf "$TMP_DIR" "$ZIP_PATH"
""".format(
            tmp_dir=tmp_dir,
            zip_path=zip_path,
            container=container_name,
            db_name=db_name,
            db_host=db_host,
            db_port=db_port,
            db_user=instance.db_user,
            db_pass=instance.db_password,
            manifest=manifest,
        )

        with docker_server._get_ssh_connection() as ssh:
            # Upload script file to avoid shell quoting issues
            ssh.write_file(script_path, script)
            ssh.execute('chmod +x %s' % script_path)

            exit_code, stdout, stderr = ssh.execute(
                'bash %s' % script_path, timeout=600,
            )

            # Remove script
            ssh.execute('rm -f %s' % script_path)

        if exit_code != 0:
            raise UserError(
                _("Backup failed on server %s:\n%s") % (docker_server.name, stderr or stdout)
            )

        zip_b64 = stdout.strip()
        if not zip_b64:
            raise UserError(_("Backup produced empty output."))

        return base64.b64decode(zip_b64)

    # ------------------------------------------------------------------
    # Cron entry point
    # ------------------------------------------------------------------
    @api.model
    def _cron_backup_all_instances(self):
        """Create backups for all running instances and clean up old ones."""
        instances = self.env['saas.instance'].search([('state', '=', 'running')])
        for instance in instances:
            try:
                self._perform_backup(instance)
                self.env.cr.commit()
            except Exception as e:
                self.env.cr.rollback()
                _logger.error("Backup failed for instance %s: %s", instance.name, e)
                try:
                    self.create({
                        'instance_id': instance.id,
                        'name': 'backup_%s' % fields.Date.today().isoformat(),
                        'state': 'failed',
                        'error_message': str(e),
                    })
                    self.env.cr.commit()
                except Exception:
                    self.env.cr.rollback()

        self._cleanup_old_backups()

    def _perform_backup(self, instance):
        """Perform a single backup for an instance."""
        today_str = fields.Date.today().isoformat()
        partner = instance.partner_id
        partner_folder = '%s_%s' % (
            partner.id, self._sanitize_name(partner.name),
        ) if partner else 'no_partner'
        db_name = instance.subdomain
        object_key = '%s/%s/backup_%s.zip' % (partner_folder, db_name, today_str)

        backup = self.create({
            'instance_id': instance.id,
            'name': 'backup_%s' % today_str,
            'bucket_path': object_key,
            'state': 'running',
        })
        self.env.cr.commit()

        try:
            zip_data = backup._create_backup_zip(instance)
            backup._upload_to_bucket(object_key, zip_data)
            url = backup._generate_presigned_url()
            now = fields.Datetime.now()
            backup.write({
                'state': 'done',
                'size_mb': round(len(zip_data) / (1024 * 1024), 2),
                'download_url': url,
                'download_url_expiry': now + datetime.timedelta(seconds=PRESIGNED_URL_EXPIRY),
            })
        except Exception as e:
            backup.write({
                'state': 'failed',
                'error_message': str(e),
            })
            raise

    @api.model
    def _cleanup_old_backups(self):
        """Delete backups older than retention period."""
        cutoff = fields.Datetime.now() - datetime.timedelta(days=BACKUP_RETENTION_DAYS)
        old_backups = self.search([
            ('create_date', '<', cutoff),
            ('state', '=', 'done'),
        ])
        for backup in old_backups:
            try:
                backup._delete_from_bucket()
                backup.unlink()
                self.env.cr.commit()
            except Exception as e:
                self.env.cr.rollback()
                _logger.error("Failed to cleanup backup %s: %s", backup.name, e)

    @staticmethod
    def _sanitize_name(name):
        if not name:
            return 'unknown'
        return ''.join(
            c if c.isalnum() or c in ('-', '_') else '_' for c in name
        ).strip('_')
