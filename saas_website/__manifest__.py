{
    'name': 'SaaS Website',
    'version': '18.0.1.0.0',
    'category': 'Website',
    'summary': 'Public pricing page, checkout & instance provisioning for SaaS',
    'description': """
        Provides a public-facing website for SaaS plans:
        - Dynamic pricing page with plan comparison
        - Checkout with auto-provisioning of SaaS instances
        - Coupon / discount code system
        - Backend management for plans and coupons
    """,
    'author': 'SaaS Manager',
    'depends': ['saas_core', 'website'],
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'views/saas_plan_views.xml',
        'views/saas_coupon_views.xml',
        'views/menus.xml',
        'templates/pricing_page.xml',
        'templates/checkout_page.xml',
        'templates/apps_page.xml',
        'data/sample_plans.xml',
    ],
    'assets': {
        'web.assets_frontend': [
            'saas_website/static/src/css/pricing.css',
            'saas_website/static/src/js/pricing.js',
        ],
    },
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
