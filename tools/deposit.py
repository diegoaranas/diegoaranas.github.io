#!/usr/bin/env python3
"""Prepare preprint-archive deposits and record them once they are made.

Nothing here talks to an archive.  Uploading is done by hand in the browser;
this script only builds what to upload and remembers what was uploaded.

    python tools/deposit.py status  <paper> [<paper> ...]
    python tools/deposit.py package <paper> [--archive NAME] [--out DIR]
    python tools/deposit.py record  <paper> --archive NAME --id ID
                                    [--version N] [--date YYYY-MM-DD] [--pdf FILE] [--url URL]

<paper> is a paper's checkout (or any folder) containing publish/paper.toml,
the one file holding that paper's metadata.  The same file drives the Research
page through tools/publish.py.  Schema:

    slug       = "mentaculuslimits"           site name: /files/<slug>.pdf, published:<slug>
    pdf        = "paper/released/x.pdf"       the public PDF, relative to <paper>
    site_pdf   = true                         serve a copy at /files/<slug>.pdf
    label      = "March 2026"                 "Draft of <label>", or the year after the journal
    page       = "research/index.html"        (optional) page the entry goes on
    title      = "..."
    status     = "draft"                      draft | under-review | published
    journal    = ""                           where it appeared, if published
    final_url  = ""                           the publisher's version, if any
    date       = "2026-03"                    date of the public version
    license    = ""                           chosen at deposit time, e.g. "CC BY 4.0"
    publisher_policy = "unchecked"            which version may be posted (published or
                                              under-review papers); never guessed
    keywords   = ["...", "..."]
    abstract   = '''...'''                    plain text, any line breaks

    [[authors]]                               in order; any author but the first
    name  = "Diego Arana Segura"              needs coauthor_ok = true before the
    orcid = "0009-0006-8358-5148"             paper can be packaged
    coauthor_ok = false

    [archive]
    targets = ["philsci", "philarchive"]      where it goes; the site links to the first

    [archive.philsci]                         one table per target; `record` fills in
    subjects = ["..."]                        id, url, version, date and sha256 (of the
    id = ""                                   PDF that was uploaded)

A paper deposited on PhilSci-Archive and PhilArchive both is packaged for
PhilArchive only once its PhilSci-Archive id is recorded, so that the
PhilArchive (PhilPapers) entry can point at the PhilSci-Archive record.
"""
import argparse
import datetime
import hashlib
import json
import re
import shutil
import sys
import textwrap
from pathlib import Path
from typing import NoReturn

sys.path.insert(0, str(Path(__file__).resolve().parent))
from publish import ARCHIVES, DEFAULT_PAGE, read_paper, record_url  # noqa: E402

SITE = Path(__file__).resolve().parent.parent
DEFAULT_OUT = Path.home() / "deposit-packages"


def die(msg: str) -> NoReturn:
    print(f"deposit.py: {msg}", file=sys.stderr)
    sys.exit(1)


def load(folder: Path):
    path = folder / "publish" / "paper.toml"
    if not path.is_file():
        die(f"no publish/paper.toml in {folder}")
    return path, read_paper(path)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def is_public(paper: dict) -> bool:
    page = SITE / paper.get("page", DEFAULT_PAGE)
    return page.is_file() and f"<!-- published:{paper['slug']} -->" in page.read_text(encoding="utf-8")


def blockers(paper: dict) -> list:
    """Reasons the paper may not be deposited at all."""
    out = []
    if not is_public(paper):
        out.append("not public on the site")
    pending = [a["name"] for a in paper["authors"][1:] if not a.get("coauthor_ok")]
    if pending:
        out.append("needs coauthor OK (" + ", ".join(pending) + ")")
    if paper.get("status") in ("published", "under-review") \
            and paper.get("publisher_policy", "unchecked") == "unchecked":
        out.append("publisher_policy unchecked")
    if not paper["archive"]["targets"]:
        out.append("no archive targets")
    return out


def target_state(paper: dict, folder: Path, name: str):
    """(state, detail) of one archive target."""
    rec = paper["archive"][name]
    pdf = folder / paper["pdf"] if paper["pdf"] else None
    if not rec.get("id"):
        return "not deposited", ""
    if not rec.get("sha256"):
        return "deposited, hash unknown", "record it with --pdf <the uploaded file>"
    if not pdf or not pdf.is_file():
        return "deposited, no local PDF to compare", ""
    if sha256(pdf) != rec["sha256"]:
        return "NEEDS NEW VERSION", f"{paper['pdf']} changed since version {rec.get('version') or '?'}"
    return "up to date", f"version {rec.get('version') or '?'}"


def cmd_status(args) -> None:
    for folder in args.papers:
        if not (folder / "publish" / "paper.toml").is_file():
            print(f"{folder}: no publish/paper.toml (not a paper in the deposit pipeline)")
            continue
        _, paper = load(folder)
        blocked = blockers(paper)
        if blocked:
            print(f"{paper['slug']}: excluded from the deposit queue: {'; '.join(blocked)}")
        if any(b != "publisher_policy unchecked" for b in blocked):
            continue
        for name in paper["archive"]["targets"]:
            state, detail = target_state(paper, folder, name)
            rec = paper["archive"][name]
            where = f" #{rec['id']}" if rec.get("id") else ""
            print(f"{paper['slug']}: {ARCHIVES[name][0]}{where}: {state}"
                  + (f" ({detail})" if detail else ""))


def wrap(text: str) -> str:
    return "\n".join(textwrap.wrap(" ".join(text.split()), 78))


def sheet(paper: dict, name: str) -> str:
    """Field-by-field text for one archive's submission form."""
    rec = paper["archive"][name]
    authors = "\n".join(
        f"  {i}. {a['name']}" + (f"  (ORCID {a['orcid']})" if a.get("orcid") else "")
        for i, a in enumerate(paper["authors"], 1))
    status = {"published": "Published", "under-review": "Unpublished (under review)",
              "draft": "Unpublished"}.get(paper.get("status", ""), paper.get("status", ""))
    subjects = "\n".join(f"  - {s}" for s in rec.get("subjects", [])) or "  (none suggested)"
    fields = [
        ("Title", paper["title"]),
        ("Authors", "\n" + authors),
        ("Abstract", "\n" + wrap(paper.get("abstract", ""))),
        ("Keywords", ", ".join(paper.get("keywords", [])) or "(none in paper.toml: add some)"),
        ("Status", status),
    ]
    if paper.get("journal"):
        fields.append(("Published in", f"{paper['journal']} ({paper['label']})"))
    if paper.get("final_url"):
        fields.append(("Publisher's version", paper["final_url"]))
    fields += [
        ("Date of this version", paper.get("date", "")),
        ("License", paper.get("license") or "(choose one in the form, then put it in paper.toml)"),
        ("Suggested subjects (pick the nearest in the form's own list)", "\n" + subjects),
    ]
    targets = paper["archive"]["targets"]
    if name != targets[0]:
        primary = paper["archive"][targets[0]]
        fields.append((f"Link to the {ARCHIVES[targets[0]][0]} record",
                       record_url(targets[0], primary)))
    out = [f"{ARCHIVES[name][0]} submission sheet: {paper['title']}",
           "Field names follow the form loosely; copy each value into its field.", ""]
    for label, value in fields:
        out.append(f"{label}: {value}" if not value.startswith("\n") else f"{label}:{value}")
        out.append("")
    return "\n".join(out)


def checklist(paper: dict, name: str, pdf_name: str, digest: str, folder: Path) -> str:
    rec = paper["archive"][name]
    arch = ARCHIVES[name][0]
    lines = [f"Checklist: {paper['title']} -> {arch}", ""]
    if rec.get("id"):
        lines += [f"[ ] This is a NEW VERSION of {arch} record {rec['id']} ({record_url(name, rec)}).",
                  "    Use the record's new-version route; do not create a new item.",
                  "    If the archive gives the new version its own id, record that id."]
    else:
        lines += [f"[ ] Search {arch} for the title first: it must not be there already."]
    lines += [
        f"[ ] Upload {pdf_name} (sha256 {digest[:16]}...), nothing else.",
        "[ ] Copy the fields from the submission sheet; check the author list and ORCID.",
        f"[ ] License: {paper.get('license') or 'choose one'}.",
    ]
    if paper.get("status") in ("published", "under-review"):
        lines.append(f"[ ] Publisher policy, as you recorded it: {paper['publisher_policy']}. "
                     "The PDF is the version it allows.")
    targets = paper["archive"]["targets"]
    if name != targets[0]:
        lines += [f"[ ] Put the {ARCHIVES[targets[0]][0]} record link in the entry "
                  "(the sheet's last field).",
                  "[ ] Afterwards, check that PhilPapers lists the paper once; if it shows two "
                  "entries, ask PhilPapers to merge them."]
    cmd = (f'python tools/deposit.py record "{folder}" --archive {name} --id <ID>'
           + (" --pdf <the file you uploaded>" if not paper["pdf"] else ""))
    lines += [
        "[ ] Once the record is live, from the site repo:",
        f"      {cmd}",
        "[ ] Then rebuild the Research page: commit paper.toml and run the paper's",
        "    publish workflow (gh workflow run publish), or for a paper kept in the",
        "    site repo, run tools/publish.py on it locally (see README).",
    ]
    return "\n".join(lines) + "\n"


def cmd_package(args) -> None:
    _, paper = load(args.paper)
    blocked = blockers(paper)
    if blocked:
        die(f"{paper['slug']} is excluded: {'; '.join(blocked)}")
    if not paper["pdf"]:
        die(f"{paper['slug']} has no pdf in paper.toml")
    pdf = args.paper / paper["pdf"]
    if not pdf.is_file() or pdf.read_bytes()[:5] != b"%PDF-":
        die(f"not a PDF: {pdf}")
    digest = sha256(pdf)
    site_copy = SITE / "files" / f"{paper['slug']}.pdf"
    if paper["site_pdf"] and site_copy.is_file() and sha256(site_copy) != digest:
        print(f"deposit.py: warning: the site serves a different /files/{paper['slug']}.pdf; "
              "publish this PDF too, or the site and the archive will disagree", file=sys.stderr)

    targets = paper["archive"]["targets"]
    names = [args.archive] if args.archive else targets
    built = []
    for name in names:
        if name not in targets:
            die(f"{name} is not among {paper['slug']}'s archive targets {targets}")
        state, _ = target_state(paper, args.paper, name)
        if state == "up to date":
            print(f"{paper['slug']}: {ARCHIVES[name][0]} is up to date; nothing to package")
            continue
        if name != targets[0] and not paper["archive"][targets[0]].get("id"):
            print(f"{paper['slug']}: {ARCHIVES[name][0]} waits for the "
                  f"{ARCHIVES[targets[0]][0]} id, so it can link to that record")
            continue
        dest = args.out / paper["slug"] / name
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        pdf_name = f"{paper['slug']}.pdf"
        shutil.copyfile(pdf, dest / pdf_name)
        (dest / "metadata.txt").write_text(sheet(paper, name), encoding="utf-8")
        (dest / "CHECKLIST.txt").write_text(
            checklist(paper, name, pdf_name, digest, args.paper.resolve()), encoding="utf-8")
        built.append(dest)
    for dest in built:
        print(f"built {dest}")


def set_keys(text: str, table: str, values: dict) -> str:
    """Set simple key = value lines inside [table] of a TOML text, keeping everything else."""
    lines = text.split("\n")
    header = f"[{table}]"
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == header)
    except StopIteration:
        return text.rstrip("\n") + f"\n\n{header}\n" + "".join(
            f"{k} = {json.dumps(v)}\n" for k, v in values.items())
    end = next((i for i in range(start + 1, len(lines)) if lines[i].lstrip().startswith("[")),
               len(lines))
    for key, value in values.items():
        line = f"{key} = {json.dumps(value)}"
        pat = re.compile(rf"^\s*{re.escape(key)}\s*=")
        hit = next((i for i in range(start + 1, end) if pat.match(lines[i])), None)
        if hit is None:
            last = max([i for i in range(start + 1, end) if lines[i].strip()], default=start)
            lines.insert(last + 1, line)
            end += 1
        else:
            lines[hit] = line
    return "\n".join(lines)


def cmd_record(args) -> None:
    path, paper = load(args.paper)
    if args.archive not in paper["archive"]["targets"]:
        die(f"{args.archive} is not among {paper['slug']}'s archive targets")
    pdf = args.pdf or (args.paper / paper["pdf"] if paper["pdf"] else None)
    if not pdf or not pdf.is_file():
        die("no PDF to hash: pass --pdf <the file you uploaded>")
    rec = paper["archive"][args.archive]
    version = args.version or (int(rec.get("version") or 0) + 1)
    values = {
        "id": args.id,
        "url": args.url or ARCHIVES[args.archive][1].format(id=args.id),
        "version": version,
        "date": args.date or datetime.date.today().isoformat(),
        "sha256": sha256(pdf),
    }
    text = path.read_text(encoding="utf-8")
    path.write_text(set_keys(text, f"archive.{args.archive}", values), encoding="utf-8",
                    newline="\n")
    read_paper(path)  # still valid TOML
    print(f"recorded {paper['slug']} on {ARCHIVES[args.archive][0]}: "
          f"#{args.id}, version {version}, {values['date']}")
    if rec.get("id") and rec["id"] != args.id:
        print(f"note: the id changed from {rec['id']}")


def main() -> None:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("status", help="what each paper needs")
    p.add_argument("papers", type=Path, nargs="+")
    p = sub.add_parser("package", help="build upload folders")
    p.add_argument("paper", type=Path)
    p.add_argument("--archive", choices=list(ARCHIVES))
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p = sub.add_parser("record", help="write a deposit's id and PDF hash into paper.toml")
    p.add_argument("paper", type=Path)
    p.add_argument("--archive", choices=list(ARCHIVES), required=True)
    p.add_argument("--id", required=True)
    p.add_argument("--version", type=int)
    p.add_argument("--date")
    p.add_argument("--pdf", type=Path)
    p.add_argument("--url")
    args = ap.parse_args()
    {"status": cmd_status, "package": cmd_package, "record": cmd_record}[args.cmd](args)


if __name__ == "__main__":
    main()
