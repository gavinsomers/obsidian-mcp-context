# Context Extraction

The parser should preserve source paths, heading paths, block ranges, and line numbers.

## Examples

Inline code like `[[Not A Link]]` should not create wikilinks.

Real links such as [[Project Atlas]] should be preserved.
