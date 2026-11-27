"""Academic Markdown Formatter & Standardizer for CyberLearn Studio.

Ensures all past and future notes and lessons adhere to publication-grade
academic courseware standards: clear hierarchical headings, distinct paragraphs,
structured bullet points, terminal command blocks, and callout boxes.
"""

from __future__ import annotations

import re


def standardize_title(raw_title: str, content: str = "") -> str:
    """Derive a clean, publication-ready Title Case title."""
    title = (raw_title or "").strip()

    # Detect if title is generic or empty
    norm_title = re.sub(r"[_\s-]+", " ", title).strip().lower()
    if not title or norm_title in {"untitled lesson", "untitled", "lesson", "untitled document", "new lesson", "new note"}:
        # Try extracting title from content
        if content:
            target_match = re.search(r"🎯\s*([A-Za-z0-9_-]+)", content)
            if target_match:
                title = target_match.group(1)
            else:
                heading_match = re.search(r"^#{1,3}\s+(.+)$", content, flags=re.MULTILINE)
                if heading_match:
                    title = heading_match.group(1)
                else:
                    first_line = content.strip().splitlines()[0]
                    clean_first = re.sub(r"^[🛡📝📚🎯📖\s*#-]+", "", first_line).strip()
                    if 3 < len(clean_first) < 50:
                        title = clean_first

    if not title:
        title = "Academic Reference Guide"

    # Clean punctuation and snake_case
    title = title.replace("_", " ").replace("-", " ").strip()
    # Normalize common abbreviations
    title = re.sub(r"\bip\b", "IP", title, flags=re.IGNORECASE)
    title = re.sub(r"\bapi\b", "API", title, flags=re.IGNORECASE)
    title = re.sub(r"\bpdf\b", "PDF", title, flags=re.IGNORECASE)
    title = re.sub(r"\bngfw\b", "NGFW", title, flags=re.IGNORECASE)
    title = re.sub(r"\bwaf\b", "WAF", title, flags=re.IGNORECASE)
    title = re.sub(r"\btcp\b", "TCP", title, flags=re.IGNORECASE)
    title = re.sub(r"\budp\b", "UDP", title, flags=re.IGNORECASE)
    title = re.sub(r"\bdns\b", "DNS", title, flags=re.IGNORECASE)
    title = re.sub(r"\bssh\b", "SSH", title, flags=re.IGNORECASE)
    title = re.sub(r"\bhttps?\b", lambda m: m.group(0).upper(), title, flags=re.IGNORECASE)

    # Convert to Title Case
    words = title.split()
    capitalized = []
    minor_words = {"a", "an", "the", "and", "but", "or", "for", "nor", "on", "at", "to", "from", "by", "over", "in", "of", "with"}
    for idx, w in enumerate(words):
        lw = w.lower()
        if idx > 0 and lw in minor_words:
            capitalized.append(lw)
        elif w.isupper() and len(w) > 1:
            capitalized.append(w)
        else:
            capitalized.append(w.capitalize())

    return " ".join(capitalized)


def standardize_academic_markdown(content: str, title: str = "") -> str:
    """Transform messy, unstructured, single-newline or imported notes into clean academic courseware."""
    if not content or not content.strip():
        return ""

    text = content.replace("\r\n", "\n").strip()

    # 1. Strip raw Telegram wrapper cards and footer tags
    text = re.sub(r"^[\s\S]*?━━━━━━━━━━━━━━━━━━\s*\n", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*[🛡📝📚🎯📖]\s*([^\n]+)\n+", "", text)
    text = re.sub(r"\n*\(ID:\s*\d+\s*\|\s*Delete with\s*/deletenote\s*\d+\)\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^\s*[\.\s·•_-]{1,4}\s*$", "", text, flags=re.MULTILINE)

    lines = [line.strip() for line in text.split("\n")]
    processed: list[str] = []
    command_acc: list[str] = []

    def flush_commands() -> None:
        nonlocal command_acc
        if command_acc:
            processed.append("")
            processed.append("```bash\n" + "\n".join(command_acc) + "\n```")
            processed.append("")
            command_acc = []

    for line in lines:
        if not line:
            flush_commands()
            if processed and processed[-1] != "":
                processed.append("")
            continue

        # Skip separator dots
        if re.match(r"^[\.\s·•_-]{1,4}$", line):
            continue

        # Check if line is a Linux shell command
        is_cmd = bool(
            re.match(r"^(touch|ls|chmod|sudo|chown|cat|rm|mkdir|cp|mv|grep|find|systemctl|iptables|ufw|nano|vim)\b", line)
            and "➔" not in line and "=" not in line and "(" not in line and ")" not in line and not line.endswith(":")
        )
        if is_cmd:
            command_acc.append(line)
            continue
        else:
            flush_commands()

        # Section indicators (e.g. "📖 01 | In Linux, these letters are actually math numbers")
        sec_match = re.match(r"^(?:📖|📚)?\s*(\d{1,2})\s*\|\s*(.+)$", line)
        if sec_match:
            sec_num = int(sec_match.group(1))
            sec_name = sec_match.group(2).strip()
            processed.append("")
            processed.append(f"## Section {sec_num}: {sec_name}")
            processed.append("")
            continue

        # Step workflow headings (e.g. "1 Create and Inspect", "Step 1: ...")
        step_match = re.match(r"^(?:Step\s+)?(\d+)[\.:\s]\s*([A-Za-z][A-Za-z0-9\s&/—–-]{3,50})$", line)
        if step_match and "(" not in line and "=" not in line:
            processed.append("")
            processed.append(f"### Step {step_match.group(1)}: {step_match.group(2).strip()}")
            processed.append("")
            continue

        # Educational Analogy or Core Concept header
        if re.match(r"^(?:💡\s*)?(In simple words|Think of it this way|Real-world analogy|Analogy):?$", line, flags=re.IGNORECASE):
            processed.append("")
            processed.append("> **💡 Core Analogy:**")
            continue

        # Educational Callout Cards
        callout_match = re.match(r"^(?:💡\s*)?(The Golden Rules|Example(?: Scenario)?:?|Why this is genius:?|Important:?|Warning:?|Key Takeaway:?)$", line, flags=re.IGNORECASE)
        if callout_match:
            heading = callout_match.group(1).rstrip(":").strip()
            processed.append("")
            processed.append(f"> **💡 {heading}:**")
            continue

        # Linux Permission String (e.g. -rwxr-xr-- or -rw-------)
        if re.match(r"^[-d][-rwx]{9}$", line):
            processed.append("")
            processed.append(f"`{line}`")
            processed.append("")
            continue

        # Standalone Question Inquiries (e.g. "Why 4, 2, and 1? Why not 1, 2, and 3, or 10, 20, and 30?")
        if re.match(r"^[A-Z][A-Za-z0-9\s,—–-]{8,85}\?$", line):
            processed.append("")
            processed.append(f"### Key Question: {line}")
            processed.append("")
            continue

        # Numbered section questions/titles (e.g. "1. How does a port work?")
        num_header = re.match(r"^(\d+)[\.:\s]\s*([A-Za-z][A-Za-z0-9\s,—–-]+\??)$", line)
        if num_header and len(line) < 60 and not line.startswith("http"):
            processed.append("")
            processed.append(f"## {standardize_title(num_header.group(2).rstrip('?'))}")
            processed.append("")
            continue

        # Standalone Topic Headers (e.g. "File permissions", "Types of firewalls:")
        if re.match(r"^(Types of firewalls|Classification of firewalls|File permissions?|Traffic action decisions|How does a port work\?):?$", line, flags=re.IGNORECASE):
            header_clean = line.rstrip(":").strip()
            processed.append("")
            processed.append(f"## {standardize_title(header_clean)}")
            processed.append("")
            continue

        # Sub-topic items like "Packet Filtering (The Basic Bouncer): Description"
        sub_type_match = re.match(r"^([A-Z][A-Za-z0-9\s&—–-]+(?:\([A-Za-z0-9\s—–-]+\))?):\s*(.+)$", line)
        if sub_type_match and len(sub_type_match.group(1)) < 60 and not line.startswith("http"):
            key = sub_type_match.group(1).strip()
            val = sub_type_match.group(2).strip()
            # If it looks like a major type or sub-section
            if any(k in key.lower() for k in ["packet filtering", "stateful", "proxy", "next-generation", "ngfw", "waf", "web application"]):
                processed.append("")
                processed.append(f"### {key}")
                processed.append(val)
                processed.append("")
                continue

        # Definition and Formula bullet points
        is_bullet_def = bool(
            re.match(r"^(Owner|Group|World)\s*:", line, flags=re.IGNORECASE)
            or re.match(r"^(Read|Write|Execute)\s*\([rwx]\)\s*=", line, flags=re.IGNORECASE)
            or re.match(r"^\d+\s*(?:\([^)]+\))?\s*=\s*", line)
            or re.match(r"^chmod\s+[0-9+]", line, flags=re.IGNORECASE)
            or re.match(r"^(?:IP address|Port|Application/service)\s*=", line, flags=re.IGNORECASE)
            or re.match(r"^[✅⛔🛡️✓✗]\s*(?:Allow|Deny|Drop|Reject|Accept)\b", line, flags=re.IGNORECASE)
        )
        if is_bullet_def:
            if ":" in line and not line.startswith("-") and not line.startswith("*"):
                parts = line.split(":", 1)
                processed.append(f"- **{parts[0].strip()}**: {parts[1].strip()}")
            elif "=" in line and not line.startswith("-") and not line.startswith("*"):
                parts = line.split("=", 1)
                processed.append(f"- **{parts[0].strip()}** = {parts[1].strip()}")
            elif line.startswith("chmod"):
                processed.append(f"- `{line}`")
            else:
                processed.append(f"- {line}")
            continue

        # Normal prose line
        # If previous item was a bullet point or blank, add directly
        if not processed or processed[-1] == "" or processed[-1].startswith(("-", "#", ">")):
            processed.append(line)
        else:
            prev = processed[-1]
            # If previous line ends with a terminal punctuation, create a new paragraph
            if prev.endswith((".", "!", "?", ":")) or len(line) > 60 or len(prev) < 40:
                processed.append("")
                processed.append(line)
            else:
                processed[-1] += " " + line

    flush_commands()

    # Join and collapse surplus spacing
    result = "\n".join(processed)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result
