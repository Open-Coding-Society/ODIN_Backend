""" ODIN site images """
import os

from __init__ import app

# The website's images ship with the code, in static/odin/. A page asks for one by its file name.
IMAGE_FOLDER = os.path.join(app.root_path, 'static', 'odin')

# The only kinds of file handed out, so nothing else left in the folder (a README, a backup) can be read
IMAGE_TYPES = ('.svg', '.png', '.jpg', '.jpeg', '.gif', '.webp')


def is_image_name(name):
    """True for a plain file name of one of IMAGE_TYPES: no folder in it, and not a hidden file."""
    return (isinstance(name, str) and name == os.path.basename(name) and not name.startswith('.')
            and os.path.splitext(name)[1].lower() in IMAGE_TYPES)


def image_file(name):
    """The path of the image with this name, or None when the folder has no such image. The name is
    matched against the folder's listing, so its letter case counts on every kind of disk."""
    if not is_image_name(name) or name not in os.listdir(IMAGE_FOLDER):
        return None
    return os.path.join(IMAGE_FOLDER, name)
