#!/usr/bin/env python3
"""Tests for the minimal native-concurrency admission contract."""
import os
import tempfile
import unittest
from unittest.mock import patch

from ci_admission import admission_decision, write_step_output


class AdmissionDecisionTests(unittest.TestCase):
    def test_native_concurrency_admits_the_run(self):
        self.assertIs(admission_decision(), True)

    def test_step_output_is_explicitly_true(self):
        with tempfile.NamedTemporaryFile(mode="r+", encoding="utf-8") as output:
            with patch.dict(os.environ, {"GITHUB_OUTPUT": output.name}):
                write_step_output(admission_decision())
            output.seek(0)
            self.assertEqual(output.read(), "admitted=true\n")

    def test_missing_github_output_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(RuntimeError):
                write_step_output(True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
