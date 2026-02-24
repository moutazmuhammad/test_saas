from odoo import api, fields, models


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

    # ========== State ==========
    state = fields.Selection(
        selection=[
            ('draft', 'Draft'),
            ('deployed', 'Deployed'),
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

    # ========== Actions ==========
    def action_deploy(self):
        for rec in self:
            rec.state = 'deployed'

    def action_suspend(self):
        for rec in self:
            rec.state = 'suspended'

    def action_cancel(self):
        for rec in self:
            rec.state = 'cancelled'

    def action_draft(self):
        for rec in self:
            rec.state = 'draft'

    def action_restart(self):
        return True

    def action_stop(self):
        return True

    def action_redeploy(self):
        return True

    def action_config(self):
        return True

    def action_create_backup(self):
        return True

    def action_update_install_module(self):
        return True

    def action_delete_instance(self):
        return True

    def action_get_users(self):
        return True

    def action_get_apps(self):
        return True


