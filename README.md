# diegoaranasegura.com

Personal academic site. Plain HTML and one stylesheet, served by GitHub Pages
from this repo's `main` branch with the custom domain in `CNAME`.

```
index.html            Home
research/index.html   Papers and conference presentations
cv/index.html         CV (embeds files/cv.pdf)
contact/index.html    Contact
misc/index.html       Technical projects
style.css             The only stylesheet (light and dark)
files/                PDFs: cv.pdf plus one PDF per published draft
assets/               Profile photo, favicon
tools/publish.py      Splices a published PDF and its block into a page
```

## Editing

Edit the HTML, commit, push. Pages redeploys in about a minute. There is no
build step and nothing to install.

## Stats

Page views come from [GoatCounter](https://diegoaranasegura.goatcounter.com/):
a `<script>` tag in the `<head>` of every page. A second inline script there
counts clicks on any `.pdf` link (CV, drafts) as an event named after the
file path, so PDF opens from the site show up under Events. New pages need the
same two tags copied in.

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
