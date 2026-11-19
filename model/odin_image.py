""" ODIN site images """
import os

from __init__ import app

# The website's images ship with the code, in odin/images/. A page asks for one by its file name.
# The folder is outside static/, which Flask serves by itself, so the image route is the only way in.
IMAGE_FOLDER = os.path.join(app.root_path, 'odin', 'images')

# The only kinds of file the route hands out, and the content type each is sent as. The types are
# written here because a slim server image may not know .webp. The folder's README is not one of them.
IMAGE_TYPES = {
    '.svg': 'image/svg+xml',
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}


def is_image_name(name):
    """True for a plain file name of one of IMAGE_TYPES: no folder in it, and not a hidden file."""
    return (isinstance(name, str) and name == os.path.basename(name) and not name.startswith('.')
            and os.path.splitext(name)[1].lower() in IMAGE_TYPES)


def image_file(name):
    """The path of the image with this name, or None when the folder has no such image. The name is
    matched against the folder's listing, so its letter case counts on every kind of disk, and a
    link is refused because it could point outside the folder."""
    if not is_image_name(name) or name not in os.listdir(IMAGE_FOLDER):
        return None
    path = os.path.join(IMAGE_FOLDER, name)
    return path if os.path.isfile(path) and not os.path.islink(path) else None


def image_type(name):
    """The content type an image with this name is sent as."""
    return IMAGE_TYPES[os.path.splitext(name)[1].lower()]
