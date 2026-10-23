import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins/principles"
SKILLS = sorted(p.parent for p in (PLUGIN / "skills").glob("*/SKILL.md"))
LANGUAGES = ("go", "python", "elixir", "typescript", "java", "rust", "csharp")

# Paths that only exist on one machine. A plugin installs elsewhere; refer to
# bundled files as ${CLAUDE_PLUGIN_ROOT}/skills/<skill>/...
LOCAL_PATH = re.compile(r"~/\.claude|/Users/|/home/[a-z]|/private/tmp|[A-Z]:\\\\Users")


def frontmatter(text):
    match = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if not match:
        return None
    fields = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(": ")
        if sep:
            fields[key] = value
    return fields


class SkillsTest(unittest.TestCase):
    def test_expected_skills_exist(self):
        names = [p.name for p in SKILLS]
        self.assertEqual(
            names,
            ["composition", "dependency-injection", "flat-code", "measure-first", "principles-audit"],
        )

    def test_frontmatter_name_matches_dir_and_description_fits(self):
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                fields = frontmatter((skill / "SKILL.md").read_text())
                self.assertIsNotNone(fields, "SKILL.md has no --- frontmatter block")
                self.assertEqual(fields.get("name"), skill.name)
                description = fields.get("description", "")
                self.assertTrue(description, "description is empty")
                self.assertLessEqual(len(description), 1024)

    def test_every_language_reference_exists_and_is_indexed(self):
        for skill in SKILLS:
            index = (skill / "SKILL.md").read_text()
            for lang in LANGUAGES:
                ref = f"references/{lang}.md"
                with self.subTest(skill=skill.name, ref=ref):
                    self.assertTrue((skill / ref).is_file(), f"{ref} missing")
                    self.assertTrue(f"`{ref}`" in index, f"{ref} not listed in SKILL.md")

    def test_indexed_files_exist(self):
        for skill in SKILLS:
            index = (skill / "SKILL.md").read_text()
            for ref in set(re.findall(r"`((?:references|scripts)/[\w./-]+)`", index)):
                with self.subTest(skill=skill.name, ref=ref):
                    self.assertTrue((skill / ref).is_file(), f"SKILL.md lists {ref}, which does not exist")

    def test_no_machine_local_paths(self):
        for path in sorted(PLUGIN.rglob("*")):
            if not path.is_file() or path.suffix not in (".md", ".py", ".json"):
                continue
            for lineno, line in enumerate(path.read_text().splitlines(), 1):
                with self.subTest(file=str(path.relative_to(ROOT)), line=lineno):
                    self.assertIsNone(LOCAL_PATH.search(line), line)

    def test_plugin_and_marketplace_agree(self):
        plugin = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
        market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
        entry = next(p for p in market["plugins"] if p["name"] == plugin["name"])
        self.assertEqual((ROOT / entry["source"]).resolve(), PLUGIN.resolve())
        self.assertEqual(entry["description"], plugin["description"])


if __name__ == "__main__":
    unittest.main()
