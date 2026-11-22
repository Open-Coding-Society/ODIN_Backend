# ODIN site images

The images the ODIN Diagnostics website shows. They are content, so the frontend
keeps no copy: a page loads each one from `GET /api/odin/image?name=<file name>`.
This folder is outside `static/`, so that route is the only address they have.

Each file comes from an image on <https://odin-diagnostics.com/>, used with ODIN's
agreement. The two logos are the original files. The other five are smaller
copies, because the originals are between 1.9 and 4.4 MB each.

| File | From the current site | Shows |
| --- | --- | --- |
| `logo-dark.svg` | `/images/logo/Odin-With-Text-Black.svg` | The ODIN mark and name in black, for light backgrounds |
| `logo-light.svg` | `/images/logo/Odin-With-Text-White.svg` | The ODIN name in white with the mark in black |
| `hero-headset-lens.webp` | `/images/hero/vr_green.png` | A close view of a headset lens in green light. It opens the home page, beside the first words |
| `headset-lens-close.webp` | `/images/hero/vr_green.png` | The same headset lens, closer. It sits beside the mission on the About page |
| `product-headset.jpg` | `/images/capabilities/V3_ODIN2.jpg` | The ODIN headset |
| `eye-tracking.webp` | `/images/eyetracking/EyeOpen.gif` | A short loop of two eyes opening |
| `partner-evonexus.png` | `/images/about/evo_nexus.png` | The EvoNexus logo in white, on a clear background |

## What was changed

Size and file type. The hero photo also has a thin line trimmed from its top and bottom edges.

- The hero photo is 1920 pixels wide. The original has a thin grey line along its top edge
  and a white one along its bottom edge. Two rows of pixels are trimmed from the top and six
  from the bottom, out of 2820, so both are gone. It is saved at a high quality setting,
  because a lower one left bands in the dark parts of the picture.
- The lens close-up is a square cut from the right of the hero photo's original, around the
  lens, 1200 pixels each way. It is saved at the same high quality setting, for the same reason.
- The headset photo is 1600 pixels wide.
- The eye loop has the same 46 frames and timing as the original GIF, saved as an
  animated WebP at about an eighth of the size.
- The EvoNexus logo is 600 pixels square.

## Things to know

- The hero photo's original, which the lens close-up is also cut from, was checked for a credit
  before it was added. Its embedded information holds three dates, all 20 August 2024, and no
  photographer, copyright or license. Ask ODIN where the photo came from. If it is a stock
  photo, its license has to cover this site.
- `logo-light.svg` is ODIN's own file, and its mark is black, so on a dark
  background only the name shows clearly. Ask ODIN for a version with a white mark.
- Two images on the current site are left out. `logo-2.svg` is a leftover logo
  from a website template, not ODIN's. `download (1).png` is a LinkedIn icon.
- The four photos of the team in `/images/about/` are left out too. The rebuilt
  site does not list the team.

## Adding an image

Put a web-sized file here with a lowercase name of words joined by hyphens, and
add it to the table. The route serves only `.svg`, `.png`, `.jpg`, `.jpeg`,
`.gif` and `.webp` files from this folder (`model/odin_image.py`).
`python scripts/verify/verify_odin_images.py` checks the folder: the names, the
table, a 1 MB limit on each file, and that an SVG holds no script and loads
nothing from another site.
