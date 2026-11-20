#!/usr/bin/env python3
"""Verify /api/odin/page, the page sections the ODIN Diagnostics website reads, end to end.

Runs the real app against a throwaway SQLite database and checksums the real dev DB
before and after to prove it was never touched.

Usage:  python scripts/verify/verify_odin_pages.py        (from the flask repo root)
Exit:   0 all checks passed, 1 otherwise.
"""
import contextlib, copy, hashlib, io, json, os, secrets, sys, tempfile
from unittest import mock

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
HOME_ORDER = ["hero", "statistics", "features", "how_it_works", "pitch", "fda"]
# The About page's sections, in the same way, and how many people its team has
ABOUT_ORDER = ["intro", "mission", "team"]
TEAM_SIZE = 4
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
    from sqlalchemy.exc import IntegrityError
    app, db = pkg.app, pkg.db
    engine = create_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(prefix='odin-'), 'new.db')}")
    with app.app_context():
        db.engines[None] = engine
    import main as flask_main  # registers every model and blueprint
    import init_odin_site
    from model import account_types
    from model.user import User
    from model.odin_section import OdinSection, initOdinSections, FIELDS, ITEM_REQUIRED_FIELDS, ITEM_OPTIONAL_FIELDS, NAME_MAX, SEED_FILE
    app.config["TESTING"] = True

    with open(SEED_FILE, encoding="utf-8") as fh:
        seed = json.load(fh)

    def as_served(section):
        """One section of a seed file as the route sends it: every part, null for one it does not have."""
        return {"name": section["name"], **{key: section.get(key) for key in FIELDS}, "items": section.get("items", [])}

    total = sum(len(sections) for sections in seed.values())

    def place(name):
        """Where a section comes in the real seed's home page, counting from 1 as the messages do."""
        return [section["name"] for section in seed["home"]].index(name) + 1

    def with_section(which, **parts):
        """The real seed with these parts of one home section changed. A part given as None is removed."""
        changed = copy.deepcopy(seed)
        section = changed["home"][place(which) - 1]
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
        """How a seed with this content was refused: the message after the file's name. When it was
        not refused cleanly, the words say what happened instead, so a failed check shows why."""
        try:
            written = run_seed(content)
        except ValueError as error:
            message = str(error)
            if not message.startswith(FILE):
                return f"refused without the file's name: {message}"
            return message[len(FILE):] if rows() == 0 else f"refused, but {rows()} rows were saved"
        clear()  # so a seed that was wrongly accepted does not fail the checks after it too
        return f"not refused, wrote {written}"

    def refused(label, content, expected):
        got = refusal(content)
        check(label, got == expected, got)

    def accepted(content):
        """What seeding this content wrote, or the refusal as text, so a check that expects it to be
        accepted fails with the reason and the script carries on."""
        try:
            return run_seed(content)
        except ValueError as error:
            return f"refused: {error}"

    def served(page="home"):
        return app.test_client().get(f"{URL}?name={page}").get_json()

    def order():
        return [section["name"] for section in served()["sections"]]

    def saved(name):
        return OdinSection.query.filter_by(page="home", name=name).first()

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

    # A database that has not been upgraded has no odin_section table, or an older one
    with app.app_context():
        db.create_all()
        OdinSection.__table__.drop(db.engine)
    code, message = init_odin_site.seed_sections()
    check("init_odin_site.py on a database without the table says to run db_upgrade.py",
          code == 1 and "odin_section" in message and "db_upgrade.py" in message, message)
    with app.app_context():
        db.session.execute(db.text("CREATE TABLE odin_section (id INTEGER NOT NULL PRIMARY KEY, page VARCHAR(40) NOT NULL, "
                                   "name VARCHAR(40) NOT NULL, position INTEGER NOT NULL, title VARCHAR(255), items JSON NOT NULL)"))
        db.session.commit()
    code, message = init_odin_site.seed_sections()
    with app.app_context():
        saved_rows = db.session.execute(db.text("SELECT count(*) FROM odin_section")).scalar()
    check("init_odin_site.py on a table without some columns names them, says to run db_upgrade.py and saves nothing",
          code == 1 and "db_upgrade.py" in message and all(key in message for key in FIELDS if key != "title")
          and "title" not in message and saved_rows == 0, message)
    with app.app_context():
        db.session.remove()
        OdinSection.__table__.drop(db.engine)
        db.create_all()
        columns = OdinSection.__table__.columns
        check("text has no length of its own in the database", isinstance(columns["text"].type, db.Text))
        check("every part of a section allows NULL, because every part is optional",
              all(columns[key].nullable for key in FIELDS))
        check("a section's items, name, page and position do not allow NULL",
              not any(columns[key].nullable for key in ("items", "name", "page", "position")))
        first = {"name": "hero", **{key: None for key in FIELDS}, "title": "One", "items": []}
        db.session.add(OdinSection("home", 0, first))
        db.session.commit()
        db.session.add(OdinSection("home", 1, first))
        try:
            db.session.commit()
            refused_twice = False
        except IntegrityError:
            db.session.rollback()
            refused_twice = True
        check("the database refuses a second section with the same page and name", refused_twice and OdinSection.query.count() == 1)
    clear()

    anon = app.test_client()
    r = anon.get(HOME)
    check("GET before the seed has run is a 404 with a message",
          r.status_code == 404 and bool((r.get_json() or {}).get("message")), r.get_json())
    for url in (URL, URL + "?name="):
        r = anon.get(url)
        body = r.get_json() or {}
        check(f"GET {url} without a page name is a 400 with a message and the field it is about",
              r.status_code == 400 and bool(body.get("message")) and body.get("errors") == {"name": "is required"}, body)

    # The file as a whole
    check("the seed file is in model/dataconfigs/",
          os.path.samefile(os.path.dirname(SEED_FILE), os.path.join(REPO, "model", "dataconfigs")), SEED_FILE)
    for label, bad in (("a list", [seed]), ("an object with no pages", {}), ("text", "home")):
        refused(f"a seed that is {label} is refused", json.dumps(bad), "the pages must be a JSON object with at least one page")
    got = refusal("{ not json")
    check("a seed that is not valid JSON is refused, and the message names the file", got.startswith("is not valid JSON"), got)
    got = refusal("[" * 100000)
    check("a seed nested too deep to read is refused the same way", got.startswith("is not valid JSON"), got)
    refused("a page given twice is refused, so neither copy is dropped",
            '{"home": [{"name": "a", "title": "A"}], "home": [{"name": "b", "title": "B"}]}', 'gives the key "home" twice in one object')
    refused("a part given twice in one section is refused",
            '{"home": [{"name": "a", "title": "A", "title": "B"}]}', 'gives the key "title" twice in one object')
    with app.app_context():
        try:
            initOdinSections(os.path.join(tempfile.mkdtemp(prefix="odin-none-"), "odin_pages.json"))
            unreadable = "not refused"
        except ValueError as error:
            unreadable = str(error)
    check("a seed file that cannot be read is refused, and the message names the file",
          unreadable.startswith(FILE + "cannot be read") and rows() == 0, unreadable)

    # Page names and section names
    rule = f"must be at most {NAME_MAX} lowercase letters, digits and underscores, and start with a letter"
    for bad in ("Home", "1home", "home page", "home-page", "", "x" * (NAME_MAX + 1)):
        refused(f"the page name {bad[:12]!r} is refused", {bad: seed["home"]}, f"the page name {bad!r} {rule}")
        refused(f"the section name {bad[:12]!r} is refused", with_section("hero", name=bad), f"home section {place('hero')}: name {rule}")
    refused("a section name that is not text is refused", with_section("hero", name=5), f"home section {place('hero')}: name {rule}")
    refused("a section without a name is refused", with_section("hero", name=None), f"home section {place('hero')}: name is required")
    longest = {"x" * NAME_MAX: [{"name": "y" * NAME_MAX, "title": "T"}]}
    check("a page name and a section name of the longest length are accepted and served",
          run_seed(longest) == ["x" * NAME_MAX + "." + "y" * NAME_MAX] and served("x" * NAME_MAX)["sections"][0]["name"] == "y" * NAME_MAX)
    clear()
    for label, bad in (("an object", {}), ("an empty list", []), ("text", "hero"), ("null", None)):
        refused(f"a page that is {label} is refused", {"home": bad}, "home must be a list with at least one section")
    refused("a section that is not an object is refused", {"home": ["hero"]}, "home section 1: must be a JSON object")
    refused("two sections with one name on a page are refused",
            {"home": [seed["home"][0], seed["home"][1], seed["home"][0]]}, f"home has two sections named {seed['home'][0]['name']}")
    check("the same section name on two pages is accepted",
          sorted(run_seed({"home": [seed["home"][0]], "about": [seed["home"][0]]})) == ["about.hero", "home.hero"])
    clear()

    # The parts of a section
    stats = f"home section {place('statistics')}: "
    refused("a part a section does not have is refused, so a misspelled one is not dropped",
            with_section("statistics", titel="ODIN"), stats + "a section has no part named titel")
    for key, (kind, size) in FIELDS.items():
        refused(f"{key}: a value that is not text is refused", with_section("statistics", **{key: 42}), stats + f"{key} must be text")
        refused(f"{key}: a blank value is refused", with_section("statistics", **{key: "   "}), stats + f"{key} must not be blank")
        refused(f"{key}: a value longer than {size} characters is refused",
                with_section("statistics", **{key: "x" * (size + 1)}), stats + f"{key} must be at most {size} characters")
    refused("a value of only a character that does not show is refused as blank",
            with_section("statistics", title="​"), stats + "title must not be blank")
    refused("a value with half of a character pair is refused before the database sees it",
            json.dumps(with_section("statistics", title="broken \ud83d")), stats + "title has a broken character that cannot be saved")
    fullest = {"name": "full", **{key: "x" * size for key, (kind, size) in FIELDS.items() if kind == "text" and key != "image_alt"}}
    check("every text part of the longest length is accepted and served whole",
          run_seed({"home": [fullest]}) == ["home.full"] and served()["sections"][0] == as_served(fullest))
    clear()
    features = f"home section {place('features')}: "
    for bad in ("missing.svg", "../main.py", "README.md", "PRODUCT-HEADSET.JPG"):
        refused(f"image: {bad!r} is refused", with_section("features", image=bad), features + "image must name an image in odin/images/")
    refused("an image without its description is refused", with_section("features", image_alt=None), features + "image needs image_alt, and image_alt needs image")
    refused("a description without its image is refused", with_section("features", image=None), features + "image needs image_alt, and image_alt needs image")
    for bad in ("http://evonexus.org/", "evonexus.org", "javascript:alert(1)", "https://", "https://user:pass@a.example/", "https://a.example/x y",
                "https://a.example:abc/", "https://a.example:99999/", "#contact", "/about/"):
        refused(f"link: {bad!r} is refused", with_section("features", link=bad),
                features + "link must be a full https link, such as https://example.com/page")
    refused("a link on a section with no image is refused", with_section("statistics", link="https://a.example/"), stats + "link needs image")
    refused("a section with only a name is refused", {"home": [{"name": "empty"}]}, "home section 1: needs a title, text, an image or items")
    refused("a section with only a line above the title and a button is refused",
            {"home": [{"name": "empty", "kicker": "Introducing", "action": "Contact Us!"}]}, "home section 1: needs a title, text, an image or items")
    for key in ("title", "text"):
        check(f"a section with only {key} is accepted", run_seed({"home": [{"name": "one", key: "Words"}]}) == ["home.one"])
        clear()

    # The items of a section
    item = seed["home"][place("statistics") - 1]["items"][0]
    for label, bad in (("an object", {}), ("an empty list", []), ("text", "one"), ("a number", 4)):
        refused(f"items that are {label} are refused", with_section("statistics", items=bad),
                stats + "items must be a list with at least one item, or be left out")
    refused("an item that is not an object is refused", with_section("statistics", items=[item, "50%"]), stats + "item 2 must be a JSON object")
    refused("a part an item does not have is refused",
            with_section("statistics", items=[{**item, "value": "50%"}]), stats + "item 1: an item has no part named value")
    for key, (kind, size) in ITEM_REQUIRED_FIELDS.items():
        without = {k: v for k, v in item.items() if k != key}
        refused(f"an item without {key} is refused", with_section("statistics", items=[item, without]), stats + f"item 2: {key} is required")
        refused(f"an item whose {key} is not text is refused",
                with_section("statistics", items=[item, {**item, key: 50}]), stats + f"item 2: {key} must be text")
        refused(f"an item whose {key} is blank is refused",
                with_section("statistics", items=[item, {**item, key: " "}]), stats + f"item 2: {key} must not be blank")
        refused(f"an item whose {key} is longer than {size} characters is refused",
                with_section("statistics", items=[item, {**item, key: "x" * (size + 1)}]), stats + f"item 2: {key} must be at most {size} characters")

    # The parts an item can also have, such as a team member's role, photo and profile
    for key, (kind, size) in ITEM_OPTIONAL_FIELDS.items():
        refused(f"an item whose {key} is not text is refused",
                with_section("statistics", items=[item, {**item, key: 50}]), stats + f"item 2: {key} must be text")
        refused(f"an item whose {key} is blank is refused",
                with_section("statistics", items=[item, {**item, key: " "}]), stats + f"item 2: {key} must not be blank")
        refused(f"an item whose {key} is longer than {size} characters is refused",
                with_section("statistics", items=[item, {**item, key: "x" * (size + 1)}]), stats + f"item 2: {key} must be at most {size} characters")
    pair = stats + "item 1: image needs image_alt, and image_alt needs image"
    refused("an item with an image and no description is refused", with_section("statistics", items=[{**item, "image": "product-headset.jpg"}]), pair)
    refused("an item with a description and no image is refused", with_section("statistics", items=[{**item, "image_alt": "The headset"}]), pair)
    refused("an item whose image is not in odin/images/ is refused",
            with_section("statistics", items=[{**item, "image": "missing.webp", "image_alt": "Nobody"}]), stats + "item 1: image must name an image in odin/images/")
    refused("an item whose link is not a full https address is refused",
            with_section("statistics", items=[{**item, "link": "www.linkedin.com/in/someone"}]),
            stats + "item 1: link must be a full https link, such as https://example.com/page")
    person = {"title": "A PERSON", "subtitle": "Their role", "note": "First degree\nSecond degree", "text": "About them.",
              "image": "product-headset.jpg", "image_alt": "A person, their role", "link": "https://profiles.example/a-person"}
    check("an item is saved and served with the parts it was given, and no others",
          accepted({"home": [{"name": "team", "items": [person, item]}]}) == ["home.team"]
          and served()["sections"][0]["items"] == [person, item])
    clear()
    check("an item can have a link and no image, as a person without a photo does",
          accepted({"home": [{"name": "team", "items": [{"title": "A PERSON", "text": "About them.", "link": "https://profiles.example/a-person"}]}]}) == ["home.team"])
    clear()
    padded = {**person, "subtitle": "  Their role  ", "note": "\n First degree\nSecond degree \n", "image_alt": " A person, their role ", "link": " https://profiles.example/a-person "}
    check("spaces around an item's other parts are trimmed, and a line break inside a note is kept",
          accepted({"home": [{"name": "team", "items": [padded]}]}) == ["home.team"] and served()["sections"][0]["items"] == [person])
    clear()
    check("a part of an item given as null is left out, the same as one not given",
          accepted({"home": [{"name": "team", "items": [{**item, "subtitle": None, "image": None, "image_alt": None}]}]}) == ["home.team"]
          and served()["sections"][0]["items"] == [item])
    clear()
    refused("an item whose other part is empty text is refused, not dropped",
            with_section("statistics", items=[{**item, "subtitle": ""}]), stats + "item 1: subtitle must not be blank")
    for label, bad in (("a NUL", "a\u0000b"), ("an escape character", "a\u001bb"), ("a character that turns the text around", "a\u202eb"), ("a carriage return", "a\rb")):
        refused(f"text with {label} in it is refused", with_section("statistics", items=[{**item, "note": bad}]),
                stats + "item 1: note has a character that does not show, such as a control character")
    check("text with a tab in it is accepted", accepted({"home": [{"name": "team", "items": [{**item, "note": "one\ttwo"}]}]}) == ["home.team"])
    clear()

    # All or nothing
    refused("a problem on a later page saves nothing from the pages before it",
            {"home": seed["home"], "about": [{"name": "empty"}]}, "about section 1: needs a title, text, an image or items")
    # A database error on the second page, made by hiding the saved row from the seed so it adds it again
    check("a second page is saved beside the first", run_seed({"about": [{"name": "mission", "title": "Our mission"}]}) == ["about.mission"])
    real_for_page = OdinSection.for_page
    with app.app_context():
        with mock.patch.object(OdinSection, "for_page", staticmethod(lambda page: [] if page == "about" else real_for_page(page))):
            try:
                initOdinSections(seed_file({"home": seed["home"], "about": [{"name": "mission", "title": "Our mission"}]}))
                failed = False
            except IntegrityError:
                failed = True
        usable = OdinSection.query.count()
    check("a database error on a later page saves nothing from the pages before it, and leaves the session usable",
          failed and usable == 1 and rows() == 1, f"failed={failed} rows={rows()}")
    clear()
    with app.app_context():
        pages, error = OdinSection.validate({"home": [{"name": "hero", "title": "  Café ODIN™  ", "items": [{"title": " 50% ", "text": " Of all "}]}]})
    check("spaces around a value are trimmed", error is None and pages["home"][0]["title"] == "Café ODIN™"
          and pages["home"][0]["items"] == [{"title": "50%", "text": "Of all"}], error)
    check("text that is not ASCII is saved and served as written",
          run_seed({"home": [{"name": "hero", "title": "Café ODIN™"}]}) == ["home.hero"] and served()["sections"][0]["title"] == "Café ODIN™")
    clear()

    # The real seed, through the script
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = init_odin_site.main()
    printed = out.getvalue().strip().splitlines()
    check("init_odin_site.py seeds an empty database, and prints what each seed did",
          code == 0 and rows() == total and len(printed) == 2 and "home.hero" in printed[1], printed)
    code, message = init_odin_site.seed_sections()
    check("init_odin_site.py run again changes nothing, and says so", code == 0 and rows() == total and "Nothing changed" in message, message)
    out = io.StringIO()
    with contextlib.redirect_stdout(out), mock.patch.object(init_odin_site, "initOdinSections", side_effect=ValueError("odin_pages.json: broken")):
        code = init_odin_site.main()
    printed = out.getvalue().strip().splitlines()
    check("when one seed is refused the script still reports the other, and exits 1",
          code == 1 and len(printed) == 2 and "Nothing changed" in printed[0] and printed[1] == "Not seeded. odin_pages.json: broken", printed)
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
    check("the home page's sections come in the order the current site shows them", order() == HOME_ORDER, order())
    check("each section has its name, every key in FIELDS and its items, and nothing else",
          all(sorted(section) == sorted(["name", "items", *FIELDS]) for section in body["sections"]))
    check("GET returns what odin_pages.json holds, with null for a part a section does not have",
          body["sections"] == [as_served(section) for section in seed["home"]], body)
    check("a section without a list has an empty list of items", body["sections"][place("hero") - 1]["items"] == [])
    about = served("about")["sections"]
    team = about[-1]["items"]
    check("the About page's sections come in the order the current site shows them", [section["name"] for section in about] == ABOUT_ORDER, about)
    check("the team has its four people, each with a name, role, degrees, bio and profile link",
          len(team) == TEAM_SIZE and all({"title", "subtitle", "note", "text", "link"} <= set(person) for person in team), team)
    check("a person's photo always comes with what it shows", all(("image" in person) == ("image_alt" in person) for person in team))
    for page, sections in seed.items():
        check(f"GET for the {page} page returns what the file holds for it",
              served(page) == {"page": page, "sections": [as_served(section) for section in sections]}, served(page))
    site = anon.get("/api/odin/site").get_json()
    labels = [section["name"] for section in seed["contact"] if section["name"] in site]
    check("each contact label is a section named for the site basic it labels, which the site route sends with text",
          labels == ["phone", "email", "address"] and all(isinstance(site[name], str) and site[name].strip() for name in labels), labels)
    images = [holder["image"] for sections in seed.values() for section in sections
              for holder in (section, *section.get("items", [])) if holder.get("image")]
    check("every image a section names is one the image route serves",
          bool(images) and all(anon.get(f"/api/odin/image?name={image}").status_code == 200 for image in images), images)
    # MySQL compares text without regard to case or accents, so a name that is not well formed must
    # never reach the database: Home would find the home page there.
    with mock.patch.object(OdinSection, "for_page", wraps=real_for_page) as looked_up:
        for page in ("Home", "HOME", "hömé", "home ", "home' OR '1'='1", "x" * 500):
            r = anon.get(URL, query_string={"name": page})
            check(f"GET for the name {page[:16]!r}, which no page can have, is a 404 with a message",
                  r.status_code == 404 and bool((r.get_json() or {}).get("message")), r.status_code)
        check("a name no page can have is never looked up in the database", looked_up.call_count == 0, looked_up.call_count)
        r = anon.get(URL, query_string={"name": "missing"})
        check("GET for a well-formed name with no page is looked up, and is a 404 with a message",
              looked_up.call_count == 1 and r.status_code == 404 and bool((r.get_json() or {}).get("message")), r.status_code)

    # Seeding a database that already has sections
    check("running the seed again writes nothing", run_seed() == [] and rows() == total and served() == body)
    check("a later seed file does not replace text that is saved",
          run_seed(with_section("hero", title="Another Title", text="Another line.")) == [] and served() == body)
    # These checks give an image to a section the file has none for
    later = with_section("pitch", image="product-headset.jpg", image_alt="The headset")
    written = run_seed(later)
    pitch = served()["sections"][place("pitch") - 1]
    check("a part added to the file later is filled in, and the seed names what it filled",
          written == ["home.pitch.image", "home.pitch.image_alt"] and pitch == as_served(later["home"][place("pitch") - 1]), f"{written} {pitch}")

    # A description belongs to its own image
    with app.app_context():
        saved("pitch").image_alt = None
        db.session.commit()
    other = with_section("pitch", image="eye-tracking.webp", image_alt="Two eyes opening")
    written = run_seed(other)
    pitch = served()["sections"][place("pitch") - 1]
    check("a saved image with no description is not given the description of another image",
          written == [] and pitch["image"] == "product-headset.jpg" and pitch["image_alt"] is None, f"{written} {pitch}")
    written = run_seed(later)
    check("a saved image with no description gets the one the file has for that image",
          written == ["home.pitch.image_alt"] and served()["sections"][place("pitch") - 1]["image_alt"] == "The headset", written)
    with app.app_context():
        saved("pitch").image = saved("pitch").image_alt = None
        db.session.commit()

    # A link belongs to its own image
    pictured = seed["home"][place("features") - 1]
    linked = with_section("features", link="https://a.example/headset")
    written = run_seed(linked)
    check("a link added to the file later is filled in under the image it is for",
          written == ["home.features.link"] and served()["sections"][place("features") - 1]["link"] == "https://a.example/headset", written)
    with app.app_context():
        section = saved("features")
        section.link, section.image, section.image_alt = None, "eye-tracking.webp", "Two eyes opening"
        db.session.commit()
    written = run_seed(linked)
    features_now = served()["sections"][place("features") - 1]
    check("a link in the file is not put under a different image that is saved",
          written == [] and features_now["link"] is None and features_now["image"] == "eye-tracking.webp", f"{written} {features_now}")
    with app.app_context():
        section = saved("features")
        section.image, section.image_alt = pictured["image"], pictured["image_alt"]
        db.session.commit()
    check("the link checks left the home page as the file has it", served() == body)

    # A saved list is one part: a change to an item in the file does not reach it
    listed = seed["home"][place("statistics") - 1]
    changed_items = [{**listed["items"][0], "subtitle": "Added later"}, *listed["items"][1:], {"title": "New", "text": "A new item"}]
    written = run_seed(with_section("statistics", items=changed_items))
    check("a saved list is left as it is when the file's list changes", written == [] and served() == body, written)

    # Parts with nothing in them
    with app.app_context():
        section = saved("statistics")
        section.items, section.title = None, "  "
        db.session.commit()
    emptied = served()["sections"][place("statistics") - 1]
    check("a saved part that is blank is served as null, and items that are null as an empty list",
          emptied["title"] is None and emptied["items"] == [], emptied)
    written = run_seed()
    check("the seed fills in items and blank text a saved section has none of",
          written == ["home.statistics.title", "home.statistics.items"] and served() == body, written)

    # The file decides the order
    swapped = copy.deepcopy(seed)
    swapped["home"][0], swapped["home"][1] = swapped["home"][1], swapped["home"][0]
    written = run_seed(swapped)
    check("sections that changed place in the file change place on the page, and the seed says so",
          written == [f"home.{HOME_ORDER[1]}.position", f"home.{HOME_ORDER[0]}.position"]
          and order() == [HOME_ORDER[1], HOME_ORDER[0], *HOME_ORDER[2:]], f"{written} {order()}")
    code, message = init_odin_site.seed_sections()
    check("init_odin_site.py puts them back in the file's order, and does not say nothing changed",
          code == 0 and order() == HOME_ORDER and "position" in message and "Nothing changed" not in message, message)
    extra = {"name": "extra", "title": "Added later"}
    written = run_seed({"home": [seed["home"][0], extra, *seed["home"][1:]]})
    check("a section added in the middle of the file later takes that place on the page",
          written == ["home.extra", *[f"home.{name}.position" for name in HOME_ORDER[1:]]]
          and order() == [HOME_ORDER[0], "extra", *HOME_ORDER[1:]], f"{written} {order()}")
    written = run_seed()
    check("a section the file no longer has stays in the database and on the page",
          sorted(order()) == sorted(HOME_ORDER + ["extra"]) and [name for name in order() if name != "extra"] == HOME_ORDER, f"{written} {order()}")
    with app.app_context():
        OdinSection.query.filter_by(name="extra").delete()
        db.session.commit()
    check("the checks above left the home page as the file has it", served() == body)

    # The real file has an about page now, so this one takes a name no real page has
    check("a page added to the file later is saved beside the others, and each is served by its own name",
          run_seed({**seed, "added_later": [{"name": "mission", "title": "Our mission"}]}) == ["added_later.mission"]
          and served("added_later") == {"page": "added_later", "sections": [as_served({"name": "mission", "title": "Our mission"})]}
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
