from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import fitz

from common import MANIFEST_PATH, ROOT, write_json_atomic


HEADING_PATTERN = re.compile(r"^(?:\d+(?:\.\d+){0,4}\.?\s+)[A-Z][A-Za-z0-9 ,/&()\-]{3,100}$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clean_page_text(text: str) -> str:
    text = text.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[str] = []
    blank = False
    for raw_line in text.splitlines():
        line = re.sub(r"[ \t]+", " ", raw_line).strip()
        if not line:
            if not blank:
                lines.append("")
            blank = True
            continue
        blank = False
        if HEADING_PATTERN.match(line) or (line.isupper() and 4 <= len(line) <= 100):
            lines.append(f"### {line}")
        else:
            lines.append(line)
    return "\n".join(lines).strip()


def front_matter(record: dict) -> str:
    fields = ("source_id", "title", "publisher", "version", "language", "source_url", "sha256")
    lines = ["---"]
    for field in fields:
        lines.append(f"{field}: {json.dumps(record[field], ensure_ascii=False)}")
    lines.append("---")
    return "\n".join(lines)


def main() -> None:
    if not MANIFEST_PATH.exists():
        raise RuntimeError("Missing corpus/manifest.json. Run 'make download' first.")
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    documents = manifest.get("documents", [])
    if not documents:
        raise RuntimeError("Corpus manifest contains no documents")

    prepared_dir = ROOT / "corpus" / "prepared"
    prepared_dir.mkdir(parents=True, exist_ok=True)

    for record in documents:
        if "local_file" not in record:
            prepared_file = record.get("prepared_file")
            if not prepared_file:
                raise RuntimeError(
                    f"Registered document has no prepared file: {record.get('source_id')}"
                )
            output_path = ROOT / prepared_file
            if not output_path.is_file():
                raise RuntimeError(f"Registered prepared document is missing: {output_path}")
            digest = sha256_file(output_path)
            if record.get("prepared_sha256") not in (None, digest):
                raise RuntimeError(f"Checksum mismatch: {output_path}")
            text = output_path.read_text(encoding="utf-8")
            if len(text) < 5_000:
                raise RuntimeError(f"Registered document contains too little text: {output_path}")
            record["prepared_sha256"] = digest
            record["bytes"] = output_path.stat().st_size
            record["text_chars"] = len(text)
            record.setdefault("page_count", None)
            record.setdefault("page_traceability", "unavailable")
            print(
                f"registered {record['source_id']}: kept {output_path.name}, "
                f"{len(text):,} text characters"
            )
            continue

        source_path = ROOT / record["local_file"]
        if sha256_file(source_path) != record["sha256"]:
            raise RuntimeError(f"Checksum mismatch: {source_path}")

        output_path = prepared_dir / f"{record['source_id']}.md"
        pdf = fitz.open(source_path)
        sections = [front_matter(record), "", f"# {record['title']} ({record['version']})", ""]
        text_chars = 0
        populated_pages = 0
        for page_number, page in enumerate(pdf, start=1):
            text = clean_page_text(page.get_text("text", sort=True))
            if len(text) >= 80:
                populated_pages += 1
            text_chars += len(text)
            sections.extend(
                [
                    f"## Source page {page_number}",
                    f"<!-- source_id:{record['source_id']} page:{page_number} -->",
                    "",
                    text or "[No extractable text on this source page]",
                    "",
                ]
            )
        page_count = pdf.page_count
        pdf.close()

        if text_chars < 5_000 or populated_pages < max(1, page_count // 2):
            raise RuntimeError(
                f"Insufficient extractable text in {source_path}: {text_chars} chars, "
                f"{populated_pages}/{page_count} populated pages"
            )

        output_path.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
        record["prepared_file"] = str(output_path.relative_to(ROOT))
        record["prepared_sha256"] = sha256_file(output_path)
        record["page_count"] = page_count
        record["page_traceability"] = "source_page_markers"
        record["text_chars"] = text_chars
        print(
            f"prepared   {record['source_id']}: {page_count} pages, "
            f"{text_chars:,} text characters"
        )

    write_json_atomic(MANIFEST_PATH, manifest)
    print(f"Prepared documents written to {prepared_dir}")


if __name__ == "__main__":
    main()
