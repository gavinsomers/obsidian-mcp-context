from obsidian_mcp_context.domain import note_title


def test_note_title_prefers_explicit_frontmatter_title():
    text = "---\ntitle: Display Name\n---\n# Heading Name\n"

    assert note_title("people/display_name.md", text) == "Display Name"


def test_note_title_uses_first_h1_for_machine_friendly_filename():
    text = '---\naliases: ["Morgan Lee"]\n---\n# Morgan Lee\n'

    assert note_title("people/morgan_lee.md", text) == "Morgan Lee"


def test_note_title_falls_back_to_filename_stem_without_note_text():
    assert note_title("people/morgan_lee.md") == "morgan_lee"
