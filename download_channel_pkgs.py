from __future__ import annotations

import hashlib
import json
from pathlib import Path
from urllib.parse import urljoin
from urllib.request import Request, urlopen

# ----  Enter here ---
CHANNEL = "https://prefix.dev/robostack-jazzy/"  # lyrical, jazzy, rolling
SUBDIRS = ["win-64"]  # ["linux-64", "noarch", "win-64"]
# ----


DESTINATION = Path(r"C:/Tim/artifactory_data/staging") / CHANNEL.split("/")[-2]
REF_FOLDER = Path(r"C:/Tim/artifactory_data/storage") / CHANNEL.split("/")[-2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)

    return digest.hexdigest()


def download(
    url: str,
    destination: Path,
    expected_sha256: str | None = None,
) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)

    # Preserve an existing file only if it is valid, when a checksum is known.
    if destination.exists():
        if expected_sha256:
            actual_sha256 = sha256_file(destination)
            if actual_sha256.lower() == expected_sha256.lower():
                print(f"Already present and verified: {destination.name}")
                return

            print(f"Existing file has an invalid checksum; replacing: {destination.name}")
            destination.unlink()
        else:
            print(f"Already present: {destination.name}")
            return

    temporary = destination.with_suffix(destination.suffix + ".partial")

    request = Request(
        url,
        headers={
            "User-Agent": "conda/24.11.0",
            "Accept": "*/*",
        },
    )

    try:
        print(f"Downloading: {url}")

        with urlopen(request, timeout=60) as response, temporary.open("wb") as output:
            while block := response.read(1024 * 1024):
                output.write(block)

        if expected_sha256:
            actual_sha256 = sha256_file(temporary)
            if actual_sha256.lower() != expected_sha256.lower():
                raise RuntimeError(
                    f"Checksum mismatch for {destination}\nExpected: {expected_sha256}\nActual:   {actual_sha256}"
                )

        temporary.replace(destination)

    except Exception:
        temporary.unlink(missing_ok=True)
        raise


for subdir in SUBDIRS:
    subdir_url = urljoin(CHANNEL, f"{subdir}/")
    local_subdir = DESTINATION / subdir

    repodata_url = urljoin(subdir_url, "repodata.json")
    repodata_path = local_subdir / "repodata.json"
    download(repodata_url, repodata_path)

    with repodata_path.open(encoding="utf-8") as file:
        repodata = json.load(file)

    packages: dict[str, dict] = {}
    packages.update(repodata.get("packages", {}))
    packages.update(repodata.get("packages.conda", {}))

    print(f"{subdir}: {len(packages)} package artifacts listed")

for filename, metadata in packages.items():
    package_url = urljoin(subdir_url, filename)
    package_path = local_subdir / filename
    reference_package_path = REF_FOLDER / subdir / filename
    expected_sha256 = metadata.get("sha256")

    # Do not download a package that is already available in the reference folder.
    if reference_package_path.exists():
        if expected_sha256:
            reference_sha256 = sha256_file(reference_package_path)

            if reference_sha256.lower() == expected_sha256.lower():
                print(f"Present in reference folder: {filename}")
                continue

            print(f"Reference file checksum does not match upstream metadata; downloading to staging: {filename}")
        else:
            # No upstream checksum is available, so existence is the best check.
            print(f"Present in reference folder: {filename}")
            continue

    download(
        package_url,
        package_path,
        expected_sha256=expected_sha256,
    )

print("Mirror download complete.")
