#!/usr/bin/env python3
"""Verify /api/odin/pages, the page list the ODIN Diagnostics website builds its menu from, and the
details /api/odin/page sends with a page's sections, end to end.

Runs the real app against a throwaway SQLite database and checksums the real dev DB
before and after to prove it was never touched.

Usage:  python scripts/verify/verify_odin_page_list.py        (from the flask repo root)
Exit:   0 all checks passed, 1 otherwise.
"""
import contextlib, hashlib, io, json, os, secrets, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("SECRET_KEY", "verify-odin-page-list")

REAL_DB = os.path.join(REPO, "instance", "volumes", "user_management.db")
PASSWORD = "Aa1!" + secrets.token_urlsafe(16)
URL = "/api/odin/pages"
PAGE = "/api/odin/page"
FILE = "odin_page_list.json: "
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
    path = os.path.join(tempfile.mkdtemp(prefix="odin-seed-"), "odin_page_list.json")
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
    from init_odin_site import seed_pages
    from model import account_types
    from model.user import User
    from model.odin_page import OdinPage, initOdinPages, FIELDS, REQUIRED, SEED_FILE
    from model.odin_section import OdinSection, NAME_MAX
    from model.odin_section import SEED_FILE as SECTIONS_FILE
    app.config["TESTING"] = True

    with open(SEED_FILE, encoding="utf-8") as fh:
        seed = json.load(fh)
    with open(SECTIONS_FILE, encoding="utf-8") as fh:
        section_seed = json.load(fh)
    first = seed[0]

    def as_served(page):
        """One page of a seed file as the route sends it: every key, null for one it does not have."""
        return {"name": page["name"], **{key: page.get(key) for key in FIELDS}}

    # Each database step opens its own app context and every request is made outside one: Flask-Login
    # keeps the signed-in user on the context, so one left open would carry a login to the next client.
    def rows():
        with app.app_context():
            return OdinPage.query.count()

    def run_seed(content=None):
        with app.app_context():
            return initOdinPages(SEED_FILE if content is None else seed_file(content))

    def clear():
        with app.app_context():
            OdinPage.query.delete()
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
        return f"not refused, wrote {written}"

    def refused(label, content, expected):
        got = refusal(content)
        check(label, got == expected, got)

    def served():
        return app.test_client().get(URL).get_json()

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

    # A database that has not been upgraded has no odin_page table
    with app.app_context():
        db.create_all()
        OdinPage.__table__.drop(db.engine)
    code, message = seed_pages()
    check("init_odin_site.py on a database without the table changes nothing and says to run db_upgrade.py",
          code == 1 and "db_upgrade.py" in message, message)
    with app.app_context():
        db.create_all()
        check("each column is as long as FIELDS says",
              all(OdinPage.__table__.columns[key].type.length == size for key, (kind, size) in FIELDS.items()))
        check("a page's name is as long as a section's page name",
              OdinPage.__table__.columns["name"].type.length == NAME_MAX == OdinSection.__table__.columns["page"].type.length)

    anon = app.test_client()
    r = anon.get(URL)
    check("GET before the seed has run is a 404 with a message",
          r.status_code == 404 and bool((r.get_json() or {}).get("message")), r.get_json())

    check("the seed file is in model/dataconfigs/",
          os.path.samefile(os.path.dirname(SEED_FILE), os.path.join(REPO, "model", "dataconfigs")), SEED_FILE)
    check("every page in the list has sections in odin_pages.json, so the menu never leads to a page with nothing on it",
          all(page["name"] in section_seed for page in seed), [page["name"] for page in seed])
    check("every page with sections is in the list, so each has a title",
          all(name in [page["name"] for page in seed] for name in section_seed), list(section_seed))

    refused("a seed that is not a list is refused", {"home": first}, "the pages must be a JSON list with at least one page")
    refused("an empty list is refused", [], "the pages must be a JSON list with at least one page")
    refused("a page that is not an object is refused", ["home"], "page 1: must be a JSON object")
    refused("a page without a name is refused", [{key: value for key, value in first.items() if key != "name"}], "page 1: name is required")
    for bad in ("Home", "1home", "home page", "h" * (NAME_MAX + 1), ""):
        got = refusal([{**first, "name": bad}])
        check(f"the name {bad[:16]!r} is refused", got.startswith("page 1: name must be at most"), got)
    refused("two pages with one name are refused, and the message says which",
            [first, {**first, "title": "Again"}], f"two pages are named {first['name']}")
    refused("a key the model does not have is refused, so a misspelled one is not dropped",
            [{**first, "tittle": "x"}], "page 1: a page has no key named tittle")
    for key in REQUIRED:
        refused(f"a page without {key} is refused", [{k: v for k, v in first.items() if k != key}], f"page 1: {key} is required")
    for key, (kind, size) in FIELDS.items():
        refused(f"{key} that is not text is refused", [{**first, key: 7}], f"page 1: {key} must be text")
        refused(f"a blank {key} is refused", [{**first, key: "   "}], f"page 1: {key} must not be blank")
        refused(f"{key} longer than its column is refused", [{**first, key: "x" * (size + 1)}],
                f"page 1: {key} must be at most {size} characters")
    refused("a problem on a later page names that page", [first, {"name": "about"}], "page 2: title is required")
    got = refusal("{ not json")
    check("a seed that is not valid JSON is refused, and the message names the file", got.startswith("is not valid JSON"), got)
    check("a refused seed saved nothing", rows() == 0, rows())

    hidden = {"name": "terms", "title": "Terms"}
    check("a page with only a name and a title is saved, and its other keys are served as null",
          run_seed([first, hidden]) == [first["name"], "terms"]
          and served() == {"pages": [as_served(first), {"name": "terms", "title": "Terms", "description": None, "menu": None}]})
    clear()

    code, message = seed_pages()
    check("init_odin_site.py seeds an empty table", code == 0 and rows() == len(seed), message)
    code, message = seed_pages()
    check("init_odin_site.py run again changes nothing", code == 0 and rows() == len(seed) and "Nothing changed" in message, message)
    clear()

    # generate_data is a Flask command. standalone_mode=False makes it return here instead of exiting,
    # and the other seeds print every account they create.
    with app.app_context(), contextlib.redirect_stdout(io.StringIO()):
        flask_main.generate_data(args=[], standalone_mode=False)
    check("generate_data, which db_init.py runs, seeds the pages", rows() == len(seed), rows())

    r = anon.get(URL)
    body = r.get_json()
    check("GET needs no login", r.status_code == 200, r.status_code)
    check("GET returns the pages and nothing else", sorted(body) == ["pages"], body)
    check("each page has its name and every key in FIELDS, and nothing else",
          all(sorted(page) == sorted(["name", *FIELDS]) for page in body["pages"]), body)
    check("GET returns what odin_page_list.json holds, in the file's order",
          body["pages"] == [as_served(page) for page in seed], body)
    for page in seed:
        r = anon.get(PAGE, query_string={"name": page["name"]})
        got = r.get_json() or {}
        check(f"GET /api/odin/page for {page['name']} sends its title and description with its sections",
              r.status_code == 200 and got.get("title") == page["title"] and got.get("description") == page.get("description")
              and bool(got.get("sections")), got)

    check("running the seed again writes nothing", run_seed() == [] and rows() == len(seed))
    check("a later seed file does not replace text that is saved",
          run_seed([{**first, "title": "Another title"}, *seed[1:]]) == [] and served() == body)
    with app.app_context():
        saved = OdinPage.named(first["name"])
        kept = saved.description
        saved.description = "   "
        db.session.commit()
    check("a key with no text is served as null", served()["pages"][0]["description"] is None)
    written = run_seed([{**first, "title": "Another title", "description": "Filled later."}, *seed[1:]])
    check("a later seed file fills only the key that had no text",
          written == [f"{first['name']}.description"] and served()["pages"][0] == {**as_served(first), "description": "Filled later."},
          f"{written} {served()}")
    with app.app_context():
        OdinPage.named(first["name"]).description = kept
        db.session.commit()

    extra = {"name": "extra", "title": "Extra", "menu": "Extra"}
    written = run_seed([extra, *seed])
    check("a page put first in the file is added first, and the others move down",
          written == ["extra", *[f"{page['name']}.position" for page in seed]]
          and [page["name"] for page in served()["pages"]] == ["extra", *[page["name"] for page in seed]], written)
    run_seed()
    check("a page the file no longer has stays in the database and in the list",
          sorted(page["name"] for page in served()["pages"]) == sorted(["extra", *[page["name"] for page in seed]]))
    with app.app_context():
        OdinPage.query.filter_by(name="extra").delete()
        db.session.commit()
    check("the checks above left the list as the file has it", served() == body)

    with app.app_context():
        OdinPage.query.delete()
        db.session.commit()
    got = anon.get(PAGE, query_string={"name": first["name"]}).get_json() or {}
    check("a page whose sections were saved before its details is served with a null title and description",
          got.get("title") is None and got.get("description") is None and bool(got.get("sections")), got)
    run_seed()

    for method in ("post", "put", "patch", "delete"):
        r = getattr(anon, method)(URL, json={"name": "home", "title": "x"})
        check(f"{method.upper()} is not allowed", r.status_code == 405, r.status_code)
    check("a refused write changed nothing", served() == body)

    # A guest may make only the requests its account type lists, and the public site is one of them
    for role in account_types.guest_roles() + ("User",):
        client = session_client(role)
        check(f"a visitor signed in as a {role} still gets the pages",
              client is not None and client.get(URL).status_code == 200,
              "could not sign in" if client is None else client.get(URL).get_json())
    check("a signed-in client did not sign the next visitor in", app.test_client().get("/api/id").status_code == 401)

    real_after = sha256(REAL_DB) if os.path.exists(REAL_DB) else None
    check("the real dev database was not touched", real_before == real_after)

    print(f"\n{'ALL PASSED' if not _failures else f'{len(_failures)} FAILED'}")
    return 0 if not _failures else 1


if __name__ == "__main__":
    sys.exit(main())
