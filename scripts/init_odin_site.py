#!/usr/bin/env python3
"""Seed the ODIN site basics into a database that already exists.

scripts/db_init.py seeds every table when it builds a database. scripts/db_upgrade.py adds the
odin_site table, or a new column of it, to an existing database but leaves it empty. This adds
the row when there is none, and fills in the fields a saved row has no text for. It never
replaces text that is there, so it is safe to run again.

Usage:  python scripts/init_odin_site.py        (from the flask repo root, after db_upgrade.py)
Exit:   0 the row is there, 1 otherwise.
"""
import os
import sys

# Add the directory containing __init__.py to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from __init__ import app, db
from model.odin_site import OdinSite, initOdinSite


def seed_site():
    """(exit code, message). Creating the table is left to db_upgrade.py, which takes a backup first."""
    with app.app_context():
        if OdinSite.__tablename__ not in db.inspect(db.engine).get_table_names():
            return 1, "The odin_site table does not exist yet. Run scripts/db_upgrade.py first."
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


if __name__ == "__main__":
    code, message = seed_site()
    print(message)
    sys.exit(code)
