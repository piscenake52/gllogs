"""scripts/build_viewer.py(index.html を GitHub Pages 用に分ける)のテスト。ブラウザ不要。"""
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import build_viewer  # noqa: E402

SAMPLE = """<!DOCTYPE html>
<html lang="ja">
<head>
<script>window.early = '<style>';</script>
<meta name="description" content="x">
<style type="text/css">
.a { color: red }
</style>
</head>
<body>
<div class="a">hello</div>
<script>
(() => {})();
</script>
<script>
(function () {})();
</script>
</body>
</html>
"""
BASE = "https://example.github.io/gllogs/viewer"


class TestBuild(unittest.TestCase):
    def build(self, html, url=BASE, preview=False):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        src = Path(tmp.name) / "index.html"
        src.write_text(html, encoding="utf-8")
        out = Path(tmp.name) / "out"
        build_viewer.build(str(src), str(out), url, preview)
        return {p.name: p.read_text(encoding="utf-8") for p in out.iterdir()}

    def test_split(self):
        f = self.build(SAMPLE)
        self.assertEqual(sorted(f), ["loader.txt", "viewer.js"])
        self.assertIn("window.early", f["loader.txt"])
        self.assertNotIn(".a { color: red }", f["loader.txt"])
        self.assertIn('src="%s/viewer.js"' % BASE, f["loader.txt"])
        written = json.loads(re.search(r"insertAdjacentHTML\('beforebegin', (\".*\")\);", f["viewer.js"]).group(1))
        self.assertIn(".a { color: red }", written)
        self.assertIn('<div class="a">hello</div>', written)
        self.assertLess(f["viewer.js"].index("(() => {})();"), f["viewer.js"].index("(function () {})();"))

    def test_preview_is_not_indexed(self):
        f = self.build(SAMPLE, preview=True)
        self.assertIn("noindex", f["index.html"])
        self.assertNotIn("noindex", f["loader.txt"])

    def test_unexpected_shape_fails(self):
        for bad in (SAMPLE.replace("</style>\n", "</style>\n<style>\n</style>\n"),
                    SAMPLE.replace("</body>", "<div>after</div>\n</body>"),
                    "<p>x</p>"):
            with self.assertRaises(build_viewer.BuildError):
                self.build(bad)

    def test_real_index(self):
        f = self.build((ROOT / "index.html").read_text(encoding="utf-8"))
        self.assertIn('rel="canonical" href="https://gl-log.blogspot.com/"', f["loader.txt"])
        self.assertLess(len(f["loader.txt"].encode("utf-8")), 20000)
        self.assertNotIn("/feeds/posts/", f["viewer.js"])


if __name__ == "__main__":
    unittest.main()
