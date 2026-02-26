#!/usr/bin/env python3
"""Tests for env-audit."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
from env_audit import scan_file, scan_directory, categorize_var, is_sensitive


class TestPatternExtraction(unittest.TestCase):
    """Test environment variable extraction from source code."""

    def _write_and_scan(self, content, suffix=".py"):
        with tempfile.NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
            f.write(content)
            f.flush()
            try:
                return scan_file(Path(f.name))
            finally:
                os.unlink(f.name)

    def test_python_os_environ_get(self):
        results = self._write_and_scan('x = os.environ.get("DATABASE_URL", "postgres://localhost")')
        self.assertIn("DATABASE_URL", results)
        self.assertEqual(results["DATABASE_URL"]["default"], "postgres://localhost")

    def test_python_os_getenv(self):
        results = self._write_and_scan('x = os.getenv("API_KEY")')
        self.assertIn("API_KEY", results)

    def test_python_os_environ_bracket(self):
        results = self._write_and_scan('x = os.environ["SECRET_KEY"]')
        self.assertIn("SECRET_KEY", results)

    def test_node_process_env(self):
        results = self._write_and_scan('const x = process.env.NODE_ENV', suffix=".js")
        self.assertIn("NODE_ENV", results)

    def test_node_process_env_with_default(self):
        results = self._write_and_scan('const x = process.env.PORT || "3000"', suffix=".js")
        self.assertIn("PORT", results)

    def test_go_os_getenv(self):
        results = self._write_and_scan('v := os.Getenv("REDIS_URL")', suffix=".go")
        self.assertIn("REDIS_URL", results)

    def test_shell_variable(self):
        results = self._write_and_scan('echo ${HOME_DIR:-/tmp}', suffix=".sh")
        self.assertIn("HOME_DIR", results)

    def test_multiple_vars_in_file(self):
        code = 'x = os.getenv("VAR_ONE")\ny = os.environ["VAR_TWO"]'
        results = self._write_and_scan(code)
        self.assertIn("VAR_ONE", results)
        self.assertIn("VAR_TWO", results)


class TestCategorization(unittest.TestCase):
    """Test variable categorization."""

    def test_database_category(self):
        self.assertEqual(categorize_var("DATABASE_URL"), "database")

    def test_auth_category(self):
        cat = categorize_var("JWT_SECRET")
        self.assertIn(cat, ["auth", "security", "secrets", "general"])

    def test_sensitive_detection(self):
        self.assertTrue(is_sensitive("API_SECRET"))
        self.assertTrue(is_sensitive("DB_PASSWORD"))
        self.assertTrue(is_sensitive("AWS_SECRET_ACCESS_KEY"))

    def test_non_sensitive(self):
        self.assertFalse(is_sensitive("NODE_ENV"))
        self.assertFalse(is_sensitive("PORT"))
        self.assertFalse(is_sensitive("LOG_LEVEL"))


class TestDirectoryScan(unittest.TestCase):
    """Test scanning a directory."""

    def test_scan_temp_project(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.py").write_text(
                'import os\nurl = os.getenv("DATABASE_URL")\nkey = os.environ["API_KEY"]\n'
            )
            (Path(tmpdir) / "server.js").write_text(
                'const port = process.env.PORT || "3000"\n'
            )
            results = scan_directory(Path(tmpdir))
            self.assertIn("DATABASE_URL", results)
            self.assertIn("API_KEY", results)
            self.assertIn("PORT", results)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            results = scan_directory(Path(tmpdir))
            self.assertEqual(len(results), 0)


class TestCLI(unittest.TestCase):
    """Test CLI invocation."""

    def _run_cli(self, *args):
        cmd = [sys.executable, os.path.join(os.path.dirname(__file__), "env_audit.py")] + list(args)
        return subprocess.run(cmd, capture_output=True, text=True)

    def test_json_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.py").write_text('x = os.environ.get("TEST_VAR", "hello")\n')
            result = self._run_cli(tmpdir, "--json")
            self.assertEqual(result.returncode, 0)
            data = json.loads(result.stdout)
            self.assertIn("TEST_VAR", data)

    def test_stats_mode(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.py").write_text('x = os.getenv("MY_VAR")\n')
            result = self._run_cli(tmpdir, "--stats")
            self.assertEqual(result.returncode, 0)

    def test_env_format_output(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "app.py").write_text('x = os.environ["DATABASE_URL"]\n')
            result = self._run_cli(tmpdir)
            self.assertEqual(result.returncode, 0)
            self.assertIn("DATABASE_URL", result.stdout)

    def test_check_mode_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = self._run_cli(tmpdir, "--check")
            self.assertEqual(result.returncode, 0)

    def test_help(self):
        result = self._run_cli("--help")
        self.assertEqual(result.returncode, 0)
        self.assertIn("env", result.stdout.lower())


if __name__ == "__main__":
    unittest.main()
