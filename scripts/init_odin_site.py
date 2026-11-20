#!/usr/bin/env python3
"""Seed the ODIN website's content into a database that already exists.

scripts/db_init.py seeds every table when it builds a database. scripts/db_upgrade.py adds the
ODIN tables, or a new column of one, to an existing database but leaves them empty. This adds
what is missing, first the site basics and then the page sections: a row the database does not
have, and the fields a saved row has no text for. It never replaces text that is there, so it is
safe to run again.

Usage:  python scripts/init_odin_site.py        (from the flask repo root, after db_upgrade.py)
Exit:   0 the site basics and the page sections are all there, 1 otherwise.
"""
import os
import sys

# Add the directory containing __init__.py to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from __init__ import app, db
from model import odin_section
from model.odin_section import OdinSection, initOdinSections
from model.odin_site import FIELDS, OdinSite, initOdinSite


def not_ready(model, columns):
    """What db_upgrade.py still has to add before this model's table can be seeded, as a message.
    None when the table and these columns are there. Creating them is left to db_upgrade.py, which
    takes a backup first."""
    inspector = db.inspect(db.engine)
    table = model.__tablename__
    if table not in inspector.get_table_names():
        return f"The {table} table does not exist yet. Run scripts/db_upgrade.py first."
    present = {column['name'] for column in inspector.get_columns(table)}
    absent = [key for key in columns if key not in present]
    if absent:
        return f"The {table} table has no column for: {', '.join(absent)}. Run scripts/db_upgrade.py first."
    return None


def seed_site():
    """(exit code, message) for the site basics."""
    with app.app_context():
        problem = not_ready(OdinSite, FIELDS)
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


def seed_sections():
    """(exit code, message) for the page sections."""
    with app.app_context():
        problem = not_ready(OdinSection, ['page', 'name', 'position', *odin_section.FIELDS, 'items'])
        if problem:
            return 1, problem
        try:
            written = initOdinSections()
        except ValueError as error:
            return 1, f"Not seeded. {error}"
        if written:
            return 0, f"Saved from model/dataconfigs/odin_pages.json: {', '.join(written)}."
        return 0, "The ODIN page sections are already there. Nothing changed."


if __name__ == "__main__":
    results = [seed_site(), seed_sections()]
    for code, message in results:
        print(message)
    sys.exit(max(code for code, message in results))
