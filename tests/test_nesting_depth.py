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


MULTILINE_GO = """\
package p

func Wide(
\ta int,
\tb int,
) int {
\tfor a > 0 {
\t\tif b > 0 {
\t\t\tfor b > 0 {
\t\t\t\tb--
\t\t\t}
\t\t}
\t}
\treturn a
}
"""

JAVA = """\
class Repo {
    // if (a) { if (b) { if (c) { } } } in a comment is not code
    Repo(int[] xs) {
        for (int x : xs) {
            if (x > 0) {
                while (x > 0) {
                    x--;
                }
            }
        }
    }

    int chain(int v) {
        if (v == 1) {
            return 1;
        } else if (v == 2) {
            return 2;
        } else if (v == 3) {
            return 3;
        }
        return 0;
    }

    void each(java.util.List<Integer> xs) {
        xs.forEach(v -> {
            if (v > 0) {
                try {
                    System.out.println(v);
                } catch (RuntimeException e) {
                    throw e;
                }
            }
        });
    }
}
"""

CSHARP = """\
public class Specs(ITestOutputHelper output) : Base(output)
{
    public void Shallow(int a)
    {
        if (a > 0)
        {
            output.WriteLine("ok");
        }
    }

    public async Task Deep(IEnumerable<int> xs)
    {
        foreach (var x in xs)
        {
            await Task.Run(() =>
            {
                if (x > 0)
                {
                    output.WriteLine("deep");
                }
            });
        }
    }
}
"""

RUST = """\
impl Glob {
    pub fn required_ext(&self) -> Option<String> {
        let mut ext = vec![];
        for t in self.tokens.iter().rev() {
            match *t {
                Token::Literal(c) => {
                    if c == '.' {
                        break;
                    }
                    ext.push(c);
                }
                _ => return None,
            }
        }
        Some(ext.into_iter().collect())
    }

    fn flat(&self, x: Option<u32>) -> u32 {
        let Some(v) = x else {
            return 0;
        };
        v
    }
}
"""

TYPESCRIPT = """\
export const findInNav = (
  item: Item | Item[],
  fun: (item: Item) => boolean
): Item | undefined => {
  if (Array.isArray(item)) {
    for (const sub of item) {
      if (fun(sub)) return sub
    }
  }
  return undefined
}

class Loader {
  async load(urls: string[]): Promise<void> {
    urls.forEach((url) => {
      if (url) {
        try {
          fetch(url)
        } catch (e) {
          throw e
        }
      }
    })
  }
}
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

    def test_go_multiline_signature_keeps_the_function_open(self):
        res = run(self.write("wide.go", MULTILINE_GO), cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("Wide: depth 4", res.stdout)

    def test_java_constructor_and_lambda_flagged_else_if_and_comment_not(self):
        res = run(self.write("Repo.java", JAVA), cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("Repo: depth 4", res.stdout)
        self.assertIn("each: depth 4", res.stdout)
        self.assertNotIn("chain", res.stdout)
        self.assertEqual(len(res.stdout.splitlines()), 2, res.stdout)

    def test_csharp_allman_lambda_counts_and_class_is_not_a_function(self):
        res = run(self.write("Specs.cs", CSHARP), cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertEqual(res.stdout.split(": ", 1)[1].strip(), "Deep: depth 4 (limit 3, heuristic)")

    def test_rust_match_arm_is_not_a_level_and_let_else_is(self):
        res = run(self.write("glob.rs", RUST), cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("required_ext: depth 4", res.stdout)
        self.assertNotIn("flat", res.stdout)  # let-else reaches depth 2 only

    def test_typescript_multiline_arrow_signature_and_callbacks(self):
        res = run(self.write("nav.ts", TYPESCRIPT), cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertIn("findInNav: depth 4", res.stdout)
        self.assertIn("load: depth 4", res.stdout)

    def test_script_obeys_its_own_limit(self):
        res = run(str(SCRIPT), cwd=self.dir)
        self.assertEqual(res.returncode, 0, res.stdout)

    def test_directory_scans_supported_files_only(self):
        self.write("src/deep.py", DEEP_PY)
        self.write("src/A.kt", "class A {}\n")
        res = run("src", cwd=self.dir)
        self.assertEqual(res.returncode, 1, res.stderr)
        self.assertNotIn("A.kt", res.stdout + res.stderr)

    def test_unsupported_file_exits_2(self):
        res = run(self.write("A.kt", "class A {}\n"), cwd=self.dir)
        self.assertEqual(res.returncode, 2)
        self.assertIn("unsupported file type '.kt'", res.stderr)

    def test_directory_without_supported_files_exits_2(self):
        self.write("kotlin/A.kt", "class A {}\n")
        res = run("kotlin", cwd=self.dir)
        self.assertEqual(res.returncode, 2)
        self.assertIn("nothing was measured", res.stderr)

    def test_missing_path_exits_2(self):
        res = run("nope", cwd=self.dir)
        self.assertEqual(res.returncode, 2)
        self.assertIn("does not exist", res.stderr)


if __name__ == "__main__":
    unittest.main()
