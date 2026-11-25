# ODIN site images

The images the ODIN Diagnostics website shows. They are content, so the frontend
keeps no copy: a page loads each one from `GET /api/odin/image?name=<file name>`.
This folder is outside `static/`, so that route is the only address they have.

Each file comes from an image on <https://odin-diagnostics.com/>, used with ODIN's
agreement. The two logos and the site icon are the original files. The other
seven are smaller copies, because the originals are between 1.5 and 4.4 MB each.

| File | From the current site | Shows |
| --- | --- | --- |
| `logo-dark.svg` | `/images/logo/Odin-With-Text-Black.svg` | The ODIN mark and name in black, for light backgrounds |
| `logo-light.svg` | `/images/logo/Odin-With-Text-White.svg` | The ODIN name in white with the mark in black |
| `site-icon.png` | `/android-chrome-192x192.png` | The ODIN mark in black on white, 192 pixels square. The icon a browser shows on the tab |
| `hero-headset-lens.webp` | `/images/hero/vr_green.png` | A close view of a headset lens in green light. The original site puts it behind the opening text of its home page |
| `product-headset.jpg` | `/images/capabilities/V3_ODIN2.jpg` | The ODIN headset |
| `eye-tracking.webp` | `/images/eyetracking/EyeOpen.gif` | A short loop of two eyes opening |
| `team-marina-zellers.webp` | `/images/about/marina_zellers.jpeg` | Marina Zellers |
| `team-michael-noon.webp` | `/images/about/michael_noon.jpeg` | Michael Noon |
| `team-connor-fourt.webp` | `/images/about/connor_fourt.jpeg` | Connor Fourt |
| `partner-evonexus.png` | `/images/about/evo_nexus.png` | The EvoNexus logo in white, on a clear background |

## What was changed

Size and file type. The lens photo also has a thin line trimmed from its top and bottom edges.

- The lens photo (`hero-headset-lens.webp`) is 1920 pixels wide. The original has a thin grey line along its top edge
  and a white one along its bottom edge. Two rows of pixels are trimmed from the top and six
  from the bottom, out of 2820, so both are gone. It is saved at a high quality setting,
  because a lower one left bands in the dark parts of the picture.
- The headset photo is 1600 pixels wide and the team photos are 640 pixels square.
- The team photos came round, with clear corners. Their files on the site are
  PNG images named `.jpeg`. They are WebP here, which keeps the clear corners at
  a small size.
- The eye loop has the same 46 frames and timing as the original GIF, saved as an
  animated WebP at about an eighth of the size.
- The EvoNexus logo is 600 pixels square.

## Things to know

- The lens photo's original was checked for a credit before it was added. Its embedded
  information holds three dates, all 20 August 2024, and no photographer, copyright or
  license. Ask ODIN where the photo came from. If it is a stock photo, its license has to
  cover this site.
- `logo-light.svg` is ODIN's own file, and its mark is black, so on a dark
  background only the name shows clearly. Ask ODIN for a version with a white mark.
- Connor Heffler's photo is not here yet. The file on the current site
  (`/images/about/connor_heffler_square.JPG`) is marked "Photo by Ruby Wallau for
  CIE", copyright Ruby Wallau 2024. It can be added once ODIN confirms that the
  photographer's permission covers this site, with the credit kept.
- Two images on the current site are left out. `logo-2.svg` is a leftover logo
  from a website template, not ODIN's. `download (1).png` is a LinkedIn icon.

## Adding an image

Put a web-sized file here with a lowercase name of words joined by hyphens, and
add it to the table. The route serves only `.svg`, `.png`, `.jpg`, `.jpeg`,
`.gif` and `.webp` files from this folder (`model/odin_image.py`).
`python scripts/verify/verify_odin_images.py` checks the folder: the names, the
table, a 1 MB limit on each file, and that an SVG holds no script and loads
nothing from another site.
