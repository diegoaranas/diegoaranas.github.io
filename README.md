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
tools/publish.py      Splices a draft's PDF and entry into research/index.html
```

## Editing

Edit the HTML, commit, push. Pages redeploys in about a minute. There is no
build step and nothing to install.

## Draft papers

Draft entries on the Research page are **not edited here**. Each paper lives in
its own private repo, which carries a `publish/` folder (`publish.env` naming
the PDF to publish and its label, `entry.html` with the title and abstract) and
a manual GitHub Actions workflow. Running that workflow checks out this repo,
runs `tools/publish.py`, and pushes the result:

- the PDF lands at `files/<slug>.pdf`;
- the entry is spliced into `research/index.html` between
  `<!-- draft:<slug> -->` and `<!-- /draft:<slug> -->`, right after the
  `<!-- drafts -->` marker on first publish, in place afterwards.

Running the workflow with `action=unpublish` removes both again. The draft
repos authenticate with a fine-grained token (secret `SITE_DEPLOY_TOKEN`)
scoped to this repository only, Contents read and write.
