from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class SaasCoupon(models.Model):
    _name = 'saas.coupon'
    _description = 'SaaS Coupon'
    _order = 'id desc'

    name = fields.Char(required=True)
    code = fields.Char(required=True)
    discount_type = fields.Selection([
        ('percentage', 'Percentage'),
        ('fixed', 'Fixed Amount'),
    ], required=True, default='percentage')
    discount_value = fields.Float(required=True)
    valid_from = fields.Date()
    valid_to = fields.Date()
    max_uses = fields.Integer(default=0, help="0 = unlimited")
    current_uses = fields.Integer(readonly=True, default=0)
    plan_ids = fields.Many2many('saas.plan', string='Restricted to Plans',
                                help="Leave empty to allow all plans")
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('code_unique', 'unique(code)', 'The coupon code must be unique.'),
    ]

    @api.constrains('discount_value', 'discount_type')
    def _check_discount_value(self):
        for coupon in self:
            if coupon.discount_value <= 0:
                raise ValidationError(_("Discount value must be positive."))
            if coupon.discount_type == 'percentage' and coupon.discount_value > 100:
                raise ValidationError(_("Percentage discount cannot exceed 100%."))

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('code'):
                vals['code'] = vals['code'].strip().upper()
        return super().create(vals_list)

    def write(self, vals):
        if vals.get('code'):
            vals['code'] = vals['code'].strip().upper()
        return super().write(vals)

    def validate(self, plan_id):
        """Validate coupon for a given plan.

        Returns (valid: bool, message: str) tuple.
        """
        self.ensure_one()
        if not self.active:
            return False, _("This coupon is no longer active.")

        today = fields.Date.context_today(self)
        if self.valid_from and today < self.valid_from:
            return False, _("This coupon is not yet valid.")
        if self.valid_to and today > self.valid_to:
            return False, _("This coupon has expired.")

        if self.max_uses > 0 and self.current_uses >= self.max_uses:
            return False, _("This coupon has reached its usage limit.")

        if self.plan_ids and plan_id not in self.plan_ids.ids:
            return False, _("This coupon is not valid for the selected plan.")

        return True, _("Coupon applied successfully!")

    def apply_discount(self, amount):
        """Apply discount to an amount and return the discounted amount."""
        self.ensure_one()
        if self.discount_type == 'percentage':
            return amount * (1 - self.discount_value / 100.0)
        else:
            return max(amount - self.discount_value, 0.0)

    def _increment_usage(self):
        """Atomically increment current_uses using SQL to prevent race conditions."""
        self.ensure_one()
        self.env.cr.execute(
            "UPDATE saas_coupon SET current_uses = current_uses + 1 WHERE id = %s",
            (self.id,)
        )
        self.invalidate_recordset(['current_uses'])
