#!/usr/bin/env python3
"""Verify /api/odin/site, the basics the ODIN Diagnostics website reads, end to end.

Runs the real app against a throwaway SQLite database and checksums the real dev DB
before and after to prove it was never touched.

Usage:  python scripts/verify/verify_odin_site.py        (from the flask repo root)
Exit:   0 all checks passed, 1 otherwise.
"""
import hashlib, json, os, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ.setdefault("SECRET_KEY", "verify-odin-site")

REAL_DB = os.path.join(REPO, "instance", "volumes", "user_management.db")
URL = "/api/odin/site"
_failures = []


def check(label, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + label + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def seed_file(content):
    """A throwaway seed file holding this content."""
    path = os.path.join(tempfile.mkdtemp(prefix="odin-seed-"), "odin_site.json")
    with open(path, "w") as fh:
        json.dump(content, fh)
    return path


def main():
    real_before = sha256(REAL_DB) if os.path.exists(REAL_DB) else None

    import __init__ as pkg
    from sqlalchemy import create_engine
    app, db = pkg.app, pkg.db
    engine = create_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(prefix='odin-'), 'new.db')}")
    with app.app_context():
        db.engines[None] = engine
    import main  # noqa: F401  registers every model and blueprint
    from model.odin_site import OdinSite, initOdinSite, FIELDS, SEED_FILE
    app.config["TESTING"] = True

    with open(SEED_FILE) as fh:
        seed = json.load(fh)

    def refused(content):
        """True when seeding from this content raises ValueError and saves no row."""
        try:
            initOdinSite(seed_file(content))
        except ValueError:
            return OdinSite.query.count() == 0
        return False

    with app.app_context():
        db.create_all()
        anon = app.test_client()

        r = anon.get(URL)
        check("GET before the seed has run is a 404 with a message",
              r.status_code == 404 and bool((r.get_json() or {}).get("message")), r.get_json())

        for key in FIELDS:
            check(f"a seed without {key} is refused", refused({k: v for k, v in seed.items() if k != key}))
        check("a blank value is refused", refused({**seed, "phone": "   "}))
        check("a value that is not text is refused", refused({**seed, "phone": 8053001100}))
        check("a value longer than its column is refused", refused({**seed, "name": "x" * (FIELDS["name"] + 1)}))
        check("a seed that is not an object is refused", refused([seed]))
        values, error = OdinSite.validate({**seed, "name": "  " + seed["name"] + "  "})
        check("spaces around a value are trimmed", error is None and values["name"] == seed["name"], error)

        check("the seed file is in model/dataconfigs/",
              os.path.samefile(os.path.dirname(SEED_FILE), os.path.join(REPO, "model", "dataconfigs")), SEED_FILE)
        check("the seed creates one row", initOdinSite() == 1 and OdinSite.query.count() == 1)
        r = anon.get(URL)
        body = r.get_json()
        check("GET needs no login", r.status_code == 200, r.status_code)
        check("GET returns exactly the keys in FIELDS", sorted(body) == sorted(FIELDS), body)
        check("GET returns what odin_site.json holds", body == {key: seed[key] for key in FIELDS}, body)

        check("running the seed again creates nothing", initOdinSite() == 0 and OdinSite.query.count() == 1)
        changed = seed_file({**seed, "name": "Another Name"})
        check("a later seed file does not replace the saved row",
              initOdinSite(changed) == 0 and anon.get(URL).get_json()["name"] == seed["name"])

        for method in ("post", "put", "patch", "delete"):
            r = getattr(anon, method)(URL, json={"name": "x"})
            check(f"{method.upper()} is not allowed", r.status_code == 405, r.status_code)
        check("a refused write changed nothing", anon.get(URL).get_json() == body)

    real_after = sha256(REAL_DB) if os.path.exists(REAL_DB) else None
    check("the real dev database was not touched", real_before == real_after)

    print(f"\n{'ALL PASSED' if not _failures else f'{len(_failures)} FAILED'}")
    return 0 if not _failures else 1


if __name__ == "__main__":
    sys.exit(main())
