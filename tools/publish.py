#!/usr/bin/env python3
"""Publish (or unpublish) a paper draft from its private repo onto this site.

Run by the `publish` GitHub Actions workflow that lives in each draft repo.
It never runs on the site itself.  Usage:

    python3 tools/publish.py --action publish   --draft <checkout> --site <checkout>
    python3 tools/publish.py --action unpublish --draft <checkout> --site <checkout>

The draft checkout must contain a `publish/` folder with two files:

    publish/publish.env    KEY=VALUE lines: SLUG, PDF, LABEL
    publish/entry.html     an <article class="entry"> snippet for research/index.html;
                           {{SLUG}} and {{LABEL}} are substituted

What happens on publish:
  * <draft>/<PDF>  is copied to  <site>/files/<SLUG>.pdf
  * the entry is spliced into <site>/research/index.html between
    <!-- draft:<SLUG> --> and <!-- /draft:<SLUG> -->, replacing an existing
    block or inserting a new one right after the <!-- drafts --> marker.
On unpublish both are removed.  Committing and pushing is the workflow's job.
"""
import argparse
import re
import shutil
import sys
from pathlib import Path

MARKER = "<!-- drafts -->"
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,60}$")
FORBIDDEN = re.compile(r"<\s*(script|iframe|object|embed|link|meta|style)\b", re.I)


def die(msg: str) -> None:
    print(f"publish.py: {msg}", file=sys.stderr)
    sys.exit(1)


def read_env(path: Path) -> dict:
    if not path.is_file():
        die(f"missing {path}")
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
    return env


def block_bounds(html: str, slug: str):
    """Span of the draft block including its indentation and trailing newline."""
    start = html.find(f"<!-- draft:{slug} -->")
    if start != -1:
        start = html.rfind("\n", 0, start) + 1
    end_tag = f"<!-- /draft:{slug} -->"
    end = html.find(end_tag)
    if (start == -1) != (end == -1):
        die(f"research/index.html has an unbalanced draft:{slug} block")
    if start == -1:
        return None
    if end < start:
        die(f"research/index.html has a reversed draft:{slug} block")
    end += len(end_tag)
    # swallow the trailing newline so removal leaves no blank line behind
    if html[end:end + 1] == "\n":
        end += 1
    return start, end


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--action", choices=["publish", "unpublish"], required=True)
    ap.add_argument("--draft", type=Path, required=True)
    ap.add_argument("--site", type=Path, required=True)
    ap.add_argument("--summary", type=Path, help="write a one-line commit message here")
    args = ap.parse_args()

    env = read_env(args.draft / "publish" / "publish.env")
    slug, label = env["SLUG"], env["LABEL"]
    page = args.site / "research" / "index.html"
    pdf_dst = args.site / "files" / f"{slug}.pdf"
    if not page.is_file():
        die(f"missing {page}")
    with page.open(encoding="utf-8", newline="") as fh:
        html = fh.read()
    if "\r" in html:
        die("research/index.html must use LF line endings")
    if MARKER not in html:
        die(f"research/index.html has no {MARKER} marker")

    if args.action == "publish":
        pdf_src = args.draft / env["PDF"]
        if not pdf_src.is_file():
            die(f"PDF not found: {env['PDF']}")
        if pdf_src.read_bytes()[:5] != b"%PDF-":
            die(f"{env['PDF']} is not a PDF")
        entry_path = args.draft / "publish" / "entry.html"
        if not entry_path.is_file():
            die("missing publish/entry.html")
        with entry_path.open(encoding="utf-8", newline="") as fh:
            entry = fh.read().replace("\r\n", "\n")
        entry = re.sub(r"<!--.*?-->", "", entry, flags=re.S).strip("\n")
        if FORBIDDEN.search(entry):
            die("entry.html may not contain script, iframe, object, embed, link, meta or style tags")
        if "<article" not in entry:
            die("entry.html must contain an <article> element")
        entry = entry.replace("{{SLUG}}", slug).replace("{{LABEL}}", label)
        # indent to match the page source; blank lines stay blank
        marker_line_start = html.rfind("\n", 0, html.index(MARKER)) + 1
        indent = html[marker_line_start:html.index(MARKER)]
        lines = [f"<!-- draft:{slug} -->", *entry.split("\n"), f"<!-- /draft:{slug} -->"]
        block = "".join((indent + ln if ln.strip() else "") + "\n" for ln in lines)

        bounds = block_bounds(html, slug)
        if bounds:
            html = html[:bounds[0]] + block + html[bounds[1]:]
            verb = "Update"
        else:
            at = html.index(MARKER) + len(MARKER)
            if html[at:at + 1] == "\n":
                at += 1
            html = html[:at] + block + html[at:]
            verb = "Publish"
        pdf_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(pdf_src, pdf_dst)
        summary = f"{verb} draft {slug} ({label})"
    else:
        bounds = block_bounds(html, slug)
        if bounds:
            html = html[:bounds[0]] + html[bounds[1]:]
        if pdf_dst.exists():
            pdf_dst.unlink()
        summary = f"Unpublish draft {slug}"

    html = re.sub(r"\n{3,}", "\n\n", html)
    with page.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
    if args.summary:
        args.summary.write_text(summary + "\n", encoding="utf-8")
    print(summary)


if __name__ == "__main__":
    main()
