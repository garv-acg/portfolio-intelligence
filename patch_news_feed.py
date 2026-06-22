import re

path = "app/data/news_feed.py"
content = open(path, encoding="utf-8").read()

# Find and replace the entire second_pass block in _fix_encoding
# Using regex to match whatever is currently there
pattern = r'    # Second pass.*?return text'
new_block = (
    "    # Second pass: Unicode codepoints for double-encoded smart quotes\n"
    "    # Run BEFORE latin1 roundtrip which would destroy these sequences\n"
    "    second_pass = [\n"
    "        (\"\u00e2\u20ac\u02dc\", \"\u2018\"),\n"
    "        (\"\u00e2\u20ac\u2122\", \"\u2019\"),\n"
    "        (\"\u00e2\u20ac\u0153\", \"\u201c\"),\n"
    "        (\"\u00e2\u20ac\u201d\", \"\u201d\"),\n"
    "        (\"\u00e2\u20ac\u201c\", \"\u2013\"),\n"
    "        (\"\u00e2\u20ac\u201e\", \"\u2014\"),\n"
    "    ]\n"
    "    for bad, good in second_pass:\n"
    "        text = text.replace(bad, good)\n"
    "    return text"
)

# Also fix the ORDER — second_pass must run before the latin1 decode
# Rewrite _fix_encoding entirely to get the order right
old_fn = content[content.find("def _fix_encoding"):content.find("\ndef _domain_from_url")]

new_fn = (
    "def _fix_encoding(text: str) -> str:\n"
    "    if not isinstance(text, str):\n"
    "        return text\n"
    "    # First: fix double-encoded smart quotes BEFORE latin1 roundtrip destroys them\n"
    "    second_pass = [\n"
    "        (\"\u00e2\u20ac\u02dc\", \"\u2018\"),\n"
    "        (\"\u00e2\u20ac\u2122\", \"\u2019\"),\n"
    "        (\"\u00e2\u20ac\u0153\", \"\u201c\"),\n"
    "        (\"\u00e2\u20ac\u201d\", \"\u201d\"),\n"
    "        (\"\u00e2\u20ac\u201c\", \"\u2013\"),\n"
    "        (\"\u00e2\u20ac\u201e\", \"\u2014\"),\n"
    "    ]\n"
    "    for bad, good in second_pass:\n"
    "        text = text.replace(bad, good)\n"
    "    # Then: byte-level replacements\n"
    "    replacements = {\n"
    "        \"\\xe2\\x80\\x99\": \"\u2019\",\n"
    "        \"\\xe2\\x80\\x98\": \"\u2018\",\n"
    "        \"\\xe2\\x80\\x9c\": \"\u201c\",\n"
    "        \"\\xe2\\x80\\x9d\": \"\u201d\",\n"
    "        \"\\xe2\\x80\\x93\": \"\u2013\",\n"
    "        \"\\xe2\\x80\\x94\": \"\u2014\",\n"
    "        \"\\xe2\\x80\\xa2\": \"\u2022\",\n"
    "        \"\\xe2\\x82\\xac\": \"\u20ac\",\n"
    "        \"\\xc2\\xa0\": \" \",\n"
    "        \"\\xc2\": \"\",\n"
    "    }\n"
    "    for bad, good in replacements.items():\n"
    "        text = text.replace(bad, good)\n"
    "    # Finally: latin1 roundtrip for any remaining garbled sequences\n"
    "    try:\n"
    "        if \"\u00e2\" in text or \"\u00c3\" in text:\n"
    "            text = text.encode(\"latin1\", errors=\"ignore\").decode(\"utf-8\", errors=\"ignore\")\n"
    "    except Exception:\n"
    "        pass\n"
    "    return text\n"
)

if old_fn in content:
    content = content.replace(old_fn, new_fn)
    open(path, "w", encoding="utf-8").write(content)
    print("_fix_encoding rewritten with correct order")
else:
    print("ERROR: could not find _fix_encoding function")
    print("First 100 chars of old_fn:", repr(old_fn[:100]))
