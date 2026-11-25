#!/usr/bin/env python3
"""Verify /api/odin/image and the images in odin/images/ that the ODIN Diagnostics website shows.

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
# What an SVG must not hold: script in any form, or anything fetched from another site
UNSAFE_SVG = re.compile(r"<(?:[\w-]+:)?script\b|\son\w+\s*=|<(?:[\w-]+:)?foreignObject\b|javascript:|@import"
                        r"|(?:href|src)\s*=\s*[\"']\s*(?:https?:)?//|url\(\s*[\"']?\s*(?:https?:)?//", re.I)
_failures = []


def check(label, cond, detail=""):
    print(("PASS  " if cond else "FAIL  ") + label + (f"   [{detail}]" if detail and not cond else ""))
    if not cond:
        _failures.append(label)


def sha256(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def webp_loops(path):
    """How many times a WebP picture plays: 0 for without end, None for a picture that does not
    move. The count is two bytes in the file's ANIM chunk, after four bytes of background colour."""
    with open(path, "rb") as fh:
        data = fh.read()
    if data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        raise ValueError(f"{os.path.basename(path)} is not a WebP file")
    at = 12  # past RIFF, the size and WEBP
    while at + 8 <= len(data):
        name, size = data[at:at + 4], int.from_bytes(data[at + 4:at + 8], "little")
        if name == b"ANIM":
            return int.from_bytes(data[at + 12:at + 14], "little")
        at += 8 + size + (size & 1)  # chunks are padded to an even length
    return None


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
    from model.odin_image import IMAGE_FOLDER, IMAGE_TYPES, image_file, image_type, is_image_name
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
    others = [name for name in files if name != "README.md" and not is_image_name(name)]
    images = [name for name in files if is_image_name(name)]
    check("odin/images/ holds images", len(images) > 0)
    check("every file there besides the README is an image the route may serve", not others, others)
    links = [name for name in files if os.path.islink(os.path.join(IMAGE_FOLDER, name))]
    check("no file there is a link, which could point outside the folder", not links, links)
    check("every image name is lowercase words joined by hyphens",
          all(NAME.fullmatch(name) for name in images), [name for name in images if not NAME.fullmatch(name)])
    check("each file type is sent as the content type browsers expect", dict(IMAGE_TYPES) == CONTENT_TYPES, IMAGE_TYPES)
    heavy = [name for name in images if os.path.getsize(os.path.join(IMAGE_FOLDER, name)) > MAX_BYTES]
    check("every image is under 1 MB", not heavy, heavy)
    endless = [name for name in images if name.endswith(".webp") and webp_loops(os.path.join(IMAGE_FOLDER, name)) == 0]
    check("no WebP picture loops without end: a page gives a visitor no way to pause one", not endless, endless)
    # A GIF's loop count is not read here, so none is kept: a moving picture is saved as WebP
    check("no picture is a GIF, whose loop this script does not read", not [name for name in images if name.endswith(".gif")])
    check("the eye picture moves, and plays once", webp_loops(os.path.join(IMAGE_FOLDER, "eye-tracking.webp")) == 1)
    with open(os.path.join(IMAGE_FOLDER, "README.md"), encoding="utf-8") as fh:
        listed = sorted(re.findall(r"^\| `([^`]+)` \|", fh.read(), flags=re.M))
    check("the README's table lists exactly the images in the folder", listed == images, f"{listed} vs {images}")
    for name in (n for n in images if n.endswith(".svg")):
        with open(os.path.join(IMAGE_FOLDER, name), encoding="utf-8") as fh:
            svg = fh.read()
        unsafe = UNSAFE_SVG.search(svg)
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
        policy = r.headers.get("Content-Security-Policy", "")
        check(f"{name} is sent with nosniff and a policy that allows no script",
              r.headers.get("X-Content-Type-Options") == "nosniff" and "default-src 'none'" in policy
              and "sandbox" in policy and "script-src" not in policy, policy)
    first = images[0]
    for bad in ('<s:script xmlns:s="http://www.w3.org/2000/svg">x</s:script>', '<a href="javascript:x">', "<style>@import url(a.css)</style>",
                '<image href="https://example.com/a.png"/>', '<rect onload="x()"/>', "<rect style=\"fill:url(//example.com/a)\"/>"):
        check(f"the SVG scan catches {bad[:32]}", UNSAFE_SVG.search(bad) is not None)
    cache = anon.get(URL, query_string={"name": first}).headers.get("Cache-Control", "")
    check("an image may stay in the browser's cache for an hour", "max-age=3600" in cache, cache)
    check("image_type gives the type for a name in capitals too", image_type("A.WEBP") == "image/webp")
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
    for path in (f"/static/odin/{first}", f"/static/odin/images/{first}", f"/uploads/odin/{first}", "/static/odin/README.md"):
        check(f"the route is the only address: {path} is a 404", anon.get(path).status_code == 404)
    embedded = [n for n in images if n.endswith(".svg") and "data:image/" in open(os.path.join(IMAGE_FOLDER, n), encoding="utf-8").read()]
    for name in embedded:
        policy = anon.get(URL, query_string={"name": name}).headers.get("Content-Security-Policy", "")
        check(f"{name} may show the pictures embedded in it when opened on its own", "img-src data:" in policy, policy)
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
