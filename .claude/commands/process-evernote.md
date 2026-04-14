You are converting Evernote notes into structured Obsidian markdown notes for the mind map vault.

Evernote's local storage is read directly — no API or export required. The pipeline:
1. **Prepare** a batch → extracts ENML content from Evernote's local Yjs storage and generates a Claude prompt
2. **Analyze** → you read the prompt and generate structured metadata JSON
3. **Apply** → creates Obsidian notes, renders web clip previews via Playwright, and copies attachments

## Quick Start

```bash
# Check status
source venv/bin/activate && python src/process_evernote.py status

# Prepare next batch (default 10 notes)
python src/process_evernote.py prepare 10

# After you generate the response JSON:
python src/process_evernote.py apply BATCH_NUM
```

## Full Workflow

### Step 1: Check Status

```bash
source venv/bin/activate && python src/process_evernote.py status
```

Shows: total notes, processed, remaining, notes with attachments, current batch number.

### Step 2: Prepare a Batch

```bash
source venv/bin/activate && python src/process_evernote.py prepare [batch_size]
# or target a specific note by GUID:
python src/process_evernote.py prepare --guid <note-guid>
```

- Default batch size: 10 notes
- Creates `evernote_batch_N.json` (note data + ENML + resources)
- Creates `evernote_batch_N_prompt.txt` (Claude analysis prompt with clean Markdown content)

**Content extraction chain** (highest → lowest fidelity):
1. **pycrdt** — decodes Yjs `.dat` file → raw ENML → clean Markdown via markdownify. Produces full article text with proper headings, links, and punctuation.
2. **SQLite** — reads `Offline_Search_Note_Content` + `Nodes_Note.source_URL`. Clean text, no structure.
3. **strings** — legacy fallback for notes where both above fail. Noisy but workable.

The prompt labels the method: `CONTENT [pycrdt]`, `CONTENT [sqlite]`, or `CONTENT [strings]`.

**Note types** the script handles:
- **Web clips**: Have `source_url` from ENML CSS metadata or SQLite `Nodes_Note`
- **Personal notes**: User-written content, no source URL

### Step 3: Analyze the Batch

Read `evernote_batch_N_prompt.txt` and generate structured metadata for each note.

For **each note** in the batch, produce:

```json
{
  "guid": "the-note-guid-from-prompt",
  "title": "Concise, accurate title",
  "source_name": "Publication name | null for personal notes",
  "source_url": "https://article-url | null for personal notes",
  "source_date": "YYYY-MM-DD",
  "summary": "2-3 sentence summary with specific insights",
  "key_points": [
    "Specific, substantive point 1",
    "Specific, substantive point 2",
    "Specific, substantive point 3",
    "Specific, substantive point 4",
    "Specific, substantive point 5"
  ],
  "tags": ["Topic", "Subtopic", "Tag"],
  "authors": ["Author Name"],
  "author_urls": {"Author Name": "https://profile-url | null"}
}
```

**Analysis guidelines**:
- For web clips: use the article content (now full clean Markdown) to determine real title, not Evernote title
- For personal notes: shorter key_points list is fine — capture the essence
- `source_date`: prefer the article's publication date; fall back to the `Created` date shown in the prompt
- Tags: use `Title-Case-With-Hyphens` format (e.g., `Mental-Health`, `AI`, `San-Francisco`)
- `author_urls`: use null if no profile URL is apparent from the content
- Content is now up to 6000 chars of clean Markdown — use it fully

Save the complete JSON array as `evernote_batch_N_response.json`.

### Step 4: Apply

```bash
source venv/bin/activate && python src/process_evernote.py apply N
# or with explicit response file:
python src/process_evernote.py apply N evernote_batch_N_response.json
```

This will:
- Create Obsidian markdown notes in `Lifegames/`
- **Render a full-length PNG preview** of each web clip via Playwright/Chromium:
  - ENML HTML with base64-embedded images from resource-cache
  - Source Serif 4 (Google Fonts) mapped to `source-serif-pro` — Medium's actual body font
  - CSS quote escaping fix (pycrdt outputs unescaped `"` in style attributes)
  - Content height auto-detected via JS getBoundingClientRect
  - 748px logical width @ 2x device pixel ratio
- Copy all attachment images to `Lifegames/Attachments/` with hash-based filenames
- Update `evernote_progress.json` with processed GUIDs

### Step 5: Repeat

Continue until all notes are processed:
```bash
python src/process_evernote.py status
python src/process_evernote.py prepare 10
# ... analyze ... apply ...
```

## Generated Note Format

### Web Clip (with source URL)
```markdown
---
title: "Article Title"
source: "Publication Name"
source_url: "https://..."
date: YYYY-MM-DD
authors:
  - Author Name
tags: ["Topic", "Tag"]
filename: "8charhash"
cssclass: article-note
file_hash: "8charhash"
evernote_guid: "full-guid"
evernote_notebook: "Personal"
generated_by: "claude-code"
generated_model: "claude-opus-4-6"
generated_at: "YYYY-MM-DD"
---

# Article Title

> [!info] Article Information
> - **Source**: [Publication](url)
> - **Date**: YYYY-MM-DD
> - **Authors**: [Name](url)

## Summary
...

## Key Points
- ...

## Author Information
- [Author](url)

## Linked Concepts
<!-- For manual wiki-linking later -->

## Notes

## Attachments
- ![[hash_preview.png]]
```

### Personal Note (no source URL)
```markdown
---
title: "Note Title"
date: YYYY-MM-DD
tags: ["Tag"]
filename: "8charhash"
evernote_guid: "full-guid"
...
---

# Note Title

## Summary
...

## Key Points
- ...

## Linked Concepts
<!-- For manual wiki-linking later -->

## Notes

## Attachments
- ![[hash_preview.png]]
```

## File Naming

- Preview: `{8charhash}_preview.png` — full-length Playwright screenshot of original ENML
- Resources: `{8charhash}.jpg` (primary), `{8charhash}_1.jpg`, `{8charhash}_2.jpg` (additional)
- Note hash: MD5 of the note GUID (consistent, reproducible across runs)
- Notes: sanitized title (removes `[]#^|\/:?*<>"`, max 100 chars)

## Evernote Storage Locations (read-only)

- **ENML content**: `~/Library/Containers/com.evernote.Evernote/Data/.../conduit-fs/https%3A%2F%2Fwww.evernote.com/majrmovies/rte/Note/internal_rteDoc/{pfx1}/{pfx2}/{guid}.dat`
- **Metadata**: `conduit-fs/.../cosm/storage/note/*.fdt` (Lucene index)
- **Resources/images**: `conduit-fs/.../resource-cache/User{id}/{guid}/{hash}` + `.mime`/`.meta`
- **SQLite DB**: `conduit-fs/.../UDB-*.sql` — tables: `Offline_Search_Note_Content`, `Nodes_Note`

## Preview Rendering Pipeline

The `_render_preview()` function produces high-fidelity web clip screenshots:

1. **ENML → HTML** (`_enml_to_html`):
   - Replace `<en-media hash="...">` with `<img src="data:image/jpeg;base64,...">` from resource-cache
   - Fix unescaped `"` in CSS font names: `"Times New Roman"` → `'Times New Roman'`
   - Inject Google Fonts CSS (Source Serif 4 renamed to `source-serif-pro` in the @font-face rules)
   - Apply CSS fixes: remove `min-height`, fix `position:absolute`, fix `calc(100vh+...)`

2. **Playwright render** (`_playwright_render`):
   - Serve via localhost HTTP (not `file://`) so cross-origin font requests work
   - Explicitly trigger `font.load()` for all registered @font-face variants
   - Auto-detect content height via `getBoundingClientRect` traversal
   - Screenshot at 748×{content_height}px logical, 2x device scale = 1496px wide PNG

3. **Fallback** (`_render_preview_fallback`):
   - PyMuPDF Story renderer when ENML is unavailable
   - Summary card with title, metadata line, first image, and article text

## Content Quality

**pycrdt extraction** (most notes):
- Full article text with proper headings, links, and punctuation
- ~6,000–10,000 chars per article
- Source URL extracted from ENML CSS custom property `--en-clipped-source-url`

**SQLite fallback**:
- Clean plain text from FTS index
- Source URL from `Nodes_Note.source_URL` (1748/1759 notes have this)

**strings fallback** (rare):
- Fragmented text — Claude should fill gaps from title and source URL context

## Example Session

```
User: /process-evernote

You:
Checking status...
  Total: 1759 notes, 2 processed, 1757 remaining

Preparing batch of 10...
  ✅ Batch 4 ready: evernote_batch_4_prompt.txt
  Content: [pycrdt] for 9/10 notes, [sqlite] for 1/10

[Read prompt, generate metadata for 10 notes]

Saving response as evernote_batch_4_response.json and applying...
  ✅ The Algorithm That Could Stop Mass Shootings.md
  ✅ On Being Present.md
  ✅ How Waymo Outlasted the Competition.md
  ... (10 total)

  ✅ Batch 4: 10/10 created, 0 failed
  Progress: 12/1759 (0.7%)
```
