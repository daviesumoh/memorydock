# Database roles

Three database users, each restricted to the project's cluster.

| User | Role | Used by |
|---|---|---|
| `md_admin` | built-in `readWriteAnyDatabase` + `dbAdminAnyDatabase` | `atlas_setup.py`, `policy_publish.py`, integration tests. Never deployed. |
| `md_gateway` | custom `md_gateway_role` | the deployed gateway and local gateway runs |
| `md_worker` | custom `md_worker_role` | the deployed worker and local worker runs |

## What the custom roles grant

The same grants apply to every database a role covers: the shared `memorydock` database and each developer's `memorydock_dev_<handle>` database. Integration tests use the admin user on throwaway `memorydock_test_<random>` databases, because Atlas custom roles can't name a database pattern.

`md_gateway_role`, per database:

- `FIND`, `INSERT`, `UPDATE`, `REMOVE` on every collection in `infra/atlas/validators/`, except `audit_log`.
- `FIND`, `INSERT` only on `audit_log`, which keeps the audit chain append-only for the application.
- `CHANGE_STREAM` on the collections the gateway watches, once they exist: `audit_log`, `memories`, `review_items`, `leases`, `approvals`, `tasks`, `effects`, `drift_events`, `policy_heads`.

`md_worker_role`, per database: the gateway's grants, plus `CHANGE_STREAM` on `turns` and CRUD on the LangGraph checkpoint collections once those exist.

Neither role gets `createIndex`, `collMod`, `dropCollection`, `dropDatabase` or any cluster action. Index and validator changes go through `md_admin` and `atlas_setup.py`.

## Changing them

`scripts/atlas_roles.py` computes both roles from the validator list, so adding a collection is: add its validator, run `make atlas-setup`, then regenerate the roles.

```
uv run python scripts/atlas_roles.py                       # preview: full desired set + diff
uv run python scripts/atlas_roles.py --add-db <database>   # cover another database
uv run python scripts/atlas_roles.py --apply               # apply after the preview is approved
```

`atlas customDbRoles update` replaces the whole privilege list, so the script always sends the complete set for every database the roles already cover. A database is only dropped from the roles with an explicit `--remove-db`; the shared database can't be removed.
