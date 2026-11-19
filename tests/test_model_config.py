import io
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from backend.agent_api import settings
from backend.agent_lab import complete


class ModelConfigTests(unittest.TestCase):
    def test_deepseek_file_drives_ui_and_request(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text("DEEPSEEK_API_KEY=test-only\n", encoding="utf-8-sig")
            self.enterContext(patch("backend.agent_lab.__file__", str(root / "backend" / "agent_lab.py")))
            self.enterContext(patch.dict(os.environ, {}, clear=True))
            public = settings()
            self.assertEqual((public["live_available"], public["provider"], public["model"]),
                             (True, "deepseek", "deepseek-flash"))
            self.assertNotIn("test-only", str(public))
            response = io.BytesIO(b'{"choices":[{"message":{"content":"OK"}}]}')
            with patch("backend.agent_lab.urlopen", return_value=response) as send:
                self.assertEqual(complete([])["content"], "OK")
            request = send.call_args.args[0]
            self.assertEqual(request.full_url, "https://api.deepseek.com/chat/completions")
            self.assertEqual(request.get_header("Authorization"), "Bearer test-only")
            self.assertEqual(json.loads(request.data)["thinking"], {"type": "disabled"})
