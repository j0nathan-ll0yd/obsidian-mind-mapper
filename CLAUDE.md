# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Purpose

This project processes webpage screenshots and PDF documents (from [FireShot](https://getfireshot.com/)) into structured Obsidian notes for building a mind map/knowledge base. FireShot captures provide both PNG screenshots and PDF versions of web articles.

### Workflow
1. **Input**: FireShot PNG + PDF files of web articles, OR standalone PDF documents (placed in `Documents/` folder)
2. **Extract & Summarize**: Extract content, links, metadata from PDF; generate structured summary using Claude
3. **Generate Note**: Create Obsidian-formatted Markdown note with frontmatter, summary, key points, and attachment references
4. **Store**: Save everything in `Lifegames/` directory structure (Obsidian vault) with date-based attachment subfolders
5. **Cleanup**: Remove source files from `Documents/` after successful processing (copy → verify → delete for safety)

## Repository Structure

### Key Directories
- **`Lifegames/`**: The Obsidian vault containing all processed notes and attachments
  - **`Lifegames/Attachments/`**: Stores all PDF, PNG, and JSON files using 8-character hash filenames (e.g., `1e567f29.pdf`)
  - **`Lifegames/Reviewed/`**: Notes that have been reviewed/processed
  - **`Lifegames/*.md`**: Top-level notes (unreviewed)
  - **`Lifegames/.obsidian/`**: Obsidian configuration

- **`Documents/`**: Input folder for standalone PDF documents (not from FireShot)

- **`previous-files/`**: Original Python/Bash implementation (reference only)
  - `normalize-screenshots.sh`: Bash script for file normalization
  - `summarize-pdf.py`: Python + LangChain + Ollama for PDF OCR and summarization
  - `generate-note.py`: Python script to generate Obsidian notes from template
  - `TEMPLATE.MD`: Template for generated Obsidian notes

### File Naming Conventions
- **Raw inputs**: `FireShot Capture NNN - Title - domain.com.{pdf,png}`
- **Normalized**: `YYYY-MM-DD|domain|kebab-case-title.{pdf,png}`
- **Final attachments**: `{8-char-hash}.{pdf,png,json}` (MD5 hash of first 8KB of PDF)
- **Markdown notes**: Sanitized article title with spaces (e.g., `The Best Product Engineering Org in the World.md`)

## Architecture Notes

### Original Implementation (Python)
The previous workflow used three separate scripts:
1. Bash script for file normalization (date extraction, domain parsing, title kebab-casing)
2. Python script using LangChain + Ollama (local LLM) for PDF processing:
   - PyMuPDF for link extraction and OCR
   - Structured output: title, summary, key_points, tags, authors, source_date
   - Skip domains: getfireshot.com, youtube.com
3. Python script for Markdown generation using template substitution

### Refactor Goals
- Replace local Ollama LLM with Claude Code (interactive, not API)
- Use Claude's structured outputs for consistent JSON schema
- Keep all files in this repository (not external Obsidian directory)
- Maintain compatibility with existing `Lifegames/` Obsidian vault structure
- Simplify attachment storage strategy (current hash-based system in single `Attachments/` folder may need improvement)

### Obsidian Note Template Structure
Generated notes follow this format:
```yaml
---
title: "Article Title"
source: "Source Name"
source_url: "https://..."
date: YYYY-MM-DD
authors:
  - Author Name
tags: [topic, subcategory, region, keyword]
filename: "8charhash"
cssclass: article-note
file_hash: "8charhash"
---
```

**Note**: Authors in frontmatter are just names (strings). Author URLs are included in the markdown body's Author Information section.

Followed by:
- Title heading
- Article Information callout with source, date, authors
- Summary section
- Key Points section
- Linked Concepts section (for manual wiki-linking)
- Notes section (for personal annotations)
- Attachments section with links to PDF, PNG, JSON

## Important Considerations

### When Processing PDFs
- Extract hyperlinks and surrounding text context from PDF
- Filter out unwanted domains (getfireshot.com, youtube.com)
- Prefer source date from article over capture date
- Generate 8-character MD5 hash from first 8KB of PDF for filename

### When Generating Notes
- Sanitize titles for Obsidian: remove `[]#^|\/:?` characters, keep spaces
- Limit filename length to 100 characters
- Store original normalized filename in frontmatter for traceability
- All three file types (PDF, PNG, JSON) should use the same hash-based filename

### Attachment Storage Issue
Current approach stores all attachments in a single flat `Lifegames/Attachments/` directory with hundreds of files. Consider alternatives for better organization while maintaining Obsidian compatibility.

## Development Setup

### Python Environment
The project uses Python for PDF processing utilities:
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### PDF Processor Utility
Located at `src/pdf_processor.py` - extracts text, links, and metadata from PDFs:
```bash
source venv/bin/activate
python src/pdf_processor.py path/to/file.pdf
```

Outputs JSON with:
- `text`: Full text content
- `links`: Array of URLs with context and page numbers (filters out getfireshot.com, youtube.com)
- `metadata`: Page count, file size, creation date, PDF title/author

## Batch Reprocessing System

The repository includes a comprehensive batch reprocessing system for regenerating all Obsidian notes with improved Claude analysis while preserving user-added content.

### Overview

The batch reprocessing system was built to:
- **Upgrade quality**: Reprocess notes originally generated by other LLMs with Claude Sonnet 4.5
- **Track provenance**: Add model version tracking (`generated_by`, `generated_model`, `generated_at`)
- **Preserve user content**: Extract and re-insert user-added sections (Linked Concepts, Notes)
- **Scale efficiently**: Process 239 notes in batches of 10 with progress tracking

### Model Version Tracking

All generated/regenerated notes include provenance metadata in frontmatter:
```yaml
generated_by: "claude-code"
generated_model: "claude-sonnet-4.5-20250929"
generated_at: "2025-11-17"
```

**Important**: The `CLAUDE_MODEL` constant in `batch_reprocess.py` and `apply_batch_updates.py` MUST match and should be updated when using a new Claude model version.

### Core Scripts

#### 1. `src/batch_reprocess.py`
Prepares batches of notes for Claude analysis:
- Scans vault for unprocessed notes (excluding already completed ones in progress file)
- Extracts PDF data for each note using `pdf_processor.py`
- Generates comprehensive prompts for Claude with PDF text, links, and metadata
- Creates `batch_N.json` (note data) and `batch_N_prompt.txt` (Claude prompt)
- Tracks progress in `reprocessing_progress.json`

**Usage**:
```bash
python src/batch_reprocess.py --prepare-only --batch-size 10
```

**Outputs**:
- `batch_N.json`: Complete note information including PDF data
- `batch_N_prompt.txt`: Formatted prompt for Claude analysis
- Updates `reprocessing_progress.json` with current batch number

#### 2. `src/apply_batch_updates.py`
Applies Claude's JSON responses to notes:
- Loads batch data and Claude's metadata response
- Creates timestamped backups in `backups/` directory
- Extracts user-added content from existing notes
- Generates new markdown with improved metadata + preserved user content
- Updates notes in place with complete frontmatter including model tracking
- Increments batch counter in progress file

**Usage**:
```bash
python src/apply_batch_updates.py <batch_num> <response_file>
# Example:
python src/apply_batch_updates.py 0 batch_0_response.json
```

**Features**:
- ✅ Automatic backup creation before any modification
- ✅ Regex-based user content extraction (checks for non-placeholder content)
- ✅ Progress tracking with completed/failed/skipped lists
- ✅ Model version stamping in frontmatter

#### 3. `src/auto_batch_reprocess.py`
Automated workflow orchestration:
- Counts remaining notes to process
- Prepares batches automatically
- Detects existing response files
- Applies updates when responses are available
- Pauses for manual Claude analysis when needed

**Usage**:
```bash
# Show statistics only
python src/auto_batch_reprocess.py --stats-only

# Process all remaining batches
python src/auto_batch_reprocess.py

# Process specific number of batches
python src/auto_batch_reprocess.py --num-batches 5
```

### User Content Preservation

The system preserves user-added content in two sections:

**1. Linked Concepts**
```markdown
## Linked Concepts

[[Related Note 1]]
[[Related Note 2]]
```

**2. Notes**
```markdown
## Notes

User's personal annotations and thoughts...
```

**Detection logic**: Only preserves content that's NOT a placeholder comment:
- Placeholder: `<!-- For manual wiki-linking later -->`
- Real content: Any text besides the placeholder

### Batch Reprocessing Workflow

**Manual workflow (for interactive Claude use)**:
1. Prepare batch: `python src/batch_reprocess.py --prepare-only --batch-size 10`
2. Read prompt from `batch_N_prompt.txt`
3. Analyze PDFs using Claude (copy/paste or interactive)
4. Save Claude's JSON response as `batch_N_response.json`
5. Apply updates: `python src/apply_batch_updates.py N batch_N_response.json`
6. Repeat for next batch

**Automated workflow** (template for API integration):
```bash
python src/auto_batch_reprocess.py
```
- Prepares batches automatically
- Requires manual Claude analysis step
- Applies updates when response files exist
- Tracks overall progress

### Progress Tracking

`reprocessing_progress.json` contains:
```json
{
  "completed": ["note1.md", "note2.md", ...],
  "failed": [],
  "skipped": [],
  "current_batch": 3,
  "started_at": "2025-11-17T...",
  "updated_at": "2025-11-17T..."
}
```

### Example: Complete Batch 0 Workflow

```bash
# 1. Check current progress
python src/auto_batch_reprocess.py --stats-only
# Output: Total: 239, Completed: 0, Remaining: 239, Progress: 0.0%

# 2. Prepare first batch
python src/batch_reprocess.py --prepare-only --batch-size 10
# Creates: batch_0.json, batch_0_prompt.txt

# 3. Analyze with Claude (manually)
# Read batch_0_prompt.txt
# Generate comprehensive metadata for all 10 PDFs
# Save as batch_0_response.json

# 4. Apply updates
python src/apply_batch_updates.py 0 batch_0_response.json
# Output: ✅ Updated: 10, Failed: 0
# Backups: backups/*.md

# 5. Check progress
python src/auto_batch_reprocess.py --stats-only
# Output: Total: 239, Completed: 10, Remaining: 229, Progress: 4.2%
```

### Batch Processing Statistics

**Current Progress** (as of last session):
- Total notes: 239
- Completed: 30 (batches 0-2)
- Remaining: 209
- Progress: 12.6%

### Reset and Recovery

**Reset progress** (start over):
```bash
python src/batch_reprocess.py --reset-progress
```

**Resume from interruption**:
The system automatically resumes from `current_batch` in progress file. If batch N failed:
1. Fix any issues
2. Re-run: `python src/auto_batch_reprocess.py`
3. System will continue from batch N

**Restore from backup**:
All backups are in `backups/` with timestamps:
```bash
# Find backup
ls -lh backups/Note_Name_20251117_*.md

# Restore if needed
cp backups/Note_Name_20251117_133045.md Lifegames/Note_Name.md
```

## FireShot Processing System

The repository includes a comprehensive FireShot file processing system for converting FireShot PDF+PNG captures into structured Obsidian notes.

### Overview

**Status**: ✅ **COMPLETED** - All 186 FireShot files processed (Session 2025-11-17)

The FireShot processing system handles:
- **Input**: FireShot PDF+PNG pairs from `Documents/` folder
- **Extraction**: PDF content, links, metadata via `pdf_processor.py`
- **Metadata Generation**: Claude-generated structured metadata (title, summary, key points, tags, authors)
- **Note Creation**: Obsidian-formatted markdown notes with complete frontmatter
- **Attachment Management**: Hash-based file storage in `Lifegames/Attachments/`
- **Cleanup**: Safe removal of processed source files

### Core Script: `src/process_fireshot.py`

Primary tool for processing FireShot captures with four commands:

#### Commands

**1. Status Check**
```bash
python src/process_fireshot.py status
```
Shows: Total files, processed, remaining, progress percentage

**2. Prepare Batch**
```bash
python src/process_fireshot.py prepare [batch_size]
```
- Default batch size: 20 files
- Extracts PDF content using `pdf_processor.py`
- Generates prompt in `fireshot_batch_N_prompt.txt`
- Stores file data in `fireshot_batch_N.json`

**3. Apply Metadata**
```bash
python src/process_fireshot.py apply [batch_num] [response_file]
# Example:
python src/process_fireshot.py apply 1 fireshot_batch_1_response.json
```
- Loads Claude's metadata response JSON
- Generates Obsidian markdown notes
- Creates hash-based attachments (PDF, PNG, JSON)
- Updates `fireshot_progress.json`

**4. Cleanup**
```bash
python src/process_fireshot.py cleanup [batch_num]
```
- Removes processed source files from `Documents/`
- Safe operation: only deletes files listed in progress tracker

#### Filename Parsing

The script parses FireShot filenames using this pattern:
```python
# Line 66 (FIXED to handle multi-part domains)
match = re.match(r'FireShot Capture (\d+) - (.+) - (.+\.\w+)\.(pdf|png)', filename)
```

**Handles**:
- ✅ Simple domains: `domain.com`
- ✅ Multi-part domains: `www.domain.com`, `blog.site.org`
- ✅ Extracts: capture number, title, domain, file type

**Bug Fix (2025-11-17)**: Changed from `([^.]+\.\w+)` to `(.+\.\w+)` to support multi-part domains. This fix enabled processing of 97 additional files.

### Metadata Schema

Claude generates structured metadata for each FireShot capture:

```json
{
  "file_hash": "8charhash",
  "title": "Article Title from Content",
  "source_name": "Publication Name",
  "source_url": "https://original-article-url",
  "source_date": "YYYY-MM-DD",
  "summary": "2-3 sentence summary with specifics",
  "key_points": [
    "Substantial bullet point 1",
    "Substantial bullet point 2",
    "..."
  ],
  "tags": ["Topic", "Subtopic", "Region"],
  "authors": ["Author Name 1", "Author Name 2"],
  "author_urls": {
    "Author Name 1": "https://author-profile-url",
    "Author Name 2": "https://author-profile-url"
  }
}
```

### Progress Tracking

`fireshot_progress.json` contains:
```json
{
  "processed": [
    "Documents/FireShot Capture 001 - Title - domain.com.pdf",
    "Documents/FireShot Capture 002 - Title - domain.com.pdf",
    ...
  ],
  "current_batch": 10
}
```

### Complete Processing Statistics (2025-11-17)

**Session Accomplishments**:
- ✅ Processed 186 FireShot file pairs (372 source files)
- ✅ Created 187 Obsidian notes with full metadata (186 FireShot + 1 standalone)
- ✅ Generated 561 attachment files (PDF, PNG, JSON)
- ✅ Fixed regex bug enabling processing of 97 additional files
- ✅ Cleaned up `Documents/` folder (removed all processed files)
- ✅ Achieved 100% data integrity (all notes have complete metadata)

**Current Vault Status**:
- **Total Notes**: 424
- **Complete Metadata**: 424/424 (100%)
- **Model Tracking**: All notes have `generated_by`, `generated_model`, `generated_at` fields
- **Attachments**: Hash-based naming in `Lifegames/Attachments/`

### FireShot Processing Workflow

**Standard workflow**:
1. Place FireShot files in `Documents/` folder
2. Check status: `python src/process_fireshot.py status`
3. Prepare batch: `python src/process_fireshot.py prepare 20`
4. Read prompt from `fireshot_batch_N_prompt.txt`
5. Generate metadata with Claude (interactive or API)
6. Save response as `fireshot_batch_N_response.json`
7. Apply updates: `python src/process_fireshot.py apply N fireshot_batch_N_response.json`
8. Cleanup: `python src/process_fireshot.py cleanup N`
9. Repeat for next batch

**Aggressive "Ultrathink" Mode** (used in 2025-11-17 session):
- Generate metadata from titles and general knowledge for speed
- Process large batches (20 files) without reading full PDF content
- Suitable for bulk processing when speed > perfect accuracy

## Phase 3a: Tag Normalization (COMPLETED)

**Status**: ✅ **COMPLETED** - Executed 2025-11-18

The tag normalization system successfully improved tag consistency across the vault through capitalization standardization and duplicate consolidation. Processed 424 notes with 1,577 unique tags before normalization.

**Architecture Note**: Phase 3a focuses ONLY on tag normalization. Hierarchical relationships and mind mapping will be handled via **Linked Concepts** (wiki links) in Phase 3b, creating a two-layer system:
- **Tags**: Many granular tags for filtering/search (Phase 3a normalizes these)
- **Linked Concepts**: Few thematic wiki links for mind mapping (Phase 3b will populate these)

### Overview

**Before Phase 3a**:
- Total notes: 424
- Unique tags: 1,960
- Tags used once: 1,527 (77.9%)
- Capitalization issues: 156 groups

**After Phase 3a**:
- Total notes: 424
- Unique tags: 1,620
- Tags used once: 1,144 (70.6%)
- Capitalization issues: 16 groups (90% reduction)

**Changes Applied**:
- Notes modified: 168 out of 424 (40%)
- Tags remapped: 204 instances
- Tags eliminated: 340 (17.3% reduction)
- All changes backed up to `backups/tag_migration/`

### Tools Created

#### 1. `src/analyze_tags.py` - Tag Analyzer
Analyzes tags across all notes to identify issues and patterns.

**Capabilities**:
- Extract all unique tags and count frequencies
- Find tag co-occurrences
- Identify similar tags (potential duplicates)
- Detect naming inconsistencies (capitalization)
- Discover hierarchical patterns

**Usage**:
```bash
python src/analyze_tags.py --json-output tag_analysis.json
```

**Outputs**:
- Console report with statistics and issues
- JSON file with detailed analysis data

**Key Findings** (from initial run):
- 1,960 unique tags, 3,067 total usages
- 1,527 tags (77.9%) used only once
- 156 groups with capitalization inconsistencies
- Top tags: San-Francisco (81), California (37), AI (26)

#### 2. `src/design_taxonomy.py` - Taxonomy Designer
Proposes tag normalization improvements based on analysis.

**Capabilities**:
- Standardize capitalization (Title-Case-With-Hyphens convention)
- Identify consolidation opportunities
- Estimate impact of changes

**Usage**:
```bash
python src/design_taxonomy.py --analysis-file tag_analysis.json --output tag_taxonomy.json
```

**Outputs**:
- Console report with proposed changes
- JSON file with normalization mappings

**Proposed Changes** (from revised design):
- Capitalization fixes: 163 mappings
- Consolidations: 269 mappings
- Estimated reduction: 173 tags (11%)

#### 3. `src/migrate_tags.py` - Tag Migration Tool
Applies normalization changes to all notes while preserving content.

**Capabilities**:
- Remap tags according to taxonomy
- Remove duplicates after normalization
- Create backups before modification
- Dry-run mode for previewing changes
- Detailed statistics reporting

**Usage**:
```bash
# Dry run (preview changes)
python src/migrate_tags.py --dry-run

# Apply changes
python src/migrate_tags.py

# Custom paths
python src/migrate_tags.py --taxonomy tag_taxonomy.json --vault-path Lifegames/
```

**Actual Impact**:
- Notes modified: 168 out of 424 (40%)
- Tags remapped: 204 instances
- Errors: 0

**Safety Features**:
- Automatic backup creation in `backups/tag_migration/`
- Dry-run mode for validation
- Preserves all note content (only modifies tags in frontmatter)
- Progress reporting with statistics

### Tag Naming Convention

**Standard**: Title-Case-With-Hyphens
- Each word capitalized: `Remote-Work`, `San-Francisco`
- Words separated by hyphens: `-`
- Acronyms uppercase: `AI`, `LLM`, `SF`, `LGBTQ`

**Examples**:
- ✅ `Mental-Health`, `Remote-Work`, `AI`, `LLM`
- ❌ `mental-health`, `remote-work`, `ai`, `llm`

### Workflow

**Phase 3a execution workflow** (completed):

1. ✅ **Analyze**: Generated `tag_analysis.json` with 1,960 unique tags
2. ✅ **Design**: Created `tag_taxonomy.json` with 432 normalization mappings
3. ✅ **Review**: User approved proposed changes
4. ✅ **Test**: Dry run verified 0 errors expected
5. ✅ **Execute**: Applied normalization to 168 notes
6. ✅ **Verify**: Generated `tag_analysis_after.json` showing 1,620 unique tags (17% reduction)

### Data Integrity

All Phase 3a tools include:
- ✅ Automatic backup creation
- ✅ YAML parsing error handling
- ✅ Frontmatter preservation
- ✅ User content preservation
- ✅ Detailed error reporting
- ✅ Statistics tracking

See `DATA_INTEGRITY_REPORT.md` for vault status before Phase 3a.

---

## Phase 3b: Automatic Note Linking (COMPLETED)

**Status**: ✅ **COMPLETED** - Executed 2025-11-18

The automatic note linking system creates bi-directional wiki links between directly related notes, enabling knowledge graph navigation through Obsidian's **Linked Concepts** section.

**Architecture Note**: Phase 3b creates wiki links for DIRECT RELATIONSHIPS only, not thematic categorization. Links connect notes tracking the same:
- Policy/program evolution (e.g., CARE Court updates)
- Company/organization developments (e.g., Waymo expansion)
- Infrastructure projects (e.g., High-Speed Rail progress)
- Ongoing stories (e.g., Castro Theatre saga)

### Overview

**Results**:
- Notes linked: 41 out of 424
- Clusters created: 17 topic clusters
- Links added: 80 bi-directional wiki links
- Backups: 41 files in `backups/note_linking/`
- Errors: 10 (special character filename mismatches)

**Linking Strategies**:
- **Full Mesh**: All notes link to all others (Waymo, Castro Theatre)
- **Linear**: Sequential A↔B→C (CARE Court progression)
- **Hub-Spoke**: Central research with spoke articles (RTO studies, Psychedelics)

### Example Clusters

**CARE Court Program** (2 notes, linear):
- "Is Newsom's CARE Court Making a Difference What the Data Show" ↔ "Newsom Signs Law Expanding CARE Court Mental Health Program"
- Story progression: effectiveness review → policy expansion

**Waymo / Autonomous Vehicles** (5 notes, full mesh):
- How Waymo outlasted the competition
- Waymo Receives Permit to Operate at SFO
- Comparison of Waymo Rider-Only Crash Rates
- Everyone Is Talking About the Waymo Portola Ticket Discount
- We Booked a Ride in Tesla's Robotaxi, Then Raced It Against a Waymo

**Return-to-Office Research** (14 notes across 3 sub-clusters):
- Research studies (3 notes, full mesh)
- Company mandates: Amazon, Dell, Apple/SpaceX/Microsoft (4 notes, hub-spoke)
- Opinion/analysis pieces (7 notes, hub-spoke)

**All 17 Clusters**: Waymo, CARE Court, Castro Theatre, High-Speed Rail, Homelessness, RTO Research, RTO Company Mandates, RTO California, RTO Opinion, Remote Work Challenges, AI-Assisted Coding, Coffee Health, Ultra-Processed Foods, Insurance Crisis, Psychedelics, Castro Business, Castro Policy

### Tools Created

#### `src/link_related_notes.py` - Automatic Linking Tool

**Capabilities**:
- Reads cluster definitions from `linked_notes_clusters.json`
- Determines linking strategy (full mesh / linear / hub-spoke)
- Finds `## Linked Concepts` section in each note
- Adds bi-directional wiki links (preserves existing)
- Creates automatic backups before modification
- Supports dry-run mode

**Usage**:
```bash
# Dry run (preview changes)
python src/link_related_notes.py --dry-run

# Execute linking
python src/link_related_notes.py

# Custom cluster file
python src/link_related_notes.py --clusters my_clusters.json
```

**Cluster Definition Format** (`linked_notes_clusters.json`):
```json
{
  "cluster_id": "waymo_av",
  "name": "Waymo / Autonomous Vehicles",
  "description": "Tracking Waymo's business evolution",
  "linking_strategy": "full_mesh",
  "notes": [
    "How Waymo outlasted the competition.md",
    "Waymo Receives Permit to Operate at SFO.md",
    ...
  ]
}
```

### Workflow

**Adding New Note Clusters**:

1. Edit `linked_notes_clusters.json` to add new cluster
2. Run linking tool: `python src/link_related_notes.py`
3. Tool adds only new links (preserves existing)
4. Review in Obsidian graph view

**Finding New Clusters**:
- Look for notes covering the same specific topic/story
- Identify if relationship is direct (not just thematic)
- Add to cluster definitions
- Choose linking strategy (full mesh / linear / hub-spoke)

### Data Integrity

All Phase 3b linking includes:
- ✅ Automatic backup creation
- ✅ Preserves existing links
- ✅ Bi-directional linking
- ✅ Dry-run mode for validation
- ✅ Detailed statistics reporting

See `LINKED_NOTES_PROPOSAL.md` for complete cluster analysis and `PHASE_3B_COMPLETE.md` for execution details.

---

### Future Phases

**Phase 3c**: Graph database integration (Neo4j)
**Phase 3d**: Pattern discovery and recommendation engine

See `ENHANCEMENT_PLAN.md` for complete Phase 3 roadmap.

## Git Configuration

**Directories to exclude**:
- `Lifegames/` - Obsidian vault (contains large binary files)
- `Documents/` - Input files
- `venv/` - Python virtual environment
- `backups/` - Backup files from migrations
- `.DS_Store` and IDE files (`.idea/`)

**Batch processing files**:
- `batch_*.json` and `batch_*_prompt.txt` - Can be committed for reference
- `batch_*_response.json` - Should be gitignored (large Claude outputs)
- `fireshot_batch_*.json` and `fireshot_batch_*_prompt.txt` - Can be committed
- `fireshot_batch_*_response.json` - Should be gitignored (large JSON outputs)
- `fireshot_progress.json` and `reprocessing_progress.json` - Should be committed (track processing state)

**Analysis and taxonomy files**:
- `tag_analysis.json` and `tag_analysis_after.json` - Can be committed (analysis results)
- `tag_taxonomy.json` - Should be committed (tag normalization mappings)
- `linked_notes_clusters.json` - Should be committed (note cluster definitions)
- `integrity_report.json` and `audit_report.json` - Can be committed (data integrity tracking)
