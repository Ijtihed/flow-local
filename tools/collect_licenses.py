"""Preserve installed runtime dependencies' license/notice files in both packages."""
import importlib.metadata as metadata
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

root = Path(__file__).resolve().parents[1]
queue = [Requirement(line).name for line in (root / "requirements.txt").read_text().splitlines()
         if line.strip() and not line.lstrip().startswith("#") and (not Requirement(line).marker or Requirement(line).marker.evaluate())]
queue.append("pyinstaller")  # Bootloader exception and license.
seen, sections = set(), []
while queue:
    name = canonicalize_name(queue.pop())
    if name in seen:
        continue
    seen.add(name)
    distribution = metadata.distribution(name)
    for dependency in distribution.requires or []:
        requirement = Requirement(dependency)
        if not requirement.marker or requirement.marker.evaluate():
            queue.append(requirement.name)
    header = f"{distribution.metadata['Name']} {distribution.version}"
    texts = []
    for file in sorted(distribution.files or [], key=str):
        if any(part in file.name.upper() for part in ("LICENSE", "COPYING", "COPYRIGHT", "NOTICE")):
            resolved = Path(distribution.locate_file(file))
            if resolved.is_file() and resolved.stat().st_size <= 1_000_000:
                try:
                    value = resolved.read_text("utf-8")
                    if "\x00" not in value:
                        texts.append(f"--- {file} ---\n{value}")
                except UnicodeError:
                    pass
    license_name = distribution.metadata.get("License-Expression") or distribution.metadata.get("License") or "See upstream license"
    sections.append(header + "\n" + license_name + "\n" + "\n".join(texts))
target = root / "build/THIRD_PARTY_NOTICES.txt"
target.parent.mkdir(parents=True, exist_ok=True)
target.write_text("Flow runtime dependency notices\n\n" + "\n\n".join(sorted(sections)) + "\n", encoding="utf-8")
print(f"Collected notices for {len(seen)} distributions.")
