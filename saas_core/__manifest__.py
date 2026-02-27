{
    'name': 'SaaS Instance Manager',
    'version': '18.0.2.0.0',
    'category': 'SaaS',
    'summary': 'Provision and manage multi-tenant Odoo instances with Docker containers',
    'description': """
Manage your SaaS platform directly from Odoo.

Key capabilities:

- **Instance lifecycle** -- provision, start, stop, restart, suspend, and delete
  Odoo instances running in Docker containers on remote servers.
- **Automatic provisioning** -- generates docker-compose and odoo.conf files,
  creates PostgreSQL users and databases, assigns ports, and initialises the
  Odoo database, all over SSH.
- **Module management** -- fetch available modules from a Docker image, organise
  them into sellable bundles, and install them on running instances.
- **Product catalog integration** -- modules and bundles are standard Odoo
  products (product.template) so they can be quoted, sold, and invoiced through
  the regular Sales workflow.
- **Infrastructure registry** -- keep track of Docker host servers, PostgreSQL
  servers, SSH keys, and base domains used by the platform.
""",
    'author': 'SaaS Platform',
    'license': 'LGPL-3',
    'depends': ['base', 'mail', 'sale'],
    'external_dependencies': {
        'python': ['paramiko', 'jinja2'],
    },
    'data': [
        'security/ir.model.access.csv',
        'data/ir_config_parameter.xml',
        'views/saas_instance_views.xml',
        'views/saas_ssh_key_pair_views.xml',
        'views/saas_docker_container_views.xml',
        'views/saas_docker_server_views.xml',
        'views/saas_db_server_views.xml',
        'views/saas_domain_views.xml',
        'views/saas_odoo_version_views.xml',
        'views/product_template_views.xml',
        'views/res_config_settings_views.xml',
        'views/saas_menus.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}
