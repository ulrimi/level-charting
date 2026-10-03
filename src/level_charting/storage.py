import hashlib
import json
import os
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

from .models import Value


def json_bytes(value) -> bytes:
    if isinstance(value, Value):
        value = value.model_dump(mode="json")
    return (
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    ).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest(value: Value) -> str:
    return sha256(json_bytes(value))


def read_model(model, path: Path):
    return model.model_validate(json.loads(path.read_bytes(), parse_float=Decimal))


def publish(directory: Path, files: dict[str, bytes]) -> None:
    """Finish all work before publishing; existing output is never reused."""
    directory = directory.resolve()
    if directory.exists():
        raise FileExistsError(
            f"Preserve existing output; choose a new directory: {directory}"
        )
    directory.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(
        prefix=".level-charting-", dir=directory.parent
    ) as temporary:
        staging = Path(temporary) / "result"
        staging.mkdir()
        for name, data in files.items():
            path = staging / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        (staging / "manifest.json").write_bytes(
            json_bytes(
                {"files": {name: sha256(data) for name, data in sorted(files.items())}}
            )
        )
        if directory.exists():
            raise FileExistsError(f"Output already exists: {directory}")
        os.rename(staging, directory)


def verify_directory(directory: Path) -> None:
    manifest = json.loads((directory / "manifest.json").read_bytes())
    for name, expected in manifest["files"].items():
        path = (directory / name).resolve()
        if not path.is_relative_to(directory.resolve()) or not path.is_file():
            raise ValueError(f"Invalid or missing packet file: {name}")
        if sha256(path.read_bytes()) != expected:
            raise ValueError(f"Packet file changed: {name}. Prepare a new version.")
