#!/usr/bin/env python3
"""Publish (or unpublish) a PDF and its page entry from a private repo onto this site.

Run by the `publish` GitHub Actions workflow that lives in each source repo
(the paper drafts, the CV).  It never runs on the site itself.  Usage:

    python3 tools/publish.py --action publish   --draft <checkout> --site <checkout>
    python3 tools/publish.py --action unpublish --draft <checkout> --site <checkout>

The source checkout must contain a `publish/` folder holding either
`publish/paper.toml` (a paper: all its metadata in one file, see below) or
these two files (the CV, talk handouts):

    publish/publish.env    KEY=VALUE lines:
                             SLUG   name on the site: the PDF is served at /files/<SLUG>.pdf
                             PDF    path of the PDF inside the source repo
                             LABEL  short text shown on the site, e.g. "March 2026"
                             PAGE   (optional) page to splice into, default research/index.html
    publish/entry.html     the HTML snippet for that page; {{SLUG}}, {{LABEL}} and
                           {{VERSION}} are substituted.  VERSION is a short hash of
                           the PDF: link to /files/{{SLUG}}.pdf?v={{VERSION}} so
                           browsers fetch the new file instead of a cached one

    publish/paper.toml     slug, pdf, label, page play the roles of the
                           publish.env keys; the entry is rendered from title,
                           journal, abstract, final_url and [archive]. Once the
                           primary archive (first of archive.targets) has an id,
                           the entry links to its record page ahead of the local
                           PDF. site_pdf = false serves no local copy. The full
                           schema is documented in tools/deposit.py.

What happens on publish:
  * <source>/<PDF>  is copied to  <site>/files/<SLUG>.pdf
  * the entry is spliced into <site>/<PAGE> between
    <!-- published:<SLUG> --> and <!-- /published:<SLUG> -->, replacing an
    existing block or inserting a new one right after the <!-- published -->
    marker.
On unpublish both are removed.  Committing and pushing is the workflow's job.
"""
import argparse
import hashlib
import html as htmllib
import re
import shutil
import sys
import tomllib
from pathlib import Path
from typing import NoReturn

MARKER = "<!-- published -->"
DEFAULT_PAGE = "research/index.html"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
FORBIDDEN = re.compile(r"<\s*(script|iframe|embed|link|meta|style)\b", re.I)
OBJECT_DATA = re.compile(r"<\s*object\b[^>]*?\bdata\s*=\s*[\"']([^\"']*)[\"']", re.I)
# archive name in paper.toml -> (link text, record-page URL)
ARCHIVES = {
    "philsci": ("PhilSci-Archive", "https://philsci-archive.pitt.edu/{id}/"),
    "philarchive": ("PhilArchive", "https://philarchive.org/rec/{id}"),
}


def die(msg: str) -> NoReturn:
    print(f"publish.py: {msg}", file=sys.stderr)
    sys.exit(1)


def read_paper(path: Path) -> dict:
    """Load a paper.toml, filling in defaults; shared with deposit.py."""
    try:
        paper = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as e:
        die(f"{path}: {e}")
    for key in ("slug", "title", "label"):
        if not paper.get(key):
            die(f"{path} must set {key}")
    paper.setdefault("site_pdf", True)
    paper.setdefault("pdf", "")
    paper.setdefault("authors", [])
    if paper["site_pdf"] and not paper["pdf"]:
        die(f"{path} must set pdf when site_pdf is true")
    archive = paper.setdefault("archive", {})
    archive.setdefault("targets", [])
    for name in archive["targets"]:
        if name not in ARCHIVES:
            die(f"{path}: unknown archive {name!r} (known: {', '.join(ARCHIVES)})")
        archive.setdefault(name, {})
    return paper


def record_url(name: str, rec: dict) -> str:
    return rec.get("url") or ARCHIVES[name][1].format(id=rec["id"])


def render_entry(paper: dict) -> str:
    """A paper.toml's Research-page entry, in the same markup as the page's others."""
    def esc(text):
        return htmllib.escape(str(text), quote=False)
    if paper.get("journal"):
        venue = f"<em>{esc(paper['journal'])}</em>, {{{{LABEL}}}}"
    else:
        venue = "Draft of {{LABEL}}"
    links = []
    targets = paper["archive"]["targets"]
    if targets and paper["archive"][targets[0]].get("id"):
        rec = paper["archive"][targets[0]]
        links.append((record_url(targets[0], rec), ARCHIVES[targets[0]][0]))
    if paper["site_pdf"]:
        links.append(("/files/{{SLUG}}.pdf?v={{VERSION}}", "PDF"))
    if paper.get("final_url"):
        links.append((paper["final_url"], "Final"))
    lines = [
        '<article class="entry">',
        f"  <h3><em>{esc(paper['title'])}</em></h3>",
        f'  <p class="venue">{venue}</p>',
    ]
    if paper.get("abstract", "").strip():
        lines += [
            "  <details>",
            "    <summary>Abstract</summary>",
            f"    <p>{esc(' '.join(paper['abstract'].split()))}</p>",
            "  </details>",
        ]
    if links:
        lines.append('  <p class="links">')
        lines += [f'    <a href="{htmllib.escape(href)}">{text}</a>' for href, text in links]
        lines.append("  </p>")
    lines.append("</article>")
    return "\n".join(lines)


def read_env(path: Path) -> dict:
    """publish.env as a dict; a paper.toml beside it takes its place (key "paper")."""
    toml_path = path.with_name("paper.toml")
    if toml_path.is_file():
        paper = read_paper(toml_path)
        env = {"SLUG": paper["slug"], "PDF": paper["pdf"], "LABEL": paper["label"],
               "PAGE": paper.get("page", DEFAULT_PAGE), "paper": paper}
    else:
        if not path.is_file():
            die(f"missing {path} (or paper.toml)")
        env = {}
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                die(f"bad line in {path.name}: {raw!r}")
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
        for key in ("SLUG", "PDF", "LABEL"):
            if not env.get(key):
                die(f"{path.name} must set {key}")
    if not SLUG_RE.match(env["SLUG"]):
        die(f"SLUG {env['SLUG']!r} must be lowercase letters, digits and hyphens")
    env.setdefault("PAGE", DEFAULT_PAGE)
    page = env["PAGE"].replace("\\", "/")
    if page.startswith("/") or ".." in page.split("/") or not page.endswith(".html"):
        die(f"PAGE {env['PAGE']!r} must be a relative .html path inside the site")
    env["PAGE"] = page
    return env


def block_bounds(html: str, slug: str, page: str):
    """Span of the published block including its indentation and trailing newline."""
    start = html.find(f"<!-- published:{slug} -->")
    if start != -1:
        start = html.rfind("\n", 0, start) + 1
    end_tag = f"<!-- /published:{slug} -->"
    end = html.find(end_tag)
    if (start == -1) != (end == -1):
        die(f"{page} has an unbalanced published:{slug} block")
    if start == -1:
        return None
    if end < start:
        die(f"{page} has a reversed published:{slug} block")
    end += len(end_tag)
    # swallow the trailing newline so removal leaves no blank line behind
    if html[end:end + 1] == "\n":
        end += 1
    return start, end


def check_entry(entry: str, slug: str) -> None:
    if FORBIDDEN.search(entry):
        die("entry.html may not contain script, iframe, embed, link, meta or style tags")
    if "<" not in entry:
        die("entry.html must contain some HTML")
    objects = re.findall(r"<\s*object\b", entry, flags=re.I)
    datas = OBJECT_DATA.findall(entry)
    if len(objects) != len(datas) or any(d.split("?", 1)[0] != f"/files/{slug}.pdf" for d in datas):
        die(f"an <object> in entry.html may only embed /files/{slug}.pdf")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", choices=["publish", "unpublish"], required=True)
    ap.add_argument("--draft", type=Path, required=True, help="source repo checkout")
    ap.add_argument("--site", type=Path, required=True)
    ap.add_argument("--summary", type=Path, help="write a one-line commit message here")
    args = ap.parse_args()

    env = read_env(args.draft / "publish" / "publish.env")
    slug, label = env["SLUG"], env["LABEL"]
    page = args.site / env["PAGE"]
    pdf_dst = args.site / "files" / f"{slug}.pdf"
    if not page.is_file():
        die(f"missing {page}")
    with page.open(encoding="utf-8", newline="") as fh:
        html = fh.read()
    if "\r" in html:
        die(f"{env['PAGE']} must use LF line endings")
    if MARKER not in html:
        die(f"{env['PAGE']} has no {MARKER} marker")

    paper = env.get("paper")
    copy_pdf = paper["site_pdf"] if paper else True

    if args.action == "publish":
        pdf_src = args.draft / env["PDF"] if env["PDF"] else None
        if copy_pdf:
            if not pdf_src or not pdf_src.is_file():
                die(f"PDF not found: {env['PDF']}")
            if pdf_src.read_bytes()[:5] != b"%PDF-":
                die(f"{env['PDF']} is not a PDF")
        if paper:
            entry = render_entry(paper)
        else:
            entry_path = args.draft / "publish" / "entry.html"
            if not entry_path.is_file():
                die("missing publish/entry.html")
            with entry_path.open(encoding="utf-8", newline="") as fh:
                entry = fh.read().replace("\r\n", "\n")
            entry = re.sub(r"<!--.*?-->", "", entry, flags=re.S).strip("\n")
        digest = ""
        if pdf_src and pdf_src.is_file():
            digest = hashlib.sha256(pdf_src.read_bytes()).hexdigest()
        version = digest[:8]
        if paper and digest:
            for name in paper["archive"]["targets"]:
                deposited = paper["archive"][name].get("sha256")
                if deposited and deposited != digest:
                    print(f"publish.py: {env['PDF']} differs from the version deposited on "
                          f"{ARCHIVES[name][0]}: it needs a new version uploaded there",
                          file=sys.stderr)
        entry = (entry.replace("{{SLUG}}", slug).replace("{{LABEL}}", label)
                      .replace("{{VERSION}}", version))
        check_entry(entry, slug)
        # indent to match the page source; blank lines stay blank
        marker_line_start = html.rfind("\n", 0, html.index(MARKER)) + 1
        indent = html[marker_line_start:html.index(MARKER)]
        lines = [f"<!-- published:{slug} -->", *entry.split("\n"), f"<!-- /published:{slug} -->"]
        block = "".join((indent + ln if ln.strip() else "") + "\n" for ln in lines)

        bounds = block_bounds(html, slug, env["PAGE"])
        if bounds:
            html = html[:bounds[0]] + block + html[bounds[1]:]
            verb = "Update"
        else:
            at = html.index(MARKER) + len(MARKER)
            if html[at:at + 1] == "\n":
                at += 1
            html = html[:at] + block + html[at:]
            verb = "Publish"
        if copy_pdf:
            pdf_dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pdf_src, pdf_dst)
        summary = f"{verb} {slug} ({label})"
    else:
        bounds = block_bounds(html, slug, env["PAGE"])
        if bounds:
            html = html[:bounds[0]] + html[bounds[1]:]
        if copy_pdf and pdf_dst.exists():
            pdf_dst.unlink()
        summary = f"Unpublish {slug}"

    html = re.sub(r"\n{3,}", "\n\n", html)
    with page.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    if args.summary:
        args.summary.write_text(summary + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
