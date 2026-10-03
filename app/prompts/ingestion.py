

VISION_READER_PROMPT = """
Read this document page.

Return:

(1) extracted_text:
Every piece of text on the page, verbatim.

Prefix every LIST-ITEM line with '- ' (markdown style),
keeping its original number or letter
(e.g. '- [3] ...' or '- 2. ...').

Tabular content should be represented as one line per row.

(2) caption:
Provide a detailed description of any chart, photo, diagram,
or notable layout.

The page's raw text layer follows. Copy exact values from it
and use the image primarily for structure and visuals:

<text>
{native_text}
</text>
"""