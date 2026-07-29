"""Validate the built wheel's identity without treating it as standalone."""

from email.parser import Parser
from importlib import metadata
from pathlib import Path
import sys
from zipfile import ZipFile

import reg_harness


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_wheel_metadata.py PATH_TO_WHEEL")

    wheel_path = Path(sys.argv[1])
    with ZipFile(wheel_path) as wheel:
        metadata_paths = [
            name for name in wheel.namelist() if name.endswith(".dist-info/METADATA")
        ]
        if len(metadata_paths) != 1:
            raise SystemExit(
                f"expected exactly one METADATA file, found {len(metadata_paths)}"
            )
        package_paths = [
            name for name in wheel.namelist() if name.startswith("reg_harness/")
        ]
        if not package_paths:
            raise SystemExit("wheel does not contain the reg_harness package")
        message = Parser().parsestr(
            wheel.read(metadata_paths[0]).decode("utf-8", errors="strict")
        )

    expected_version = reg_harness.__version__
    installed_version = metadata.version("reg-harness")
    if message["Name"] != "reg-harness":
        raise SystemExit(f"unexpected wheel name: {message['Name']!r}")
    if message["Version"] != expected_version:
        raise SystemExit(
            f"wheel version {message['Version']!r} != runtime {expected_version!r}"
        )
    if installed_version != expected_version:
        raise SystemExit(
            f"installed version {installed_version!r} != runtime {expected_version!r}"
        )

    print(f"validated {wheel_path.name}: reg-harness {expected_version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
