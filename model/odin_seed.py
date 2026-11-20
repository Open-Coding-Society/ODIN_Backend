""" Reading and checking the ODIN seed files """
import json
import os
from urllib.parse import urlsplit

from model.odin_image import image_file

# What a value holds: plain text, a link to another site, or the name of a file in odin/images/
TEXT, LINK, IMAGE = 'text', 'link', 'image'


def load_seed(path):
    """The JSON a seed file holds. A file that cannot be used raises ValueError with a message that
    starts with the file's name."""
    name = os.path.basename(path)
    try:
        # utf-8 whatever the server's locale is, so accented text is not stored garbled
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except OSError as e:
        raise ValueError(f"{name}: cannot be read ({e.strerror})")
    except ValueError as e:  # text that is not JSON, or not utf-8
        raise ValueError(f"{name}: is not valid JSON ({e})")


def checked_value(value, kind, max_len):
    """(value, problem) for one value of a seed: the text with the spaces around it removed, or what
    is wrong with it, worded to follow the value's name. The text must fit its column, because MySQL
    refuses what SQLite would quietly store. A link must be a full https address and an image must be
    a file in odin/images/, so a seed cannot hold one a page could not use."""
    if not isinstance(value, str):
        return None, "must be text"
    value = value.strip()
    if not value:
        return None, "must not be blank"
    if len(value) > max_len:
        return None, f"must be at most {max_len} characters"
    if kind == LINK and not _is_https_link(value):
        return None, "must be a full https link, such as https://example.com/page"
    if kind == IMAGE and image_file(value) is None:
        return None, "must name an image in odin/images/"
    return value, None


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
