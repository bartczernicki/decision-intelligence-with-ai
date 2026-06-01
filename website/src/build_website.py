#!/usr/bin/env python3
"""Build the static Decision Intelligence book website from notebooks."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable


ROOT = Path(__file__).resolve().parents[2]
NOTEBOOKS = ROOT / "Notebooks"
WEBSITE_ROOT = ROOT / "website"
WEBSITE = WEBSITE_ROOT / "dist"
RAW = WEBSITE / "_raw"
CHAPTERS_DIR = WEBSITE / "chapters"
ASSETS_DIR = WEBSITE / "assets"
CONFIG_PATH = WEBSITE_ROOT / "src" / "build_website_config.json"
IMAGES_DIR = ROOT / "Images"
WARNING_OUTPUT_KEYWORD = "warning CS1701:"
NOTEBOOK_DESCRIPTIONS = {
    "1a - Decision Intelligence - Introducing the Decision Intelligence Framework.ipynb": "A readable introduction to decisions, decision quality, and the Decision Intelligence Framework.",
    "1b - Decision Intelligence - Decision Framing.ipynb": "How to shape the decision problem before evaluating options or recommendations.",
    "1c - Decision Intelligence - Gathering Intelligence.ipynb": "Reducing uncertainty with data, evidence, historical context, and generative AI support.",
    "1d - Decision Intelligence - Decision Execution.ipynb": "The bridge between choosing and acting, including forms of execution and accountability.",
    "1e - Decision Intelligence - Decision Execution with Intuition.ipynb": "When intuition helps, when it fails, and how it fits into systematic decision work.",
    "1f - Decision Intelligence - Decision Execution with Decision Rules.ipynb": "Reusable rules, heuristics, and domain-specific patterns for consistent decisions.",
    "1g - Decision Intelligence - Decision Execution with Quantitative Methods.ipynb": "Using probability, measurement, and simulation to make better quantitative choices.",
    "1h - Decision Intelligence - Decision Communication.ipynb": "Communicating decisions so people understand the conclusion, rationale, and action.",
    "1i - Decision Intelligence - Applying the Decision Intelligence Framework.ipynb": "An end-to-end example that brings the framework components together.",
    "1j - Decision Intelligence - Enterprise Decision Intelligence.ipynb": "How decision systems become repeatable, observable, explainable, and scalable.",
}


IMAGE_BASE_URL = "https://raw.githubusercontent.com/bartczernicki/DecisionIntelligence.GenAI.Workshop/main/Images"
LOGO_URL = "https://raw.githubusercontent.com/bartczernicki/DecisionIntelligence.GenAI.Workshop/main/Images/DecisionIntelligenceLogo.png"
FRAMEWORK_URL = "https://raw.githubusercontent.com/bartczernicki/DecisionIntelligence.GenAI.Workshop/main/Images/DecisionIntelligenceFramework/DecisionIntelligence.png"


def slugify(value: str) -> str:
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def notebook_metadata(notebook_file: str) -> dict[str, str]:
    stem = Path(notebook_file).stem
    parts = [part.strip() for part in stem.split(" - ")]
    if len(parts) < 3:
        raise ValueError(
            f"Notebook filename must include a code, group, and title: {notebook_file}"
        )

    code = parts[0]
    group = parts[1]
    title = parts[-1]
    return {
        "code": code,
        "group": group,
        "notebook": notebook_file,
        "raw": f"{stem}.html",
        "file": f"{slugify(f'{code} {title}')}.html",
        "title": title,
        "short": title,
        "description": NOTEBOOK_DESCRIPTIONS.get(
            notebook_file, f"Static reading edition generated from the {title} notebook."
        ),
    }


def image_url(filename: str) -> str:
    return f"{IMAGE_BASE_URL}/{filename}"


def load_chapter_groups(config: dict[str, object]) -> dict[str, str]:
    groups = config.get("chapter_groups", [])
    if not isinstance(groups, list):
        raise ValueError("build_website_config.json chapter_groups must be a list.")

    chapter_groups: dict[str, str] = {}
    for entry in groups:
        if not isinstance(entry, dict):
            raise ValueError("Each chapter_groups entry must be an object.")
        name = entry.get("name")
        logo = entry.get("logo")
        if not isinstance(name, str) or not name:
            raise ValueError("Each chapter_groups entry must include a string name.")
        if not isinstance(logo, str) or not logo:
            raise ValueError(f"{name} must include a string logo.")
        if name in chapter_groups:
            raise ValueError(f"Duplicate chapter group in config: {name}")
        if not (IMAGES_DIR / logo).exists():
            raise FileNotFoundError(f"Configured chapter group logo does not exist: {logo}")
        chapter_groups[name] = image_url(logo)
    return chapter_groups


def load_build_config() -> tuple[dict[str, object], list[dict[str, str]]]:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(config.get("book_version"), str):
        raise ValueError("build_website_config.json must include a string book_version.")
    if not isinstance(config.get("notebooks"), list):
        raise ValueError("build_website_config.json must include a notebooks list.")

    chapters: list[dict[str, str]] = []
    seen_files: set[str] = set()
    for entry in config["notebooks"]:
        if not isinstance(entry, dict):
            raise ValueError("Each notebooks entry must be an object.")
        notebook_file = entry.get("file")
        include_in_build = entry.get("include_in_build")
        if not isinstance(notebook_file, str):
            raise ValueError("Each notebooks entry must include a string file.")
        if not isinstance(include_in_build, bool):
            raise ValueError(f"{notebook_file} must include a boolean include_in_build.")
        if notebook_file in seen_files:
            raise ValueError(f"Duplicate notebook in config: {notebook_file}")
        seen_files.add(notebook_file)
        if not (NOTEBOOKS / notebook_file).exists():
            raise FileNotFoundError(f"Configured notebook does not exist: {notebook_file}")
        if include_in_build:
            chapters.append(notebook_metadata(notebook_file))

    if not chapters:
        raise ValueError("At least one notebook must have include_in_build set to true.")
    return config, chapters


CONFIG, CHAPTERS = load_build_config()
CHAPTER_GROUP_LOGOS = load_chapter_groups(CONFIG)
BOOK_VERSION = str(CONFIG["book_version"])
BOOK_TITLE = "Decision Intelligence with AI"


class HeadingParser(HTMLParser):
    OUTPUT_CLASSES = {
        "output_wrapper",
        "output",
        "output_area",
        "output_subarea",
        "output_markdown",
        "output_html",
        "output_text",
    }

    def __init__(self) -> None:
        super().__init__()
        self.headings: list[dict[str, str]] = []
        self._current: dict[str, str] | None = None
        self._output_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        class_names = set((attr.get("class") or "").split())
        if self._output_depth:
            self._output_depth += 1
            return

        if class_names & self.OUTPUT_CLASSES:
            self._output_depth = 1
            return

        if tag in {"h2", "h3", "h4"}:
            if attr.get("id"):
                self._current = {"tag": tag, "id": attr["id"] or "", "text": ""}

    def handle_data(self, data: str) -> None:
        if self._current is not None:
            self._current["text"] += data

    def handle_endtag(self, tag: str) -> None:
        if self._output_depth:
            self._output_depth -= 1
            return

        if self._current is not None and tag == self._current["tag"]:
            text = re.sub(r"\s+", " ", self._current["text"]).strip(" ¶")
            if text:
                self.headings.append({**self._current, "text": text})
            self._current = None


class LocalLinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.refs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = dict(attrs)
        for key in ("href", "src"):
            if attr.get(key):
                self.refs.append(attr[key] or "")


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=ROOT, check=True)


def clean() -> None:
    if WEBSITE.exists():
        shutil.rmtree(WEBSITE)
    CHAPTERS_DIR.mkdir(parents=True)
    ASSETS_DIR.mkdir(parents=True)
    RAW.mkdir(parents=True)


def convert_notebooks() -> None:
    command = [
        "jupyter",
        "nbconvert",
        "--to",
        "html",
        "--template",
        "basic",
        "--output-dir",
        str(RAW),
    ]
    command.extend(str(NOTEBOOKS / chapter["notebook"]) for chapter in CHAPTERS)
    run(command)


def find_matching_div_end(html: str, start: int) -> int:
    depth = 0
    for match in re.finditer(r"</?div\b[^>]*>", html[start:], re.IGNORECASE):
        tag = match.group(0)
        depth += -1 if tag.startswith("</") else 1
        if depth == 0:
            return start + match.end()
    return len(html)


def remove_blocks_by_class(
    html: str, class_name: str, should_remove: Callable[[str], bool]
) -> str:
    start_pattern = re.compile(
        rf"<div\b(?=[^>]*\bclass=[\"'][^\"']*\b{re.escape(class_name)}\b)[^>]*>",
        re.IGNORECASE,
    )
    result = []
    cursor = 0
    while True:
        match = start_pattern.search(html, cursor)
        if not match:
            result.append(html[cursor:])
            break

        result.append(html[cursor : match.start()])
        end = find_matching_div_end(html, match.start())
        block = html[match.start() : end]
        if not should_remove(block):
            result.append(block)
        cursor = end
    return "".join(result)


def remove_warning_outputs(html: str) -> str:
    html = remove_blocks_by_class(
        html,
        "output_wrapper",
        lambda block: WARNING_OUTPUT_KEYWORD in block,
    )
    return remove_blocks_by_class(
        html,
        "output_wrapper",
        lambda block: not re.search(
            r"<div\b(?=[^>]*\bclass=[\"'][^\"']*\boutput_area\b)",
            block,
            re.IGNORECASE,
        ),
    )


def normalize_notebook_html(html: str) -> str:
    html = html.replace('alt="No description has been provided for this image"', 'alt=""')
    html = re.sub(r"<img(?![^>]*\bloading=)", '<img loading="lazy"', html)
    html = remove_warning_outputs(html)
    return html


def chapter_toc(raw_html: str) -> str:
    parser = HeadingParser()
    parser.feed(raw_html)
    if not parser.headings:
        return ""

    links = []
    for heading in parser.headings:
        level_class = f"toc-{heading['tag']}"
        links.append(
            f'<a class="{level_class}" href="#{escape(heading["id"], quote=True)}">'
            f"{escape(heading['text'])}</a>"
        )
    return f"""
<nav class="chapter-toc" aria-label="Chapter table of contents">
  <strong>On this page</strong>
  {''.join(links)}
</nav>
"""


def chapter_group_heading(
    group: str, class_name: str, heading_id: str | None = None, tag: str = "div"
) -> str:
    group_logo = CHAPTER_GROUP_LOGOS.get(group)
    logo = (
        f'<img src="{escape(group_logo, quote=True)}" alt="" aria-hidden="true">'
        if group_logo
        else ""
    )
    id_attr = f' id="{escape(heading_id, quote=True)}"' if heading_id else ""
    return f'<{tag} class="{class_name}"{id_attr}>{logo}<span>{escape(group)}</span></{tag}>'


def sidebar(prefix: str, current_file: str) -> str:
    home_active = " active" if current_file == "index.html" else ""
    items = [
        f'<a class="chapter-link{home_active}" href="{prefix}index.html" data-title="contents overview">'
        '<span class="chapter-code">TOC</span><span>Contents</span></a>'
    ]

    current_group = None
    for chapter in CHAPTERS:
        if chapter["group"] != current_group:
            current_group = chapter["group"]
            items.append(chapter_group_heading(current_group, "chapter-group"))

        active = " active" if chapter["file"] == current_file else ""
        data_title = escape(
            f"{chapter['code']} {chapter['group']} {chapter['title']}".lower(), quote=True
        )
        items.append(
            f'<a class="chapter-link{active}" href="{prefix}chapters/{chapter["file"]}" data-title="{data_title}">'
            f'<span class="chapter-code">{chapter["code"].upper()}</span><span>{escape(chapter["short"])}</span></a>'
        )

    return f"""
<aside class="book-sidebar" aria-label="Book navigation">
  <a class="book-brand" href="{prefix}index.html">
    <img src="{LOGO_URL}" alt="Decision Intelligence logo">
    <span class="book-brand-text">
      <span>{escape(BOOK_TITLE)}</span>
      <span class="book-version">Version {escape(BOOK_VERSION)}</span>
    </span>
  </a>
  <div class="sidebar-actions" data-pagefind-ignore="all">
    <button class="theme-toggle" type="button" data-theme-toggle aria-label="Switch to dark mode" aria-pressed="false">
      <span class="theme-toggle-icon" aria-hidden="true">☀</span>
    </button>
    <a class="source-link" href="https://github.com/bartczernicki/DecisionIntelligence.GenAI.Workshop" target="_blank" rel="noopener noreferrer">
      <span>Source</span>
      <svg aria-hidden="true" viewBox="0 0 24 24" width="24" height="24">
        <path fill="currentColor" d="M12 2C6.48 2 2 6.58 2 12.22c0 4.52 2.87 8.35 6.84 9.71.5.09.68-.22.68-.49 0-.24-.01-1.04-.01-1.89-2.51.47-3.16-.62-3.36-1.19-.11-.29-.6-1.19-1.03-1.43-.35-.19-.85-.66-.01-.67.79-.01 1.35.74 1.54 1.05.9 1.55 2.34 1.11 2.91.85.09-.67.35-1.11.64-1.37-2.22-.26-4.55-1.14-4.55-5.05 0-1.11.39-2.03 1.03-2.75-.1-.26-.45-1.31.1-2.71 0 0 .84-.27 2.75 1.05A9.28 9.28 0 0 1 12 6.99c.85 0 1.71.12 2.51.34 1.91-1.32 2.75-1.05 2.75-1.05.55 1.4.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.92-2.34 4.79-4.57 5.05.36.32.68.93.68 1.89 0 1.37-.01 2.47-.01 2.81 0 .27.18.59.69.49A10.05 10.05 0 0 0 22 12.22C22 6.58 17.52 2 12 2Z"/>
      </svg>
    </a>
  </div>
  <div class="pagefind-search-shell" data-pagefind-ignore="all">
    <span class="search-label">Search book</span>
    <pagefind-modal-trigger button-text="Search the book"></pagefind-modal-trigger>
    <pagefind-modal></pagefind-modal>
  </div>
  <nav class="chapter-nav" aria-label="Chapters">
    {''.join(items)}
  </nav>
</aside>
<div class="nav-backdrop" data-close-nav></div>
"""


def page_shell(
    *,
    title: str,
    body: str,
    prefix: str,
    current_file: str,
    description: str,
    social_title: str | None = None,
) -> str:
    pagefind_prefix = prefix
    site_url = ""
    full_title = f"{title} | Decision Intelligence"
    preview_title = social_title or full_title
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(full_title)}</title>
  <meta name="description" content="{escape(description, quote=True)}">
  <meta name="book-version" content="{escape(BOOK_VERSION, quote=True)}">
  <meta property="og:title" content="{escape(preview_title, quote=True)}">
  <meta property="og:description" content="{escape(description, quote=True)}">
  <meta property="og:type" content="website">
  <meta property="og:image" content="{FRAMEWORK_URL}">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="{escape(preview_title, quote=True)}">
  <meta name="twitter:description" content="{escape(description, quote=True)}">
  <meta name="twitter:image" content="{FRAMEWORK_URL}">
  <script>
    (function () {{
      try {{
        var saved = localStorage.getItem('di-theme');
        var theme = saved || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
        document.documentElement.dataset.theme = theme;
      }} catch (error) {{
        document.documentElement.dataset.theme = 'light';
      }}
    }})();
  </script>
  <link rel="icon" href="{prefix}assets/favicon.svg" type="image/svg+xml">
  <link rel="stylesheet" href="{prefix}assets/site.css">
  <link rel="stylesheet" href="{pagefind_prefix}pagefind/pagefind-component-ui.css">
  {site_url}
</head>
<body data-page="{escape(current_file, quote=True)}">
  <a class="skip-link" href="#main-content">Skip to content</a>
  <div class="reading-progress" aria-hidden="true"><span></span></div>
  <button class="nav-toggle" type="button" aria-label="Open chapter navigation" aria-expanded="false">Menu</button>
  {sidebar(prefix, current_file)}
  <main id="main-content" class="book-main">
    {body}
  </main>
  <script type="module" src="{pagefind_prefix}pagefind/pagefind-component-ui.js"></script>
  <script src="{prefix}assets/site.js"></script>
</body>
</html>
"""


def build_index() -> None:
    group_sections = []
    current_group = None
    cards = []
    for chapter in CHAPTERS:
        if chapter["group"] != current_group:
            if current_group is not None:
                group_sections.append(
                    f"""
  <section class="chapter-group-section" aria-labelledby="group-{slugify(current_group)}">
    {chapter_group_heading(current_group, "chapter-grid-heading", f"group-{slugify(current_group)}", "h3")}
    <div class="chapter-grid">
      {''.join(cards)}
    </div>
  </section>"""
                )
            current_group = chapter["group"]
            cards = []

        data_title = escape(
            f"{chapter['code']} {chapter['title']} {chapter['description']}".lower(),
            quote=True,
        )
        cards.append(
            f"""
<a class="chapter-card" href="chapters/{chapter['file']}" data-title="{data_title}">
  <strong>{escape(chapter['title'])}</strong>
  <span>{escape(chapter['description'])}</span>
</a>"""
        )

    if current_group is not None:
        group_sections.append(
            f"""
  <section class="chapter-group-section" aria-labelledby="group-{slugify(current_group)}">
    {chapter_group_heading(current_group, "chapter-grid-heading", f"group-{slugify(current_group)}", "h3")}
    <div class="chapter-grid">
      {''.join(cards)}
    </div>
  </section>"""
        )

    body = f"""
<div data-pagefind-body>
<section class="book-hero" aria-labelledby="book-title">
  <h1 class="hero-title" id="book-title">{escape(BOOK_TITLE)}</h1>
  <div class="author-row" aria-label="Author links">
    <span>Authored by Bart Czernicki</span>
    <div class="author-links">
      <a href="https://www.linkedin.com/in/bartczernicki/" aria-label="Bart Czernicki on LinkedIn" target="_blank" rel="noopener noreferrer">
        <svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22"><path fill="currentColor" d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.14 1.45-2.14 2.94v5.67H9.34V9h3.42v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.46v6.28ZM5.32 7.43a2.06 2.06 0 1 1 0-4.12 2.06 2.06 0 0 1 0 4.12Zm1.78 13.02H3.53V9H7.1v11.45ZM22.23 0H1.77C.79 0 0 .77 0 1.72v20.56C0 23.23.79 24 1.77 24h20.46c.98 0 1.77-.77 1.77-1.72V1.72C24 .77 23.21 0 22.23 0Z"/></svg>
      </a>
      <a href="https://github.com/bartczernicki" aria-label="Bart Czernicki on GitHub" target="_blank" rel="noopener noreferrer">
        <svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22"><path fill="currentColor" d="M12 2C6.48 2 2 6.58 2 12.22c0 4.52 2.87 8.35 6.84 9.71.5.09.68-.22.68-.49 0-.24-.01-1.04-.01-1.89-2.51.47-3.16-.62-3.36-1.19-.11-.29-.6-1.19-1.03-1.43-.35-.19-.85-.66-.01-.67.79-.01 1.35.74 1.54 1.05.9 1.55 2.34 1.11 2.91.85.09-.67.35-1.11.64-1.37-2.22-.26-4.55-1.14-4.55-5.05 0-1.11.39-2.03 1.03-2.75-.1-.26-.45-1.31.1-2.71 0 0 .84-.27 2.75 1.05A9.28 9.28 0 0 1 12 6.99c.85 0 1.71.12 2.51.34 1.91-1.32 2.75-1.05 2.75-1.05.55 1.4.2 2.45.1 2.71.64.72 1.03 1.63 1.03 2.75 0 3.92-2.34 4.79-4.57 5.05.36.32.68.93.68 1.89 0 1.37-.01 2.47-.01 2.81 0 .27.18.59.69.49A10.05 10.05 0 0 0 22 12.22C22 6.58 17.52 2 12 2Z"/></svg>
      </a>
      <a href="http://twitter.com/bartczernicki" aria-label="Bart Czernicki on X" target="_blank" rel="noopener noreferrer">
        <svg aria-hidden="true" viewBox="0 0 24 24" width="22" height="22"><path fill="currentColor" d="M18.9 2.25h3.68l-8.04 9.19L24 21.75h-7.4l-5.8-7.58-6.63 7.58H.49l8.6-9.83L0 2.25h7.59l5.24 6.93 6.07-6.93Zm-1.29 17.68h2.04L6.48 3.97H4.29l13.32 15.96Z"/></svg>
      </a>
    </div>
  </div>
  <div class="book-hero-copy">
    <p class="lede">Interactive companion website to the Decision Intelligence with AI book.</p>
    <div class="hero-actions">
      <a class="primary-action" href="chapters/{CHAPTERS[0]['file']}">Start reading</a>
      <a class="secondary-action" href="#chapters">Browse chapters</a>
    </div>
  </div>
  <img class="hero-image" src="{FRAMEWORK_URL}" alt="Decision Intelligence Framework">
</section>
<section id="chapters" class="chapter-grid-section" aria-label="Contents">
  <div class="section-heading">
    <p class="eyebrow">Contents</p>
  </div>
  {''.join(group_sections)}
</section>
</div>
"""
    (WEBSITE / "index.html").write_text(
        page_shell(
            title=BOOK_TITLE,
            body=body,
            prefix="",
            current_file="index.html",
            description="Decision Intelligence read-only book",
            social_title=BOOK_TITLE,
        ),
        encoding="utf-8",
    )


def build_chapters() -> None:
    for index, chapter in enumerate(CHAPTERS):
        raw_html = normalize_notebook_html((RAW / chapter["raw"]).read_text(encoding="utf-8"))
        prev_chapter = CHAPTERS[index - 1] if index > 0 else None
        next_chapter = CHAPTERS[index + 1] if index < len(CHAPTERS) - 1 else None

        prev_link = (
            f'<a class="pager-link" data-prev-chapter href="{prev_chapter["file"]}">'
            f'<span>Previous</span><strong>{escape(prev_chapter["short"])}</strong></a>'
            if prev_chapter
            else '<span class="pager-link disabled"><span>Previous</span><strong>Contents</strong></span>'
        )
        next_link = (
            f'<a class="pager-link align-right" data-next-chapter href="{next_chapter["file"]}">'
            f'<span>Next</span><strong>{escape(next_chapter["short"])}</strong></a>'
            if next_chapter
            else '<a class="pager-link align-right" data-next-chapter href="../index.html"><span>Next</span><strong>Back to Contents</strong></a>'
        )

        body = f"""
<article class="chapter-page">
  <div data-pagefind-body>
  <header class="chapter-header">
    <a class="back-link" href="../index.html">Back to contents</a>
    <p class="eyebrow">Chapter {chapter['code'].upper()}</p>
    <h1>{escape(chapter['title'])}</h1>
    <p class="chapter-summary">{escape(chapter['description'])}</p>
  </header>
  {chapter_toc(raw_html)}
  <section class="notebook-content">
    {raw_html}
  </section>
  </div>
  <nav class="chapter-pager" aria-label="Chapter navigation">
    {prev_link}
    {next_link}
  </nav>
</article>
"""
        (CHAPTERS_DIR / chapter["file"]).write_text(
            page_shell(
                title=chapter["title"],
                body=body,
                prefix="../",
                current_file=chapter["file"],
                description=chapter["description"],
            ),
            encoding="utf-8",
        )


def write_assets() -> None:
    (ASSETS_DIR / "favicon.svg").write_text(FAVICON, encoding="utf-8")
    (ASSETS_DIR / "site.css").write_text(SITE_CSS.strip() + "\n", encoding="utf-8")
    (ASSETS_DIR / "site.js").write_text(SITE_JS.strip() + "\n", encoding="utf-8")
    (WEBSITE_ROOT / "README.md").write_text(README.strip() + "\n", encoding="utf-8")


def generate_pagefind() -> None:
    run(["npx", "-y", "pagefind", "--site", "website/dist"])


def validate_links() -> None:
    errors: list[str] = []
    for html_file in sorted(WEBSITE.glob("**/*.html")):
        parser = LocalLinkParser()
        parser.feed(html_file.read_text(encoding="utf-8"))
        for ref in parser.refs:
            if ref.startswith(("http://", "https://", "mailto:", "data:", "#")):
                continue
            clean_ref = ref.split("#", 1)[0]
            if not clean_ref:
                continue
            target = (html_file.parent / clean_ref).resolve()
            if not target.exists():
                errors.append(f"{html_file.relative_to(ROOT)} -> {ref}")
    if errors:
        raise SystemExit("Missing local links:\n" + "\n".join(errors))


def main() -> None:
    clean()
    convert_notebooks()
    build_index()
    build_chapters()
    shutil.rmtree(RAW)
    write_assets()
    generate_pagefind()
    validate_links()
    print(f"Built website {BOOK_VERSION} with {len(CHAPTERS)} chapters and Pagefind search.")


FAVICON = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">
  <rect width="64" height="64" rx="12" fill="#134e4a"/>
  <path d="M16 18h15c10 0 17 6 17 14s-7 14-17 14H16V18Zm10 8v12h5c5 0 8-2 8-6s-3-6-8-6h-5Z" fill="#fff"/>
</svg>"""


README = """# Decision Intelligence Static Website

This folder contains the source automation and generated output for the static website built from notebooks selected in `src/build_website_config.json`.

## Folder Layout

- `src/` contains the build and deploy scripts.
- `src/build_website_config.json` controls the book version and which notebooks are included.
- `dist/` contains the generated static website.

## Build

From the repository root:

```bash
python3 website/src/build_website.py
```

The build converts notebooks to HTML, wraps them in the static book shell, generates the Pagefind index, and validates local links.

To include or exclude notebooks, edit `src/build_website_config.json` and change `include_in_build`.

For compatibility, the root wrapper still works:

```bash
python3 scripts/build_website.py
```

## Test Locally

```bash
python3 -m http.server 8765 --directory website/dist
```

Open `http://127.0.0.1:8765/`. Pagefind search is intended to run from a static server, not directly from `file://`.

To stop the local server, press `Ctrl+C` in the terminal where it is running.

If that terminal is no longer available, stop the process listening on port `8765`:

```bash
lsof -ti tcp:8765 | xargs kill
```

## Deploy To Azure Blob Static Website

Enable static website hosting on the storage account with `index.html` as the index document. Then deploy the contents of `website/dist/` to `$web`:

```bash
website/src/deploy_website.sh "<storage-account-name>" [resource-group]
```

The contents of `website/dist/` should land at the root of `$web`, so `$web/index.html`, `$web/assets/`, `$web/chapters/`, and `$web/pagefind/` are siblings.

## Cache Guidance

During active editing, keep `index.html` and chapter HTML on a short cache. Pagefind and asset files can use longer cache headers after content stabilizes, but regenerate Pagefind whenever notebook content changes.
"""


SITE_CSS = r"""
:root {
  --paper: #f7f5f0;
  --panel: #ffffff;
  --panel-subtle: #eeece6;
  --panel-warm: #fbf7ee;
  --ink: #282724;
  --heading: #1f211f;
  --muted: #68645d;
  --line: #d8d3c8;
  --teal: #3b746e;
  --teal-dark: #275652;
  --berry: #8f2d46;
  --gold: #9a6b1d;
  --code-bg: #20211f;
  --code-text: #f4f1e9;
  --output-bg: rgba(59, 116, 110, 0.08);
  --output-border: rgba(59, 116, 110, 0.24);
  --output-accent: #3b746e;
  --focus-ring: rgba(59, 116, 110, 0.34);
  --backdrop: rgba(28, 28, 25, 0.38);
  --shadow: 0 18px 45px rgba(38, 38, 31, 0.12);
  --sidebar-width: 318px;
  color-scheme: light;
}

:root[data-theme="dark"] {
  --paper: #121313;
  --panel: #1c1d1d;
  --panel-subtle: #171818;
  --panel-warm: #211f1b;
  --ink: #e8e4dc;
  --heading: #f4efe6;
  --muted: #aaa39a;
  --line: #353532;
  --teal: #7ca7a1;
  --teal-dark: #a8c5bf;
  --berry: #d48a9b;
  --gold: #d4b06a;
  --code-bg: #0d0e0e;
  --code-text: #eee9df;
  --output-bg: rgba(124, 167, 161, 0.12);
  --output-border: rgba(124, 167, 161, 0.28);
  --output-accent: #7ca7a1;
  --focus-ring: rgba(124, 167, 161, 0.34);
  --backdrop: rgba(0, 0, 0, 0.58);
  --shadow: 0 18px 45px rgba(0, 0, 0, 0.34);
  color-scheme: dark;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body {
  margin: 0;
  color: var(--ink);
  background: var(--paper);
  font-family: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  line-height: 1.65;
}
a { color: var(--teal-dark); }
a:hover { color: var(--berry); }
a:focus-visible,
button:focus-visible {
  outline: 3px solid var(--focus-ring);
  outline-offset: 3px;
}

.skip-link {
  position: fixed;
  top: 10px;
  left: 10px;
  transform: translateY(-150%);
  z-index: 60;
  border-radius: 8px;
  padding: 10px 14px;
  background: var(--panel);
  color: var(--teal-dark);
  font-weight: 800;
  box-shadow: var(--shadow);
}
.skip-link:focus { transform: translateY(0); }

.reading-progress {
  position: fixed;
  inset: 0 0 auto 0;
  height: 4px;
  background: transparent;
  z-index: 30;
}
.reading-progress span {
  display: block;
  width: 0;
  height: 100%;
  background: linear-gradient(90deg, var(--teal), var(--gold), var(--berry));
}

.book-sidebar {
  position: fixed;
  inset: 0 auto 0 0;
  width: var(--sidebar-width);
  padding: 26px 18px;
  overflow-y: auto;
  background: var(--panel-subtle);
  border-right: 1px solid var(--line);
  z-index: 20;
}
.book-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  color: var(--ink);
  text-decoration: none;
  font-weight: 800;
  line-height: 1.15;
  margin-bottom: 24px;
}
.book-brand img { width: 42px; height: 42px; object-fit: contain; }
.book-brand-text {
  display: grid;
  gap: 3px;
}
.book-version {
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
}

.sidebar-actions {
  display: flex;
  align-items: center;
  gap: 14px;
  margin: -4px 0 20px;
}
.source-link {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--ink);
  font-size: 1.42rem;
  font-weight: 800;
  line-height: 1;
  text-decoration: none;
}
.source-link:hover {
  color: var(--teal-dark);
}
.source-link svg {
  flex: 0 0 auto;
}

.theme-toggle {
  display: inline-grid;
  place-items: center;
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  border: 0;
  border-radius: 999px;
  padding: 0;
  background: transparent;
  color: var(--ink);
  cursor: pointer;
}
.theme-toggle:hover {
  color: var(--teal-dark);
}
.theme-toggle-icon {
  display: inline-grid;
  place-items: center;
  font-size: 1.55rem;
  line-height: 1;
}
:root[data-theme="dark"] .theme-toggle-icon {
  color: var(--teal-dark);
}

.search-label {
  display: block;
  color: var(--muted);
  font-size: 0.78rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0;
  margin-bottom: 8px;
}
.pagefind-search-shell { margin-bottom: 18px; }
.pagefind-search-shell pagefind-modal-trigger {
  --pagefind-ui-primary: var(--teal-dark);
  --pagefind-ui-text: var(--ink);
  --pagefind-ui-background: var(--panel);
  --pagefind-ui-border: var(--line);
  --pagefind-ui-border-radius: 8px;
  --pagefind-ui-font: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  display: block;
}
.pagefind-search-shell pagefind-modal {
  --pagefind-ui-primary: var(--teal-dark);
  --pagefind-ui-text: var(--ink);
  --pagefind-ui-background: var(--panel);
  --pagefind-ui-border: var(--line);
  --pagefind-ui-tag: var(--panel-subtle);
  --pagefind-ui-border-radius: 8px;
  --pagefind-ui-font: ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

.chapter-nav {
  display: grid;
  gap: 6px;
  margin-top: 18px;
}
.chapter-group {
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--muted);
  font-size: 0.8rem;
  font-weight: 800;
  line-height: 1.2;
  margin: 14px 10px 2px;
  text-transform: uppercase;
}
.chapter-group img {
  flex: 0 0 26px;
  width: 26px;
  height: 26px;
  object-fit: contain;
}
.chapter-group span { min-width: 0; }
.chapter-link {
  display: grid;
  grid-template-columns: 44px 1fr;
  align-items: start;
  min-height: 44px;
  gap: 10px;
  padding: 8px 10px;
  border-radius: 8px;
  color: var(--ink);
  text-decoration: none;
  font-size: 0.84rem;
  line-height: 1.22;
  overflow-wrap: anywhere;
}
.chapter-link span:last-child { padding-top: 4px; }
.chapter-link:hover,
.chapter-link.active {
  background: var(--panel);
  color: var(--teal-dark);
  box-shadow: 0 1px 0 rgba(59, 116, 110, 0.12);
}
.chapter-code {
  display: inline-grid;
  place-items: center;
  min-width: 36px;
  height: 28px;
  border-radius: 999px;
  background: #ddebe7;
  color: var(--teal-dark);
  font-size: 0.76rem;
  font-weight: 800;
}
:root[data-theme="dark"] .chapter-code {
  background: #27302e;
  color: #b7d0cb;
}

.book-main {
  min-height: 100vh;
  margin-left: var(--sidebar-width);
}
.nav-toggle {
  display: none;
  position: fixed;
  top: 14px;
  right: 14px;
  z-index: 35;
  min-height: 42px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 0 14px;
  background: var(--panel);
  color: var(--teal-dark);
  font-weight: 800;
  box-shadow: var(--shadow);
}
.nav-backdrop { display: none; }

.book-hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 520px);
  align-items: center;
  column-gap: clamp(28px, 5vw, 72px);
  row-gap: 12px;
  min-height: 72vh;
  padding: clamp(38px, 7vw, 86px);
  border-bottom: 1px solid var(--line);
  background: linear-gradient(135deg, var(--panel) 0%, var(--panel-subtle) 54%, rgba(159, 18, 57, 0.08) 100%);
}
.hero-title {
  grid-column: 1 / -1;
  font-size: clamp(2rem, 4vw, 3.8rem);
}
.author-row {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px 14px;
  color: var(--muted);
  font-size: 1rem;
  font-weight: 700;
}
.author-links {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
.author-links a {
  display: inline-grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 8px;
  color: var(--teal-dark);
  text-decoration: none;
}
.author-links a:hover {
  background: var(--panel-subtle);
  color: var(--berry);
}
.author-links svg { display: block; }
.book-hero-copy {
  max-width: 760px;
  margin-top: clamp(10px, 2vw, 24px);
}
.eyebrow {
  margin: 0 0 12px;
  color: var(--berry);
  font-size: 0.78rem;
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: 0;
}
h1, h2, h3, h4 {
  color: var(--heading);
  line-height: 1.18;
  letter-spacing: 0;
}
h1 { margin: 0; font-size: clamp(2.25rem, 5vw, 4.9rem); }
h2 { font-size: clamp(1.7rem, 3vw, 2.6rem); }
.lede,
.chapter-summary {
  max-width: 760px;
  color: var(--muted);
  font-size: 1.14rem;
}
.hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 28px;
}
.primary-action,
.secondary-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 46px;
  min-width: 164px;
  border-radius: 8px;
  padding: 0 18px;
  font-weight: 800;
  text-decoration: none;
}
.primary-action { background: var(--teal-dark); color: #fff; }
.primary-action:hover { background: var(--berry); color: #fff; }
.secondary-action { border: 1px solid var(--line); background: var(--panel); color: var(--teal-dark); }
.hero-image {
  width: 100%;
  max-height: 480px;
  object-fit: contain;
}

.chapter-grid-section { padding: clamp(34px, 6vw, 74px); }
.section-heading { max-width: 900px; margin-bottom: 24px; }
.section-heading h2 { margin: 0; }
.chapter-group-section + .chapter-group-section { margin-top: 34px; }
.chapter-grid-heading {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  color: var(--heading);
  font-size: 1.3rem;
  line-height: 1.2;
  margin: 0 0 14px;
}
.chapter-grid-heading img {
  flex: 0 0 34px;
  width: 34px;
  height: 34px;
  object-fit: contain;
}
.chapter-grid-heading span { min-width: 0; }
.chapter-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
  gap: 14px;
}
.chapter-card {
  display: grid;
  grid-template-rows: auto auto 1fr;
  gap: 12px;
  min-height: 210px;
  padding: 22px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--ink);
  text-decoration: none;
  box-shadow: 0 8px 22px rgba(44, 47, 43, 0.06);
}
.chapter-card:hover {
  border-color: rgba(59, 116, 110, 0.48);
  transform: translateY(-2px);
  box-shadow: var(--shadow);
}
.chapter-card strong { font-size: 1.16rem; line-height: 1.25; }
.chapter-card span:last-child { color: var(--muted); }

.chapter-page {
  width: min(100%, 1040px);
  margin: 0 auto;
  padding: clamp(32px, 6vw, 74px) clamp(20px, 5vw, 72px) 58px;
}
.chapter-header {
  margin-bottom: 24px;
  padding-bottom: 26px;
  border-bottom: 1px solid var(--line);
}
.chapter-header h1 { font-size: clamp(2rem, 4vw, 4.1rem); }
.back-link {
  display: inline-flex;
  margin-bottom: 22px;
  color: var(--teal-dark);
  font-weight: 800;
  text-decoration: none;
}
.chapter-toc {
  display: grid;
  gap: 7px;
  margin: 0 0 32px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
}
.chapter-toc strong {
  color: var(--teal-dark);
  font-size: 0.9rem;
}
.chapter-toc a {
  color: var(--ink);
  line-height: 1.3;
  text-decoration: none;
}
.chapter-toc a:hover { color: var(--berry); }
.chapter-toc .toc-h4 { padding-left: 16px; color: var(--muted); }

.notebook-content { padding: 0; background: transparent; }
.notebook-content .cell { margin: 0 0 18px; }
.notebook-content .prompt { display: none; }
.notebook-content .inner_cell,
.notebook-content .text_cell_render { width: 100%; }
.notebook-content p { margin: 0 0 1rem; }
.notebook-content img { max-width: 100%; height: auto; }
.notebook-content blockquote {
  margin: 24px 0;
  padding: 18px 22px;
  border-left: 4px solid var(--gold);
  background: var(--panel-warm);
  color: var(--ink);
}
.notebook-content table {
  display: block;
  width: 100%;
  overflow-x: auto;
  border-collapse: collapse;
  margin: 22px 0;
  background: var(--panel);
  border: 1px solid var(--line);
}
.notebook-content th,
.notebook-content td {
  padding: 12px 14px;
  border: 1px solid var(--line);
  vertical-align: top;
}
.notebook-content th {
  background: var(--panel-subtle);
  color: var(--teal-dark);
}
.notebook-content code,
.notebook-content pre {
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}
.notebook-content pre {
  overflow-x: auto;
  padding: 16px;
  border-radius: 8px;
  background: var(--code-bg);
  color: var(--code-text);
}
.notebook-content .highlight.hl-csharp pre {
  color: #d4d4d4;
  font-size: 0.8rem;
  line-height: 1.45;
}
.notebook-content .code_cell .output_wrapper {
  position: relative;
  margin: 12px 0 0;
  padding: 22px 14px 14px;
  border: 1px solid var(--output-border);
  border-left: 4px solid var(--output-accent);
  border-radius: 8px;
  background: var(--output-bg);
  font-size: 0.72rem;
  line-height: 1.45;
}
.notebook-content .code_cell .output_wrapper::before {
  content: "Output";
  position: absolute;
  top: 7px;
  left: 14px;
  color: var(--output-accent);
  font-size: 0.62rem;
  font-weight: 800;
  letter-spacing: 0;
  line-height: 1;
  text-transform: uppercase;
}
.notebook-content .code_cell .output_wrapper pre {
  margin: 0;
  padding: 0;
  border-radius: 0;
  background: transparent;
  color: var(--ink);
}
.notebook-content .code_cell .output_wrapper pre,
.notebook-content .code_cell .output_wrapper p,
.notebook-content .code_cell .output_wrapper li,
.notebook-content .code_cell .output_wrapper table,
.notebook-content .code_cell .output_wrapper th,
.notebook-content .code_cell .output_wrapper td,
.notebook-content .code_cell .output_subarea,
.notebook-content .code_cell .output_html,
.notebook-content .code_cell .output_markdown {
  font-size: inherit;
  line-height: inherit;
}
.notebook-content .code_cell .output_markdown,
.notebook-content .code_cell .output_markdown * {
  font-size: min(0.72rem, 12px);
  line-height: 1.45;
}
.notebook-content .highlight.hl-csharp .k,
.notebook-content .highlight.hl-csharp .kt { color: #569cd6; }
.notebook-content .highlight.hl-csharp .s,
.notebook-content .highlight.hl-csharp .s1,
.notebook-content .highlight.hl-csharp .s2,
.notebook-content .highlight.hl-csharp .se { color: #ce9178; }
.notebook-content .highlight.hl-csharp .c,
.notebook-content .highlight.hl-csharp .c1,
.notebook-content .highlight.hl-csharp .cm { color: #6a9955; }
.notebook-content .highlight.hl-csharp .n { color: #d4d4d4; }
.notebook-content .highlight.hl-csharp .na,
.notebook-content .highlight.hl-csharp .nf { color: #dcdcaa; }
.notebook-content .highlight.hl-csharp .nn { color: #4ec9b0; }
.notebook-content .highlight.hl-csharp .mi,
.notebook-content .highlight.hl-csharp .mf { color: #b5cea8; }
.notebook-content .highlight.hl-csharp .p,
.notebook-content .highlight.hl-csharp .o { color: #c8c8c8; }
.notebook-content h2,
.notebook-content h3,
.notebook-content h4 { position: relative; }
.anchor-link {
  color: #a0a09a;
  text-decoration: none;
  padding-left: 0.35rem;
}
.section-copy {
  margin-left: 8px;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 3px 7px;
  background: var(--panel);
  color: var(--teal-dark);
  cursor: pointer;
  font-size: 0.75rem;
  font-weight: 800;
  vertical-align: middle;
}

.chapter-pager {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 48px;
  padding-top: 26px;
  border-top: 1px solid var(--line);
}
.pager-link {
  display: grid;
  gap: 4px;
  min-height: 88px;
  padding: 18px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--ink);
  text-decoration: none;
}
.pager-link span {
  color: var(--muted);
  font-size: 0.82rem;
  font-weight: 800;
  text-transform: uppercase;
}
.pager-link strong { line-height: 1.25; }
.pager-link.align-right { text-align: right; }
.pager-link:not(.disabled):hover { border-color: var(--teal); box-shadow: var(--shadow); }
.pager-link.disabled { opacity: 0.48; }

@media (max-width: 900px) {
  .book-sidebar {
    transform: translateX(-100%);
    transition: transform 180ms ease;
    box-shadow: var(--shadow);
  }
  body.nav-open .book-sidebar { transform: translateX(0); }
  .book-main { margin-left: 0; }
  .nav-toggle { display: inline-flex; align-items: center; }
  body.nav-open .nav-backdrop {
    display: block;
    position: fixed;
    inset: 0;
    background: var(--backdrop);
    z-index: 15;
  }
  .book-hero {
    grid-template-columns: 1fr;
    min-height: auto;
    padding-top: 78px;
  }
  .hero-image { max-height: 340px; }
}

@media (max-width: 620px) {
  :root { --sidebar-width: min(86vw, 318px); }
  h1 { font-size: 2.25rem; }
  .book-hero,
  .chapter-grid-section { padding-left: 20px; padding-right: 20px; }
  .chapter-page { padding-top: 74px; }
  .chapter-pager { grid-template-columns: 1fr; }
  .pager-link.align-right { text-align: left; }
}

@media print {
  body { background: #fff; color: #111; }
  .book-sidebar,
  .nav-toggle,
  .nav-backdrop,
  .reading-progress,
  .back-link,
  .chapter-pager,
  .chapter-toc,
  .section-copy,
  .skip-link { display: none !important; }
  .book-main { margin-left: 0; }
  .chapter-page { width: 100%; padding: 0; }
  .chapter-header { break-after: avoid; }
  a { color: #111; text-decoration: underline; }
  .notebook-content blockquote,
  .notebook-content table { break-inside: avoid; }
}
"""


SITE_JS = r"""
(function () {
  const body = document.body;
  const progressBar = document.querySelector('.reading-progress span');
  const navToggle = document.querySelector('.nav-toggle');
  const closeNav = document.querySelector('[data-close-nav]');
  const themeToggle = document.querySelector('[data-theme-toggle]');
  const themeToggleIcon = document.querySelector('.theme-toggle-icon');

  function getInitialTheme() {
    try {
      const saved = localStorage.getItem('di-theme');
      if (saved === 'light' || saved === 'dark') return saved;
    } catch (error) {
      return document.documentElement.dataset.theme || 'light';
    }
    return document.documentElement.dataset.theme || 'light';
  }

  function applyTheme(theme, persist) {
    const normalized = theme === 'dark' ? 'dark' : 'light';
    document.documentElement.dataset.theme = normalized;
    if (themeToggle) {
      themeToggle.setAttribute('aria-pressed', String(normalized === 'dark'));
      themeToggle.setAttribute(
        'aria-label',
        normalized === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'
      );
    }
    if (themeToggleIcon) themeToggleIcon.textContent = normalized === 'dark' ? '☾' : '☀';
    if (persist) {
      try {
        localStorage.setItem('di-theme', normalized);
      } catch (error) {
        // Ignore storage failures; the visual toggle still works for this page.
      }
    }
  }

  function updateProgress() {
    if (!progressBar) return;
    const scrollTop = window.scrollY || document.documentElement.scrollTop;
    const max = document.documentElement.scrollHeight - window.innerHeight;
    const percent = max > 0 ? Math.min(100, Math.max(0, (scrollTop / max) * 100)) : 0;
    progressBar.style.width = percent + '%';
  }

  function setNav(open) {
    body.classList.toggle('nav-open', open);
    if (navToggle) navToggle.setAttribute('aria-expanded', String(open));
  }

  function isTypingTarget(target) {
    if (!target) return false;
    const tag = target.tagName;
    return target.isContentEditable || tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
  }

  function copySectionLink(heading, button) {
    const url = new URL(window.location.href);
    url.hash = heading.id;
    const text = url.toString();
    const fallback = function () {
      window.prompt('Copy section link', text);
    };
    if (!navigator.clipboard) {
      fallback();
      return;
    }
    navigator.clipboard.writeText(text).then(function () {
      const original = button.textContent;
      button.textContent = 'Copied';
      window.setTimeout(function () {
        button.textContent = original;
      }, 1200);
    }).catch(fallback);
  }

  if (navToggle) {
    navToggle.addEventListener('click', () => setNav(!body.classList.contains('nav-open')));
  }

  if (closeNav) {
    closeNav.addEventListener('click', () => setNav(false));
  }

  if (themeToggle) {
    applyTheme(getInitialTheme(), false);
    themeToggle.addEventListener('click', () => {
      const current = document.documentElement.dataset.theme === 'dark' ? 'dark' : 'light';
      applyTheme(current === 'dark' ? 'light' : 'dark', true);
    });
  }

  document.querySelectorAll('.chapter-link').forEach((link) => {
    link.addEventListener('click', () => setNav(false));
  });

  document.querySelectorAll('.notebook-content h2[id], .notebook-content h3[id], .notebook-content h4[id]').forEach((heading) => {
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'section-copy';
    button.textContent = 'Copy link';
    button.setAttribute('aria-label', 'Copy link to ' + heading.textContent.replace('¶', '').trim());
    button.addEventListener('click', () => copySectionLink(heading, button));
    heading.appendChild(button);
  });

  window.addEventListener('keydown', (event) => {
    if (event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey || isTypingTarget(event.target)) {
      return;
    }
    if (event.key === 'ArrowLeft') {
      const prev = document.querySelector('[data-prev-chapter]');
      if (prev) window.location.href = prev.href;
    }
    if (event.key === 'ArrowRight') {
      const next = document.querySelector('[data-next-chapter]');
      if (next) window.location.href = next.href;
    }
  });

  window.addEventListener('scroll', updateProgress, { passive: true });
  window.addEventListener('resize', updateProgress);
  updateProgress();
})();
"""


if __name__ == "__main__":
    main()
