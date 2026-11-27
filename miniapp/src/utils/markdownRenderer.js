/**
 * High-Fidelity Academic & Professional Document Renderer for CyberLearn Studio PDF View
 * Formats Markdown, notes, tables, callouts, and Linux terminal snippets into a publication-ready document.
 */

export function cleanTitle(raw, content = "") {
  let title = (raw || "").trim();
  if (!title || /^untitled\s*(lesson|document|course)?$/i.test(title)) {
    if (content) {
      const targetMatch = content.match(/🎯\s*([A-Za-z0-9_-]+)/i) ||
                          content.match(/^#{1,2}\s+([^\n]+)/m) ||
                          content.match(/\b(file[_\s]permissions?|firewalls?|networking|linux)\b/i);
      if (targetMatch) {
        title = targetMatch[1];
      }
    }
  }
  if (!title || /^untitled\s*(lesson|document|course)?$/i.test(title)) {
    title = "Academic Reference Guide";
  }
  return title
    .replace(/[_-]+/g, " ")
    .trim()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

export function smartFormatAcademicText(raw) {
  if (!raw || !raw.trim()) return "";
  let text = raw.replace(/\r\n/g, "\n");

  // 1. Strip raw Telegram broadcast headers (e.g. "🛡️ Study note\n━━━━━━━━━━━━━━━━━━\n🎯 file_permission\n")
  text = text.replace(/^[\s\S]*?━━━━━━━━━━━━━━━━━━\s*\n/i, "");
  text = text.replace(/^\s*[🎯📚]\s*[A-Za-z0-9_ -]+\s*\n+/i, "");

  // 2. Remove stray dot spacer lines (e.g. "." or ".." or "·")
  text = text.replace(/^\s*[\.\s·•_-]{1,4}\s*$/gm, "");

  let lines = text.split("\n");
  const processed = [];
  let commandAcc = [];

  const flushCommands = () => {
    if (commandAcc.length) {
      processed.push("");
      processed.push("```bash\n" + commandAcc.join("\n") + "\n```");
      processed.push("");
      commandAcc = [];
    }
  };

  for (let i = 0; i < lines.length; i++) {
    const rawLine = lines[i];
    const l = rawLine.trim();

    // Skip empty lines
    if (!l) {
      flushCommands();
      processed.push("");
      continue;
    }

    // Skip stray dots
    if (/^[\.\s·•_-]{1,4}$/.test(l)) continue;

    // Check if line is a bash command
    const isCmd = /^(touch|ls|chmod|sudo|chown|cat|rm|mkdir|cp|mv|grep|find|systemctl|iptables|ufw)\b/.test(l) &&
                  !l.includes("➔") && !l.includes("=") && !l.includes("(") && !l.includes(")") && !l.endsWith(":");
    if (isCmd) {
      commandAcc.push(l);
      continue;
    } else {
      flushCommands();
    }

    // Telegram Section headers (e.g., "📖 01 | In Linux, these letters are actually math numbers")
    const secMatch = l.match(/^(?:📖|📚)?\s*(\d{1,2})\s*\|\s*(.+)$/);
    if (secMatch) {
      const secNum = parseInt(secMatch[1], 10);
      processed.push("");
      processed.push(`## Section ${secNum}: ${secMatch[2].trim()}`);
      processed.push("");
      continue;
    }

    // Step Workflows (e.g., "1 Create and Inspect", "2  Lock the Vault")
    const stepMatch = l.match(/^(\d+)\s{1,4}([A-Z][A-Za-z0-9\s&/—–-]{3,40})$/);
    if (stepMatch && !l.includes("(") && !l.includes("=")) {
      processed.push("");
      processed.push(`### Step ${stepMatch[1]}: ${stepMatch[2].trim()}`);
      processed.push("");
      continue;
    }

    // Standalone Inquiry Questions (e.g., "Why 4, 2, and 1? Why not 1, 2, and 3, or 10, 20, and 30?")
    if (/^[A-Z][A-Za-z0-9\s,—–-]{8,80}\?$/.test(l)) {
      processed.push("");
      processed.push(`### Key Inquiry: ${l}`);
      processed.push("");
      continue;
    }

    // Linux Permission string: -rwxr-xr-- or -rw-------
    if (/^[-d][-rwx]{9}$/.test(l)) {
      processed.push("");
      processed.push(`\`${l}\``);
      processed.push("");
      continue;
    }

    // Standalone headings like "File permissions" or "File Permissions"
    if (/^(File permissions?|Types of firewalls?:?|Summary:?)$/i.test(l)) {
      processed.push("");
      processed.push(`## ${cleanTitle(l.replace(/:$/, ""))}`);
      processed.push("");
      continue;
    }

    // Series Subtitles like "Cybersecurity Journey — Day 11"
    if (/^Cybersecurity Journey/i.test(l)) {
      processed.push("");
      processed.push(`**${l}**`);
      processed.push("");
      continue;
    }

    // Friendly greeting like "Hey, everyone"
    if (/^Hey,\s*everyone/i.test(l)) {
      processed.push("");
      processed.push(l);
      processed.push("");
      continue;
    }

    // Educational callouts (e.g. "The Golden Rules:", "💡 Example:", "Example:")
    if (/^(?:💡\s*)?(The Golden Rules:?|Example:?|Why this is genius:?|Important:?|Warning:?)/i.test(l)) {
      processed.push("");
      processed.push(`💡 **${l.replace(/^[💡\s]+/, "").replace(/:$/, "")}**`);
      processed.push("");
      continue;
    }

    // Definition & Calculation bullets
    if (
      /^(Owner|Group|World)\s*:/i.test(l) ||
      /^(Read|Write|Execute)\s*\([rwx]\)\s*=/i.test(l) ||
      /^\d+\s*(?:\([^)]+\))?\s*=\s*/i.test(l) ||
      /^chmod\s+[0-9+]/i.test(l)
    ) {
      if (/^(Owner|Group|World)\s*:/i.test(l)) {
        processed.push(`- **${l.replace(/:.*/, "")}**: ${l.replace(/^[^:]+:\s*/, "")}`);
      } else if (/^chmod\s+[0-9+]/i.test(l)) {
        processed.push(`- \`${l.replace(/\s*➔.*$/, "")}\` ${l.includes("➔") ? "➔ " + l.replace(/^.*?➔\s*/, "") : ""}`);
      } else {
        processed.push(`- ${l}`);
      }
      continue;
    }

    // Normal prose line
    if (processed.length > 0 && processed[processed.length - 1] !== "" && !processed[processed.length - 1].startsWith("-")) {
      const prev = processed[processed.length - 1];
      if (prev.endsWith(".") || prev.endsWith("!") || prev.endsWith(":") || l.length > 60 || prev.length < 50) {
        processed.push("");
        processed.push(l);
      } else {
        processed[processed.length - 1] += " " + l;
      }
    } else {
      processed.push(l);
    }
  }

  flushCommands();
  return processed.join("\n").replace(/\n{3,}/g, "\n\n").trim();
}

export function estimateReadingStats(text) {
  const clean = (text || "").trim();
  const words = clean ? clean.split(/\s+/).length : 0;
  const minutes = Math.max(1, Math.ceil(words / 190));
  const chars = clean.length;
  return { words, minutes, chars };
}

function escapeHtml(str) {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function isSafeImageUrl(url) {
  const clean = (url || "").trim();
  return (
    clean.startsWith("/api/images/") ||
    clean.startsWith("https://") ||
    clean.startsWith("http://") ||
    clean.startsWith("data:image/")
  );
}

function renderImageFigure(altRaw, urlRaw) {
  const url = (urlRaw || "").trim();
  if (!isSafeImageUrl(url)) return "";
  const safeSrc = escapeHtml(url);
  const altClean = (altRaw || "").trim();
  const safeAlt = escapeHtml(altClean || "Lesson explanation image");
  const showCaption =
    altClean &&
    !/^(image|pasted-image|explanation image|screenshot)$/i.test(altClean);
  return `<figure class="pdf-image-figure"><img src="${safeSrc}" alt="${safeAlt}" class="pdf-lesson-image" loading="lazy" />${
    showCaption ? `<figcaption class="pdf-image-caption">${safeAlt}</figcaption>` : ""
  }</figure>`;
}

function formatInline(str) {
  return str
    // Images: ![alt](url) — must run before Links
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_, alt, url) => {
      if (!isSafeImageUrl(url)) return "";
      return `<img src="${escapeHtml(url.trim())}" alt="${escapeHtml((alt || "").trim() || "Lesson image")}" class="pdf-lesson-image-inline" loading="lazy" />`;
    })
    // Links: [text](url)
    .replace(
      /\[([^\]]+)\]\(([^)]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="pdf-link">$1</a>'
    )
    // Multiline & inline Bold: **text** or __text__
    .replace(/\*\*([\s\S]+?)\*\*/g, "<strong>$1</strong>")
    .replace(/__([\s\S]+?)__/g, "<strong>$1</strong>")
    // Italic: *text* or _text_
    .replace(/(?<!\*)\*([^*\n]+)\*(?!\*)/g, "<em>$1</em>")
    .replace(/(?<!\w)_([^_\n]+)_(?!\w)/g, "<em>$1</em>")
    // Strip leftover dangling ** or __
    .replace(/\*\*|__/g, "");
}

function isTableBlock(lines) {
  if (lines.length < 2) return false;
  // Markdown pipe table
  if (lines[0].includes("|") && lines.some((l) => /^\s*\|?\s*[-:]+[-| :]*\|?\s*$/.test(l))) {
    return true;
  }
  // Multi-space / tab separated table (e.g. Binary switches table)
  const colCounts = lines.map((l) => l.trim().split(/\s{2,}|\t/).length);
  return (
    colCounts.length >= 2 &&
    colCounts[0] >= 3 &&
    colCounts.every((c) => Math.abs(c - colCounts[0]) <= 1)
  );
}

function renderTable(lines) {
  // 1. Pipe table
  if (lines[0].includes("|")) {
    const rows = lines
      .filter((l) => !/^\s*\|?\s*[-:]+[-| :]*\|?\s*$/.test(l))
      .map((l) =>
        l
          .replace(/^\||\|$/g, "")
          .split("|")
          .map((c) => c.trim())
      );
    if (!rows.length) return "";
    let html = '<div class="pdf-table-wrapper"><table class="pdf-academic-table"><thead><tr>';
    rows[0].forEach((h) => {
      html += `<th>${formatInline(escapeHtml(h))}</th>`;
    });
    html += "</tr></thead><tbody>";
    for (let i = 1; i < rows.length; i++) {
      html += "<tr>";
      rows[i].forEach((c) => {
        html += `<td>${formatInline(escapeHtml(c))}</td>`;
      });
      html += "</tr>";
    }
    html += "</tbody></table></div>";
    return html;
  }

  // 2. Multi-space / tab separated table
  const rows = lines.map((l) => l.trim().split(/\s{2,}|\t/));
  let html = '<div class="pdf-table-wrapper"><table class="pdf-academic-table"><thead><tr>';
  rows[0].forEach((h) => {
    html += `<th>${formatInline(escapeHtml(h.trim()))}</th>`;
  });
  html += "</tr></thead><tbody>";
  for (let i = 1; i < rows.length; i++) {
    html += "<tr>";
    rows[i].forEach((c) => {
      html += `<td>${formatInline(escapeHtml(c.trim()))}</td>`;
    });
    html += "</tr>";
  }
  html += "</tbody></table></div>";
  return html;
}

export function renderMarkdownToHtml(md) {
  if (!md || !md.trim()) {
    return '<p class="pdf-empty-notice"><em>No lesson text entered yet. Write lesson notes in the editor to preview.</em></p>';
  }

  // Pre-process and structure raw notes, Telegram broadcast dumps, or single-newline notes
  const structuredMd = smartFormatAcademicText(md);
  let text = structuredMd.replace(/\r\n/g, "\n");

  // Preserve explicit code blocks first
  const codeBlocks = [];
  text = text.replace(/```([\w-]*)\n([\s\S]*?)\n```/g, (_, lang, code) => {
    const id = `§§CODEBLOCK${codeBlocks.length}§§`;
    codeBlocks.push({ lang: lang || "code", code: escapeHtml(code.trim()) });
    return `\n\n${id}\n\n`;
  });

  // Preserve inline code `...`
  const inlineCodes = [];
  text = text.replace(/`([^`\n]+)`/g, (_, code) => {
    const id = `§§INLINECODE${inlineCodes.length}§§`;
    inlineCodes.push(escapeHtml(code));
    return id;
  });

  // Pre-process multiline bold markers like **Cybersecurity Journey — Day 11\n\n**
  text = text.replace(/\*\*([\s\S]*?)\*\*/g, (_, inner) => {
    return `**${inner.replace(/\n+/g, " ").trim()}**`;
  });

  // Split into structural blocks by double (or more) newlines
  const rawBlocks = text.split(/\n\s*\n+/);
  const htmlParts = [];

  for (let b = 0; b < rawBlocks.length; b++) {
    const block = rawBlocks[b].trim();
    if (!block) continue;

    // Filter out stray dot or spacing-only blocks (often typed in Telegram for blank lines)
    if (/^[\.\s·•_-]+$/.test(block) && block.length <= 4) {
      continue;
    }

    // Check Code Block Placeholder
    if (block.startsWith("§§CODEBLOCK") && block.endsWith("§§")) {
      htmlParts.push(block);
      continue;
    }

    const lines = block.split("\n");
    const cleanLines = lines.map((l) => l.trim()).filter((l) => l && !/^[\.\s·]+$/.test(l));
    if (!cleanLines.length) continue;

    // Check Table
    if (isTableBlock(cleanLines)) {
      htmlParts.push(renderTable(cleanLines));
      continue;
    }

    // Check Standalone Image Block: ![alt](url)
    const imageMatch = cleanLines.length === 1 && cleanLines[0].match(/^!\[([^\]]*)\]\(([^)]+)\)$/);
    if (imageMatch) {
      const fig = renderImageFigure(imageMatch[1], imageMatch[2]);
      if (fig) {
        htmlParts.push(fig);
        continue;
      }
    }

    // Check Explicit Headings: # H1, ## H2, ### H3
    const headingMatch = block.match(/^(#{1,6})\s+(.+)$/);
    if (headingMatch && cleanLines.length === 1) {
      const level = Math.min(headingMatch[1].length, 3);
      const title = formatInline(escapeHtml(headingMatch[2].trim()));
      htmlParts.push(`<h${level} class="pdf-h${level}">${title}</h${level}>`);
      continue;
    }

    // Check Step Banners (e.g., "1 Create and Inspect", "2  Lock the Vault")
    const stepMatch = block.match(/^(\d+)\s+([A-Za-z0-9\s&/—–-]+)$/);
    if (stepMatch && cleanLines.length === 1 && block.length < 50) {
      const stepNum = stepMatch[1];
      const stepTitle = formatInline(escapeHtml(stepMatch[2].trim()));
      htmlParts.push(
        `<div class="pdf-step-banner"><span class="pdf-step-badge">Step ${stepNum}</span><span class="pdf-step-title">${stepTitle}</span></div>`
      );
      continue;
    }

    // Check Standalone Section Titles (e.g., "File permissions", "Types of firewalls:")
    if (
      cleanLines.length === 1 &&
      cleanLines[0].length < 60 &&
      !cleanLines[0].endsWith(".") &&
      !cleanLines[0].includes("=") &&
      (/^[A-Z][A-Za-z0-9\s&/—–-]+:?$/.test(cleanLines[0]) || /^[A-Z0-9\s—–-]+$/.test(cleanLines[0]))
    ) {
      const titleText = cleanLines[0];
      if (titleText.endsWith(":")) {
        htmlParts.push(
          `<div class="pdf-callout-lead"><span class="pdf-lead-icon">💡</span><strong>${formatInline(escapeHtml(titleText))}</strong></div>`
        );
      } else {
        htmlParts.push(`<h2 class="pdf-h2">${formatInline(escapeHtml(titleText))}</h2>`);
      }
      continue;
    }

    // Check Educational Callouts (e.g., "The Golden Rules:", "Why this is genius:", "In simple words:")
    if (/^(The Golden Rules:|Why this is genius:|In simple words:|Remember:|Note:|Important:|Warning:|Key Takeaways:)/i.test(cleanLines[0])) {
      const headerText = cleanLines[0];
      const bodyLines = cleanLines.slice(1).join("\n").trim();
      let calloutHtml = `<div class="pdf-callout-card"><div class="pdf-callout-title"><strong>${escapeHtml(headerText)}</strong></div>`;
      if (bodyLines) {
        calloutHtml += `<div class="pdf-callout-body">${formatInline(escapeHtml(bodyLines)).replace(/\n/g, "<br />")}</div>`;
      }
      calloutHtml += "</div>";
      htmlParts.push(calloutHtml);
      continue;
    }

    // Check Blockquote (> )
    if (cleanLines.every((l) => /^\s*>\s?/.test(l))) {
      const inner = cleanLines.map((l) => formatInline(escapeHtml(l.replace(/^\s*>\s?/, "").trim()))).join("<br />");
      htmlParts.push(`<blockquote class="pdf-blockquote">${inner}</blockquote>`);
      continue;
    }

    // Check Bullet List (- , * , • )
    if (cleanLines.every((l) => /^\s*[-*•]\s+/.test(l))) {
      let listHtml = '<ul class="pdf-ul">';
      cleanLines.forEach((l) => {
        const item = formatInline(escapeHtml(l.replace(/^\s*[-*•]\s+/, "").trim()));
        listHtml += `<li class="pdf-li">${item}</li>`;
      });
      listHtml += "</ul>";
      htmlParts.push(listHtml);
      continue;
    }

    // Check Numbered List (1. , 2) , etc.)
    if (cleanLines.every((l) => /^\s*\d+[\.\)]\s+/.test(l))) {
      let listHtml = '<ol class="pdf-ol">';
      cleanLines.forEach((l) => {
        const item = formatInline(escapeHtml(l.replace(/^\s*\d+[\.\)]\s+/, "").trim()));
        listHtml += `<li class="pdf-li">${item}</li>`;
      });
      listHtml += "</ol>";
      htmlParts.push(listHtml);
      continue;
    }

    // Check Linux Permission String (e.g., "-rwxr-xr--" or "-rw-------" or "drwxr-xr-x")
    if (cleanLines.length === 1 && /^[-d][-rwx]{9}$/.test(cleanLines[0])) {
      htmlParts.push(
        `<div class="pdf-terminal-snippet"><span class="pdf-term-label">Permission Mode</span><code>${cleanLines[0]}</code></div>`
      );
      continue;
    }

    // Check standalone command lines (e.g. "touch test.txt\nls -l test.txt")
    const isCommandBlock = cleanLines.every((l) =>
      /^\s*(touch|chmod|chown|sudo|cat|rm|ls|mkdir|cp|mv|grep|find|systemctl|iptables|ufw|nano|vim)\b/.test(l)
    );
    if (isCommandBlock && cleanLines.length <= 4) {
      let cmdHtml = '<div class="pdf-code-block"><div class="pdf-code-header"><span>BASH COMMAND</span></div><pre><code>';
      cleanLines.forEach((l) => {
        cmdHtml += `<span class="pdf-cmd-prompt">$</span> ${escapeHtml(l.trim())}\n`;
      });
      cmdHtml += "</code></pre></div>";
      htmlParts.push(cmdHtml);
      continue;
    }

    // Standard Unified Paragraph
    // Join lines that belong together, preventing scattered layout
    // If lines are short badge definitions (like "Owner: ...\nGroup: ...\nWorld: ..."), keep with soft break <br>
    const isItemDefinitions = cleanLines.length > 1 && cleanLines.every((l) => /^[A-Za-z0-9\s]+:/.test(l));
    const joiner = isItemDefinitions ? "<br />" : " ";
    const paragraphText = cleanLines.join(joiner);

    htmlParts.push(`<p class="pdf-p">${formatInline(escapeHtml(paragraphText))}</p>`);
  }

  let finalHtml = htmlParts.join("\n\n");

  // Restore Inline Codes
  inlineCodes.forEach((code, i) => {
    finalHtml = finalHtml.replaceAll(`§§INLINECODE${i}§§`, `<code class="pdf-inline-code">${code}</code>`);
  });

  // Restore Code Blocks
  codeBlocks.forEach(({ lang, code }, i) => {
    finalHtml = finalHtml.replaceAll(
      `§§CODEBLOCK${i}§§`,
      `<div class="pdf-code-block"><div class="pdf-code-header"><span>${lang.toUpperCase()}</span></div><pre><code>${code}</code></pre></div>`
    );
  });

  return finalHtml;
}
