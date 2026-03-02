import logging

from odoo import fields, models, _
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class SaasInstanceWebsite(models.Model):
    _inherit = 'saas.instance'

    plan_id = fields.Many2one('saas.plan', tracking=True)
    billing_period = fields.Selection([
        ('monthly', 'Monthly'),
        ('yearly', 'Yearly'),
    ], tracking=True)
    user_count = fields.Integer(tracking=True)
    coupon_id = fields.Many2one('saas.coupon', readonly=True)
    unit_price = fields.Float(readonly=True)
    subtotal = fields.Float(readonly=True)
    discount_amount = fields.Float(readonly=True)
    total_amount = fields.Float(readonly=True)
    start_date = fields.Date()

    def action_provision_from_plan(self):
        """Assign infrastructure from plan defaults, add bundles, and deploy."""
        self.ensure_one()
        plan = self.plan_id
        if not plan:
            raise UserError(_("No plan set on this instance."))

        # Find first available infrastructure
        docker_server = self.env['saas.container.physical.server'].search([], limit=1, order='sequence')
        if not docker_server:
            raise UserError(_("No Docker server available for provisioning."))

        db_server = self.env['saas.psql.physical.server'].search([], limit=1, order='sequence')
        if not db_server:
            raise UserError(_("No database server available for provisioning."))

        domain = self.env['saas.based.domain'].search([], limit=1)
        if not domain:
            raise UserError(_("No base domain configured."))

        odoo_version = plan.odoo_version_id
        if not odoo_version:
            odoo_version = self.env['saas.odoo.version'].search([], limit=1)
        if not odoo_version:
            raise UserError(_("No Odoo version configured."))

        # Write infra fields onto instance
        self.write({
            'domain_id': domain.id,
            'odoo_version_id': odoo_version.id,
            'docker_server_id': docker_server.id,
            'db_server_id': db_server.id,
        })

        # Add bundle lines from plan
        for bundle in plan.bundle_ids:
            product = self.env['product.product'].search([
                ('product_tmpl_id', '=', bundle.id),
            ], limit=1)
            if product:
                self.env['saas.instance.module.line'].create({
                    'instance_id': self.id,
                    'product_id': product.id,
                })

        # Deploy the instance
        self.action_deploy()
        self.start_date = fields.Date.context_today(self)
        return True
