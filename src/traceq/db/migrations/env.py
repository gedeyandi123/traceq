"""Alembic environment: runs the migrations connected as the owner role."""

from alembic import context
from sqlalchemy import create_engine

with create_engine(context.config.attributes["url"]).connect() as connection:
    context.configure(connection=connection, transaction_per_migration=True)
    with context.begin_transaction():
        context.run_migrations()
