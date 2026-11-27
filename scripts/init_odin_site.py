#!/usr/bin/env python3
"""Seed the ODIN website's content into a database that already exists.

scripts/db_init.py seeds every table when it builds a database. scripts/db_upgrade.py adds the
ODIN tables, or a new column of one, to an existing database but leaves them empty. This adds
what is missing. It seeds the site basics first, then the pages, then the page sections. A missing row is added,
and a saved row gets only the fields it has no text for. Text that is there is never replaced,
so it is safe to run again.

Usage:  python scripts/init_odin_site.py        (from the flask repo root, after db_upgrade.py)
Exit:   0 the site basics, the pages and the page sections are all there, 1 otherwise.
"""
import os
import sys

# Add the directory containing __init__.py to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from sqlalchemy.exc import SQLAlchemyError

from __init__ import app, db
from model.odin_page import OdinPage, initOdinPages
from model.odin_section import OdinSection, initOdinSections
from model.odin_site import OdinSite, initOdinSite


def not_ready(model):
    """What db_upgrade.py still has to add before this model's table can be seeded, as a message.
    None when the table and every column of the model are there. Creating them is left to
    db_upgrade.py, which takes a backup first."""
    inspector = db.inspect(db.engine)
    table = model.__tablename__
    if table not in inspector.get_table_names():
        return f"The {table} table does not exist yet. Run scripts/db_upgrade.py first."
    present = {column['name'] for column in inspector.get_columns(table)}
    absent = [column.name for column in model.__table__.columns if column.name not in present]
    if absent:
        return f"The {table} table has no column for: {', '.join(absent)}. Run scripts/db_upgrade.py first."
    return None


def seed_site():
    """(exit code, message) for the site basics."""
    with app.app_context():
        problem = not_ready(OdinSite)
        if problem:
            return 1, problem
        had_row = OdinSite.current() is not None
        try:
            written = initOdinSite()
        except ValueError as error:
            return 1, f"Not seeded. {error}"
        if not had_row:
            return 0, "Seeded the ODIN site basics from model/dataconfigs/odin_site.json."
        if written:
            return 0, f"Filled in the fields that had no text: {', '.join(written)}."
        return 0, "The ODIN site basics are already there. Nothing changed."


def seed_pages():
    """(exit code, message) for the pages."""
    with app.app_context():
        problem = not_ready(OdinPage)
        if problem:
            return 1, problem
        try:
            written = initOdinPages()
        except ValueError as error:
            return 1, f"Not seeded. {error}"
        except SQLAlchemyError as error:
            # A row the database refuses, such as a hand-entered name that differs only by case on
            # MySQL. The seeds after this one still run.
            return 1, f"Not seeded. The database refused the pages ({error.__class__.__name__})."
        if written:
            return 0, f"Saved from model/dataconfigs/odin_page_list.json: {', '.join(written)}."
        return 0, "The ODIN pages are already there. Nothing changed."


def seed_sections():
    """(exit code, message) for the page sections."""
    with app.app_context():
        problem = not_ready(OdinSection)
        if problem:
            return 1, problem
        try:
            written = initOdinSections()
        except ValueError as error:
            return 1, f"Not seeded. {error}"
        if written:
            return 0, f"Saved from model/dataconfigs/odin_pages.json: {', '.join(written)}."
        return 0, "The ODIN page sections are already there. Nothing changed."


def main():
    """Runs each seed and returns the exit code. Each message is printed as its seed finishes, so
    the earlier ones are on screen even if a later one stops with an error."""
    exit_code = 0
    for seed in (seed_site, seed_pages, seed_sections):
        code, message = seed()
        print(message, flush=True)
        exit_code = max(exit_code, code)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
