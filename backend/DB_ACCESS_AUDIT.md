# DB Access Audit (Task 4)

Date: 2026-04-22
Scope: `grunt/**/*.py`
Rule: Find `session.execute(...)` usages outside explicitly allowed modules:
- `grunt/core/document/mixins/write.py`
- `grunt/core/document/mixins/read.py`
- `grunt/core/document/query.py`
- `grunt/core/document/service.py`

## Summary

- Total matches outside the allow-list: **57**
- Mostly low-level framework internals where SQLAlchemy expression control is intentional

Top files by count:
- `grunt/core/metadata/registry.py` (9)
- `grunt/core/search/service.py` (7)
- `grunt/core/document/multi_link.py` (6)
- `grunt/core/document/tree.py` (5)
- `grunt/core/document/links.py` (5)

## Classification

### A) Keep as low-level SQLAlchemy internals (no mechanical `grunt.db.*` swap)

These modules are framework internals with transaction/locking/CTE/bulk semantics:
- `grunt/core/metadata/registry.py`
- `grunt/core/search/service.py`
- `grunt/core/document/multi_link.py`
- `grunt/core/document/tree.py`
- `grunt/core/document/links.py`
- `grunt/core/document/versioning.py`
- `grunt/core/document/relations.py`
- `grunt/core/naming/service.py` (uses `SELECT ... FOR UPDATE` semantics)
- `grunt/core/doctypes/doc_type/doc_type.py`
- `grunt/core/document/aggregate.py`

### B) Intentional raw SQL / diagnostics

- `grunt/core/reports/engine.py` (user-provided SQL report executor, guarded to SELECT)
- `grunt/api/v1/health.py` (`SELECT 1` readiness probe)
- `grunt/core/db/profiler.py` (example snippet in profiler docs)
- `grunt/api/messages.py` (commented example line)

### C) Application-layer candidates for future unification

No remaining candidates in this pass.

## Completed in this pass

- Added `grunt.db.insert_one()` and `grunt.db.insert_many()` in `grunt/db.py`.
- Added `grunt.db.bulk_update()` in `grunt/db.py`.
- Migrated `grunt/core/email/service.py` queue insertion to `grunt.db.insert_one()`.
- Migrated `grunt/core/notification/service.py` notification insertion to `grunt.db.insert_one()`.
- Migrated `grunt/core/app/document_api.py` `bulk_insert()` to `grunt.db.insert_many()`.
- Migrated `grunt/core/app/document_api.py` `bulk_update()` to `grunt.db.bulk_update()`.
- Migrated `grunt/core/i18n/service.py` DB overrides loading to `grunt.db.get_all(..., limit=None)`.

## Proposed next step (safe)

1. Keep categories A/B as intentional exceptions.
2. Start next refactor task from the master plan.
