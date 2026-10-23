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


def expected_references():
    """(skill dir, reference path, SKILL.md text) for every skill and language."""
    for skill in SKILLS:
        index = (skill / "SKILL.md").read_text()
        yield from ((skill, f"references/{lang}.md", index) for lang in LANGUAGES)


def indexed_files():
    """(skill dir, path) for every references/ or scripts/ path a SKILL.md lists."""
    for skill in SKILLS:
        index = (skill / "SKILL.md").read_text()
        refs = set(re.findall(r"`((?:references|scripts)/[\w./-]+)`", index))
        yield from ((skill, ref) for ref in sorted(refs))


def plugin_text_lines():
    """(path, line number, line) for every .md, .py and .json file in the plugin."""
    files = (p for p in sorted(PLUGIN.rglob("*")) if p.is_file() and p.suffix in (".md", ".py", ".json"))
    for path in files:
        yield from ((path, n, line) for n, line in enumerate(path.read_text().splitlines(), 1))


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
                assert fields is not None, "SKILL.md has no --- frontmatter block"
                self.assertEqual(fields.get("name"), skill.name)
                description = fields.get("description", "")
                self.assertTrue(description, "description is empty")
                self.assertLessEqual(len(description), 1024)

    def test_agents_have_required_frontmatter(self):
        agents = sorted((PLUGIN / "agents").glob("*.md"))
        self.assertEqual([p.stem for p in agents], ["principles-auditor"])
        for agent in agents:
            with self.subTest(agent=agent.name):
                fields = frontmatter(agent.read_text())
                assert fields is not None, "agent has no --- frontmatter block"
                self.assertEqual(fields.get("name"), agent.stem)
                missing = [k for k in ("description", "model", "color") if not fields.get(k)]
                self.assertEqual(missing, [], "empty or missing frontmatter keys")

    def test_every_language_reference_exists_and_is_indexed(self):
        for skill, ref, index in expected_references():
            with self.subTest(skill=skill.name, ref=ref):
                self.assertTrue((skill / ref).is_file(), f"{ref} missing")
                self.assertTrue(f"`{ref}`" in index, f"{ref} not listed in SKILL.md")

    def test_references_cover_exactly_the_supported_languages(self):
        for skill in SKILLS:
            with self.subTest(skill=skill.name):
                found = {p.stem for p in (skill / "references").glob("*.md")}
                self.assertEqual(found, set(LANGUAGES), "add the language to LANGUAGES or remove the file")

    def test_plugin_root_variable_only_in_skill_md(self):
        # Claude Code expands ${CLAUDE_PLUGIN_ROOT} in SKILL.md text only; elsewhere
        # it stays literal and the shell has no such variable. Use <plugin-root>.
        for path, lineno, line in plugin_text_lines():
            if path.name == "SKILL.md":
                continue
            with self.subTest(file=str(path.relative_to(ROOT)), line=lineno):
                self.assertNotIn("${CLAUDE_PLUGIN_ROOT}", line)

    def test_indexed_files_exist(self):
        for skill, ref in indexed_files():
            with self.subTest(skill=skill.name, ref=ref):
                self.assertTrue((skill / ref).is_file(), f"SKILL.md lists {ref}, which does not exist")

    def test_no_machine_local_paths(self):
        for path, lineno, line in plugin_text_lines():
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
