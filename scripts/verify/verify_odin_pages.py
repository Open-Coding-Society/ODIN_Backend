#!/usr/bin/env python3
"""Verify /api/odin/page, the page sections the ODIN Diagnostics website reads, end to end.

Runs the real app against a throwaway SQLite database and checksums the real dev DB
before and after to prove it was never touched.

Usage:  python scripts/verify/verify_odin_pages.py        (from the flask repo root)
Exit:   0 all checks passed, 1 otherwise.
"""
import contextlib, copy, hashlib, io, json, os, secrets, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("SECRET_KEY", "verify-odin-pages")

REAL_DB = os.path.join(REPO, "instance", "volumes", "user_management.db")
PASSWORD = "Aa1!" + secrets.token_urlsafe(16)
URL = "/api/odin/page"
HOME = URL + "?name=home"
# The home page's sections, in the order the current site shows them
HOME_ORDER = ["hero", "statistics", "features", "how_it_works", "pitch", "fda", "contact"]
FILE = "odin_pages.json: "
_failures = []


def check(label, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + label + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def seed_file(content):
    """A throwaway seed file holding this text, or this value as JSON."""
    path = os.path.join(tempfile.mkdtemp(prefix="odin-seed-"), "odin_pages.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content if isinstance(content, str) else json.dumps(content, ensure_ascii=False))
    return path


def main():
    real_before = sha256(REAL_DB) if os.path.exists(REAL_DB) else None

    import __init__ as pkg
    from sqlalchemy import create_engine
    app, db = pkg.app, pkg.db
    engine = create_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(prefix='odin-'), 'new.db')}")
    with app.app_context():
        db.engines[None] = engine
    import main as flask_main  # registers every model and blueprint
    from model import account_types
    from model.user import User
    from model.odin_section import OdinSection, initOdinSections, FIELDS, ITEM_FIELDS, NAME_MAX, SEED_FILE
    from init_odin_site import seed_sections
    app.config["TESTING"] = True

    with open(SEED_FILE, encoding="utf-8") as fh:
        seed = json.load(fh)

    def as_served(section):
        """One section of a seed file as the route sends it: every part, null for one it does not have."""
        return {"name": section["name"], **{key: section.get(key) for key in FIELDS}, "items": section.get("items", [])}

    def with_section(which, **parts):
        """The real seed with these parts of one home section changed. A part given as None is removed."""
        changed = copy.deepcopy(seed)
        section = next(s for s in changed["home"] if s["name"] == which)
        for key, value in parts.items():
            if value is None:
                section.pop(key, None)
            else:
                section[key] = value
        return changed

    # Each database step opens its own app context and every request is made outside one: Flask-Login
    # keeps the signed-in user on the context, so one left open would carry a login to the next client.
    def rows():
        with app.app_context():
            return OdinSection.query.count()

    def run_seed(content=None):
        with app.app_context():
            return initOdinSections(SEED_FILE if content is None else seed_file(content))

    def clear():
        with app.app_context():
            OdinSection.query.delete()
            db.session.commit()

    def refusal(content):
        """The message a seed with this content is refused with, without the file's name. None when
        it was not refused, the message does not start with the file's name, or a row was saved."""
        try:
            run_seed(content)
        except ValueError as error:
            message = str(error)
            return message[len(FILE):] if message.startswith(FILE) and rows() == 0 else None
        return None

    def served(page="home"):
        return app.test_client().get(f"{URL}?name={page}").get_json()

    def session_client(role):
        """A client signed in through the Flask session login as a new account of this role."""
        uid = "zz_odin_" + role.lower()
        with app.app_context():
            db.session.add(User(name=uid, uid=uid, password=PASSWORD, role=role))
            db.session.commit()
            User.query.filter_by(_uid=uid).first().activate()
        client = app.test_client()
        signed_in = client.post("/login", data={"username": uid, "password": PASSWORD}).status_code == 302
        return client if signed_in else None

    # A database that has not been upgraded has no odin_section table
    with app.app_context():
        db.create_all()
        OdinSection.__table__.drop(db.engine)
    code, message = seed_sections()
    check("init_odin_site.py on a database without the table changes nothing and says to run db_upgrade.py",
          code == 1 and "odin_section" in message and "db_upgrade.py" in message, message)
    with app.app_context():
        db.create_all()
        columns = OdinSection.__table__.columns
        check("each column is as long as FIELDS says, and text has no length of its own",
              all(columns[key].type.length == size for key, (kind, size) in FIELDS.items() if key != "text")
              and isinstance(columns["text"].type, db.Text))
        check("every part of a section allows NULL, because every part is optional",
              all(columns[key].nullable for key in FIELDS))
        check("a page name and a section name are as long as NAME_MAX",
              columns["page"].type.length == NAME_MAX and columns["name"].type.length == NAME_MAX)

    anon = app.test_client()
    r = anon.get(HOME)
    check("GET before the seed has run is a 404 with a message",
          r.status_code == 404 and bool((r.get_json() or {}).get("message")), r.get_json())
    for url in (URL, URL + "?name="):
        r = anon.get(url)
        check(f"GET {url} without a page name is a 400 with a message",
              r.status_code == 400 and bool((r.get_json() or {}).get("message")), r.get_json())

    # The file as a whole
    check("the seed file is in model/dataconfigs/",
          os.path.samefile(os.path.dirname(SEED_FILE), os.path.join(REPO, "model", "dataconfigs")), SEED_FILE)
    for bad in ([seed], {}, "text"):
        check(f"a seed that is {json.dumps(bad)[:12]} and not an object of pages is refused",
              refusal(json.dumps(bad)) == "the pages must be a JSON object with at least one page")
    check("a seed that is not valid JSON is refused, and the message names the file",
          (refusal("{ not json") or "").startswith("is not valid JSON"))
    with app.app_context():
        try:
            initOdinSections(os.path.join(tempfile.mkdtemp(prefix="odin-none-"), "odin_pages.json"))
            unreadable = None
        except ValueError as error:
            unreadable = str(error)
    check("a seed file that cannot be read is refused, and the message names the file",
          (unreadable or "").startswith(FILE + "cannot be read") and rows() == 0, unreadable)

    # Page names and section names
    rule = f"must be lowercase letters, digits and underscores, starting with a letter, at most {NAME_MAX} characters"
    for bad in ("Home", "1home", "home page", "home-page", "", "x" * (NAME_MAX + 1)):
        check(f"the page name {bad[:12]!r} is refused",
              refusal({bad: seed["home"]}) == f"the page name {bad!r} {rule}")
        check(f"the section name {bad[:12]!r} is refused",
              refusal(with_section("hero", name=bad)) == f"home section 1: name is required and {rule}")
    check("a section without a name is refused", refusal(with_section("hero", name=None)) == f"home section 1: name is required and {rule}")
    check("a name of the longest length is accepted",
          run_seed({"x" * NAME_MAX: [{"name": "y" * NAME_MAX, "title": "T"}]}) == ["x" * NAME_MAX + "." + "y" * NAME_MAX])
    clear()
    for bad in ({}, [], "hero", None):
        check(f"a page that is {json.dumps(bad)} and not a list of sections is refused",
              refusal({"home": bad}) == "home must be a list with at least one section")
    check("a section that is not an object is refused", refusal({"home": ["hero"]}) == "home section 1: must be a JSON object")
    twice = {"home": [seed["home"][0], seed["home"][1], seed["home"][0]]}
    check("two sections with one name on a page are refused", refusal(twice) == "home has two sections named hero")
    check("the same section name on two pages is accepted",
          sorted(run_seed({"home": [seed["home"][0]], "about": [seed["home"][0]]})) == ["about.hero", "home.hero"])
    clear()

    # The parts of a section
    check("a key a section does not have is refused, so a misspelled one is not dropped",
          refusal(with_section("hero", titel="ODIN")) == "home section 1: titel is not a part a section has")
    for key, (kind, size) in FIELDS.items():
        where = f"home section 2: {key} "
        check(f"{key}: a value that is not text is refused", refusal(with_section("statistics", **{key: 42})) == where + "must be text")
        check(f"{key}: a blank value is refused", refusal(with_section("statistics", **{key: "   "})) == where + "must not be blank")
        check(f"{key}: a value longer than {size} characters is refused",
              refusal(with_section("statistics", **{key: "x" * (size + 1)})) == where + f"must be at most {size} characters")
    check("text of the longest length is accepted and served whole",
          run_seed({"home": [{"name": "long", "text": "x" * FIELDS["text"][1]}]}) == ["home.long"]
          and served()["sections"][0]["text"] == "x" * FIELDS["text"][1])
    clear()
    for bad in ("http://evonexus.org/", "evonexus.org", "javascript:alert(1)", "https://", "https://user:pass@a.example/", "https://a.example/x y", "#contactus", "/about/"):
        check(f"link: {bad!r} is refused",
              refusal(with_section("contact", link=bad)) == "home section 7: link must be a full https link, such as https://example.com/page")
    for bad in ("missing.svg", "../main.py", "README.md", "PRODUCT-HEADSET.JPG"):
        check(f"image: {bad!r} is refused",
              refusal(with_section("features", image=bad)) == "home section 3: image must name an image in odin/images/")
    together = "home section 3: image and image_alt go together: give both or neither"
    check("an image without its description is refused", refusal(with_section("features", image_alt=None)) == together)
    check("a description without its image is refused", refusal(with_section("features", image=None)) == together)
    nothing = "home section 1: has nothing to show: give it a title, text, an image or items"
    check("a section with only a name is refused", refusal({"home": [{"name": "empty"}]}) == nothing)
    check("a section with only a line above the title and a button is refused",
          refusal({"home": [{"name": "empty", "eyebrow": "Introducing", "action": "Contact Us!", "link": "https://a.example/"}]}) == nothing)
    for key in ("title", "text"):
        check(f"a section with only {key} is accepted", run_seed({"home": [{"name": "one", key: "Words"}]}) == ["home.one"])
        clear()

    # The items of a section
    item = seed["home"][1]["items"][0]
    for bad in ({}, [], "one", 4):
        check(f"items that are {json.dumps(bad)} and not a list of items are refused",
              refusal(with_section("statistics", items=bad)) == "home section 2: items must be a list with at least one item, or be left out")
    check("an item that is not an object is refused",
          refusal(with_section("statistics", items=[item, "50%"])) == "home section 2: item 2 must be a JSON object")
    check("a key an item does not have is refused",
          refusal(with_section("statistics", items=[{**item, "value": "50%"}])) == "home section 2: item 1: value is not a part an item has")
    for key, (kind, size) in ITEM_FIELDS.items():
        where = f"home section 2: item 2: {key} "
        without = {k: v for k, v in item.items() if k != key}
        check(f"an item without {key} is refused", refusal(with_section("statistics", items=[item, without])) == where + "is required")
        check(f"an item whose {key} is not text is refused",
              refusal(with_section("statistics", items=[item, {**item, key: 50}])) == where + "must be text")
        check(f"an item whose {key} is blank is refused",
              refusal(with_section("statistics", items=[item, {**item, key: " "}])) == where + "must not be blank")
        check(f"an item whose {key} is longer than {size} characters is refused",
              refusal(with_section("statistics", items=[item, {**item, key: "x" * (size + 1)}])) == where + f"must be at most {size} characters")

    # All or nothing
    check("a problem on a later page saves nothing from the pages before it",
          refusal({"home": seed["home"], "about": [{"name": "empty"}]}) == "about section 1: has nothing to show: give it a title, text, an image or items")
    with app.app_context():
        pages, error = OdinSection.validate({"home": [{"name": "hero", "title": "  Café ODIN™  ", "items": [{"title": " 50% ", "text": " Of all "}]}]})
    check("spaces around a value are trimmed", error is None and pages["home"][0]["title"] == "Café ODIN™"
          and pages["home"][0]["items"] == [{"title": "50%", "text": "Of all"}], error)
    check("text that is not ASCII is saved and served as written",
          run_seed({"home": [{"name": "hero", "title": "Café ODIN™"}]}) == ["home.hero"] and served()["sections"][0]["title"] == "Café ODIN™")
    clear()

    # The real seed
    code, message = seed_sections()
    check("init_odin_site.py seeds an empty table, and names what it saved",
          code == 0 and rows() == len(seed["home"]) and "home.hero" in message, message)
    code, message = seed_sections()
    check("init_odin_site.py run again changes nothing", code == 0 and rows() == len(seed["home"]) and "Nothing changed" in message, message)
    clear()

    # generate_data is a Flask command. standalone_mode=False makes it return here instead of exiting,
    # and the other seeds print every account they create.
    with app.app_context(), contextlib.redirect_stdout(io.StringIO()):
        flask_main.generate_data(args=[], standalone_mode=False)
    check("generate_data, which db_init.py runs, seeds the page sections", rows() == sum(len(sections) for sections in seed.values()))

    r = anon.get(HOME)
    body = r.get_json()
    check("GET needs no login", r.status_code == 200, r.status_code)
    check("GET returns the page's name and its sections", sorted(body) == ["page", "sections"] and body["page"] == "home", body)
    names = [section["name"] for section in body["sections"]]
    check("the home page's sections come in the order the current site shows them", names == HOME_ORDER, names)
    check("each section has its name, every key in FIELDS and its items, and nothing else",
          all(sorted(section) == sorted(["name", "items", *FIELDS]) for section in body["sections"]))
    check("GET returns what odin_pages.json holds, with null for a part a section does not have",
          body["sections"] == [as_served(section) for section in seed["home"]], body)
    check("a section without a list has an empty list of items", body["sections"][0]["items"] == [])
    images = [section["image"] for section in body["sections"] if section["image"]]
    check("every image a section names is one the image route serves",
          bool(images) and all(anon.get(f"/api/odin/image?name={image}").status_code == 200 for image in images), images)
    for page in ("missing", "Home", "home ", "home' OR '1'='1", "x" * 500):
        r = anon.get(URL, query_string={"name": page})
        check(f"GET for the page {page[:16]!r}, which does not exist, is a 404 with a message",
              r.status_code == 404 and bool((r.get_json() or {}).get("message")), r.status_code)

    # Seeding a database that already has sections
    check("running the seed again writes nothing", run_seed() == [] and rows() == len(seed["home"]) and served() == body)
    check("a later seed file does not replace text that is saved",
          run_seed(with_section("hero", title="Another Title", text="Another line.")) == [] and served() == body)
    later = with_section("hero", image="product-headset.jpg", image_alt="The headset")
    written = run_seed(later)
    hero = served()["sections"][0]
    check("a part added to the file later is filled in, and names what was filled",
          written == ["home.hero.image", "home.hero.image_alt"] and hero == as_served(later["home"][0]), f"{written} {hero}")
    with app.app_context():
        saved = OdinSection.query.filter_by(page="home", name="statistics").first()
        saved.items, saved.title = [], "  "
        db.session.commit()
    check("a section with no items yet is served with an empty list", served()["sections"][1]["items"] == [])
    written = run_seed()
    check("the seed fills in items and blank text a saved section has none of",
          written == ["home.statistics.title", "home.statistics.items"] and served()["sections"][1] == body["sections"][1], written)

    extra = {"name": "extra", "title": "Added later"}
    reordered = {"home": [seed["home"][0], extra, *seed["home"][1:]]}
    written = run_seed(reordered)
    names = [section["name"] for section in served()["sections"]]
    check("a section added in the middle of the file later takes that place on the page",
          written == ["home.extra"] and names == ["hero", "extra", *HOME_ORDER[1:]], f"{written} {names}")
    written = run_seed()
    names = [section["name"] for section in served()["sections"]]
    check("a saved section the file no longer has is kept, after the ones that share its place",
          written == [] and sorted(names) == sorted(HOME_ORDER + ["extra"]) and names.index("extra") == 2, f"{written} {names}")
    with app.app_context():
        OdinSection.query.filter_by(name="extra").delete()
        hero_row = OdinSection.query.filter_by(page="home", name="hero").first()
        hero_row.image = hero_row.image_alt = None
        db.session.commit()
    check("the checks above left the home page as the file has it", served() == body)

    check("a second page is saved beside the first, and each is served by its own name",
          run_seed({**seed, "about": [{"name": "mission", "title": "Our mission"}]}) == ["about.mission"]
          and served("about") == {"page": "about", "sections": [as_served({"name": "mission", "title": "Our mission"})]}
          and served() == body)

    for method in ("post", "put", "patch", "delete"):
        r = getattr(anon, method)(HOME, json={"name": "hero", "title": "x"})
        check(f"{method.upper()} is not allowed", r.status_code == 405, r.status_code)
    check("a refused write changed nothing", served() == body)

    # A guest may make only the requests its account type lists, and the public site is one of them
    for role in account_types.guest_roles() + ("User",):
        client = session_client(role)
        check(f"a visitor signed in as a {role} still gets the page's sections",
              client is not None and client.get(HOME).status_code == 200,
              "could not sign in" if client is None else client.get(HOME).get_json())
    check("a signed-in client did not sign the next visitor in", app.test_client().get("/api/id").status_code == 401)

    real_after = sha256(REAL_DB) if os.path.exists(REAL_DB) else None
    check("the real dev database was not touched", real_before == real_after)

    print(f"\n{'ALL PASSED' if not _failures else f'{len(_failures)} FAILED'}")
    return 0 if not _failures else 1


if __name__ == "__main__":
    sys.exit(main())
