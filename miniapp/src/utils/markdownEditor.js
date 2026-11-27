/**
 * Comprehensive Markdown Editor utilities for CyberLearn Studio
 * Supports inline wrapping, line-level prefixes, list auto-continuation,
 * unformatting/toggling, link insertion, and active format detection.
 */

/**
 * Applies or removes inline wrapping (e.g., **bold**, *italic*, `code`).
 * If selection is already wrapped, unwraps it.
 * If empty selection, inserts prefix + suffix and places cursor in between.
 */
export function applyInlineFormat(value, start, end, prefix, suffix = prefix) {
  const selected = value.substring(start, end);
  const prefixLen = prefix.length;
  const suffixLen = suffix.length;

  // Case 1: Text is selected
  if (start !== end) {
    // Check if the selected text itself starts and ends with the markers
    if (selected.startsWith(prefix) && selected.endsWith(suffix) && selected.length >= prefixLen + suffixLen) {
      // Unwrap the inside
      const unwrapped = selected.slice(prefixLen, selected.length - suffixLen);
      const nextValue = value.substring(0, start) + unwrapped + value.substring(end);
      return {
        value: nextValue,
        selectionStart: start,
        selectionEnd: start + unwrapped.length,
      };
    }

    // Check if the markers are immediately outside the selection
    const hasPrefixBefore = value.substring(start - prefixLen, start) === prefix;
    const hasSuffixAfter = value.substring(end, end + suffixLen) === suffix;
    if (hasPrefixBefore && hasSuffixAfter) {
      // Unwrap
      const nextValue = value.substring(0, start - prefixLen) + selected + value.substring(end + suffixLen);
      return {
        value: nextValue,
        selectionStart: start - prefixLen,
        selectionEnd: start - prefixLen + selected.length,
      };
    }

    // Otherwise, wrap the selection
    const wrapped = prefix + selected + suffix;
    const nextValue = value.substring(0, start) + wrapped + value.substring(end);
    return {
      value: nextValue,
      selectionStart: start + prefixLen,
      selectionEnd: start + prefixLen + selected.length,
    };
  }

  // Case 2: No text selected (collapsed cursor)
  // Check if cursor is right between markers (e.g. **|**) -> unwrap
  const hasPrefixBefore = value.substring(start - prefixLen, start) === prefix;
  const hasSuffixAfter = value.substring(start, start + suffixLen) === suffix;
  if (hasPrefixBefore && hasSuffixAfter) {
    const nextValue = value.substring(0, start - prefixLen) + value.substring(start + suffixLen);
    return {
      value: nextValue,
      selectionStart: start - prefixLen,
      selectionEnd: start - prefixLen,
    };
  }

  // Insert markers and place cursor between them
  const inserted = prefix + suffix;
  const nextValue = value.substring(0, start) + inserted + value.substring(start);
  return {
    value: nextValue,
    selectionStart: start + prefixLen,
    selectionEnd: start + prefixLen,
  };
}

/**
 * Finds the start of the line containing pos, and the end of the line containing endPos.
 */
function getLineRange(value, start, end) {
  const lineStart = value.lastIndexOf("\n", start - 1) + 1;
  let lineEnd = value.indexOf("\n", end);
  if (lineEnd === -1) {
    lineEnd = value.length;
  }
  return { lineStart, lineEnd };
}

/**
 * Line-level formatting: headings (## ), bullet lists (- ), quotes (> ).
 * Toggles prefix on each selected line.
 */
export function applyLinePrefix(value, start, end, prefix, matchRegex) {
  const { lineStart, lineEnd } = getLineRange(value, start, end);
  const block = value.substring(lineStart, lineEnd);
  const lines = block.split("\n");

  // Determine if ALL non-empty lines already match the prefix
  const nonEmptyLines = lines.filter((line) => line.trim().length > 0);
  const allMatch =
    nonEmptyLines.length > 0 &&
    nonEmptyLines.every((line) => matchRegex.test(line));

  let transformedLines;
  if (allMatch) {
    // Strip the prefix
    transformedLines = lines.map((line) => line.replace(matchRegex, ""));
  } else {
    // Prepend the prefix (and clean up conflicting heading/list prefixes if needed)
    transformedLines = lines.map((line) => {
      // If line already has another heading, replace it
      if (prefix.startsWith("#")) {
        const cleaned = line.replace(/^#{1,6}\s*/, "");
        return prefix + cleaned;
      }
      return prefix + line;
    });
  }

  const newBlock = transformedLines.join("\n");
  const nextValue = value.substring(0, lineStart) + newBlock + value.substring(lineEnd);

  return {
    value: nextValue,
    selectionStart: lineStart,
    selectionEnd: lineStart + newBlock.length,
  };
}

/**
 * Numbered list formatting (1. , 2. , 3. ).
 * Numbers selected lines sequentially or toggles off if already numbered.
 */
export function applyNumberedList(value, start, end) {
  const { lineStart, lineEnd } = getLineRange(value, start, end);
  const block = value.substring(lineStart, lineEnd);
  const lines = block.split("\n");

  const numberedRegex = /^\s*\d+\.\s+/;
  const nonEmpty = lines.filter((l) => l.trim().length > 0);
  const allNumbered = nonEmpty.length > 0 && nonEmpty.every((l) => numberedRegex.test(l));

  let transformedLines;
  if (allNumbered) {
    transformedLines = lines.map((l) => l.replace(numberedRegex, ""));
  } else {
    let num = 1;
    transformedLines = lines.map((l) => {
      if (l.trim().length === 0) return l;
      const cleaned = l.replace(/^[-*]\s+|\d+\.\s+/, "");
      const res = `${num}. ${cleaned}`;
      num++;
      return res;
    });
  }

  const newBlock = transformedLines.join("\n");
  const nextValue = value.substring(0, lineStart) + newBlock + value.substring(lineEnd);

  return {
    value: nextValue,
    selectionStart: lineStart,
    selectionEnd: lineStart + newBlock.length,
  };
}

/**
 * Code Block formatting (```lang\n...\n```).
 */
export function applyCodeBlock(value, start, end, lang = "") {
  const selected = value.substring(start, end);
  const codeBlockRegex = /^```[\w-]*\n([\s\S]*?)\n```$/;

  // If already code block, unwrap
  const match = selected.match(codeBlockRegex);
  if (match) {
    const inner = match[1];
    const nextValue = value.substring(0, start) + inner + value.substring(end);
    return {
      value: nextValue,
      selectionStart: start,
      selectionEnd: start + inner.length,
    };
  }

  if (start !== end) {
    // Wrap selection
    const wrapped = `\`\`\`${lang}\n${selected}\n\`\`\``;
    const nextValue = value.substring(0, start) + wrapped + value.substring(end);
    return {
      value: nextValue,
      selectionStart: start,
      selectionEnd: start + wrapped.length,
    };
  }

  // Collapsed cursor: insert template and position inside
  const template = `\`\`\`${lang}\n\n\`\`\``;
  const nextValue = value.substring(0, start) + template + value.substring(start);
  const cursorInside = start + 4 + (lang ? lang.length : 0);
  return {
    value: nextValue,
    selectionStart: cursorInside,
    selectionEnd: cursorInside,
  };
}

/**
 * Link formatting: inserts [text](url).
 */
export function applyLink(value, start, end, linkText, url) {
  const safeText = (linkText || "").trim() || "link text";
  let safeUrl = (url || "").trim() || "https://";
  if (!safeUrl.startsWith("http://") && !safeUrl.startsWith("https://") && !safeUrl.startsWith("tg://")) {
    safeUrl = `https://${safeUrl}`;
  }

  const markdown = `[${safeText}](${safeUrl})`;
  const nextValue = value.substring(0, start) + markdown + value.substring(end);
  const newPos = start + markdown.length;

  return {
    value: nextValue,
    selectionStart: newPos,
    selectionEnd: newPos,
  };
}

/**
 * Smart Enter key handler for auto-continuing bullet lists, numbered lists, and quotes.
 * Returns null if not handled (default browser Enter should run).
 */
export function handleSmartEnter(value, cursor) {
  const lineStart = value.lastIndexOf("\n", cursor - 1) + 1;
  const currentLine = value.substring(lineStart, cursor);

  // 1. Bullet list (- or *)
  const bulletMatch = currentLine.match(/^(\s*)([-*])\s+(.*)$/);
  if (bulletMatch) {
    const [, indent, bulletChar, content] = bulletMatch;
    // Empty item: clear prefix
    if (!content.trim()) {
      const nextValue = value.substring(0, lineStart) + indent + value.substring(cursor);
      return {
        value: nextValue,
        selectionStart: lineStart + indent.length,
        selectionEnd: lineStart + indent.length,
      };
    }
    // Continue bullet list
    const insertion = `\n${indent}${bulletChar} `;
    const nextValue = value.substring(0, cursor) + insertion + value.substring(cursor);
    const newPos = cursor + insertion.length;
    return {
      value: nextValue,
      selectionStart: newPos,
      selectionEnd: newPos,
    };
  }

  // 2. Numbered list (1. 2. 3. )
  const numMatch = currentLine.match(/^(\s*)(\d+)\.\s+(.*)$/);
  if (numMatch) {
    const [, indent, numStr, content] = numMatch;
    const num = parseInt(numStr, 10);
    // Empty item: clear number
    if (!content.trim()) {
      const nextValue = value.substring(0, lineStart) + indent + value.substring(cursor);
      return {
        value: nextValue,
        selectionStart: lineStart + indent.length,
        selectionEnd: lineStart + indent.length,
      };
    }
    // Continue numbered list
    const insertion = `\n${indent}${num + 1}. `;
    const nextValue = value.substring(0, cursor) + insertion + value.substring(cursor);
    const newPos = cursor + insertion.length;
    return {
      value: nextValue,
      selectionStart: newPos,
      selectionEnd: newPos,
    };
  }

  // 3. Blockquote (> )
  const quoteMatch = currentLine.match(/^(\s*)>\s*(.*)$/);
  if (quoteMatch) {
    const [, indent, content] = quoteMatch;
    if (!content.trim()) {
      const nextValue = value.substring(0, lineStart) + indent + value.substring(cursor);
      return {
        value: nextValue,
        selectionStart: lineStart + indent.length,
        selectionEnd: lineStart + indent.length,
      };
    }
    const insertion = `\n${indent}> `;
    const nextValue = value.substring(0, cursor) + insertion + value.substring(cursor);
    const newPos = cursor + insertion.length;
    return {
      value: nextValue,
      selectionStart: newPos,
      selectionEnd: newPos,
    };
  }

  return null;
}

/**
 * Smart Tab handler: indents or un-indents lines by 2 spaces.
 */
export function handleTab(value, start, end, isShift) {
  const { lineStart, lineEnd } = getLineRange(value, start, end);
  const block = value.substring(lineStart, lineEnd);
  const lines = block.split("\n");

  let transformedLines;
  if (isShift) {
    // Un-indent 2 spaces or tab
    transformedLines = lines.map((l) => l.replace(/^(  |\t)/, ""));
  } else {
    // Indent 2 spaces
    transformedLines = lines.map((l) => `  ${l}`);
  }

  const newBlock = transformedLines.join("\n");
  const nextValue = value.substring(0, lineStart) + newBlock + value.substring(lineEnd);

  return {
    value: nextValue,
    selectionStart: lineStart,
    selectionEnd: lineStart + newBlock.length,
  };
}

/**
 * Detects which format is currently active at the cursor/selection position.
 */
export function detectActiveFormat(value, start, end) {
  if (!value) return null;

  // Check code block (multi-line)
  const beforeAll = value.substring(0, start);
  const codeBlockCount = (beforeAll.match(/```/g) || []).length;
  if (codeBlockCount % 2 === 1) {
    return "code";
  }

  // Check line prefix at current line
  const lineStart = value.lastIndexOf("\n", start - 1) + 1;
  let lineEnd = value.indexOf("\n", start);
  if (lineEnd === -1) lineEnd = value.length;
  const currentLine = value.substring(lineStart, lineEnd);

  if (/^#{1,6}\s/.test(currentLine)) return "heading";
  if (/^\s*[-*]\s/.test(currentLine)) return "bullet";
  if (/^\s*\d+\.\s/.test(currentLine)) return "numbered";
  if (/^\s*>\s/.test(currentLine)) return "quote";

  const posInLine = start - lineStart;

  // Check Bold (**text**)
  const boldRegex = /\*\*([^*]+)\*\*/g;
  let match;
  while ((match = boldRegex.exec(currentLine)) !== null) {
    if (posInLine >= match.index && posInLine <= match.index + match[0].length) {
      return "bold";
    }
  }

  // Check Italic (*text*)
  const italicRegex = /(?<!\*)\*([^*]+)\*(?!\*)/g;
  while ((match = italicRegex.exec(currentLine)) !== null) {
    if (posInLine >= match.index && posInLine <= match.index + match[0].length) {
      return "italic";
    }
  }

  // Check Inline Code (`code`)
  const codeRegex = /`([^`]+)`/g;
  while ((match = codeRegex.exec(currentLine)) !== null) {
    if (posInLine >= match.index && posInLine <= match.index + match[0].length) {
      return "inline-code";
    }
  }

  // Check Link ([text](url))
  const linkRegex = /\[([^\]]+)\]\(([^)]+)\)/g;
  while ((match = linkRegex.exec(currentLine)) !== null) {
    if (posInLine >= match.index && posInLine <= match.index + match[0].length) {
      return "link";
    }
  }

  return null;
}
