# ODIN site images

The images the ODIN Diagnostics website shows. They are content, so the frontend
keeps no copy: a page loads each one from `GET /api/odin/image?name=<file name>`.

Each file is a web-sized copy of an image on <https://odin-diagnostics.com/>,
used with ODIN's agreement. The originals are much larger and are not kept here.

| File | From the current site | Shows |
| --- | --- | --- |
| `logo-dark.svg` | `/images/logo/Odin-With-Text-Black.svg` | The ODIN logo in black, for light backgrounds |
| `logo-light.svg` | `/images/logo/Odin-With-Text-White.svg` | The ODIN logo in white, for dark backgrounds |
| `product-headset.jpg` | `/images/capabilities/V3_ODIN2.jpg` | The ODIN headset |
| `eye-tracking.webp` | `/images/eyetracking/EyeOpen.gif` | A short loop of eyes being tracked |
| `team-connor-heffler.jpg` | `/images/about/connor_heffler_square.JPG` | Connor Heffler |
| `team-marina-zellers.webp` | `/images/about/marina_zellers.jpeg` | Marina Zellers |
| `team-michael-noon.webp` | `/images/about/michael_noon.jpeg` | Michael Noon |
| `team-connor-fourt.webp` | `/images/about/connor_fourt.jpeg` | Connor Fourt |
| `partner-evonexus.png` | `/images/about/evo_nexus.png` | The EvoNexus logo in white, on a clear background |

## What was changed

Only size and file type. The two logos are the original files.

- The headset photo is 1600 pixels wide and the team photos are 640 pixels square.
- Three team photos are round with clear corners, so they are WebP, which keeps the
  clear corners at a small size.
- The eye loop has the same 46 frames and timing as the original GIF, saved as an
  animated WebP at about an eighth of the size.
- The EvoNexus logo is 600 pixels square.

## Adding an image

Put a web-sized file here with a lowercase name of words joined by hyphens, and
add it to the table. The route serves only `.svg`, `.png`, `.jpg`, `.jpeg`,
`.gif` and `.webp` files from this folder (`model/odin_image.py`), and each one
must stay under 1 MB. Run `python scripts/verify/verify_odin_images.py`.

An SVG must not hold scripts or load anything from another site.
