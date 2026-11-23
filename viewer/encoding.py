"""Accept UTF-8 localized game tables as well as the older Windows-1252 files."""
import re
from pathlib import Path

LEGACY_DECODER = re.compile(r'new TextDecoder\("(?:windows-1252|latin1)"\)\.decode\(')
DECODER = """
const wc3Utf8 = new TextDecoder("utf-8", {fatal:true});
const wc3Ansi = new TextDecoder("windows-1252");
function wc3GameText(bytes) {
  try { return wc3Utf8.decode(bytes); }
  catch { return wc3Ansi.decode(bytes); }
}
"""

def patch_text_decoders(dist):
    for chunk in sorted((Path(dist) / 'assets').glob('*.js')):
        source = chunk.read_text()
        patched, count = LEGACY_DECODER.subn('wc3GameText(', source)
        if count:
            chunk.write_text(DECODER + patched)
