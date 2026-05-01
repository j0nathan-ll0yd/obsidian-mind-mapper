# CLAUDE.md

## Project Purpose

Converts web articles and notes from multiple sources (FireShot captures, Evernote, standalone PDFs) into structured Obsidian markdown notes for a personal knowledge base / mind map.

**Pipeline**: Source content -> PDF/ENML extraction -> Claude metadata generation -> Obsidian note creation -> Attachment storage -> Source cleanup.

## Tech Stack

- **Language**: Python 3 (no package.json / no Node)
- **PDF extraction**: PyMuPDF (`fitz`)
- **Evernote extraction**: pycrdt (Yjs CRDT), markdownify (ENML->Markdown), Playwright (preview rendering)
- **Dependencies**: `requirements.txt` -- install via `pip install -r requirements.txt`
- **Virtual env**: `venv/` -- activate with `source venv/bin/activate`

## Commands

All commands require `source venv/bin/activate` first.

### Evernote Processing (primary active pipeline)
```bash
python src/process_evernote.py status              # Show progress
python src/process_evernote.py prepare [size]       # Prepare batch (default 10)
python src/process_evernote.py prepare --guid GUID  # Single note by GUID
python src/process_evernote.py apply N [file]       # Apply Claude response
```

### FireShot Processing (completed -- 321 files processed)
```bash
python src/process_fireshot.py status
python src/process_fireshot.py prepare [batch_size]
python src/process_fireshot.py apply N response.json
python src/process_fireshot.py cleanup N
```

### Batch Reprocessing (completed -- 238/239 notes)
```bash
python src/batch_reprocess.py --prepare-only --batch-size 10
python src/apply_batch_updates.py N response.json
python src/auto_batch_reprocess.py [--stats-only] [--num-batches N]
python src/batch_reprocess.py --reset-progress
```

### Tag Management
```bash
python src/analyze_tags.py --json-output tag_analysis.json
python src/design_taxonomy.py --analysis-file tag_analysis.json --output tag_taxonomy.json
python src/migrate_tags.py [--dry-run]
```

### Note Linking
```bash
python src/discover_clusters.py --output /tmp/link_candidates.json
python src/link_related_notes.py [--dry-run]
```

### Utilities
```bash
python src/pdf_processor.py path/to/file.pdf       # Extract text/links/metadata as JSON
python src/audit_notes.py --vault Lifegames         # Audit vault notes
python src/check_data_integrity.py                  # Integrity check
python src/reprocess_notes.py --vault Lifegames [--dry-run] [--note "Name.md"]
```

## Project Structure

```
src/                          # All Python scripts
  process_evernote.py         # Evernote -> Obsidian (1311 lines, primary pipeline)
  process_fireshot.py         # FireShot PDF+PNG -> Obsidian
  pdf_processor.py            # PDF text/link/metadata extraction (PyMuPDF)
  file_utils.py               # Hash generation, title sanitization, file matching
  batch_reprocess.py          # Prepare batches for note reprocessing
  apply_batch_updates.py      # Apply Claude responses to existing notes
  auto_batch_reprocess.py     # Automated batch workflow orchestration
  analyze_tags.py             # Tag frequency/consistency analysis
  design_taxonomy.py          # Tag normalization proposal generator
  migrate_tags.py             # Apply tag normalization to vault
  discover_clusters.py        # Find related notes by tag co-occurrence / title similarity
  link_related_notes.py       # Apply bi-directional wiki links between related notes
  audit_notes.py              # Vault audit (generation source, orphans, integrity)
  check_data_integrity.py     # Data integrity verification
  fix_data_integrity.py       # Integrity issue remediation
  reprocess_notes.py          # Interactive note reprocessing with Claude

Lifegames/                    # Obsidian vault (gitignored)
  *.md                        # ~2315 notes (unreviewed)
  Attachments/                # ~16892 files, hash-based names (8char MD5)
  .obsidian/                  # Obsidian config

Documents/                    # Input folder for new PDFs (gitignored)
backups/                      # Migration backups (gitignored)
archive/                      # Old batch artifacts (gitignored)
previous-files/               # Original Python/Bash implementation (gitignored, reference only)

.claude/commands/             # Claude Code slash commands
  process-evernote.md         # /process-evernote workflow
  process-fireshot.md         # /process-fireshot workflow
  reprocess-notes.md          # /reprocess-notes workflow
  link-notes.md               # /link-notes workflow
```

## Key Conventions

### File Naming
- **Attachments**: `{8char-md5-hash}.{ext}` -- hash of first 8KB of source file (or note GUID for Evernote)
- **Evernote previews**: `{hash}_preview.png` -- Playwright-rendered ENML screenshot
- **Evernote resources**: `{hash}.jpg`, `{hash}_1.jpg`, `{hash}_2.jpg` (additional images)
- **Notes**: Sanitized article title, spaces preserved, `[]#^|\/:?*<>"` removed, max 100 chars

### Tag Format
`Title-Case-With-Hyphens` -- each word capitalized, separated by hyphens. Acronyms uppercase (`AI`, `LLM`, `SF`).

### Frontmatter Schema
```yaml
title: "Article Title"
source: "Publication Name"         # omit for personal notes
source_url: "https://..."          # omit for personal notes
date: YYYY-MM-DD
authors: ["Author Name"]
tags: ["Topic", "Subtopic"]
filename: "8charhash"
cssclass: article-note
file_hash: "8charhash"
evernote_guid: "guid"              # Evernote notes only
evernote_notebook: "Personal"      # Evernote notes only
generated_by: "claude-code"
generated_model: "claude-opus-4-6"
generated_at: "YYYY-MM-DD"
```

### Note Sections (in order)
1. `# Title`
2. `> [!info] Article Information` -- source, date, authors callout
3. `## Summary` -- 2-3 sentences
4. `## Key Points` -- bulleted list
5. `## Author Information` -- author links (if available)
6. `## Linked Concepts` -- wiki links to related notes (user-editable)
7. `## Notes` -- personal annotations (user-editable)
8. `## Attachments` -- `![[hash.ext]]` embeds

### User Content Preservation
When reprocessing notes, sections 6 (Linked Concepts) and 7 (Notes) must be preserved. Content is "real" if it is anything other than the placeholder `<!-- For manual wiki-linking later -->`.

### Model Tracking
The `CLAUDE_MODEL` constant in `process_evernote.py` (currently `claude-opus-4-6`) must match the model actually used. Update when switching models.

## Evernote Processing Details

Reads Evernote's local macOS storage directly (no API/export needed).

**Storage locations** (all read-only):
- ENML content: `~/Library/Containers/com.evernote.Evernote/Data/.../conduit-fs/.../rte/Note/internal_rteDoc/{pfx1}/{pfx2}/{guid}.dat`
- SQLite DB: `conduit-fs/.../UDB-*.sql` -- tables `Offline_Search_Note_Content`, `Nodes_Note`
- Resources: `resource-cache/User{id}/{guid}/{hash}` + `.mime`/`.meta`

**Content extraction priority** (highest fidelity first):
1. **pycrdt** -- Yjs .dat -> ENML -> Markdown via markdownify. Full article with headings/links.
2. **SQLite** -- FTS index plain text + `Nodes_Note.source_URL`.
3. **strings** -- Raw binary extraction fallback. Noisy.

**Preview rendering** (`_render_preview`):
- ENML -> HTML with base64-embedded images from resource-cache
- Playwright/Chromium at 748px width, 2x DPR
- Google Fonts (Source Serif 4 mapped to `source-serif-pro`)
- Auto-detected content height via JS getBoundingClientRect
- Fallback: PyMuPDF Story renderer summary card

**Progress**: `evernote_progress.json` -- current_batch: 1363, completed notes tracked by GUID.

## Processing Status

| Pipeline | Status | Count |
|----------|--------|-------|
| FireShot | Complete | 321 file pairs processed |
| Batch reprocess | Complete | 238/239 notes reprocessed |
| Tag normalization | Complete | 1960 -> 1620 unique tags |
| Note linking | Complete | 17 clusters, 80 bi-directional links |
| Evernote | Active | batch 1363, ~1759 total notes |

## Git Configuration

**Gitignored**: `Lifegames/`, `Documents/`, `venv/`, `backups/`, `archive/`, `previous-files/`, `.omc/`, all batch response/intermediate files.

**Tracked**: `src/`, `.claude/commands/`, progress JSON files, analysis JSON files, `linked_notes_clusters.json`, `tag_taxonomy.json`.

## Claude Code Slash Commands

- `/process-evernote` -- Full Evernote batch workflow (prepare -> analyze -> apply)
- `/process-fireshot` -- FireShot PDF+PNG processing workflow
- `/reprocess-notes` -- Audit and reprocess existing vault notes
- `/link-notes` -- Discover and apply bi-directional wiki links between related notes
