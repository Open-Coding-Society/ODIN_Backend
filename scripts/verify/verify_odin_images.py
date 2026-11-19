#!/usr/bin/env python3
"""Verify /api/odin/image and the images in static/odin/ that the ODIN Diagnostics website shows.

Runs the real app against a throwaway SQLite database and checksums the real dev DB
before and after to prove it was never touched.

Usage:  python scripts/verify/verify_odin_images.py        (from the flask repo root)
Exit:   0 all checks passed, 1 otherwise.
"""
import hashlib, os, re, secrets, sys, tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ.setdefault("SECRET_KEY", "verify-odin-images")

REAL_DB = os.path.join(REPO, "instance", "volumes", "user_management.db")
PASSWORD = "Aa1!" + secrets.token_urlsafe(16)
URL = "/api/odin/image"
MAX_BYTES = 1024 * 1024  # a page loads several images, so each one stays small
NAME = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*\.[a-z]+")
CONTENT_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
                 ".gif": "image/gif", ".webp": "image/webp"}
_failures = []


def check(label, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + label + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    real_before = sha256(REAL_DB) if os.path.exists(REAL_DB) else None

    import __init__ as pkg
    from sqlalchemy import create_engine
    app, db = pkg.app, pkg.db
    engine = create_engine(f"sqlite:///{os.path.join(tempfile.mkdtemp(prefix='odin-images-'), 'new.db')}")
    with app.app_context():
        db.engines[None] = engine
    import main  # noqa: F401  registers every model and blueprint
    from model import account_types
    from model.user import User
    from model.odin_image import IMAGE_FOLDER, IMAGE_TYPES, image_file, is_image_name
    app.config["TESTING"] = True
    with app.app_context():
        db.create_all()

    def session_client(role):
        """A client signed in through the Flask session login as a new account of this role. Made
        outside an app context, so its login is not carried over to another client."""
        uid = "zz_odin_" + role.lower()
        with app.app_context():
            db.session.add(User(name=uid, uid=uid, password=PASSWORD, role=role))
            db.session.commit()
            User.query.filter_by(_uid=uid).first().activate()
        client = app.test_client()
        signed_in = client.post("/login", data={"username": uid, "password": PASSWORD}).status_code == 302
        return client if signed_in else None

    # The folder
    files = sorted(os.listdir(IMAGE_FOLDER))
    images = [name for name in files if name != "README.md"]
    check("static/odin/ holds images", len(images) > 0)
    check("every file there besides the README is an image the route may serve",
          all(is_image_name(name) for name in images), [name for name in images if not is_image_name(name)])
    check("every image name is lowercase words joined by hyphens",
          all(NAME.fullmatch(name) for name in images), [name for name in images if not NAME.fullmatch(name)])
    check("the route's file types each have a content type here", sorted(CONTENT_TYPES) == sorted(IMAGE_TYPES))
    heavy = [name for name in images if os.path.getsize(os.path.join(IMAGE_FOLDER, name)) > MAX_BYTES]
    check("every image is under 1 MB", not heavy, heavy)
    with open(os.path.join(IMAGE_FOLDER, "README.md"), encoding="utf-8") as fh:
        listed = sorted(re.findall(r"^\| `([^`]+)` \|", fh.read(), flags=re.M))
    check("the README's table lists exactly the images in the folder", listed == images, f"{listed} vs {images}")
    for name in (n for n in images if n.endswith(".svg")):
        with open(os.path.join(IMAGE_FOLDER, name), encoding="utf-8") as fh:
            svg = fh.read()
        unsafe = re.search(r"<script|\son\w+\s*=|<foreignObject|(?:href|src)\s*=\s*[\"'](?:https?:)?//", svg, flags=re.I)
        check(f"{name} holds no script and loads nothing from another site", unsafe is None, unsafe and unsafe.group(0))

    # The route
    anon = app.test_client()
    for name in images:
        r = anon.get(URL, query_string={"name": name})
        with open(os.path.join(IMAGE_FOLDER, name), "rb") as fh:
            same = r.status_code == 200 and r.data == fh.read()
        check(f"{name} is served whole, with no login", same, r.status_code)
        kind = CONTENT_TYPES[os.path.splitext(name)[1]]
        check(f"{name} is sent as {kind}", r.headers.get("Content-Type", "").split(";")[0] == kind, r.headers.get("Content-Type"))
        check(f"{name} cannot run script or be read as another type",
              r.headers.get("X-Content-Type-Options") == "nosniff" and "sandbox" in r.headers.get("Content-Security-Policy", ""))
    first = images[0]
    etag = anon.get(URL, query_string={"name": first}).headers.get("ETag")
    r = anon.get(URL, query_string={"name": first}, headers={"If-None-Match": etag or ""})
    check("an image the browser already has is not sent again (304)", bool(etag) and r.status_code == 304, r.status_code)

    for label, query in (("no name", {}), ("an empty name", {"name": ""})):
        r = anon.get(URL, query_string=query)
        check(f"{label} is a 400 with a message", r.status_code == 400 and bool((r.get_json() or {}).get("message")), r.status_code)
    refused = ["missing.png", "README.md", "../main.py", "../../main.py", "/etc/passwd", "odin/" + first,
               first + "/../../../main.py", "..", ".", ".hidden.png", first.upper(), first + ".bak", "main.py"]
    for name in refused:
        r = anon.get(URL, query_string={"name": name})
        check(f"the name {name!r} is a 404 with a message",
              r.status_code == 404 and bool((r.get_json() or {}).get("message")), f"{r.status_code} {r.data[:40]!r}")
    check("a path escape written with %2F is refused too", anon.get(URL + "?name=..%2Fmain.py").status_code == 404)
    check("image_file gives no path for a name outside the folder",
          image_file("../main.py") is None and image_file("README.md") is None and image_file(first) is not None)

    for method in ("post", "put", "patch", "delete"):
        r = getattr(anon, method)(URL, query_string={"name": first})
        check(f"{method.upper()} is not allowed", r.status_code == 405, r.status_code)

    # A guest may make only the requests its account type lists, and the site's images are among them
    for role in account_types.guest_roles() + ("User",):
        client = session_client(role)
        check(f"a visitor signed in as a {role} still gets the images",
              client is not None and client.get(URL, query_string={"name": first}).status_code == 200,
              "could not sign in" if client is None else client.get(URL, query_string={"name": first}).status_code)

    real_after = sha256(REAL_DB) if os.path.exists(REAL_DB) else None
    check("the real dev database was not touched", real_before == real_after)

    print(f"\n{'ALL PASSED' if not _failures else f'{len(_failures)} FAILED'}")
    return 0 if not _failures else 1


if __name__ == "__main__":
    sys.exit(main())
