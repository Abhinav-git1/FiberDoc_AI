# Database migrations (Alembic)

Every change to the database structure is a numbered script in `versions/`. Each script has an `upgrade()` that applies
the change and a `downgrade()` that undoes it. The database records which version it is at in the `alembic_version` table.

The app runs `alembic upgrade head` itself at startup (`init_db` in `app/db/session.py`), so a new or older
database is brought up to date automatically. The commands below are for working on the schema. Run them from `backend/`:

```bash
alembic current                                  # which version this database is at
alembic history                                  # every migration, in order
alembic upgrade head                             # apply everything not yet applied
alembic downgrade -1                             # undo the last migration
alembic revision --autogenerate -m "add reports" # draft a migration from changes in app/db/models.py
```

The database URL comes from `DATABASE_URL` in `backend/.env`. No URL or password is stored in `alembic.ini`.

## Changing a table

1. Edit the model in `app/db/models.py`.
2. Run `alembic revision --autogenerate -m "..."`, then **read the generated file**. Autogenerate sees new or removed
   tables, columns and indexes. It cannot tell a rename from a drop followed by an add, and it never moves data, so
   write those steps by hand (`op.alter_column(..., new_column_name=...)`, `op.execute("UPDATE ...")`).
3. Run `alembic upgrade head`, then `alembic downgrade -1`, then `alembic upgrade head` again, to check that both
   directions work.
4. Commit the model change and the migration together.

## Versions

| Revision | What it does |
|---|---|
| `0001` | Baseline: the 8 tables that existed before Alembic (users, projects, documents, chunks, rules, findings, review_comments, audit_events) |
| `0002` | Chat storage: `chats`, `chat_messages` |

A database created before Alembic is not rebuilt. On its first startup, `init_db` adds any columns it is missing
(the same statements that used to run at every startup), records it as `0001`, and then applies `0002` onwards.
