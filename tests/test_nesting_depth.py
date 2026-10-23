import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "plugins/principles/skills/flat-code/scripts/nesting_depth.py"

DEEP_PY = """\
def deep(x):
    if x:
        for y in x:
            if y:
                while y:
                    pass
"""

ELIF_PY = """\
def chain(x):
    if x == 1:
        return 1
    elif x == 2:
        return 2
    elif x == 3:
        return 3
    elif x == 4:
        return 4
    return 0
"""

DEEP_GO = """\
package p

func Deep(xs []int) {
\tfor _, x := range xs {
\t\tif x > 0 {
\t\t\tfor i := 0; i < x; i++ {
\t\t\t\tprintln(i)
\t\t\t}
\t\t}
\t}
}
"""

DEEP_EX = """\
defmodule M do
  def deep(xs) do
    for x <- xs do
      if x do
        case x do
          _ -> :ok
        end
      end
    end
  end
end
"""


def run(*args, cwd):
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, text=True
    )


class NestingDepthTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, name, text):
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(text))
        return name

    def test_python_over_limit_reports_and_exits_1(self):
        res = run(self.write("deep.py", DEEP_PY), cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("deep: depth 5 (limit 3)", res.stdout)

    def test_python_at_limit_exits_0(self):
        res = run("--max", "5", self.write("deep.py", DEEP_PY), cwd=self.dir)
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_elif_chain_is_not_nesting(self):
        res = run(self.write("chain.py", ELIF_PY), cwd=self.dir)
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_go_heuristic_flags_depth_4(self):
        res = run(self.write("deep.go", DEEP_GO), cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("Deep: depth 4", res.stdout)

    def test_elixir_heuristic_flags_depth_4(self):
        res = run(self.write("deep.ex", DEEP_EX), cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("deep: depth 4", res.stdout)

    def test_directory_scans_supported_files_only(self):
        self.write("src/deep.py", DEEP_PY)
        self.write("src/A.java", "class A {}\n")
        res = run("src", cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertNotIn("A.java", res.stdout + res.stderr)

    def test_unsupported_file_exits_2(self):
        res = run(self.write("A.java", "class A {}\n"), cwd=self.dir)
        self.assertEqual(res.returncode, 2)
        self.assertIn("unsupported file type '.java'", res.stderr)

    def test_directory_without_supported_files_exits_2(self):
        self.write("java/A.java", "class A {}\n")
        res = run("java", cwd=self.dir)
        self.assertEqual(res.returncode, 2)
        self.assertIn("nothing was measured", res.stderr)

    def test_missing_path_exits_2(self):
        res = run("nope", cwd=self.dir)
        self.assertEqual(res.returncode, 2)
        self.assertIn("does not exist", res.stderr)


if __name__ == "__main__":
    unittest.main()
