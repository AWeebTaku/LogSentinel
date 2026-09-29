"""Line -> message content, and masking of volatile tokens.

`content` drops the per-dataset header (timestamps, pids, node ids). For BGL/Thunderbird the header
also carries the **ground-truth label** (first token), so stripping it here is a leakage guard:
nothing downstream may ever see it.
"""
import re

# whitespace-separated header tokens to drop before the message (split(None, n) collapses padding)
_HEADER_TOKENS = {
    "hdfs": 4,          # date time pid LEVEL -> "dfs.Component: message"
    "bgl": 9,           # label ts date node time node type component level
    "thunderbird": 8,   # label ts date host Mon D HH:MM:SS user@host
}

# One alternation, one pass: block ids, IPv4(:port), hex, any number.
_MASK = re.compile(
    r"blk_-?\d+|\b\d{1,3}(?:\.\d{1,3}){3}(?::\d+)?\b|\b0x[0-9a-fA-F]+\b|(?<![A-Za-z])-?\d+(?:\.\d+)?"
)
_WS = re.compile(r"\s+")


def content(line: str, dataset: str) -> str:
    n = _HEADER_TOKENS[dataset]
    parts = line.split(None, n)
    return parts[n] if len(parts) > n else ""


def mask(text: str) -> str:
    return _WS.sub(" ", _MASK.sub("<*>", text)).strip()
