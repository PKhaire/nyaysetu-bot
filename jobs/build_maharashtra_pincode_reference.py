"""Build the deterministic Maharashtra PIN assistance reference.

The source directory is a checkout of the India Post ``pin`` repository's
``api/v01/json`` directory. The generated file contains administrative hints
only; customers remain responsible for entering and confirming their complete
address.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


SOURCE_REPOSITORY = "https://github.com/IndiaPost/pin"
OPEN_DATA_CATALOGUE = (
    "https://www.data.gov.in/catalog/"
    "all-india-pincode-directory-through-webservice"
)


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


def build_reference(
    source_directory: Path,
    *,
    source_revision: str,
) -> dict[str, object]:
    pincodes: dict[str, dict[str, object]] = {}
    for source_path in sorted(source_directory.glob("*.json")):
        records = json.loads(source_path.read_text(encoding="utf-8"))
        maharashtra = [
            record
            for record in records
            if _clean(record.get("statename")).casefold() == "maharashtra"
            or _clean(record.get("circlename")).casefold() == "maharashtra"
        ]
        if not maharashtra:
            continue

        pin = _clean(maharashtra[0].get("pincode"))
        if len(pin) != 6 or not pin.isdigit():
            continue

        districts = sorted(
            {
                _clean(record.get("Districtname")).title()
                for record in maharashtra
                if _clean(record.get("Districtname"))
            }
        )
        talukas = sorted(
            {
                _clean(record.get("Taluk")).title()
                for record in maharashtra
                if _clean(record.get("Taluk"))
            }
        )
        offices = sorted(
            {
                _clean(record.get("officename"))
                for record in maharashtra
                if _clean(record.get("officename"))
            }
        )
        pincodes[pin] = {
            "districts": districts,
            "talukas": talukas,
            "offices": offices,
        }

    return {
        "source": {
            "repository": SOURCE_REPOSITORY,
            "revision": source_revision,
            "open_data_catalogue": OPEN_DATA_CATALOGUE,
        },
        "state": "Maharashtra",
        "pincodes": pincodes,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source_directory", type=Path)
    parser.add_argument("output_path", type=Path)
    parser.add_argument("--source-revision", required=True)
    args = parser.parse_args()

    reference = build_reference(
        args.source_directory,
        source_revision=args.source_revision,
    )
    args.output_path.parent.mkdir(parents=True, exist_ok=True)
    args.output_path.write_text(
        json.dumps(reference, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )
    print(f"pincodes={len(reference['pincodes'])}")
    print(f"output={args.output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
