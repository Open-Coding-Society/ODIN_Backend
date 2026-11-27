""" ODIN pages """
import os

from __init__ import db
from model.odin_seed import NAME_MAX, NAME_RULE, TEXT, checked_value, is_name, load_seed

# The pages the website starts with. They are data, so a page's title or its place in the menu
# never comes from code.
SEED_FILE = os.path.join(os.path.dirname(__file__), "dataconfigs", "odin_page_list.json")

# What a page says about itself. JSON key (also the column name): (what it holds, max length)
FIELDS = {
    'title': (TEXT, 100),        # the page's name in the browser tab
    'description': (TEXT, 255),  # one line about the page, for search results and link previews
    'menu': (TEXT, 40),          # the page's words in the site menu; a page without them is not in it
}
REQUIRED = ('title',)


class OdinPage(db.Model):
    """
    OdinPage Model

    One page of the ODIN Diagnostics website: what it is called, the line that describes it and
    its words in the site menu. The frontend knows each page's address and reads the rest here.
    The page's sections are OdinSection rows with the same page name.

    Attributes:
        id (db.Column): The primary key.
        name (db.Column): The page's name, which no other page has, such as home.
        position (db.Column): Where the page comes in the menu, counting from 0.
        title ... menu (db.Column): One column per key in FIELDS.
    """
    __tablename__ = 'odin_page'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(NAME_MAX), unique=True, nullable=False)
    position = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(FIELDS['title'][1]), nullable=False)
    description = db.Column(db.String(FIELDS['description'][1]), nullable=True)
    menu = db.Column(db.String(FIELDS['menu'][1]), nullable=True)

    # Constructor: takes the place in the menu and one page's checked values
    def __init__(self, position, values):
        self.position = position
        self.name = values['name']
        for key in FIELDS:
            setattr(self, key, values[key])

    def __repr__(self):
        return f"OdinPage(id={self.id}, name={self.name})"

    # CRUD read: the name and every key in FIELDS, None for one the page has nothing for
    def read(self):
        missing = self.missing()
        return {'name': self.name, **{key: None if key in missing else getattr(self, key) for key in FIELDS}}

    def missing(self):
        """The keys this page has no text for: NULL, empty or only spaces."""
        return [key for key in FIELDS if not (getattr(self, key) or '').strip()]

    def fill_missing(self, values):
        """Writes the checked values into the keys this page has no text for, and leaves the rest
        as they are. Returns the keys it filled. The caller commits."""
        filled = [key for key in self.missing() if values[key] is not None]
        for key in filled:
            setattr(self, key, values[key])
        return filled

    @staticmethod
    def listed():
        """Every page, in menu order. Empty before the seed has run."""
        return OdinPage.query.order_by(OdinPage.position, OdinPage.id).all()

    @staticmethod
    def named(name):
        """The page with this name, or None."""
        return OdinPage.query.filter_by(name=name).first()

    @staticmethod
    def validate(inputs):
        """(pages, error) from the seed's JSON, which is a list of pages in menu order. Each needs
        a name of its own and a title. A key the model does not have is refused, so a misspelled
        one is not dropped without a word."""
        if not isinstance(inputs, list) or not inputs:
            return None, "the pages must be a JSON list with at least one page"
        pages = []
        for number, page in enumerate(inputs, start=1):
            values, problem = _checked_page(page)
            if problem:
                return None, f"page {number}: {problem}"
            if any(values['name'] == other['name'] for other in pages):
                return None, f"two pages are named {values['name']}"
            pages.append(values)
        return pages, None


def _checked_page(page):
    """(values, problem) for one page of the seed: its name and every key in FIELDS."""
    if not isinstance(page, dict):
        return None, "must be a JSON object"
    if page.get('name') is None:
        return None, "name is required"
    if not is_name(page['name']):
        return None, f"name {NAME_RULE}"
    unknown = sorted(set(page) - {'name', *FIELDS})
    if unknown:
        return None, f"a page has no key named {unknown[0]}"
    values = {'name': page['name']}
    for key, (kind, max_len) in FIELDS.items():
        if page.get(key) is None:
            if key in REQUIRED:
                return None, f"{key} is required"
            values[key] = None
            continue
        values[key], problem = checked_value(page[key], kind, max_len)
        if problem:
            return None, f"{key} {problem}"
    return values, None


def initOdinPages(path=SEED_FILE):
    """Seeds the pages in odin_page_list.json. Adds the ones the database does not have, fills the
    keys a saved page has no text for, and puts the pages in the file's order. A saved page the
    file no longer has is kept, after the file's pages. Saved text is never replaced. All of it is
    saved, or none. Returns what it wrote: the name of a new page, and name.key for a filled key or
    a changed position."""
    pages, error = OdinPage.validate(load_seed(path))
    if error:
        raise ValueError(f"{os.path.basename(path)}: {error}")
    saved = {page.name: page for page in OdinPage.listed()}
    written = []
    for position, values in enumerate(pages):
        page = saved.get(values['name'])
        if page is None:
            db.session.add(OdinPage(position, values))
            written.append(values['name'])
            continue
        changed = page.fill_missing(values)
        if page.position != position:
            page.position = position
            changed.append('position')
        written.extend(f"{page.name}.{key}" for key in changed)
    # A page the file no longer has would keep its old place, which could put it ahead of the
    # file's first page. Each goes after the file's pages, in the order they had.
    listed = {values['name'] for values in pages}
    for position, page in enumerate((page for page in saved.values() if page.name not in listed), start=len(pages)):
        if page.position != position:
            page.position = position
            written.append(f"{page.name}.position")
    try:
        db.session.commit()
    except Exception:
        # Whatever uses the session next must not find this seed half done in it
        db.session.rollback()
        raise
    return written
