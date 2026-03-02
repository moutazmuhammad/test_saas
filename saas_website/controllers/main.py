import re
import logging

from odoo import http, _
from odoo.http import request

_logger = logging.getLogger(__name__)

SUBDOMAIN_RE = re.compile(r'^[a-z0-9]([a-z0-9-]{1,61}[a-z0-9])?$')


class SaaSWebsite(http.Controller):

    # ------------------------------------------------------------------
    # Pricing page (public)
    # ------------------------------------------------------------------
    @http.route('/pricing', type='http', auth='public', website=True)
    def pricing_page(self, **kw):
        plans = request.env['saas.plan'].sudo().search([
            ('active', '=', True),
        ], order='sequence, id')
        return request.render('saas_website.pricing_page', {
            'plans': plans,
        })

    # ------------------------------------------------------------------
    # AJAX: server-side price calculation (public)
    # ------------------------------------------------------------------
    @http.route('/pricing/calculate', type='json', auth='public', website=True)
    def pricing_calculate(self, plan_id, billing_period, user_count, coupon_code=False):
        plan = request.env['saas.plan'].sudo().browse(int(plan_id)).exists()
        if not plan or not plan.active:
            return {'error': _("Invalid plan.")}

        if billing_period not in ('monthly', 'yearly'):
            return {'error': _("Invalid billing period.")}

        try:
            user_count = int(user_count)
        except (ValueError, TypeError):
            return {'error': _("Invalid user count.")}

        result = plan.calculate_price(billing_period, user_count, coupon_code)
        return result

    # ------------------------------------------------------------------
    # AJAX: coupon validation (public)
    # ------------------------------------------------------------------
    @http.route('/pricing/validate-coupon', type='json', auth='public', website=True)
    def validate_coupon(self, coupon_code, plan_id):
        if not coupon_code:
            return {'valid': False, 'message': _("Please enter a coupon code.")}

        coupon = request.env['saas.coupon'].sudo().search([
            ('code', '=', coupon_code.strip().upper()),
        ], limit=1)

        if not coupon:
            return {'valid': False, 'message': _("Invalid coupon code.")}

        valid, message = coupon.validate(int(plan_id))
        return {'valid': valid, 'message': message}

    # ------------------------------------------------------------------
    # Checkout page (authenticated users only)
    # ------------------------------------------------------------------
    @http.route('/subscribe', type='http', auth='user', website=True)
    def subscribe_page(self, plan_id=None, billing_period='monthly',
                       user_count=1, coupon_code='', **kw):
        if not plan_id:
            return request.redirect('/pricing')

        plan = request.env['saas.plan'].sudo().browse(int(plan_id)).exists()
        if not plan or not plan.active:
            return request.redirect('/pricing')

        if billing_period not in ('monthly', 'yearly'):
            billing_period = 'monthly'

        try:
            user_count = int(user_count)
        except (ValueError, TypeError):
            user_count = plan.min_users

        user_count = max(plan.min_users, min(user_count, plan.max_users))

        price_info = plan.calculate_price(billing_period, user_count, coupon_code)

        # Get first domain for subdomain preview
        domain = request.env['saas.based.domain'].sudo().search([], limit=1)
        base_domain = domain.name if domain else 'example.com'

        return request.render('saas_website.checkout_page', {
            'plan': plan,
            'billing_period': billing_period,
            'user_count': user_count,
            'coupon_code': coupon_code or '',
            'price_info': price_info,
            'base_domain': base_domain,
            'partner': request.env.user.partner_id,
        })

    # ------------------------------------------------------------------
    # Process checkout (authenticated POST)
    # ------------------------------------------------------------------
    @http.route('/subscribe/process', type='http', auth='user',
                website=True, methods=['POST'])
    def subscribe_process(self, **post):
        # Extract and validate parameters
        plan_id = post.get('plan_id')
        billing_period = post.get('billing_period')
        user_count = post.get('user_count')
        coupon_code = post.get('coupon_code', '').strip()
        subdomain = post.get('subdomain', '').strip().lower()

        # Validate plan
        if not plan_id:
            return request.redirect('/pricing')

        plan = request.env['saas.plan'].sudo().browse(int(plan_id)).exists()
        if not plan or not plan.active:
            return request.redirect('/pricing')

        # Validate billing period
        if billing_period not in ('monthly', 'yearly'):
            return request.redirect('/pricing')

        # Validate user count
        try:
            user_count = int(user_count)
        except (ValueError, TypeError):
            return request.redirect('/pricing')
        user_count = max(plan.min_users, min(user_count, plan.max_users))

        # Validate subdomain format
        if not subdomain or not SUBDOMAIN_RE.match(subdomain):
            return request.render('saas_website.checkout_page', {
                'plan': plan,
                'billing_period': billing_period,
                'user_count': user_count,
                'coupon_code': coupon_code,
                'price_info': plan.calculate_price(billing_period, user_count, coupon_code),
                'base_domain': self._get_base_domain(),
                'partner': request.env.user.partner_id,
                'error': _("Invalid subdomain. Use 3-63 characters: lowercase letters, numbers, and hyphens."),
            })

        # Check subdomain uniqueness
        existing = request.env['saas.instance'].sudo().search([
            ('subdomain', '=', subdomain),
        ], limit=1)
        if existing:
            return request.render('saas_website.checkout_page', {
                'plan': plan,
                'billing_period': billing_period,
                'user_count': user_count,
                'coupon_code': coupon_code,
                'price_info': plan.calculate_price(billing_period, user_count, coupon_code),
                'base_domain': self._get_base_domain(),
                'partner': request.env.user.partner_id,
                'error': _("This subdomain is already taken. Please choose another."),
            })

        # Recalculate price server-side (never trust frontend amounts)
        price_info = plan.calculate_price(billing_period, user_count, coupon_code)

        # Find and validate coupon
        coupon = False
        if coupon_code and price_info['coupon_valid']:
            coupon = request.env['saas.coupon'].sudo().search([
                ('code', '=', coupon_code.upper()),
            ], limit=1)
            if coupon:
                # Re-validate to ensure it's still valid
                valid, _msg = coupon.validate(plan.id)
                if valid:
                    coupon._increment_usage()
                else:
                    coupon = False

        # Create instance directly with billing fields
        instance = request.env['saas.instance'].sudo().create({
            'subdomain': subdomain,
            'partner_id': request.env.user.partner_id.id,
            'plan_id': plan.id,
            'billing_period': billing_period,
            'user_count': user_count,
            'coupon_id': coupon.id if coupon else False,
            'unit_price': price_info['unit_price'],
            'subtotal': price_info['subtotal'],
            'discount_amount': price_info['discount_amount'],
            'total_amount': price_info['total'],
        })

        # Trigger provisioning
        try:
            instance.action_provision_from_plan()
        except Exception as e:
            _logger.error("Provisioning failed for instance %s: %s", instance.id, e)
            # Don't fail the whole request — the instance is created,
            # provisioning can be retried from backend
            return request.render('saas_website.thank_you_page', {
                'instance': instance,
                'provisioning_error': str(e),
            })

        return request.redirect('/subscribe/thank-you/%d' % instance.id)

    # ------------------------------------------------------------------
    # Thank-you page
    # ------------------------------------------------------------------
    @http.route('/subscribe/thank-you/<int:instance_id>', type='http',
                auth='user', website=True)
    def thank_you_page(self, instance_id, **kw):
        instance = request.env['saas.instance'].sudo().browse(instance_id).exists()
        if not instance:
            return request.redirect('/pricing')

        # Only allow viewing your own instance
        if instance.partner_id != request.env.user.partner_id:
            return request.redirect('/pricing')

        return request.render('saas_website.thank_you_page', {
            'instance': instance,
        })

    # ------------------------------------------------------------------
    # Apps marketplace (public)
    # ------------------------------------------------------------------
    @http.route('/apps', type='http', auth='public', website=True)
    def apps_page(self, version=None, search='', **kw):
        OdooVersion = request.env['saas.odoo.version'].sudo()
        Product = request.env['product.template'].sudo()

        # Versions that actually have modules
        all_versions = OdooVersion.search([])
        versions = all_versions.filtered(lambda v: v.module_count > 0)

        # Resolve selected version filter
        current_version = False
        if version:
            try:
                current_version = OdooVersion.browse(int(version)).exists()
            except (ValueError, TypeError):
                pass

        # Build search domain
        domain = [('saas_type', '=', 'module')]
        if current_version:
            domain.append(('saas_odoo_version_id', '=', current_version.id))
        if search:
            search = search.strip()
            domain = [
                '&',
                ('saas_type', '=', 'module'),
            ] + (['&', ('saas_odoo_version_id', '=', current_version.id)] if current_version else []) + [
                '|', '|',
                ('name', 'ilike', search),
                ('technical_name', 'ilike', search),
                ('description_sale', 'ilike', search),
            ]

        modules = Product.search(domain, order='name')

        # Group by version
        grouped = []
        if current_version:
            grouped.append({
                'version': current_version,
                'modules': modules,
            })
        else:
            for ver in versions:
                ver_modules = modules.filtered(
                    lambda m, v=ver: m.saas_odoo_version_id == v
                )
                if ver_modules:
                    grouped.append({
                        'version': ver,
                        'modules': ver_modules,
                    })

        return request.render('saas_website.apps_page', {
            'versions': versions,
            'current_version': current_version,
            'grouped_modules': grouped,
            'search': search,
            'module_count': len(modules),
        })

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_base_domain(self):
        domain = request.env['saas.based.domain'].sudo().search([], limit=1)
        return domain.name if domain else 'example.com'
