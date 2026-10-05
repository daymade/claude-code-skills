"""Synthetic structure fixtures; run with uv run --with pytest pytest scripts/test_html_to_markdown.py."""
from collections import Counter
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from html_to_markdown import convert_html, prepare_html, verify_links, markdown_links
from convert import select_tools

PANDOC = pytest.mark.skipif(not shutil.which("pandoc"), reason="requires pandoc")


@pytest.fixture
def html_file(tmp_path):
    def write(source):
        path = tmp_path / "sample.html"
        path.write_text(source, encoding="utf-8")
        return path
    return write


@PANDOC
def test_card_title_and_preview(html_file):
    md = convert_html(html_file('''<ol><li><a href="1.md"><strong>First title</strong>
    <p>A separate preview with [brackets].</p></a></li></ol>'''))
    assert '[**First title**](1.md)' in md
    assert '\n\n' in md
    assert 'A separate preview' in md
    assert markdown_links(md) == Counter({'1.md': 1})
    assert md.index('](1.md)') < md.index('A separate preview')


@PANDOC
def test_figure_caption_is_separate(html_file):
    md = convert_html(html_file('''<figure><img src="images/sample.png" alt="Diagram">
    <figcaption>Caption <a href="sources.md#one">source</a></figcaption></figure>
    <p>Following paragraph.</p>'''))
    assert '![Diagram](images/sample.png)\n\nCaption [source](sources.md#one)' in md
    assert 'Caption' not in md.splitlines()[0]
    assert '\n\nFollowing paragraph.' in md


@PANDOC
def test_headings_and_fenced_heading_text(html_file):
    md = convert_html(html_file('<h1>Chapter</h1><h2>Section</h2><h3>Detail</h3>'
                                '<pre><code class="language-text"># This is code\n## Also code</code></pre>'))
    assert '# Chapter\n' in md and '## Section\n' in md and '### Detail\n' in md
    assert '``` text\n# This is code\n## Also code\n```' in md


@PANDOC
def test_escaped_label_fragments_and_uri_encoding(html_file):
    md = convert_html(html_file('<a href="guide.md#part-2">A [label] *literal*</a> '
                                '<a href="other page.md#说明">Second</a>'))
    assert r'A \[label\] \*literal\*' in md
    assert verify_links(Counter({'guide.md#part-2': 1, 'other page.md#说明': 1}), md) == 2


@PANDOC
@pytest.mark.parametrize('broken', [
    '[Title\n\nPreview](1.md)',
    '```markdown\n[Title](1.md)\n```',
    '![Title](1.md)',
    'Title (1.md)',
])
def test_broken_card_never_false_green(broken):
    with pytest.raises(ValueError, match=r"1.md.*1 missing"):
        verify_links(Counter({'1.md': 1}), broken)


@PANDOC
def test_duplicate_link_loss_and_encoded_delimiters():
    with pytest.raises(ValueError, match='1 missing'):
        verify_links(Counter({'one.md': 2}), '[One](one.md)')
    with pytest.raises(ValueError, match='verification failed'):
        verify_links(Counter({'one.md%23part': 1}), '[One](one.md#part)')


def test_selector_scope_and_default_no_truncation():
    source = ('<html><head><title>Site title</title></head><body><nav><a href="nav.md">Nav</a></nav>'
              '<article id="content" class="article"><h1>Title</h1><a href="body.md">Body</a>'
              '<script>ignored()</script></article><p>Tail</p></body></html>')
    body, links = prepare_html(source)
    assert 'Tail' in body and 'nav.md' in body and 'Site title' not in body
    for selector in ['article', '#content', '.article']:
        selected, selected_links = prepare_html(source, selector)
        assert selected_links == Counter({'body.md': 1})
        assert 'nav.md' not in selected and 'Tail' not in selected and 'ignored' not in selected
    assert links == Counter({'nav.md': 1, 'body.md': 1})


@pytest.mark.parametrize('selector', ['missing', 'article p', 'p'])
def test_selector_missing_complex_or_ambiguous_is_error(selector):
    with pytest.raises(ValueError):
        prepare_html('<p>First</p><p>Second</p>', selector)


@PANDOC
def test_failed_verification_does_not_write_cli_output(tmp_path, monkeypatch, capsys):
    import convert
    import html_to_markdown
    source = tmp_path / 'broken.htm'
    source.write_text('<a href="missing.md"><strong>Title</strong><p>Preview</p></a>', encoding='utf-8')
    output = tmp_path / 'out.md'
    output.write_text('Existing content', encoding='utf-8')
    real_pandoc = html_to_markdown._pandoc
    def broken_conversion(text, source_format, target_format, extra_args=()):
        if source_format == 'html':
            return '[Title\n\nPreview](missing.md)'
        return real_pandoc(text, source_format, target_format, extra_args)
    monkeypatch.setattr(html_to_markdown, '_pandoc', broken_conversion)
    monkeypatch.setattr(sys, 'argv', ['convert.py', str(source), '-o', str(output)])
    with pytest.raises(SystemExit) as error:
        convert.main()
    assert error.value.code == 1
    assert 'missing.md' in capsys.readouterr().err
    assert output.read_text() == 'Existing content'


@PANDOC
def test_htm_cli_and_office_tool_selection(tmp_path, monkeypatch):
    import convert
    monkeypatch.setattr(convert, 'check_tool_available', lambda tool: True)
    assert select_tools(Path('office.docx'), 'quick') == ['pandoc']
    assert select_tools(Path('office.docx'), 'heavy') == ['pandoc', 'markitdown']
    assert select_tools(Path('office.pptx'), 'quick') == ['markitdown']
    source = tmp_path / 'input.htm'
    source.write_text('<nav>Nav</nav><main><h2>Content</h2><a href="#section">Jump</a></main>')
    output = tmp_path / 'out.md'
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('convert.py')),
                             str(source), '-o', str(output), '--html-selector', 'main'],
                            text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert 'HTML links verified' in result.stdout
    assert output.read_text().startswith('## Content')
    assert 'Nav' not in output.read_text()


@PANDOC
def test_heading_offset_does_not_touch_code(html_file):
    md = convert_html(html_file('<h1>Lesson</h1><h2>Topic</h2>'
                                '<pre><code class="language-text"># Code title</code></pre>'), heading_offset=2)
    assert '### Lesson' in md and '#### Topic' in md
    assert '# Code title' in md and '### Code title' not in md
    with pytest.raises(ValueError, match='exceed'):
        convert_html(html_file('<h5>Deep</h5>'), heading_offset=2)


@PANDOC
def test_saved_markdown_validator_cli(tmp_path):
    source = tmp_path / 'source.html'
    source.write_text('<a href="1.md"><strong>Title</strong><p>Preview</p></a>')
    md = tmp_path / 'existing.md'
    md.write_text('[Title\n\nPreview](1.md)')
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('html_to_markdown.py')),
                             str(source), str(md)], text=True, capture_output=True)
    assert result.returncode == 1 and '1.md' in result.stderr
    md.write_text('[Title](1.md)\n\nPreview')
    result = subprocess.run([sys.executable, str(Path(__file__).with_name('html_to_markdown.py')),
                             str(source), str(md)], text=True, capture_output=True)
    assert result.returncode == 0 and '1 source hyperlinks' in result.stdout


@PANDOC
def test_caption_title_and_description_are_distinct_paragraphs(html_file):
    md = convert_html(html_file('<figure><img src="diagram.png" alt="Diagram">'
                                '<figcaption>\n  <strong>Caption title</strong>'
                                '<span>Explanation text.</span></figcaption></figure>'))
    assert '![Diagram](diagram.png)\n\n**Caption title**\n\nExplanation text.' in md


@PANDOC
def test_styled_pager_and_svg_link_are_markdown_links(html_file):
    md = convert_html(html_file('<nav><a class="pager" href="next.md"><span class="direction">'
                                '<svg viewBox="0 0 16 16"><path d="M3 8"/></svg>Next</span>'
                                '<strong>Title</strong></a></nav>'))
    assert markdown_links(md) == Counter({'next.md': 1})
    assert 'data:image/svg+xml' in md


@PANDOC
@pytest.mark.parametrize('flag', ['--heavy', '--assets-dir'])
def test_unsupported_html_modes_fail_explicitly(tmp_path, flag):
    source = tmp_path / 'source.html'
    source.write_text('<p>Body</p>')
    command = [sys.executable, str(Path(__file__).with_name('convert.py')), str(source), flag]
    if flag == '--assets-dir':
        command.append(str(tmp_path / 'assets'))
    result = subprocess.run(command, text=True, capture_output=True)
    assert result.returncode == 2 and 'unsupported' in result.stderr
    assert not source.with_suffix('.md').exists()


@PANDOC
def test_svg_internal_style_is_preserved(html_file):
    import base64
    import re
    md = convert_html(html_file('<style>.page {color: red}</style>'
                                '<svg viewBox="0 0 100 100">'
                                '<style>.colored {fill: #ff0000}</style>'
                                '<defs><linearGradient id="paint"><stop offset="0%"/></linearGradient></defs>'
                                '<rect class="colored" width="100" height="100"/>'
                                '</svg>'))
    encoded = re.search(r'data:image/svg\+xml;base64,([A-Za-z0-9+/=]+)', md)
    assert encoded
    svg = base64.b64decode(encoded.group(1)).decode()
    assert '<style>.colored {fill: #ff0000}</style>' in svg
    assert 'class="colored"' in svg and 'viewBox=' in svg
    assert '.page' not in svg
    import xml.etree.ElementTree as ET
    parsed = ET.fromstring(svg)
    assert parsed.find('.//{http://www.w3.org/2000/svg}linearGradient') is not None
