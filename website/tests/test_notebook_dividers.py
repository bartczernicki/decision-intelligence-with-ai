"""Regression checks for source-only, repeatable notebook section ornaments."""

import copy
from contextlib import redirect_stdout
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "src" / "format_notebook_dividers.py"
SPEC = importlib.util.spec_from_file_location("format_notebook_dividers", SOURCE)
dividers = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(dividers)
MARKER = dividers.MARKER


def markdown(source, **extra):
    return {"cell_type": "markdown", "source": source.splitlines(keepends=True), "metadata": {}, **extra}


class MarkdownDividerTests(unittest.TestCase):
    def test_first_heading_and_every_atx_level_are_decorated_without_changing_text(self):
        source = "\n\n".join("#" * level + f" Heading {level} ##" for level in range(1, 7))
        result = dividers.format_markdown(source)
        self.assertEqual(result.count(MARKER), 6)
        for level in range(1, 7):
            self.assertIn(MARKER + "\n\n" + "#" * level + f" Heading {level} ##", result)
        self.assertEqual(dividers.format_markdown(result), result)

    def test_code_fences_indentation_escaping_and_html_are_not_headings(self):
        source = """```markdown
# fenced
~~~
## still fenced
````  

~~~markdown
### tilde fenced
~~~~

    # indented
\t## tab indented
\\# escaped
####### seven hashes
#missing-space

<!--
## comment
-->
<pre>
# raw code

## raw code after blank
</pre>

<script>
### script
</script>

<div>
#### HTML content
</div>
##### still in HTML block

<custom-element flag="yes">
###### custom HTML content
</custom-element>

## Actual heading
"""
        result = dividers.format_markdown(source)
        self.assertEqual(result.count(MARKER), 1)
        self.assertEqual(result.replace(MARKER + "\n\n", ""), source)

    def test_closed_html_title_can_be_followed_by_real_heading(self):
        source = '<div>Book title</div>\n\n### Opening\n'
        self.assertEqual(dividers.format_markdown(source), '<div>Book title</div>\n\n' + MARKER + '\n\n### Opening\n')

    def test_only_adjacent_actual_rules_are_replaced(self):
        source = "---\n\nExplanation\n\n***\n\n### One\n\nSeparate content\n\n___\nMore content\n\n- - -\n#### Two\n"
        result = dividers.format_markdown(source)
        self.assertTrue(result.startswith("---\n\nExplanation\n\n"))
        self.assertIn("___\nMore content", result)
        self.assertNotIn("***", result)
        self.assertNotIn("- - -", result)
        self.assertEqual(result.count(MARKER), 2)
        self.assertEqual(dividers.format_markdown(result), result)

    def test_setext_underlines_are_not_removed_as_rules(self):
        source = "A Setext heading\n---\n\n### ATX heading\n"
        result = dividers.format_markdown(source)
        self.assertTrue(result.startswith("A Setext heading\n---\n\n"))
        self.assertEqual(result.count(MARKER), 1)

    def test_spaced_hyphens_are_a_rule_even_after_paragraph_text(self):
        source = "Paragraph\n- - -\n### Heading\n"
        self.assertEqual(dividers.format_markdown(source), "Paragraph\n\n" + MARKER + "\n\n### Heading\n")

    def test_rule_after_setext_heading_is_an_actual_rule(self):
        source = "A Setext heading\n===\n---\n### ATX heading\n"
        result = dividers.format_markdown(source)
        self.assertEqual(result, "A Setext heading\n===\n\n" + MARKER + "\n\n### ATX heading\n")

    def test_crlf_and_heading_without_final_newline_are_preserved(self):
        source = "Text\r\n\r\n### Heading"
        result = dividers.format_markdown(source)
        self.assertEqual(result, "Text\r\n\r\n" + MARKER + "\r\n\r\n### Heading")
        self.assertEqual(dividers.format_markdown(result), result)


class NotebookDividerTests(unittest.TestCase):
    def test_cross_cell_rule_only_cell_is_retained_with_its_metadata(self):
        previous = markdown("---\n", id="rule-id", metadata={"tags": ["keep"]})
        notebook = {"cells": [previous, markdown("### Heading\n", id="heading-id")]}
        changed = dividers.format_notebook(notebook)
        self.assertEqual(changed, {0, 1})
        self.assertEqual(previous, {"cell_type": "markdown", "source": [], "metadata": {"tags": ["keep"]}, "id": "rule-id"})
        self.assertEqual("".join(notebook["cells"][1]["source"]), MARKER + "\n\n### Heading\n")
        self.assertEqual(dividers.format_notebook(notebook), set())

    def test_cross_cell_trailing_rule_removal_preserves_explanation_and_other_rules(self):
        source = "---\n\nExplanation stays.\n\n---\n"
        notebook = {"cells": [markdown(source), markdown("\n### Heading\n")]}
        dividers.format_notebook(notebook)
        self.assertEqual("".join(notebook["cells"][0]["source"]), "---\n\nExplanation stays.\n\n")
        self.assertEqual("".join(notebook["cells"][1]["source"]), "\n" + MARKER + "\n\n### Heading\n")

    def test_cross_cell_rule_is_preserved_when_content_or_code_intervenes(self):
        code = {"cell_type": "code", "source": ["# source"], "metadata": {}, "execution_count": 9, "outputs": [{"text": "# output"}]}
        notebook = {"cells": [markdown("---\n"), code, markdown("### Heading\n"), markdown("---\n"), markdown("Intro\n\n### Later\n")]}
        before = copy.deepcopy(notebook)
        dividers.format_notebook(notebook)
        self.assertEqual(notebook["cells"][0], before["cells"][0])
        self.assertEqual(notebook["cells"][1], before["cells"][1])
        self.assertEqual(notebook["cells"][3], before["cells"][3])

    def test_json_patches_only_sources_and_preserves_outputs_attachments_and_formatting(self):
        notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {"custom": "unchanged"}, "cells": [
            markdown("### Café\n\nOriginal paragraph.\n", id="markdown-id", attachments={"figure.png": {"image/png": "opaque=="}}),
            {"cell_type": "code", "source": ["# code heading"], "id": "code-id", "metadata": {"custom": 7}, "execution_count": 4, "outputs": [{"output_type": "display_data", "data": {"text/markdown": "# AI output", "text/html": "<h1>AI heading</h1>"}, "metadata": {}}]},
        ]}
        original = json.dumps(notebook, ensure_ascii=True, indent=1) + "\n"
        formatted, count = dividers.format_notebook_text(original)
        self.assertEqual(count, 1)
        parsed = json.loads(formatted)
        expected = copy.deepcopy(notebook)
        dividers.format_notebook(expected)
        self.assertEqual(parsed, expected)
        # Unchanged source lines retain their exact original JSON escaping.
        self.assertIn(r"Caf\u00e9", formatted)
        inserted_json = "".join("    " + json.dumps(line, ensure_ascii=False) + ",\n" for line in [MARKER + "\n", "\n"])
        self.assertEqual(formatted.replace(inserted_json, "", 1), original)
        self.assertEqual(dividers.format_notebook_text(formatted), (formatted, 0))

    def test_string_sources_and_compact_json_are_supported(self):
        original = '{"cells":[{"cell_type":"markdown","source":"# Heading"}],"metadata":{"source":"not a cell"}}'
        formatted, count = dividers.format_notebook_text(original)
        self.assertEqual(count, 1)
        self.assertEqual(json.loads(formatted)["cells"][0]["source"], MARKER + "\n\n# Heading")
        self.assertTrue(formatted.endswith(',"metadata":{"source":"not a cell"}}'))

    def test_check_mode_is_read_only_and_returns_pending_status(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "example.ipynb"
            original = json.dumps({"cells": [markdown("# Heading")]})
            path.write_text(original)
            with redirect_stdout(io.StringIO()):
                self.assertEqual(dividers.main(["--check", str(path)]), 1)
                self.assertEqual(path.read_text(), original)
                self.assertEqual(dividers.main([str(path)]), 0)
                self.assertEqual(dividers.main(["--check", str(path)]), 0)


if __name__ == "__main__":
    unittest.main()
