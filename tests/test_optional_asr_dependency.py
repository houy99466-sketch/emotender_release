import builtins
import importlib
import os
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

os.environ.setdefault("LLM_API_KEY", "test-key")
os.environ.setdefault("LLM_BASE_URL", "https://example.test/v1")
os.environ.setdefault("LLM_MODEL", "test-model")


class OptionalAsrDependencyTests(unittest.TestCase):
    def test_backend_imports_without_funasr_for_text_api(self):
        original_import = builtins.__import__
        original_backend = sys.modules.pop("emotender_backend", None)
        original_funasr = sys.modules.pop("funasr", None)

        def blocked_import(name, *args, **kwargs):
            if name == "funasr":
                raise ModuleNotFoundError("No module named 'funasr'")
            return original_import(name, *args, **kwargs)

        builtins.__import__ = blocked_import
        try:
            backend = importlib.import_module("emotender_backend")
            self.assertIsNone(backend.ASR_MODEL)
        finally:
            builtins.__import__ = original_import
            sys.modules.pop("emotender_backend", None)
            if original_backend is not None:
                sys.modules["emotender_backend"] = original_backend
            if original_funasr is not None:
                sys.modules["funasr"] = original_funasr


if __name__ == "__main__":
    unittest.main()
