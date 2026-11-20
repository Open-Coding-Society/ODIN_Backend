#!/usr/bin/env python3
"""Verify /api/odin/site, the basics the ODIN Diagnostics website reads, end to end.

Runs the real app against a throwaway SQLite database and checksums the real dev DB
before and after to prove it was never touched.

Usage:  python scripts/verify/verify_odin_site.py        (from the flask repo root)
Exit:   0 all checks passed, 1 otherwise.
"""
import contextlib, hashlib, io, json, os, secrets, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(REPO)
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "scripts"))
os.environ.setdefault("SECRET_KEY", "verify-odin-site")

REAL_DB = os.path.join(REPO, "instance", "volumes", "user_management.db")
PASSWORD = "Aa1!" + secrets.token_urlsafe(16)
URL = "/api/odin/site"
_failures = []


def check(label, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + label + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def seed_file(text):
    """A throwaway seed file holding this text."""
    path = os.path.join(tempfile.mkdtemp(prefix="odin-seed-"), "odin_site.json")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)
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
    from model.odin_site import OdinSite, initOdinSite, FIELDS, SEED_FILE
    from init_odin_site import seed_site
    app.config["TESTING"] = True

    with open(SEED_FILE, encoding="utf-8") as fh:
        seed = json.load(fh)

    # Each database step opens its own app context and every request is made outside one: Flask-Login
    # keeps the signed-in user on the context, so one left open would carry a login to the next client.
    def rows():
        with app.app_context():
            return OdinSite.query.count()

    def run_seed(path=SEED_FILE):
        with app.app_context():
            return initOdinSite(path)

    def clear():
        with app.app_context():
            OdinSite.query.delete()
            db.session.commit()

    def refusal(content):
        """The message a seed with this content is refused with, or None when it was not refused or saved a row."""
        text = content if isinstance(content, str) else json.dumps(content)
        try:
            run_seed(seed_file(text))
        except ValueError as error:
            return str(error) if rows() == 0 else None
        return None

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

    # A database that has not been upgraded has no odin_site table
    with app.app_context():
        db.create_all()
        OdinSite.__table__.drop(db.engine)
    code, message = seed_site()
    check("init_odin_site.py on a database without the table changes nothing and says to run db_upgrade.py",
          code == 1 and "db_upgrade.py" in message, message)
    with app.app_context():
        db.create_all()
        check("each column is as long as FIELDS says",
              all(OdinSite.__table__.columns[key].type.length == size for key, (kind, size) in FIELDS.items()))
        added_later = [key for key in FIELDS if OdinSite.__table__.columns[key].nullable]
        check("the fields added after the table existed allow NULL, so db_upgrade.py can add them in place",
              added_later == ["copyright", "instagram", "linkedin", "logo_dark", "logo_light"], added_later)

    anon = app.test_client()
    r = anon.get(URL)
    check("GET before the seed has run is a 404 with a message",
          r.status_code == 404 and bool((r.get_json() or {}).get("message")), r.get_json())

    for key in FIELDS:
        check(f"a seed without {key} is refused, and the message names the file and {key}",
              refusal({k: v for k, v in seed.items() if k != key}) == f"odin_site.json: {key} is required")
    check("a blank value is refused", refusal({**seed, "phone": "   "}) == "odin_site.json: phone is required")
    check("a value that is not text is refused", refusal({**seed, "phone": 8053001100}) == "odin_site.json: phone must be text")
    check("a value longer than its column is refused",
          refusal({**seed, "name": "x" * (FIELDS["name"][1] + 1)}) == f"odin_site.json: name must be at most {FIELDS['name'][1]} characters")
    for bad in ("http://www.instagram.com/odin", "www.instagram.com/odin", "javascript:alert(1)", "https://", "https://a.example/x y",
                "https://a.example/\"onclick"):
        check(f"the link {bad!r} is refused",
              refusal({**seed, "instagram": bad}) == "odin_site.json: instagram must be a link that starts with https://")
    for bad in ("missing.svg", "../main.py", "README.md", "LOGO-DARK.SVG"):
        check(f"the logo {bad!r} is refused",
              refusal({**seed, "logo_dark": bad}) == "odin_site.json: logo_dark must name an image in odin/images/")
    check("a seed that is not an object is refused", (refusal([seed]) or "").startswith("odin_site.json: "))
    check("a seed that is not valid JSON is refused, and the message names the file",
          (refusal("{ not json") or "").startswith("odin_site.json: is not valid JSON"))
    with app.app_context():
        values, error = OdinSite.validate({**seed, "name": "  " + seed["name"] + "  "})
    check("spaces around a value are trimmed", error is None and values["name"] == seed["name"], error)

    accented = {**seed, "name": "Café ODIN"}
    check("text that is not ASCII is saved and served as written",
          run_seed(seed_file(json.dumps(accented, ensure_ascii=False))) == list(FIELDS)
          and anon.get(URL).get_json()["name"] == "Café ODIN")
    clear()

    check("the seed file is in model/dataconfigs/",
          os.path.samefile(os.path.dirname(SEED_FILE), os.path.join(REPO, "model", "dataconfigs")), SEED_FILE)
    code, message = seed_site()
    check("init_odin_site.py seeds an empty table", code == 0 and rows() == 1, message)
    code, message = seed_site()
    check("init_odin_site.py run again changes nothing", code == 0 and rows() == 1 and "Nothing changed" in message, message)
    clear()

    # generate_data is a Flask command. standalone_mode=False makes it return here instead of exiting,
    # and the other seeds print every account they create.
    with app.app_context(), contextlib.redirect_stdout(io.StringIO()):
        flask_main.generate_data(args=[], standalone_mode=False)
    check("generate_data, which db_init.py runs, seeds the site row", rows() == 1)

    r = anon.get(URL)
    body = r.get_json()
    check("GET needs no login", r.status_code == 200, r.status_code)
    check("GET returns exactly the keys in FIELDS", sorted(body) == sorted(FIELDS), body)
    check("GET returns what odin_site.json holds", body == {key: seed[key] for key in FIELDS}, body)

    check("running the seed again writes nothing", run_seed() == [] and rows() == 1)
    changed = seed_file(json.dumps({**seed, "name": "Another Name"}))
    check("a later seed file does not replace text that is saved",
          run_seed(changed) == [] and anon.get(URL).get_json()["name"] == seed["name"])

    # A row saved before a field was added has no text for it until the seed runs again
    with app.app_context():
        site = OdinSite.current()
        site.copyright, site.logo_light = None, "   "
        db.session.commit()
    older = anon.get(URL).get_json()
    check("a field with no text yet is served as null, with the rest unchanged",
          older["copyright"] is None and older["name"] == seed["name"], older)
    code, message = seed_site()
    check("init_odin_site.py fills in only the fields that had no text, and names them",
          code == 0 and "copyright, logo_light" in message and anon.get(URL).get_json() == body, message)
    check("filling in a field from a later seed file leaves saved text alone",
          run_seed(changed) == [] and anon.get(URL).get_json() == body)

    for method in ("post", "put", "patch", "delete"):
        r = getattr(anon, method)(URL, json={"name": "x"})
        check(f"{method.upper()} is not allowed", r.status_code == 405, r.status_code)
    check("a refused write changed nothing", anon.get(URL).get_json() == body)

    # A guest may make only the requests its account type lists, and the public site is one of them
    for role in account_types.guest_roles() + ("User",):
        client = session_client(role)
        check(f"a visitor signed in as a {role} still gets the site basics",
              client is not None and client.get(URL).status_code == 200,
              "could not sign in" if client is None else client.get(URL).get_json())
    check("a signed-in client did not sign the next visitor in", app.test_client().get("/api/id").status_code == 401)

    real_after = sha256(REAL_DB) if os.path.exists(REAL_DB) else None
    check("the real dev database was not touched", real_before == real_after)

    print(f"\n{'ALL PASSED' if not _failures else f'{len(_failures)} FAILED'}")
    return 0 if not _failures else 1


if __name__ == "__main__":
    sys.exit(main())
