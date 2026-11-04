"""Regression checks for notebook HTML included in the static website."""

import importlib.util
from html.parser import HTMLParser
from pathlib import Path
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "src" / "build_website.py"
SPEC = importlib.util.spec_from_file_location("build_website", SOURCE)
build_website = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(build_website)


class ScriptParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag == "script":
            self.scripts.append(dict(attrs))


class NotebookRuntimeOutputTests(unittest.TestCase):
    RUNTIME_OUTPUT = """
<div class="output_area">
  <div class="output_html rendered_html output_subarea">
    <div>
      <div id="dotnet-interactive-this-cell-$CACHE_BUSTER$" style="display: none">
        Runtime output cell marker
      </div>
      <script type="text/javascript">
        async function probeAddresses(addresses) {
          return fetch(`${addresses[0]}discovery`, {method: 'POST'});
        }
        probeAddresses(['http://127.0.0.1:2048/', 'http://10.0.0.39:2048/']);
      </script>
    </div>
  </div>
</div>
"""

    def test_bootstrap_removed_without_losing_static_sibling_outputs(self):
        html = """
<h2 id="setup">Setup</h2>
<pre><code>&lt;script&gt;probeAddresses(['http://localhost:1234/'])&lt;/script&gt;</code></pre>
<div class="output_wrapper"><div class="output">
""" + self.RUNTIME_OUTPUT + """
<div class="output_area"><div class="output_html rendered_html output_subarea">
  <p>Installed packages</p><table><tr><td>Version 1.0</td></tr></table>
  <img src="../Images/example.png" alt="Example">
</div></div>
<div class="output_area"><pre>Decision: proceed</pre></div>
</div></div>
"""

        normalized = build_website.normalize_notebook_html(html)
        parser = ScriptParser()
        parser.feed(normalized)

        self.assertEqual(parser.scripts, [])
        self.assertNotIn("dotnet-interactive-this-cell-", normalized)
        self.assertNotIn("http://127.0.0.1:2048/", normalized)
        self.assertIn('<h2 id="setup">Setup</h2>', normalized)
        self.assertIn("&lt;script&gt;probeAddresses(['http://localhost:1234/'])&lt;/script&gt;", normalized)
        self.assertIn("Installed packages", normalized)
        self.assertIn("<table><tr><td>Version 1.0</td></tr></table>", normalized)
        self.assertIn('src="../Images/example.png"', normalized)
        self.assertIn("Decision: proceed", normalized)

    def test_bootstrap_only_output_does_not_leave_an_empty_wrapper(self):
        html = '<div class="output_wrapper"><div class="output">' + self.RUNTIME_OUTPUT + "</div></div>"

        normalized = build_website.normalize_notebook_html(html)

        self.assertEqual(normalized.strip(), "")

    def test_static_output_mentioning_runtime_marker_is_preserved(self):
        html = '<div class="output_area"><pre>dotnet-interactive-this-cell-example</pre></div>'

        self.assertEqual(build_website.normalize_notebook_html(html), html)


if __name__ == "__main__":
    unittest.main()
