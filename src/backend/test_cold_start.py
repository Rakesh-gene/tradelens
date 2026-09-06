from pathlib import Path
import subprocess
import sys
import unittest


class ColdStartTestCase(unittest.TestCase):
    def test_server_imports_in_a_fresh_python_process(self):
        backend_directory = Path(__file__).resolve().parent
        result = subprocess.run(
            [sys.executable, "-c", "import server"],
            cwd=backend_directory,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
