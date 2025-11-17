# Obsidian Mind Mapper Refactor Plan

## Executive Summary

This document outlines architectural approaches for refactoring the Obsidian Mind Mapper from Python scripts using local LLMs (Ollama) to an interactive Claude Code-based workflow. The goal is to maintain the same output quality while leveraging Claude Code's interactive capabilities instead of API calls.

---

## Current Workflow Analysis

### Existing Pipeline
```
FireShot Files (PNG + PDF) OR Standalone PDFs
    ↓
[1] normalize-screenshots.sh
    → Renames to: YYYY-MM-DD|domain|title.{pdf,png}
    ↓
[2] summarize-pdf.py (LangChain + Ollama + PyMuPDF)
    → Extracts: title, summary, key_points, tags, authors, source_date, links
    → Outputs: JSON file with structured data
    ↓
[3] generate-note.py
    → Generates: Obsidian markdown from template
    → Creates: 8-char hash filenames for all assets
    → Moves: Everything to Lifegames/ vault
```

### Pain Points to Address
1. **Local LLM dependency** - Requires Ollama running, model downloads, GPU/CPU usage
2. **Separate scripts** - Three distinct steps requiring manual chaining
3. **Limited flexibility** - Can't easily ask questions or handle edge cases
4. **Attachment clutter** - 680+ files in flat Attachments/ directory
5. **External vault** - Previously stored in external Obsidian directory

---

## Architectural Approaches

### Approach A: Fully Interactive Workflow
**Concept**: User manually invokes Claude Code for each processing session

**Workflow**:
1. User places files in `Documents/` folder
2. User opens Claude Code and says: "Process the new documents in Documents/"
3. Claude Code:
   - Scans folder for new PDFs/PNGs
   - Reads each PDF using Read tool (supports PDF)
   - Analyzes content and generates structured summary
   - Creates markdown notes and moves files to Lifegames/
   - Reports results to user

**Pros**:
- ✅ No scripting infrastructure needed
- ✅ Maximum flexibility - Claude can ask clarifying questions
- ✅ Can handle edge cases conversationally
- ✅ No API costs
- ✅ User maintains full control over each processing session

**Cons**:
- ❌ Not automated - requires manual invocation
- ❌ Inconsistent - each session might be slightly different
- ❌ Harder to batch process many files
- ❌ User must be present during processing

**Best for**: Small batches, one-off documents, when you want to review each item

---

### Approach B: Slash Command Pipeline
**Concept**: Create custom slash commands for repeatable workflows

**Implementation**:
```bash
.claude/commands/
  ├── process-document.md     # Main pipeline command
  ├── normalize-files.md      # Step 1: Normalize filenames
  ├── analyze-pdf.md          # Step 2: Extract and summarize
  └── generate-note.md        # Step 3: Create Obsidian note
```

**Workflow**:
1. User places files in `Documents/`
2. User runs `/process-document` in Claude Code
3. Command expands with detailed instructions for Claude
4. Claude executes full pipeline programmatically

**Pros**:
- ✅ Repeatable - same command produces consistent results
- ✅ Easy to invoke - single slash command
- ✅ Can be composed - individual steps available separately
- ✅ Documentation built-in - command files explain what they do
- ✅ No API costs

**Cons**:
- ❌ Requires command setup/maintenance
- ❌ Less flexible than fully interactive
- ❌ Still requires user to trigger
- ❌ Edge cases need to be pre-defined in commands

**Best for**: Regular processing of similar documents, established workflow

---

### Approach C: Script + Claude Interactive
**Concept**: Lightweight script for orchestration, Claude for intelligence

**Implementation**:
```python
# process.py
import subprocess
import json
from pathlib import Path

def main():
    # 1. Normalize filenames (simple file operations)
    normalize_files("Documents/")

    # 2. For each PDF, launch Claude Code in focused mode
    for pdf in Path("Documents/").glob("*.pdf"):
        # Extract text, get metadata
        pdf_text = extract_pdf_text(pdf)

        # Create a focused prompt for Claude
        prompt = f"""
        Analyze this PDF and create structured output:
        Title: [extract from content]
        Summary: [2-3 sentences]
        Key Points: [3-5 bullet points]
        Tags: [relevant topics]

        PDF Text:
        {pdf_text}
        """

        # Write prompt to temp file, invoke Claude Code
        # Claude reads, responds with structured data

    # 3. Generate markdown from Claude's outputs
    generate_notes()

if __name__ == "__main__":
    main()
```

**Pros**:
- ✅ Partially automated - script handles boring parts
- ✅ Claude focuses on what it's good at (analysis/extraction)
- ✅ Can batch process multiple files
- ✅ Scriptable/schedulable

**Cons**:
- ❌ Requires Python scripting
- ❌ More complex architecture
- ❌ Claude Code invocation from script is non-trivial
- ❌ Less interactive than pure approaches

**Best for**: High-volume processing, when automation matters

---

### Approach D: Claude Code as the Script
**Concept**: Write the entire pipeline in TypeScript/JavaScript that Claude Code can execute

**Implementation**:
```typescript
// src/process-documents.ts
import { readPDF, generateHash, createMarkdown } from './utils';
import Anthropic from '@anthropic-ai/sdk';

async function processDocuments() {
  const files = await scanInputDirectory();

  for (const file of files) {
    // 1. Normalize filename
    const normalized = await normalizeFilename(file);

    // 2. Extract PDF content
    const pdfContent = await readPDF(normalized);

    // 3. Call Claude API for analysis
    const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const analysis = await anthropic.messages.create({
      model: "claude-3-5-sonnet-20241022",
      messages: [{
        role: "user",
        content: `Analyze this article: ${pdfContent}`
      }]
    });

    // 4. Generate markdown note
    await createMarkdown(analysis, normalized);
  }
}
```

**Pros**:
- ✅ Fully automated
- ✅ Structured outputs via API
- ✅ Type-safe with TypeScript
- ✅ Can run on schedule/CI/CD
- ✅ Professional architecture

**Cons**:
- ❌ **Violates requirement** - Uses API, not interactive Claude Code
- ❌ API costs (though minimal for this use case)
- ❌ Requires API key management
- ❌ More complex setup (Node.js, dependencies)

**Best for**: Production use cases, but NOT aligned with stated goals

---

## Recommended Hybrid Approach

### Primary: Approach B (Slash Commands) + Interactive Fallback

**Why this works best**:
1. **Repeatability** - Slash commands provide consistency
2. **Flexibility** - Can still interact with Claude for edge cases
3. **No API required** - Fully interactive as requested
4. **Low maintenance** - Commands are just markdown files
5. **Discoverable** - Easy to see what's available via `/help`

**Implementation Strategy**:

#### Phase 1: Core Slash Command
Create `/process-document` that:
1. Prompts user: "Which file should I process?" (shows list from Documents/)
2. Reads the PDF using Read tool
3. Analyzes content and generates structured summary
4. Creates markdown note with proper frontmatter
5. Moves files to appropriate locations
6. Reports success/issues

#### Phase 2: Batch Processing
Enhance `/process-document` with:
- `--all` flag to process all files in Documents/
- `--reviewed` flag to mark as reviewed automatically
- Progress reporting for multiple files

#### Phase 3: Modular Commands
Break into smaller commands:
- `/normalize` - Just rename files
- `/analyze <file>` - Just extract and summarize
- `/create-note <json>` - Just generate markdown from existing JSON

---

## Key Implementation Decisions

### 1. PDF Processing Method

**Option A: Claude Read Tool**
- Built-in PDF support in Claude Code
- Simple: `Read tool → PDF content`
- May lose some formatting/link data

**Option B: PyMuPDF Library**
- Precise link extraction with coordinates
- Better metadata extraction
- Requires Python dependency

**Recommendation**: Start with Read tool, add PyMuPDF if link extraction is critical

### 2. Structured Output Strategy

Without API's structured outputs feature, we need to ensure consistency:

**Option A: Strict Prompting**
```
Return ONLY valid JSON in exactly this format:
{
  "title": "string",
  "summary": "string",
  "key_points": ["string"],
  "tags": ["string"],
  "authors": [{"name": "string", "url": "string"}],
  "source_date": "YYYY-MM-DD"
}
```

**Option B: JSON Schema Validation**
- Provide JSON schema in prompt
- Validate Claude's output
- Re-prompt if invalid

**Option C: Interactive Extraction**
- Ask Claude to extract each field separately
- Build up the JSON progressively
- More reliable but slower

**Recommendation**: Option A with fallback to B for validation

### 3. File Naming and Hashing

**Current**: 8-char MD5 hash of first 8KB of PDF

**Alternatives**:
- **Content-based**: Hash of full PDF content (slower, more unique)
- **Title-based**: Sanitized title + date (readable, may collide)
- **UUID**: Guaranteed unique (not deterministic)
- **Keep current**: Already works, deterministic

**Recommendation**: Keep current approach - it's deterministic and collision-resistant

### 4. Attachment Storage Architecture

**Current Pain**: 680+ files in flat `Lifegames/Attachments/` directory

**Option A: Subfolders by Date**
```
Lifegames/
  Attachments/
    2025/
      01/
        1e567f29.pdf
        1e567f29.png
        1e567f29.json
```
✅ Pros: Chronological organization, easier to find recent items
❌ Cons: Requires date tracking, Obsidian links get longer

**Option B: Subfolders by Hash Prefix**
```
Lifegames/
  Attachments/
    1e/
      1e567f29.pdf
      1e567f29.png
    2f/
      2f3a9b12.pdf
```
✅ Pros: Balanced distribution, Git-like structure
❌ Cons: Less human-navigable, still hundreds of folders

**Option C: Co-located with Notes**
```
Lifegames/
  The Best Product Engineering Org/
    The Best Product Engineering Org.md
    1e567f29.pdf
    1e567f29.png
    1e567f29.json
```
✅ Pros: Everything together, easy to find
❌ Cons: Breaks current Obsidian link structure, more folders

**Option D: Keep Flat, Improve Naming**
```
Lifegames/
  Attachments/
    2025-01-28_www.jamesshore.com_1e567f29.pdf
    2025-01-28_www.jamesshore.com_1e567f29.png
```
✅ Pros: Still flat, but more descriptive filenames
❌ Cons: Longer filenames, still 680+ files in one folder

**Option E: Hybrid - Date-based Subfolders + Hash**
```
Lifegames/
  Attachments/
    2025-01/
      1e567f29.pdf
      1e567f29.png
      2f3a9b12.pdf
    2025-02/
      ...
```
✅ Pros: ~20-50 files per folder, chronological browsing
❌ Cons: Requires YYYY-MM parsing

**Recommendation**: Option E (Date-based subfolders by month)
- Manageable folder sizes (20-50 files per month)
- Chronological browsing still possible
- Doesn't break existing Obsidian link structure (just changes path)
- Easy to implement with existing date metadata

---

## Migration Strategy

### For Existing Files
Should we migrate the 680+ existing attachments to new structure?

**Option 1: Leave as-is**
- New files use new structure
- Old files stay in flat directory
- Dual-path system

**Option 2: Gradual migration**
- Move files when notes are edited/reviewed
- Eventually everything migrates

**Option 3: One-time migration script**
- Migrate all at once
- Update all markdown references
- Clean break

**Recommendation**: Option 1 (leave existing), unless folder performance is a real problem

---

## Development Roadmap

### Milestone 1: Proof of Concept (Manual)
- Manually process 1-2 PDFs using Claude Code Read tool
- Test PDF reading quality
- Experiment with structured output prompts
- Validate Obsidian markdown generation

### Milestone 2: Basic Slash Command
- Create `/process-document` command
- Single file processing
- Generate JSON + Markdown
- Store in new attachment structure

### Milestone 3: Batch Processing
- Process multiple files in one session
- Progress tracking
- Error handling

### Milestone 4: Refinements
- Link extraction from PDFs
- Author detection improvements
- Tag generation enhancements
- Duplicate detection

### Milestone 5: Quality of Life
- `/review-note` command to move to Reviewed/
- `/search-notes` for finding existing content
- `/reprocess` to regenerate notes from existing PDFs

---

## Decisions Made

1. **Processing frequency**: Weekly
2. **Batch sizes**: ~10 files per session
3. **Link extraction**: Critical - requires PyMuPDF integration
4. **Existing attachments**: Leave in flat structure (no migration)
5. **Primary input type**: FireShot (PNG + PDF with domain info)

---

## Final Architecture Decision

**Approach B: Slash Command Pipeline with PyMuPDF**

### Why This Fits
- ✅ Weekly batches of 10 files → Slash command is perfect
- ✅ Critical link extraction → PyMuPDF integration required
- ✅ FireShot focus → Can parse domain from filename
- ✅ Batch processing → Command handles multiple files
- ✅ No migration → New files use date-based folders, old files stay put

### Implementation Plan

**Technology Stack**:
- **Orchestration**: Claude Code slash command
- **PDF Processing**: PyMuPDF (fitz) for link extraction
- **LLM Analysis**: Interactive Claude (no API)
- **Storage**: Date-based subfolders (YYYY-MM/) for new files

**Attachment Structure**:
```
Lifegames/
  Attachments/
    # Old files (680+) - keep as-is
    1e567f29.pdf
    2f3a9b12.png
    ...
    # New files - organized by month
    2025-01/
      a1b2c3d4.pdf
      a1b2c3d4.png
      a1b2c3d4.json
    2025-02/
      ...
```

---

## Next Steps

### Phase 1: Setup Python Environment
1. Create `requirements.txt` with PyMuPDF
2. Create `src/pdf_processor.py` for link extraction utility
3. Test link extraction on sample FireShot PDFs

### Phase 2: Create Slash Command
1. Create `.claude/commands/process-fireshot.md`
2. Command workflow:
   - List all files in Documents/
   - For each PDF:
     - Run PyMuPDF script to extract links, text, metadata
     - Pass to Claude for analysis (title, summary, key_points, tags, authors)
     - Generate Obsidian markdown
     - Move files to Lifegames/ with date-based subfolder
   - Report progress for all 10 files

### Phase 3: Refinement
1. Handle edge cases (missing metadata, broken links)
2. Add duplicate detection
3. Improve tag generation
4. Create `/review-note` helper command

### Ready to Start?
We can begin with Phase 1 - setting up the Python environment and PDF processing utilities.
