"""Skill loader: scan layered paths, parse frontmatter, load skill content."""
from __future__ import annotations
import re
from dataclasses import dataclass
from pathlib import Path

@dataclass
class SkillInfo:
    name: str
    description: str
    path: Path
    base_dir: str
    source: str

_FRONTMATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)

def parse_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    body = text[m.end():]
    metadata: dict[str, str] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, value = line.partition(":")
            metadata[key.strip()] = value.strip()
    return metadata, body

def scan_skills(cwd: str = ".") -> dict[str, SkillInfo]:
    cwd_path = Path(cwd).resolve()
    home = Path.home()
    search_dirs = [
        (cwd_path / ".ohmycode" / "skills", ".ohmycode/skills/"),
        (cwd_path / ".claude" / "skills", ".claude/skills/"),
        (cwd_path / ".agents" / "skills", ".agents/skills/"),
        (home / ".ohmycode" / "skills", "~/.ohmycode/skills/"),
    ]
    skills: dict[str, SkillInfo] = {}
    for base_dir, source_label in search_dirs:
        if not base_dir.is_dir():
            continue
        for child in sorted(base_dir.iterdir()):
            if not child.is_dir():
                continue
            skill_file = child / "SKILL.md"
            if not skill_file.is_file():
                continue
            dir_name = child.name
            if dir_name in skills:
                continue
            try:
                text = skill_file.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, _ = parse_frontmatter(text)
            name = meta.get("name", dir_name)
            description = meta.get("description", "")
            skills[dir_name] = SkillInfo(
                name=name, description=description,
                path=skill_file.resolve(), base_dir=str(child.resolve()),
                source=source_label,
            )
    return skills

def load_skill(skill: SkillInfo, arguments: str = "") -> str:
    text = skill.path.read_text(encoding="utf-8")
    _, body = parse_frontmatter(text)
    body = body.strip()
    if arguments:
        if "$ARGUMENTS" in body:
            body = body.replace("$ARGUMENTS", arguments)
        else:
            body = body + "\n\n" + arguments
    return f"Base directory for this skill: {skill.base_dir}\n\n{body}"
