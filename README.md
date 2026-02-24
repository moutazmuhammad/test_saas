I have an existing Odoo SaaS management module with the following models:

- saas.instance
- saas.container.physical.server
- saas.psql.physical.server
- saas.odoo.version
- saas.ssh.key.pair
- saas.based.domain
- res.config.settings (extended)

Do NOT recreate models. Do NOT rename models. Only extend logic.

==================================================
CURRENT BEHAVIOR
==================================================
- action_deploy only changes state to 'deployed'
- action_restart, action_stop, action_redeploy, action_delete_instance, etc return True
- No Docker provisioning exists yet
- No SSH execution logic exists
- No Jinja rendering exists
- No filesystem creation logic exists

==================================================
NEW REQUIREMENTS
==================================================
1) When deploying an instance:

- Connect via SSH to saas.container.physical.server
- Create folder structure remotely:

  <docker_base_path>/partner_code/<subdomain>/
  ├── addons
  ├── config
  │   └── odoo.conf
  ├── data
  │   └── odoo
  └── docker-compose.yml

- Execute remote commands:

  mkdir -p ./data/odoo ./config ./addons
  chown -R 1000:1000 ./data/odoo ./config ./addons
  chmod -R 777 ./data/odoo ./config ./addons

2) Generate docker-compose.yml remotely using Jinja template:

- image from saas.odoo.version (docker_image + docker_image_tag)
- container name = odoo_<subdomain>
- ports from xmlrpc_port and longpolling_port
- mount volumes:
  ./data/odoo
  ./config
  ./addons

3) Generate config/odoo.conf remotely using Jinja template:

- admin_passwd, db_user, db_password from saas.instance
- psql_physical_server_id.ip_v4, psql_port
- extra_config if any

4) Each instance must have unique:

- db_user
- db_password

> The module should generate random strong db_user and db_password for each instance and save them in the saas.instance record.

⚠️ Do NOT create databases. Do NOT execute SQL. PostgreSQL database creation is out of scope.

5) Execute docker-compose up -d remotely

6) Initialize Odoo database inside container using:

docker compose exec <container> odoo \
  -d <subdomain> \
  --db_user=<db_user> \
  --db_password=<db_password> \
  --init=base,sale,crm \
  --without-demo=all \
  --stop-after-init \
  --no-http

> The container should connect to an existing database server; creation of DB or user in PostgreSQL is not handled by this module.

==================================================
STATE MANAGEMENT
==================================================
- saas.instance states:
  draft → provisioning → running → failed → suspended → cancelled
- Deploy flow: draft → provisioning → running, failed on error
- Stop: docker stop
- Restart: docker restart
- Delete: docker rm -f + delete instance folder
- Suspend: docker stop
- Redeploy: docker compose down + up

==================================================
ARCHITECTURE REQUIREMENTS
==================================================
- Use paramiko for SSH
- Use Jinja2 for template rendering
- Use subprocess only locally if required
- Handle SSH key authentication using saas.ssh.key.pair.private_key_file
- All provisioning must be idempotent
- Capture logs of:
  directory creation, docker up, db init
  Store logs in provisioning_log text field
- Auto assign ports if xmlrpc_port is empty using saas_default_instance_starting_port
- Prevent port conflicts per physical server
- Secure handling of db_user and db_password in memory; do not log plain text
- Timeout protection for SSH commands

==================================================
OUTPUT EXPECTED
==================================================
1) Updated Python methods only for actions that need changes
2) Any new fields added (if necessary)
3) Jinja template examples for docker-compose.yml and odoo.conf
4) Clear explanation of provisioning flow
5) Production-ready, scalable, and secure SaaS provisioning logic
