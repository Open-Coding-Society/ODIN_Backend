""" ODIN site basics """
import json
import os

from __init__ import db

# The text the website starts with. It is data, so changing the site's wording never means editing code.
SEED_FILE = os.path.join(os.path.dirname(__file__), "dataconfigs", "odin_site.json")

# JSON key (also the column name): max string length
FIELDS = {
    'name': 100,
    'tagline': 255,
    'phone': 40,
    'email': 255,
    'address': 255,
}


class OdinSite(db.Model):
    """
    OdinSite Model

    What every page of the ODIN Diagnostics website shows: the company name, its tagline and how to
    reach it. One row holds them, so the frontend keeps no website text of its own.

    Attributes:
        id (db.Column): The primary key.
        name ... address (db.Column): One column per key in FIELDS.
    """
    __tablename__ = 'odin_site'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    tagline = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(40), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    address = db.Column(db.String(255), nullable=False)

    # Constructor: takes the checked values, one per key in FIELDS
    def __init__(self, values):
        for key in FIELDS:
            setattr(self, key, values[key])

    def __repr__(self):
        return f"OdinSite(id={self.id}, name={self.name})"

    # CRUD create
    def create(self):
        db.session.add(self)
        db.session.commit()
        return self

    # CRUD read: every key in FIELDS
    def read(self):
        return {key: getattr(self, key) for key in FIELDS}

    @staticmethod
    def current():
        """The site's row, or None before the seed has run."""
        return OdinSite.query.order_by(OdinSite.id).first()

    @staticmethod
    def validate(inputs):
        """(values, error) from the seed's JSON. Every key in FIELDS must be text that is not blank and
        fits its column, because MySQL refuses what SQLite would quietly store."""
        if not isinstance(inputs, dict):
            return None, "the site basics must be a JSON object"
        values = {}
        for key, max_len in FIELDS.items():
            value = inputs.get(key)
            if not isinstance(value, str) or not value.strip():
                return None, f"{key} is required"
            value = value.strip()
            if len(value) > max_len:
                return None, f"{key} must be at most {max_len} characters"
            values[key] = value
        return values, None


def initOdinSite(path=SEED_FILE):
    """Creates the site's row from odin_site.json if there is none yet. Returns the number created.
    Safe to run more than once."""
    if OdinSite.current():
        return 0
    with open(path) as f:
        values, error = OdinSite.validate(json.load(f))
    if error:
        raise ValueError(f"{os.path.basename(path)}: {error}")
    OdinSite(values).create()
    return 1
