import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Clean up old saas.odoo.module / saas.odoo.product references and
    rename columns that were given clearer field names in 18.0.2.0.0."""
    if not version:
        return

    _logger.info("Pre-migration: cleaning old references and renaming columns")

    # ------------------------------------------------------------------
    # 1. Null out product_id and module_id in instance module lines.
    #    These pointed to saas.odoo.product and saas.odoo.module respectively,
    #    but are now redefined as Many2one to product.product.
    # ------------------------------------------------------------------
    cr.execute("""
        UPDATE saas_instance_module_line
        SET product_id = NULL, module_id = NULL
    """)

    # ------------------------------------------------------------------
    # 2. Drop the old many2many rel table for installed modules
    #    (was saas.odoo.module ids, now will be product.product ids)
    # ------------------------------------------------------------------
    cr.execute("""
        DROP TABLE IF EXISTS saas_instance_installed_module_rel
    """)

    # ------------------------------------------------------------------
    # 3. Drop old foreign key constraints that will be recreated
    # ------------------------------------------------------------------
    cr.execute("""
        ALTER TABLE saas_instance_module_line
        DROP CONSTRAINT IF EXISTS saas_instance_module_line_product_id_fkey
    """)
    cr.execute("""
        ALTER TABLE saas_instance_module_line
        DROP CONSTRAINT IF EXISTS saas_instance_module_line_module_id_fkey
    """)

    # ------------------------------------------------------------------
    # 4. Rename columns on saas_instance for clearer field names
    # ------------------------------------------------------------------
    column_renames = [
        ('based_domain_id', 'domain_id'),
        ('container_physical_server_id', 'docker_server_id'),
        ('psql_physical_server_id', 'db_server_id'),
        ('admin_passwd', 'admin_password'),
    ]

    for old_col, new_col in column_renames:
        # Check if old column exists (it won't on a fresh install)
        cr.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'saas_instance' AND column_name = %s
        """, (old_col,))
        if cr.fetchone():
            _logger.info("Renaming saas_instance.%s -> %s", old_col, new_col)
            cr.execute(
                'ALTER TABLE saas_instance RENAME COLUMN "%s" TO "%s"' % (old_col, new_col)
            )

    # ------------------------------------------------------------------
    # 5. Update SQL constraint names that reference old column names
    # ------------------------------------------------------------------
    cr.execute("""
        SELECT constraint_name FROM information_schema.table_constraints
        WHERE table_name = 'saas_instance'
          AND constraint_name LIKE '%%container_physical_server%%'
    """)
    for row in cr.fetchall():
        cr.execute('ALTER TABLE saas_instance DROP CONSTRAINT IF EXISTS "%s"' % row[0])

    _logger.info("Pre-migration: completed")
