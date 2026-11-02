# diegoaranasegura.com

Personal academic site. Plain HTML, one stylesheet and one small script, served
by GitHub Pages from this repo's `main` branch with the custom domain in
`CNAME`.

```
index.html            Home
research/index.html   Papers and conference presentations
cv/index.html         CV (embeds files/cv.pdf)
contact/index.html    Contact
misc/index.html       Technical projects
talks/<slug>/         Talk handouts: unlinked pages, filled by tools/publish.py
style.css             The only stylesheet (light and dark)
nav.js                Collapses the menu behind a toggle on narrow screens
files/                PDFs: cv.pdf plus one PDF per published draft
assets/               Profile photo, favicon
tools/publish.py      Splices a published PDF and its block into a page
tools/deposit.py      Prepares preprint-archive deposits and records them
papers/               paper.toml for papers that have no repo of their own
```

## Editing

Edit the HTML, commit, push. Pages redeploys in about a minute. There is no
build step and nothing to install.

## Stats

Page views come from [GoatCounter](https://diegoaranasegura.goatcounter.com/):
a `<script>` tag in the `<head>` of every page. A second inline script there
counts clicks on any `.pdf` link (CV, drafts) as an event named after the
file path, so PDF opens from the site show up under Events. New pages need the
same two tags copied in, plus the `/nav.js` script tag and the header (with its
`nav-toggle` button) from an existing page.

## Published files (draft papers, CV)

The draft entries on the Research page and the block on the CV page are **not
edited here**. Each paper lives in its own private repo, and so does the CV; each
carries a `publish/` folder (`publish.env` naming the PDF to publish, its label
and, for the CV, the target page; `entry.html` with the HTML block) and a manual
GitHub Actions workflow. Running that workflow checks out this repo, runs
`tools/publish.py`, and pushes the result:

- the PDF lands at `files/<slug>.pdf`;
- the block is spliced into the target page between
  `<!-- published:<slug> -->` and `<!-- /published:<slug> -->`, right after the
  `<!-- published -->` marker on first publish, in place afterwards.

Running the workflow with `action=unpublish` removes both again. The source
repos authenticate with a fine-grained token (secret `SITE_DEPLOY_TOKEN`)
scoped to this repository only, Contents read and write.

A paper's `publish/` folder holds a single `publish/paper.toml` instead of
`publish.env` and `entry.html`: the PDF, the label, and the paper's metadata
(title, authors with ORCIDs, abstract, keywords, status, archive records), from
which `publish.py` renders the entry. The schema is at the top of
`tools/deposit.py`. A paper with no repo of its own (*Equivalence and Theory
Expansion*) keeps its `paper.toml` under `papers/<slug>/publish/` here and is
rebuilt locally:

```
python tools/publish.py --action publish --draft papers/equivalencetheoryexpansion --site .
```

## Preprint archives

Every public paper also goes on PhilSci-Archive or PhilArchive, or both
(`[archive] targets` in its `paper.toml`; the first is the primary). Once a
paper has an id on its primary archive, its Research entry links to that
archive's record page, with the local PDF after it.

Nothing here logs in to or submits to an archive: uploading is done by hand.
Neither archive documents a deposit API (PhilPapers' API is read-only), so none
is used.

The workflow, from this repo, with `<paper>` the paper's checkout (e.g.
`../../Writing/2026 The Statistical Mechanical Empire and its Detractors`):

1. **See what is needed:** `python tools/deposit.py status <paper> ...`. Each
   archive shows *not deposited*, *up to date*, or *NEEDS NEW VERSION* (the
   PDF's hash differs from the one deposited). The script won't queue a paper
   that isn't on the site, has a coauthor who hasn't given an OK
   (`coauthor_ok = true` on that author), or is published or under review with
   `publisher_policy = "unchecked"`.
2. **Build the package:** `python tools/deposit.py package <paper>`. This
   writes `~/deposit-packages/<slug>/<archive>/`: the PDF, `metadata.txt`
   (the form's fields, ready to paste, with suggested subjects) and
   `CHECKLIST.txt`. The packages stay out of every repo. A paper going to both
   archives is packaged for PhilArchive only once its PhilSci-Archive id is
   recorded, so the PhilArchive (PhilPapers) entry can point at the
   PhilSci-Archive record. A new version of an existing record goes through
   the record's own new-version route; never a fresh deposit.
3. **Upload by hand** in the browser, following the checklist.
4. **Paste the id back:**
   `python tools/deposit.py record <paper> --archive philsci --id 12345`.
   This writes the id, the record URL, a version number (one more than the
   last), today's date and the PDF's hash into `paper.toml`. Pass `--pdf` if
   the uploaded file isn't the paper's `pdf`, and `--version`/`--date` to
   override.
5. **Rebuild:** commit `paper.toml` in the paper's repo and run its `publish`
   workflow. For a paper under `papers/`, run `publish.py` as above and commit
   here.

`publish.py` also warns when it publishes a PDF that differs from a deposited
one.
