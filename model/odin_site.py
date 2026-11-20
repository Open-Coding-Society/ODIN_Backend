""" ODIN site basics """
import json
import os
from urllib.parse import urlsplit

from __init__ import db
from model.odin_image import image_file

# The text the website starts with. It is data, so changing the site's wording never means editing code.
SEED_FILE = os.path.join(os.path.dirname(__file__), "dataconfigs", "odin_site.json")

# What a field holds: plain text, a link to another site, or the name of a file in odin/images/
TEXT, LINK, IMAGE = 'text', 'link', 'image'

# JSON key (also the column name): (what it holds, max string length)
FIELDS = {
    'name': (TEXT, 100),
    'tagline': (TEXT, 255),
    'phone': (TEXT, 40),
    'email': (TEXT, 255),
    'address': (TEXT, 255),
    'copyright': (TEXT, 255),
    'instagram': (LINK, 255),
    'linkedin': (LINK, 255),
    'logo_dark': (IMAGE, 100),
    'logo_light': (IMAGE, 100),
}


class OdinSite(db.Model):
    """
    OdinSite Model

    What every page of the ODIN Diagnostics website shows: the company name, its tagline, how to
    reach it, its logos and the lines in the footer. One row holds them, so the frontend reads them
    here instead of keeping a copy.

    Attributes:
        id (db.Column): The primary key.
        name ... logo_light (db.Column): One column per key in FIELDS.
    """
    __tablename__ = 'odin_site'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(FIELDS['name'][1]), nullable=False)
    tagline = db.Column(db.String(FIELDS['tagline'][1]), nullable=False)
    phone = db.Column(db.String(FIELDS['phone'][1]), nullable=False)
    email = db.Column(db.String(FIELDS['email'][1]), nullable=False)
    address = db.Column(db.String(FIELDS['address'][1]), nullable=False)
    # Fields added after the table existed allow NULL, so db_upgrade.py can add them in place. The
    # seed still requires every one of them, and fills them into a row that was saved before.
    copyright = db.Column(db.String(FIELDS['copyright'][1]), nullable=True)
    instagram = db.Column(db.String(FIELDS['instagram'][1]), nullable=True)
    linkedin = db.Column(db.String(FIELDS['linkedin'][1]), nullable=True)
    logo_dark = db.Column(db.String(FIELDS['logo_dark'][1]), nullable=True)
    logo_light = db.Column(db.String(FIELDS['logo_light'][1]), nullable=True)

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

    # CRUD read: every key in FIELDS, None for one this row has no text for
    def read(self):
        return {key: None if key in self.missing() else getattr(self, key) for key in FIELDS}

    def missing(self):
        """The keys this row has no text for: NULL, empty or only spaces."""
        return [key for key in FIELDS if not (getattr(self, key) or '').strip()]

    def fill_missing(self, values):
        """Writes the checked values into the fields this row has no text for, and leaves the rest
        as they are. Returns the keys it filled."""
        filled = self.missing()
        for key in filled:
            setattr(self, key, values[key])
        if filled:
            db.session.commit()
        return filled

    @staticmethod
    def current():
        """The site's row, or None before the seed has run."""
        return OdinSite.query.order_by(OdinSite.id).first()

    @staticmethod
    def validate(inputs):
        """(values, error) from the seed's JSON. Every key in FIELDS must be text that is not blank and
        fits its column, because MySQL refuses what SQLite would quietly store. A link must be a full
        https address and an image must be a file in odin/images/, so the seed refuses one a page
        could not use."""
        if not isinstance(inputs, dict):
            return None, "the site basics must be a JSON object"
        values = {}
        for key, (kind, max_len) in FIELDS.items():
            value = inputs.get(key)
            if value is None:
                return None, f"{key} is required"
            if not isinstance(value, str):
                return None, f"{key} must be text"
            value = value.strip()
            if not value:
                return None, f"{key} is required"
            if len(value) > max_len:
                return None, f"{key} must be at most {max_len} characters"
            if kind == LINK and not _is_https_link(value):
                return None, f"{key} must be a full https link, such as https://example.com/page"
            if kind == IMAGE and image_file(value) is None:
                return None, f"{key} must name an image in odin/images/"
            values[key] = value
        return values, None


def _is_https_link(value):
    """True for an https address that names a site, with no sign-in part and no character that
    could end the address early where a page puts it."""
    if not value.isprintable() or any(c.isspace() or c in '"\'<>\\' for c in value):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return parts.scheme == 'https' and bool(parts.hostname) and '@' not in parts.netloc


def initOdinSite(path=SEED_FILE):
    """Creates the site's row from odin_site.json if there is none yet. If there is one, fills in only
    the fields it has no text for, which is how a field added later reaches a database that already
    exists. Text that is saved is never replaced, and a row with nothing missing is left alone
    without the file being read. Returns the keys it wrote. Safe to run more than once."""
    site = OdinSite.current()
    if site is not None and not site.missing():
        return []
    name = os.path.basename(path)
    try:
        # utf-8 whatever the server's locale is, so accented text is not stored garbled
        with open(path, encoding="utf-8") as f:
            seed = json.load(f)
    except OSError as e:
        raise ValueError(f"{name}: cannot be read ({e.strerror})")
    except ValueError as e:  # text that is not JSON, or not utf-8
        raise ValueError(f"{name}: is not valid JSON ({e})")
    values, error = OdinSite.validate(seed)
    if error:
        raise ValueError(f"{name}: {error}")
    if site is None:
        OdinSite(values).create()
        return list(FIELDS)
    return site.fill_missing(values)
