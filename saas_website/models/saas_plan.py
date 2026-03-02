import re

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaasPlan(models.Model):
    _name = 'saas.plan'
    _description = 'SaaS Plan'
    _order = 'sequence, id'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)
    slug = fields.Char(compute='_compute_slug', store=True, readonly=False)
    description = fields.Text()
    monthly_price = fields.Float(string='Monthly Price / User', tracking=True)
    yearly_price = fields.Float(string='Yearly Price / User', tracking=True)
    min_users = fields.Integer(default=1)
    max_users = fields.Integer(default=100)
    trial_days = fields.Integer(default=0)
    feature_ids = fields.One2many('saas.plan.feature', 'plan_id', string='Features')
    bundle_ids = fields.Many2many('product.template', string='Module Bundles',
                                  domain=[('saas_type', '=', 'bundle')])
    odoo_version_id = fields.Many2one('saas.odoo.version', string='Odoo Version')
    is_popular = fields.Boolean(string='Popular Badge')
    sequence = fields.Integer(default=10)
    active = fields.Boolean(default=True)
    color = fields.Integer()

    _sql_constraints = [
        ('slug_unique', 'unique(slug)', 'The slug must be unique.'),
    ]

    @api.constrains('min_users', 'max_users')
    def _check_user_limits(self):
        for plan in self:
            if plan.min_users < 1:
                raise ValidationError(_("Minimum users must be at least 1."))
            if plan.max_users < plan.min_users:
                raise ValidationError(_("Maximum users must be greater than or equal to minimum users."))

    @api.depends('name')
    def _compute_slug(self):
        for plan in self:
            if plan.name and not plan.slug:
                slug = plan.name.lower().strip()
                slug = re.sub(r'[^\w\s-]', '', slug)
                slug = re.sub(r'[\s_]+', '-', slug)
                slug = re.sub(r'-+', '-', slug).strip('-')
                plan.slug = slug

    def calculate_price(self, billing_period, user_count, coupon_code=False):
        """Server-side price calculation.

        Returns dict with unit_price, subtotal, discount_amount, total,
        coupon_valid, coupon_message.
        """
        self.ensure_one()
        user_count = max(self.min_users, min(user_count, self.max_users))

        if billing_period == 'yearly':
            unit_price = self.yearly_price
        else:
            unit_price = self.monthly_price

        subtotal = unit_price * user_count
        discount_amount = 0.0
        coupon_valid = False
        coupon_message = ''

        if coupon_code:
            coupon = self.env['saas.coupon'].sudo().search([
                ('code', '=', coupon_code.strip().upper()),
            ], limit=1)
            if coupon:
                valid, message = coupon.validate(self.id)
                coupon_valid = valid
                coupon_message = message
                if valid:
                    discount_amount = subtotal - coupon.apply_discount(subtotal)
            else:
                coupon_message = _("Invalid coupon code.")

        total = subtotal - discount_amount
        return {
            'unit_price': unit_price,
            'subtotal': subtotal,
            'discount_amount': discount_amount,
            'total': max(total, 0.0),
            'coupon_valid': coupon_valid,
            'coupon_message': coupon_message,
            'user_count': user_count,
        }


class SaasPlanFeature(models.Model):
    _name = 'saas.plan.feature'
    _description = 'SaaS Plan Feature'
    _order = 'sequence, id'

    plan_id = fields.Many2one('saas.plan', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
