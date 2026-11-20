""" ODIN page sections """
import os
import re

from __init__ import db
from model import odin_site
from model.odin_seed import IMAGE, LINK, TEXT, checked_value, load_seed

# The sections each page of the website starts with. They are data, so the wording a new database
# gets never comes from code.
SEED_FILE = os.path.join(os.path.dirname(__file__), "dataconfigs", "odin_pages.json")

# A page's name and a section's name, such as how_it_works
NAME_MAX = 40
NAME_PATTERN = re.compile(r'[a-z][a-z0-9_]*')
NAME_RULE = f"must be at most {NAME_MAX} lowercase letters, digits and underscores, and start with a letter"

# The parts a section can have, all optional. JSON key (also the column name): (what it holds, max length)
FIELDS = {
    'kicker': (TEXT, 100),     # the short line above the title
    'title': (TEXT, 255),
    'text': (TEXT, 4000),
    'action': (TEXT, 100),     # the words on the section's button
    'image': (IMAGE, 100),
    'image_alt': (TEXT, 255),  # what the image shows, for a visitor who cannot see it
    'link': (LINK, 255),       # the other site the section's image leads to
}

# The parts of one item in a section's list, such as one statistic or one feature. An item has a
# title and one of two things under it: text of its own, or `field`, the name of the site basic it
# shows. A contact detail uses `field`, so the phone number is kept in one place.
ITEM_FIELDS = {
    'title': (TEXT, 100),
    'text': (TEXT, 500),
}
SITE_FIELD = 'field'
# The site basics an item can show: the ones that are plain text
SITE_TEXT_FIELDS = [key for key, (kind, max_len) in odin_site.FIELDS.items() if kind == TEXT]


def is_name(value):
    """True for text that can name a page or a section."""
    return isinstance(value, str) and len(value) <= NAME_MAX and NAME_PATTERN.fullmatch(value) is not None


class OdinSection(db.Model):
    """
    OdinSection Model

    One section of one page of the ODIN Diagnostics website, such as the home page's hero or its
    list of features. The frontend reads a page's sections here instead of keeping a copy.

    Attributes:
        id (db.Column): The primary key.
        page (db.Column): The page the section is on, such as home.
        name (db.Column): The section's name, which no other section of the page has, such as hero.
        position (db.Column): Where the section comes on its page, counting from 0.
        kicker ... link (db.Column): One column per key in FIELDS.
        items (db.Column): The section's list, each item holding the keys in ITEM_FIELDS and SITE_FIELD.
    """
    __tablename__ = 'odin_section'
    __table_args__ = (db.UniqueConstraint('page', 'name', name='uq_odin_section_page_name'),)

    id = db.Column(db.Integer, primary_key=True)
    page = db.Column(db.String(NAME_MAX), nullable=False)
    name = db.Column(db.String(NAME_MAX), nullable=False)
    position = db.Column(db.Integer, nullable=False)
    kicker = db.Column(db.String(FIELDS['kicker'][1]), nullable=True)
    title = db.Column(db.String(FIELDS['title'][1]), nullable=True)
    # Text has no length of its own in the database. The seed holds it to FIELDS['text'].
    text = db.Column(db.Text, nullable=True)
    action = db.Column(db.String(FIELDS['action'][1]), nullable=True)
    image = db.Column(db.String(FIELDS['image'][1]), nullable=True)
    image_alt = db.Column(db.String(FIELDS['image_alt'][1]), nullable=True)
    link = db.Column(db.String(FIELDS['link'][1]), nullable=True)
    items = db.Column(db.JSON, nullable=False)

    # Constructor: takes the page, the place on it, and one section's checked values
    def __init__(self, page, position, values):
        self.page = page
        self.position = position
        self.name = values['name']
        for key in FIELDS:
            setattr(self, key, values[key])
        self.items = values['items']

    def __repr__(self):
        return f"OdinSection(id={self.id}, page={self.page}, name={self.name})"

    # CRUD read: the name, every key in FIELDS (None for a part the section has nothing for) and the
    # items, each with the same keys whenever it was saved
    def read(self):
        missing = self.missing()
        parts = {key: None if key in missing else getattr(self, key) for key in FIELDS}
        items = [{key: item.get(key) for key in (*ITEM_FIELDS, SITE_FIELD)} for item in self.items or []]
        return {'name': self.name, **parts, 'items': items}

    def missing(self):
        """The parts this section has nothing for: NULL, empty or only spaces."""
        return [key for key in FIELDS if not (getattr(self, key) or '').strip()]

    def fill_missing(self, values):
        """Writes the checked values into the parts this section has nothing for, and leaves the
        rest as they are. Returns the keys it filled. The caller commits."""
        missing = self.missing()
        # A description belongs to its own image. When only one of the two is saved, the other is
        # filled only if the file still names the saved image.
        if ('image' in missing) != ('image_alt' in missing) and self.image != values['image']:
            missing = [key for key in missing if key not in ('image', 'image_alt')]
        filled = [key for key in missing if values[key] is not None]
        for key in filled:
            setattr(self, key, values[key])
        if not self.items and values['items']:
            self.items = values['items']
            filled.append('items')
        return filled

    @staticmethod
    def for_page(page):
        """The page's sections in the order the page shows them. Empty for a page with none."""
        return OdinSection.query.filter_by(page=page).order_by(OdinSection.position, OdinSection.id).all()

    @staticmethod
    def validate(inputs):
        """(pages, error) from the seed's JSON, which is {page name: [section, ...]}. Each section
        needs a name of its own on the page, and something to show. A part the model does not have
        is refused, so a misspelled one is not dropped without a word."""
        if not isinstance(inputs, dict) or not inputs:
            return None, "the pages must be a JSON object with at least one page"
        pages = {}
        for page, sections in inputs.items():
            if not is_name(page):
                return None, f"the page name {page!r} {NAME_RULE}"
            if not isinstance(sections, list) or not sections:
                return None, f"{page} must be a list with at least one section"
            checked = []
            for number, section in enumerate(sections, start=1):
                values, problem = _checked_section(section)
                if problem:
                    return None, f"{page} section {number}: {problem}"
                if any(values['name'] == other['name'] for other in checked):
                    return None, f"{page} has two sections named {values['name']}"
                checked.append(values)
            pages[page] = checked
        return pages, None


def _checked_section(section):
    """(values, problem) for one section of the seed: its name, every key in FIELDS and its items."""
    if not isinstance(section, dict):
        return None, "must be a JSON object"
    if section.get('name') is None:
        return None, "name is required"
    if not is_name(section['name']):
        return None, f"name {NAME_RULE}"
    unknown = sorted(set(section) - {'name', 'items', *FIELDS})
    if unknown:
        return None, f"a section has no part named {unknown[0]}"
    values = {'name': section['name']}
    for key, (kind, max_len) in FIELDS.items():
        if section.get(key) is None:
            values[key] = None
            continue
        values[key], problem = checked_value(section[key], kind, max_len)
        if problem:
            return None, f"{key} {problem}"
    if (values['image'] is None) != (values['image_alt'] is None):
        return None, "image needs image_alt, and image_alt needs image"
    values['items'], problem = _checked_items(section.get('items'))
    if problem:
        return None, problem
    if not (values['title'] or values['text'] or values['image'] or values['items']):
        return None, "needs a title, text, an image or items"
    return values, None


def _checked_items(items):
    """(items, problem) for a section's list. A section without one has an empty list."""
    if items is None:
        return [], None
    if not isinstance(items, list) or not items:
        return None, "items must be a list with at least one item, or be left out"
    checked = []
    for number, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            return None, f"item {number} must be a JSON object"
        unknown = sorted(set(item) - {*ITEM_FIELDS, SITE_FIELD})
        if unknown:
            return None, f"item {number}: an item has no part named {unknown[0]}"
        if item.get('title') is None:
            return None, f"item {number}: title is required"
        if (item.get('text') is None) == (item.get(SITE_FIELD) is None):
            return None, f"item {number}: give text or {SITE_FIELD}, one of the two"
        values = {key: None for key in (*ITEM_FIELDS, SITE_FIELD)}
        for key, (kind, max_len) in ITEM_FIELDS.items():
            if item.get(key) is None:
                continue
            values[key], problem = checked_value(item[key], kind, max_len)
            if problem:
                return None, f"item {number}: {key} {problem}"
        if item.get(SITE_FIELD) is not None:
            if item[SITE_FIELD] not in SITE_TEXT_FIELDS:
                return None, f"item {number}: {SITE_FIELD} must be one of the site basics: {', '.join(SITE_TEXT_FIELDS)}"
            values[SITE_FIELD] = item[SITE_FIELD]
        checked.append(values)
    return checked, None


def initOdinSections(path=SEED_FILE):
    """Seeds the sections in odin_pages.json. Adds the ones the database does not have, fills the
    parts a saved section has nothing for, and puts each page in the file's order. Saved text is
    never replaced. All of it is saved, or none. Returns what it wrote: page.section for a new
    section, and page.section.part for a filled part or a changed position."""
    pages, error = OdinSection.validate(load_seed(path))
    if error:
        raise ValueError(f"{os.path.basename(path)}: {error}")
    written = []
    for page, sections in pages.items():
        saved = {section.name: section for section in OdinSection.for_page(page)}
        for position, values in enumerate(sections):
            section = saved.get(values['name'])
            if section is None:
                db.session.add(OdinSection(page, position, values))
                written.append(f"{page}.{values['name']}")
                continue
            changed = section.fill_missing(values)
            if section.position != position:
                section.position = position
                changed.append('position')
            written.extend(f"{page}.{section.name}.{key}" for key in changed)
    try:
        db.session.commit()
    except Exception:
        # Whatever uses the session next must not find this seed half done in it
        db.session.rollback()
        raise
    return written
