from __future__ import annotations

import hashlib
import json
import tempfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from common import MANIFEST_PATH, ROOT, write_json_atomic

ALLOWED_HOSTS = {
    "unece.org",
    "www.unece.org",
    "docs.un.org",
    "documents.un.org",
    "cdn.euroncap.com",
}
MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024


@dataclass(frozen=True)
class Source:
    source_id: str
    title: str
    publisher: str
    version: str
    language: str
    landing_page: str
    source_url: str
    filename: str
    sha256: str


SOURCES = [
    Source(
        source_id="unece_r152_rev2",
        title="UN Regulation No. 152 Rev.2",
        publisher="UNECE",
        version="Rev.2",
        language="English",
        landing_page="https://unece.org/transport/documents/2023/06/standards/un-regulation-no-152-rev2",
        source_url=(
            "https://documents.un.org/api/symbol/access?"
            "s=E/ECE/TRANS/505/REV.3/ADD.151/REV.2&l=en&t=pdf"
        ),
        filename="UNECE_UN_R152_Rev2.pdf",
        sha256="dc9cc84498dcae8f0888067ad3967fb5a346e814bc2f19128987a654c8a193de",
    ),
    Source(
        source_id="euroncap_aeb_c2c_v431",
        title="Euro NCAP AEB Car-to-Car Test Protocol",
        publisher="Euro NCAP",
        version="4.3.1",
        language="English",
        landing_page="https://www.euroncap.com/safety-assist/",
        source_url="https://cdn.euroncap.com/cars/assets/euro_ncap_aeb_c2c_test_protocol_v431_532926aad1.pdf",
        filename="EuroNCAP_AEB_C2C_v4.3.1.pdf",
        sha256="71683795b98d60f6478be26c131f3f392d355a599020fd1e77577ac67fce3f1a",
    ),
    Source(
        source_id="euroncap_collision_avoidance_v1041",
        title="Euro NCAP Safety Assist Collision Avoidance Assessment Protocol",
        publisher="Euro NCAP",
        version="10.4.1",
        language="English",
        landing_page="https://www.euroncap.com/safety-assist/",
        source_url="https://cdn.euroncap.com/cars/assets/euro_ncap_assessment_protocol_sa_collision_avoidance_v1041_fafe1dd418.pdf",
        filename="EuroNCAP_Collision_Avoidance_v10.4.1.pdf",
        sha256="911225776a14d31a830c48f7bcd5472425a0b0a53b44bc47fc42cc7ff899147f",
    ),
]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_pdf(path: Path) -> None:
    if path.stat().st_size < 10_000:
        raise RuntimeError(f"Downloaded file is unexpectedly small: {path}")
    with path.open("rb") as handle:
        if handle.read(5) != b"%PDF-":
            raise RuntimeError(f"Downloaded content is not a PDF: {path}")


def validate_download_url(url: str) -> None:
    parsed = urlsplit(url)
    host = (parsed.hostname or "").lower()
    if parsed.scheme.lower() != "https":
        raise RuntimeError(f"Refusing non-HTTPS document URL: {url}")
    if host not in ALLOWED_HOSTS:
        raise RuntimeError(f"Refusing non-official host: {host}")


class OfficialRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        validate_download_url(newurl)
        return super().redirect_request(request, fp, code, msg, headers, newurl)


def validate_source_file(source: Source, path: Path) -> None:
    validate_pdf(path)
    digest = sha256_file(path)
    if digest != source.sha256:
        raise RuntimeError(
            f"Checksum mismatch for {source.source_id}: "
            f"expected {source.sha256}, got {digest}"
        )


def preserve_document_policy(record: dict, previous: dict) -> None:
    if "enabled" in previous:
        record["enabled"] = bool(previous["enabled"])


def download(source: Source, destination: Path) -> str:
    validate_download_url(source.source_url)

    request = Request(
        source.source_url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
            "Referer": source.landing_page,
        },
    )
    opener = build_opener(OfficialRedirectHandler())
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent,
            prefix=f".{destination.name}.",
            suffix=".part",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            with opener.open(request, timeout=120) as response:
                validate_download_url(response.geturl())
                content_type = response.headers.get_content_type()
                if content_type != "application/pdf":
                    raise RuntimeError(
                        f"Unexpected content type for {source.source_id}: {content_type}"
                    )
                raw_length = response.headers.get("Content-Length")
                if raw_length:
                    try:
                        content_length = int(raw_length)
                    except ValueError as error:
                        raise RuntimeError(
                            f"Invalid Content-Length for {source.source_id}: {raw_length}"
                        ) from error
                    if content_length > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError(
                            f"Document exceeds {MAX_DOWNLOAD_BYTES} byte limit: "
                            f"{source.source_id}"
                        )
                downloaded = 0
                while chunk := response.read(1024 * 1024):
                    downloaded += len(chunk)
                    if downloaded > MAX_DOWNLOAD_BYTES:
                        raise RuntimeError(
                            f"Document exceeds {MAX_DOWNLOAD_BYTES} byte limit: "
                            f"{source.source_id}"
                        )
                    output.write(chunk)

        assert temporary is not None
        validate_source_file(source, temporary)
        temporary.replace(destination)
        return "application/pdf"
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> None:
    raw_dir = ROOT / "corpus" / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)

    previous: dict[str, dict] = {}
    previous_documents: list[dict] = []
    schema_version = 1
    if MANIFEST_PATH.exists():
        payload = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        previous_documents = payload.get("documents", [])
        previous = {item["source_id"]: item for item in previous_documents}
        schema_version = payload.get("schema_version", schema_version)

    documents = []
    seen_hashes: dict[str, str] = {}
    for source in SOURCES:
        destination = raw_dir / source.filename
        if destination.exists():
            validate_source_file(source, destination)
            content_type = "application/pdf"
            action = "kept"
        else:
            content_type = download(source, destination)
            action = "downloaded"

        digest = sha256_file(destination)
        if digest in seen_hashes:
            raise RuntimeError(
                f"Duplicate document content: {source.source_id} and {seen_hashes[digest]}"
            )
        seen_hashes[digest] = source.source_id

        old = previous.get(source.source_id, {})
        retrieved_at = old.get("retrieved_at") if old.get("sha256") == digest else None
        record = {
            **asdict(source),
            "content_type": content_type,
            "bytes": destination.stat().st_size,
            "sha256": digest,
            "local_file": str(destination.relative_to(ROOT)),
            "retrieved_at": retrieved_at or datetime.now(timezone.utc).isoformat(),
        }
        preserve_document_policy(record, old)
        if old.get("sha256") == digest:
            for field in (
                "enabled",
                "prepared_file",
                "prepared_sha256",
                "page_count",
                "page_traceability",
                "text_chars",
            ):
                if field in old:
                    record[field] = old[field]
        documents.append(record)
        print(f"{action:10s} {source.source_id}: {destination.stat().st_size:,} bytes")

    managed_source_ids = {source.source_id for source in SOURCES}
    registered_documents = [
        record
        for record in previous_documents
        if record.get("source_id") not in managed_source_ids
    ]
    for record in registered_documents:
        prepared_file = record.get("prepared_file")
        prepared_sha256 = record.get("prepared_sha256")
        if not prepared_file or not prepared_sha256:
            raise RuntimeError(
                f"Registered document is missing prepared metadata: {record.get('source_id')}"
            )
        prepared_path = ROOT / prepared_file
        if not prepared_path.is_file():
            raise RuntimeError(f"Registered prepared document is missing: {prepared_path}")
        if sha256_file(prepared_path) != prepared_sha256:
            raise RuntimeError(f"Registered document checksum mismatch: {prepared_path}")
        documents.append(record)
        print(f"registered {record['source_id']}: kept {prepared_path.name}")

    write_json_atomic(
        MANIFEST_PATH,
        {
            "schema_version": max(schema_version, 2 if registered_documents else 1),
            "documents": documents,
        },
    )
    print(f"Manifest written: {MANIFEST_PATH}")


if __name__ == "__main__":
    main()
