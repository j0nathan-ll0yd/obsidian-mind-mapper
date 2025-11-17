You are processing FireShot webpage captures (PNG + PDF) or standalone PDFs into structured Obsidian notes for the mind map.

## Your Task

Process all PDFs in the `Documents/` folder through this pipeline:

1. **List Files**: Show all PDF files in `Documents/` to the user
2. **For Each PDF**:
   a. Extract content using the PDF processor utility
   b. Analyze the content and generate structured metadata
   c. Create an Obsidian markdown note
   d. Move files to the Lifegames vault with proper organization
3. **Report Results**: Summarize what was processed

## Step-by-Step Instructions

### Step 1: List PDF Files
List all PDF files in the Documents/ folder and show them to the user:
```bash
ls -1 Documents/*.pdf
```

Ask the user if they want to process all files or specific ones.

### Step 2: Process Each PDF

For each PDF file to process:

#### 2a. Extract PDF Content
Run the PDF processor utility:
```bash
source venv/bin/activate && python src/pdf_processor.py "Documents/FILENAME.pdf"
```

This outputs JSON with:
- `text`: Full article text
- `links`: Array of hyperlinks with context
- `metadata`: Page count, file size, creation date, PDF metadata

#### 2b. Analyze Content
Using the extracted text and your intelligence, generate a structured analysis in JSON format:

```json
{
  "title": "Article title (extract from text)",
  "source_name": "Source publication name (e.g., 'Scientific American')",
  "source_url": "Main article URL (from links if available, or best guess from domain)",
  "source_date": "YYYY-MM-DD (prefer article date over PDF creation date)",
  "summary": "2-3 sentence summary of the article",
  "key_points": [
    "First key point",
    "Second key point",
    "Third key point (3-5 total)"
  ],
  "tags": ["Topic1", "Topic2", "Category", "Region", "Keyword"],
  "authors": ["Author Name"],
  "author_urls": {
    "Author Name": "https://author-profile-url.com (if available)"
  }
}
```

**Important Analysis Guidelines**:
- Extract the actual article title from the text content
- Identify the source publication (Scientific American, New York Times, etc.)
- Find the source URL from the links (usually the first substantive link)
- Prefer the article's publication date over the PDF creation date
- Write a concise, informative summary
- Extract 3-5 genuinely important key points (not just a list of topics)
- Generate relevant tags: topics, categories, regions, keywords
- Extract author names from the text (frontmatter is just names as strings)
- Extract author profile URLs to use in the markdown body's Author section

#### 2c. Generate File Hash
Create an 8-character MD5 hash from the PDF for filenames:
```bash
head -c 8192 "Documents/FILENAME.pdf" | md5 | cut -c1-8
```

Store this hash as a variable (e.g., `HASH="a1b2c3d4"`)

#### 2d. Extract Date for Folder Organization
Extract the year-month for the attachment subfolder:
- If source_date is available: use it (e.g., "2025-01" from "2025-01-15")
- Otherwise: use PDF creation date from metadata
- Otherwise: use current year-month

Store as `YEAR_MONTH` (e.g., "2025-01")

#### 2e. Create Obsidian Markdown Note
Using the template structure, create a markdown file:

**Frontmatter**:
```yaml
---
title: "Article Title"
source: "Source Name"
source_url: "https://..."
date: YYYY-MM-DD
authors:
  - Author Name
tags: [Tag1, Tag2, Tag3]
filename: "8charhash"
cssclass: article-note
file_hash: "8charhash"
---
```

**Content**:
```markdown
# Article Title

> [!info]+ Article Information
> - **Source**: [Source Name](source_url)
> - **Date**: YYYY-MM-DD
> - **Authors**: [Author Name](author_url) OR Author Name (if no URL)

## Summary
[2-3 sentence summary]

## Key Points
- Key point 1
- Key point 2
- Key point 3

## Linked Concepts
<!-- For manual wiki-linking later -->

## Notes
<!-- For personal annotations -->

## Attachments
- PDF: ![[YEAR_MONTH/HASH.pdf]]
- PNG: ![[YEAR_MONTH/HASH.png]] (if exists)

## External Links
[List of extracted links with context]
- [Link context text](url)
```

Save this file as: `Lifegames/SANITIZED_TITLE.md`

**Title Sanitization**: Remove these characters: `[]#^|\/:?` but keep spaces. Limit to 100 chars.

#### 2f. Create JSON Data File
Save the structured analysis JSON to:
```
Lifegames/Attachments/YEAR_MONTH/HASH.json
```

#### 2g. Move Files to Vault
Create the attachment subfolder if needed:
```bash
mkdir -p "Lifegames/Attachments/YEAR_MONTH"
```

Move the PDF (copy first, then verify and remove):
```bash
# Copy PDF to destination
cp "Documents/FILENAME.pdf" "Lifegames/Attachments/YEAR_MONTH/HASH.pdf"

# Verify the copy succeeded and file exists at destination
if [ -f "Lifegames/Attachments/YEAR_MONTH/HASH.pdf" ]; then
  # Remove source file
  rm "Documents/FILENAME.pdf"
  echo "✓ Moved PDF successfully"
else
  echo "✗ Error: Failed to copy PDF, source file preserved"
fi
```

Move the PNG if it exists (look for matching FireShot PNG):
```bash
# Find matching PNG (FireShot creates both PDF and PNG with similar names)
PNG_FILE=$(ls "Documents/MATCHING_FILE.png" 2>/dev/null)

if [ -n "$PNG_FILE" ]; then
  # Copy PNG to destination
  cp "$PNG_FILE" "Lifegames/Attachments/YEAR_MONTH/HASH.png"

  # Verify and remove
  if [ -f "Lifegames/Attachments/YEAR_MONTH/HASH.png" ]; then
    rm "$PNG_FILE"
    echo "✓ Moved PNG successfully"
  else
    echo "✗ Error: Failed to copy PNG, source file preserved"
  fi
else
  echo "No matching PNG found (this is OK for standalone PDFs)"
fi
```

**Safety Notes**:
- Always copy first, then verify destination exists before removing source
- If copy fails, preserve the source file and report error
- Use explicit error checking to prevent data loss

### Step 3: Report Results

After processing all files, provide a summary:
- Number of files processed
- Titles of generated notes
- Any errors or warnings
- Location of new notes in Lifegames/

## Important Notes

- **Progress tracking**: Update the user after each file is processed
- **Error handling**: If PDF extraction fails, skip that file and continue
- **Duplicate detection**: Check if a note with the same title already exists
- **Link extraction**: Include all extracted links in the "External Links" section
- **Date-based folders**: New files go in YYYY-MM subfolders, old files stay flat
- **PNG matching**: FireShot creates both PDF and PNG with similar names - try to match them
- **File cleanup**: Source files are REMOVED from Documents/ after successful move (copy → verify → delete)

## Example Workflow

```
User runs: /process-fireshot

You respond:
"I found 3 PDFs in Documents/:
1. This Powerful Psychedelic Could Help Relieve Traumatic Brain Injury _ Scientific American.pdf
2. popos-guide.pdf
3. Optimism is associated with exceptional longevity in 2 epidemiologic cohorts of men and women.pdf

Would you like me to process all of them?"

[User confirms]

"Processing file 1/3: This Powerful Psychedelic...
- Extracting content... ✓
- Analyzing article... ✓
- Generated note: 'This Powerful Psychedelic Shows Promise for Relieving Traumatic Brain Injury'
- Created files in Lifegames/Attachments/2024-01/
- Hash: a1b2c3d4

Processing file 2/3: popos-guide.pdf
..."
```

## Edge Cases to Handle

1. **Image-based PDFs**: If text extraction returns empty, inform user and skip
2. **No matching PNG**: That's fine, just process the PDF
3. **Existing notes**: Check if title already exists, warn user
4. **Missing metadata**: Use sensible defaults (current date, "Unknown" source, etc.)
5. **Invalid URLs**: If no valid source URL found, use first non-skipped link or leave blank