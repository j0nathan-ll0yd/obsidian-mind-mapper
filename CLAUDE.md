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

## Git Configuration
- `Lifegames/` directory should NOT be committed (contains large binary files)
- `Documents/` should NOT be committed (input files)
- `venv/` should NOT be committed (Python virtual environment)
- `.DS_Store` and IDE files (`.idea/`) should be ignored
