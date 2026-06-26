from obsidian_mcp_context.parser import parse_markdown_text, parse_plain_text


def test_parser_extracts_tasks_links_tags_and_headings():
    parsed = parse_markdown_text(
        """---
type: daily
---
# Morning

- [ ] Follow up with [[Morgan Lee]] about [[Project Atlas]]
- [x] Send invoice

## Project Notes

Discussed [[Synthetic Knowledge Base]].
- [ ] Draft Phase 1 plan #product
""",
        "Daily/2026-06-25.md",
    )

    open_tasks = [task for task in parsed.tasks if not task.checked]
    checked_tasks = [task for task in parsed.tasks if task.checked]

    assert len(open_tasks) == 2
    assert len(checked_tasks) == 1
    assert open_tasks[0].line_number == 6
    assert open_tasks[0].heading == "Morning"
    assert open_tasks[1].heading == "Project Notes"
    assert any(line.text == "Discussed [[Synthetic Knowledge Base]]." for line in parsed.lines)
    assert {link.link_target for link in parsed.links} == {
        "Morgan Lee",
        "Project Atlas",
        "Synthetic Knowledge Base",
    }
    assert [tag.tag for tag in parsed.tags] == ["product"]


def test_parser_ignores_tasks_links_and_tags_inside_fenced_code():
    parsed = parse_markdown_text(
        """# Project Atlas

```python
#ignore-tag
- [ ] ignore task inside code
[[Ignore Me]]
```

- [ ] Review timeline
""",
        "Projects/Atlas.md",
    )

    assert len(parsed.tasks) == 1
    assert parsed.tasks[0].task_text == "Review timeline"
    assert parsed.tasks[0].line_number == 9
    assert parsed.links == []
    assert parsed.tags == []


def test_parser_ignores_wikilinks_and_tags_inside_inline_code():
    parsed = parse_markdown_text(
        "Use `[[target]]` and `#ignore` as examples, but link [[Real Note]] #real.\n",
        "Examples.md",
    )

    assert [link.link_target for link in parsed.links] == ["Real Note"]
    assert [tag.tag for tag in parsed.tags] == ["real"]


def test_parse_plain_text_creates_source_block_and_lines_without_markdown_objects():
    parsed = parse_plain_text(
        "Meeting notes\n\nPlain #tag [[Link]] text\n",
        "Notes/plain.txt",
    )

    assert len(parsed.blocks) == 1
    assert parsed.blocks[0].source_path == "Notes/plain.txt"
    assert parsed.blocks[0].start_line == 1
    assert parsed.blocks[0].end_line == 3
    assert [line.line_number for line in parsed.lines] == [1, 3]
    assert parsed.tasks == []
    assert parsed.links == []
    assert parsed.tags == []
