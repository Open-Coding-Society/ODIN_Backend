# dataconfigs (model/dataconfigs/)

The values that make this deployment *this* deployment, kept as data instead of code. A school or
organisation that forks OCS changes the files here, not the Python. Code that decides who may do
something, or what a form offers, reads these files; it does not name a role, a school or an email domain itself.

| File | What it holds | Read by | Served to the pages by |
|---|---|---|---|
| `account_types.json` | The kinds of account, their roles, who counts as staff, how long a verification lasts, what each type may do, and how each behaves on the sign-up form | `model/account_types.py` | `GET /api/signup-options` (the form's part only) |
| `schools.json` | The schools a student can choose at sign-up | `model/schools.py` | `GET /api/signup-options` |
| `permissions.json` | Who may make each request: open to anyone, any signed-in account, or only some roles | `model/permissions.py` | not sent |
| `odin_site.json` | The basics of the ODIN Diagnostics website: the company name, its tagline, its contact details, its logos and the footer's links and copyright line | `model/odin_site.py` | `GET /api/odin/site` (from the saved row) |
| `odin_page_list.json` | The pages of the ODIN Diagnostics website in menu order: each page's title, description and menu words | `model/odin_page.py` | `GET /api/odin/pages` and `GET /api/odin/page?name=<page>` (from the saved rows) |
| `odin_pages.json` | The sections of each page of the ODIN Diagnostics website, in the order the page shows them | `model/odin_section.py` | `GET /api/odin/page?name=<page>` (from the saved rows) |

Each file is added to this folder in the change that makes its values data. Data files that are not
here yet: `model/presence_schedules.json`, the starter bell schedules for the presence system.

## How they are loaded

- **Once, at startup.** The files here are read and checked when the app starts. **A change needs a
  restart**, and in production a redeploy, because the files are copied into the image.
- **Bad data stops the app at startup**, with a message naming the file and the field
  (`account_types.json: guest.lifetime_hours must be a whole number, 1 or more`). That is on
  purpose: a typo fails where you see it, not later on somebody's login. The rules are in the
  `_check` function of each loader.

## account_types.json

Top level:

| Key | Meaning |
|---|---|
| `admin_role` | The one role that can do everything, and the only one that can make another account an Admin. Must be one of `staff_roles`. |
| `staff_roles` | Roles that manage accounts. They see the staff controls in Account Administration and can use the staff endpoints. |
| `essential_roles` | Roles of which at least one active account must always remain. |
| `verification_interval_days` | How long a verification stays current, and the most a Teacher/Admin can grant. |
| `default_verification_days` | The number suggested when a Teacher/Admin is asked how long to verify for. |
| `verification_exempt_roles` | Roles that are never re-verified. |
| `default_account_type` | The type used when a sign-up names none, or one that is not listed. It must be offered on the sign-up form (have a `signup_label`). |
| `account_types` | The types, by name. See below. |

Each entry in `account_types` has a `role` (every type needs its own) and any of these. The comments
at the top of `model/account_types.py` are the full reference; the groups are:

- **Who it is:** `google_verified_domains` (an email in one of these, verified by Google, activates the
  account at sign-up), `staff_created`, `verification_days`.
- **Limits:** `github_check` (default true), `active_on_signup`, `lifetime_hours`,
  `allowed_requests` (the only `"METHOD /path"` requests the type may make),
  `requests_per_minute`.
- **The Guest Window:** `requires_open_window` (the type can be created or come back only while a
  Teacher/Admin has the window open) and `window_max_minutes`.
- **Spring:** `spring_role` (the role Spring is told these accounts have at login, such as `ROLE_MENTOR`: granted while the account is active, taken away when it is not; see `model/role_attestation.py`). Never an Admin or Teacher role.
- **The sign-up form:** `signup_label` (offered, with this text; a type without one is not offered),
  `signup_note`, `asks_school`, `email_required`, `spring_account`, and for the Google step `google_signin_domains` (the email domains the form accepts, which can be more than the ones that activate at once) and `google_prompt`.

A type that skips the GitHub check must have a list of allowed requests and the Guest Window, and its
role cannot be a staff role. The loader refuses anything else.

## schools.json

A list of `{"name": ..., "label": ...}`. The **name** is saved on the account; the **label** is what the
form shows. Names must be unique. Nothing checks an account's school against the list: it is what the
form offers, not a rule about who can have an account.

## permissions.json

One file that answers "who may call this?" for every request the app has. A request is written
`"METHOD route"`, with the route as Flask knows it: `"GET /api/id"`, `"POST /api/user/<string:uid>/verify"`.
Every request is in exactly one of these lists. **A request in none of them is one nobody may make.**

| List | Who may make the request |
|---|---|
| `public` | Anyone, with or without an account, on purpose: the home page, login, sign-up. |
| `public_restricted` | Anyone, on purpose, but the route runs code or spends a provider's credit. Nothing goes here until it has been reviewed to run in a sandbox and under a rate limit. Empty today. |
| `legacy_open` | Anyone, because it has always been so and nobody has yet decided that it should be. Groups of requests, each with an `owner` and a `review_by` date. The aim is for this list to get shorter: each request moves to `public`, or to a list that needs an account. |
| `device_key` | A device that sends the device key. The route checks the key. |
| `session` | A page behind the Flask session login. |
| `signed_in` | Any active account. |
| `roles` | For each role, the requests only some roles may make. A request for Teachers and Admins is in both lists. |

`open_in_development` is not a list of its own kind: it names requests that are open while `IS_PRODUCTION`
is not true. Each must also be in `signed_in` or `roles`, which says who may make it in production.

**Today the file describes the guards; it does not replace them.** It is checked against the code, and nothing
reads it to refuse a request yet. A check written inside a route (an account may change only its own record)
stays in the route.

The loader refuses a request that is in two lists, a role that `account_types.json` does not have, an entry
that is not `"METHOD /route"`, and a `legacy_open` group with no owner or date.

`python scripts/verify/verify_permissions.py` is the check to run whenever a route is added or changed. It fails when:

- a route has no entry, or an entry has no route;
- the file and the guard on a route say different things, in development or in production;
- a request not listed as open answers a caller with no account, when really called;
- a `legacy_open` group is past its `review_by` date.

It calls the routes on a throwaway copy of the app with no network and no provider keys
(`scripts/rbac/rbac_prober.py`), so it is safe to run anywhere.

## odin_site.json

The basics every page of the ODIN Diagnostics website shows. `FIELDS` in `model/odin_site.py` lists
each key with what it holds and its size:

- Text: `name`, `tagline`, `phone`, `email`, `address`, `copyright`.
- Links, which must be full `https://` addresses: `instagram`, `linkedin`.
- Images, which must name a file in `odin/images/`: `logo_dark` (the logo in black, for light
  backgrounds) and `logo_light` (the name in white, for dark backgrounds; its mark is black, see
  `odin/images/README.md`).

Every key is required and must not be blank.

This file is a seed, so it is loaded differently from the files above. It is not read at startup. It
gives the `odin_site` table its one row, and after that only fills in fields that row has no text for:

- `scripts/db_init.py` seeds it when it builds or rebuilds a database, so a rebuild picks up an edited file.
- `scripts/db_upgrade.py` adds the table, or a column added later, to an existing database but does
  not seed it. Run `python scripts/init_odin_site.py` afterwards. Until then `GET /api/odin/site`
  answers 404 for a missing row, and `null` for a field that has no text yet.
- After deploying code that adds a field, run `db_upgrade.py` right away. Until the column exists
  the route answers 500, as any query of a table with a missing column does.

`GET /api/odin/site` serves the saved row. Text that is saved is never replaced, so editing a value in
the file does not change a database that already has one, and a row with nothing missing is left
alone without the file being read. Bad data stops the seed with a message naming the file and the
field (`odin_site.json: phone is required`).

The route is also in the guest account type's `allowed_requests` in `account_types.json`, so a visitor
who is signed in as a guest still gets the site's text.

`python scripts/verify/verify_odin_site.py` checks the seed and the route.

## odin_page_list.json

The pages of the ODIN Diagnostics website, as a list in menu order:

```json
[ { "name": "home", "title": "ODIN Diagnostics", "description": "...", "menu": "Home" } ]
```

`FIELDS` in `model/odin_page.py` lists each key with its size:

- `name` is the page's name, which no other page has. It follows the same rule as a page name in
  `odin_pages.json`, and the two files use the same names.
- `title` is the page's name in the browser tab. It is required.
- `description` is one line about the page, for search results and link previews.
- `menu` is the page's words in the site menu. A page without them is not in the menu.

The frontend knows each page's address. Everything a visitor reads about a page comes from here.

Like the other ODIN files, this one is a seed and follows the same steps: `scripts/db_init.py`
seeds it, and after `scripts/db_upgrade.py` adds the `odin_page` table, run
`python scripts/init_odin_site.py`. A new page is added, a saved page gets only the keys it has
no text for, and the pages take the file's order. A saved page the file no longer has is kept,
after the file's pages. Saved text is never replaced. Bad data stops the
seed with a message naming the file and the page (`odin_page_list.json: page 2: title is required`).

`GET /api/odin/pages` sends `{"pages": [...]}` in menu order, each page with its `name` and every
key in `FIELDS` (`null` for one it has nothing for), and answers 404 before the seed has run.
`GET /api/odin/page?name=<page>` sends the page's `title` and `description` with its sections. A
page is in this list and has sections in `odin_pages.json`: with only one of the two, the route
answers 404. Both routes are public and in the guest account type's `allowed_requests`.

After deploying this code, run `db_upgrade.py` and then `init_odin_site.py` right away. Until the
`odin_page` table exists both routes answer 500, as any query of a missing table does, and until
it is seeded they answer 404.

`python scripts/verify/verify_odin_page_list.py` checks the seed and the routes.

## odin_pages.json

The sections of each page of the ODIN Diagnostics website. The file is an object with one key per
page. Each page is the list of its sections, in the order the page shows them:

```json
{ "home": [ { "name": "hero", "title": "...", "text": "..." },
            { "name": "statistics", "items": [ { "title": "50%", "text": "..." } ] } ] }
```

A page's name and a section's name are at most 40 lowercase letters, digits and underscores, and
start with a letter (`how_it_works`). A section needs a `name` that no other section of its page
has. Every other part is optional. `FIELDS` in `model/odin_section.py` lists each part with what it
holds and its size:

- Text: `kicker` (the short line above the title), `title`, `text` and `action` (the words on the
  section's button; where the button leads is up to the page).
- `image` names a file in `odin/images/`, and `image_alt` says what it shows. Give both or neither.
- `items` is a list for a section that shows several of one thing, such as statistics or features.
  Each item needs a `title` and a `text`. Leave `items` out of a section that has no list.

A section needs a title, text, an image or items. A part that is not listed here is refused, so a
misspelled one is not dropped without a word. So is a key given twice in one object.

Like `odin_site.json`, this file is a seed. It is not read at startup:

- `scripts/db_init.py` seeds it when it builds or rebuilds a database.
- `scripts/db_upgrade.py` adds the `odin_section` table to an existing database but does not seed
  it. Run `python scripts/init_odin_site.py` afterwards. Until then `GET /api/odin/page?name=home`
  answers 404.
- After deploying this code, run `db_upgrade.py` right away. Until the table exists the route
  answers 500, as any query of a missing table does.

Seeding again is safe. The whole file is checked before anything is saved. Then all of it is saved,
or none:

- A section the database does not have is added.
- A section it already has keeps its saved text. Only its empty parts are filled in. So a part
  added to the file later reaches the database, but changing wording in the file does not change
  text that is already saved.
- The file decides the order of a page's sections.
- A section that was removed from the file, or renamed in it, stays in the database and on the
  page. Delete its row to take it off.

To change wording a database already holds, change it in the file and in the saved row (a database
update). Bad data stops the seed with a message naming the file, the page and the section by its
place on the page (`odin_pages.json: home section 2: item 1: text is required`).

`GET /api/odin/page?name=<page>` sends `{"page": ..., "title": ..., "description": ..., "sections": [...]}`. Each section has its
`name`, every part in `FIELDS` (`null` for one it has nothing for) and its `items` (an empty list
when it has none). The route is public and is in the guest account type's `allowed_requests`, like
the site basics. `python scripts/verify/verify_odin_pages.py` checks the seed and the route.

## What the sign-up page is told

`GET /api/signup-options` is public, because the form is shown to people with no account. It sends the
schools, the offered account types with how each behaves, and the type to start on. It sends nothing about roles, lifetimes or limits. The pages build the form from it. They keep their
own list of schools and of the student and mentor types, used only when Flask cannot be asked (an older Flask, an error), so sign-up
never ends up with nothing to choose.

## Changing something

1. **Add a school:** add an entry to `schools.json`, restart.
2. **Add an account type:** add it to `account_types.json` with its own `role` and, to offer it on the
   form, a `signup_label`. Say how it behaves with the flags above. Restart. No page change.
3. **Rename a role** (say `Teacher` becomes `Instructor`): change it in `staff_roles`, in the type, and in
   the accounts already saved (a database update: roles are stored on each account). Code does not name
   the roles, so that is all.
4. **Add or change a route:** add its request to the list that says who may make it in `permissions.json`,
   and guard the route to match (`@token_required()` for `signed_in`, `@token_required([...])` for `roles`).
   `python scripts/verify/verify_permissions.py` fails until the two agree. A new route goes in `public` only when it
   is meant for people with no account, and never in `legacy_open`.
5. **Run the checks** from the repo root, each against a throwaway database:
   `python scripts/verify/verify_signup_options.py` (what the form is told),
   `python scripts/verify/verify_account_admin.py`,
   `python scripts/verify/verify_activation.py`,
   `python scripts/verify/verify_dataconfigs.py` (that these files are here and explained),
   `python scripts/verify/verify_permissions.py` (that `permissions.json` matches the routes). Set
   `DEFAULT_PASSWORD`, `ADMIN_PASSWORD`, `TEACHER_PASSWORD`, `USER_PASSWORD` and `MY_PASSWORD` to
   passwords that follow the password rule if your `.env` has weak ones.

## What does not belong here

- **Secrets and per-environment values** (keys, passwords, URLs, the seeded accounts): those are
  environment variables, in `.env`.
- **Anything about one person.** These files are the same for everyone.
- **Spring.** The Java backend has its own roles and settings and does not read these files yet.

## Not yet data

Still in code, and candidates to move here: the default role `"User"` in the model and the restore code,
`User.is_teacher()`, the seeded accounts' roles, the password rule (it must stay in step with Spring's),
the starter sections (CSP, CSSE, CSA), and the allowed origins for cross-origin requests.
