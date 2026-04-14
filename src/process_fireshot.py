#!/usr/bin/env python3
"""
Process FireShot PDF+PNG pairs into Obsidian notes.

This script:
1. Finds all FireShot Capture PDFs in Documents/
2. Extracts content from each PDF using pdf_processor
3. Prepares batches for Claude to generate metadata
4. After Claude generates metadata, creates notes and moves files
"""

import json
import os
import re
import hashlib
import shutil
from pathlib import Path
from datetime import datetime
from pdf_processor import extract_pdf_data

# Paths
REPO_ROOT = Path(__file__).parent.parent
DOCUMENTS_DIR = REPO_ROOT / "Documents"
LIFEGAMES_DIR = REPO_ROOT / "Lifegames"
ATTACHMENTS_DIR = LIFEGAMES_DIR / "Attachments"
PROGRESS_FILE = REPO_ROOT / "fireshot_progress.json"

# Ensure directories exist
ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)


def load_progress():
    """Load processing progress."""
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"processed": [], "current_batch": 0}


def save_progress(progress):
    """Save processing progress."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


def get_file_hash(pdf_path):
    """Generate 8-character hash from first 8KB of PDF."""
    with open(pdf_path, "rb") as f:
        data = f.read(8192)  # First 8KB
    return hashlib.md5(data).hexdigest()[:8]


def sanitize_title(title):
    """Sanitize title for Obsidian filename."""
    # Remove problematic characters
    sanitized = re.sub(r'[\[\]#^|\\/:?*<>"]', '', title)
    # Limit length
    if len(sanitized) > 100:
        sanitized = sanitized[:97] + "..."
    return sanitized.strip()


def parse_fireshot_filename(filename):
    """Parse FireShot filename to extract components."""
    # Format: FireShot Capture NNN - Title - domain.com.pdf or www.domain.com.pdf
    match = re.match(r'FireShot Capture (\d+) - (.+) - (.+\.\w+)\.(pdf|png)', filename)
    if match:
        capture_num, title, domain, ext = match.groups()
        return {
            "capture_num": capture_num,
            "title": title,
            "domain": domain,
            "ext": ext
        }
    return None


def find_fireshot_pairs():
    """Find all FireShot PDF+PNG pairs in Documents/."""
    pdf_files = list(DOCUMENTS_DIR.glob("FireShot Capture*.pdf"))
    pairs = []

    for pdf_path in sorted(pdf_files):
        pdf_info = parse_fireshot_filename(pdf_path.name)
        if not pdf_info:
            continue

        # Look for matching PNG
        png_name = pdf_path.stem + ".png"
        png_path = DOCUMENTS_DIR / png_name

        pairs.append({
            "pdf": pdf_path,
            "png": png_path if png_path.exists() else None,
            "info": pdf_info
        })

    return pairs


def prepare_batch(pairs, batch_size=10):
    """Prepare a batch of files for Claude processing."""
    progress = load_progress()
    processed = set(progress["processed"])

    # Filter out already processed
    unprocessed = [p for p in pairs if str(p["pdf"]) not in processed]

    if not unprocessed:
        print("✅ All FireShot files already processed!")
        return None

    # Take next batch
    batch = unprocessed[:batch_size]
    batch_num = progress["current_batch"] + 1

    # Extract PDF data for each file
    batch_data = []
    for pair in batch:
        print(f"📄 Extracting: {pair['pdf'].name}")
        try:
            pdf_data = extract_pdf_data(str(pair["pdf"]))
            file_hash = get_file_hash(pair["pdf"])

            batch_data.append({
                "pdf_path": str(pair["pdf"]),
                "png_path": str(pair["png"]) if pair["png"] else None,
                "file_hash": file_hash,
                "info": pair["info"],
                "pdf_data": pdf_data
            })
        except Exception as e:
            print(f"❌ Error extracting {pair['pdf'].name}: {e}")
            continue

    # Save batch data
    batch_file = REPO_ROOT / f"fireshot_batch_{batch_num}.json"
    with open(batch_file, "w") as f:
        json.dump(batch_data, f, indent=2)

    # Generate prompt file
    prompt = generate_batch_prompt(batch_data, batch_num)
    prompt_file = REPO_ROOT / f"fireshot_batch_{batch_num}_prompt.txt"
    with open(prompt_file, "w") as f:
        f.write(prompt)

    print(f"\n✅ Batch {batch_num} prepared: {len(batch_data)} files")
    print(f"   Data: {batch_file}")
    print(f"   Prompt: {prompt_file}")
    print(f"\n📋 Next: Generate metadata, save as fireshot_batch_{batch_num}_response.json")

    return batch_num


def generate_batch_prompt(batch_data, batch_num):
    """Generate prompt for Claude to process batch."""
    prompt = f"""I need you to analyze {len(batch_data)} web article PDFs and generate structured metadata for Obsidian notes.

For EACH document below, provide a JSON object with:
{{
  "file_hash": "the hash from the document info",
  "title": "Concise, descriptive title (from article content, not FireShot filename)",
  "source_name": "Publication/organization",
  "source_url": "Primary article URL (extract from PDF links/metadata)",
  "source_date": "YYYY-MM-DD (prefer article date over capture date)",
  "summary": "2-3 sentence comprehensive summary with specific data/statistics",
  "key_points": [
    "5 substantial, specific bullet points",
    "Include concrete numbers and findings",
    "Focus on insights and significance"
  ],
  "tags": ["relevant", "specific", "tags"],
  "authors": ["Author Name"],
  "author_urls": {{"Author Name": "url"}}
}}

Generate a JSON array with one object per document. Focus on accuracy, specificity, and insights.

IMPORTANT:
- Extract the real article title from the PDF content, not the FireShot filename
- Find the source URL from the PDF links/metadata
- Skip any links to getfireshot.com or youtube.com
- Prefer the article's publication date over the capture date

DOCUMENTS TO ANALYZE:
"""

    for i, item in enumerate(batch_data, 1):
        pdf_data = item["pdf_data"]
        info = item["info"]

        prompt += f"\n\n{'='*70}\n"
        prompt += f"DOCUMENT {i}/{len(batch_data)}\n"
        prompt += f"{'='*70}\n"
        prompt += f"FireShot Filename: {info['title']}\n"
        prompt += f"Domain: {info['domain']}\n"
        prompt += f"File Hash: {item['file_hash']}\n\n"

        prompt += f"PDF METADATA:\n"
        prompt += f"- Pages: {pdf_data.get('metadata', {}).get('page_count', 'unknown')}\n"
        prompt += f"- File Size: {pdf_data.get('metadata', {}).get('file_size', 'unknown')} bytes\n"
        prompt += f"- PDF Title: {pdf_data.get('metadata', {}).get('title', 'unknown')}\n"
        prompt += f"- PDF Author: {pdf_data.get('metadata', {}).get('author', 'unknown')}\n\n"

        # Text content (limited)
        text = pdf_data.get('text', '')
        prompt += f"TEXT (first 3000 chars):\n{text[:3000]}\n\n"

        # Links
        links = pdf_data.get('links', [])
        # Filter out unwanted domains
        filtered_links = [
            link for link in links
            if 'getfireshot.com' not in link.get('url', '') and
               'youtube.com' not in link.get('url', '')
        ]
        prompt += f"LINKS ({len(filtered_links)} total, filtered):\n"
        prompt += json.dumps(filtered_links[:20], indent=2)  # Show first 20
        prompt += "\n"

    prompt += f"\n\n{'='*70}\n"
    prompt += "Please provide ONLY the JSON array, no additional text.\n"

    return prompt


def apply_batch_metadata(batch_num, response_file):
    """Apply metadata from Claude response to create notes."""
    # Load batch data
    batch_file = REPO_ROOT / f"fireshot_batch_{batch_num}.json"
    with open(batch_file) as f:
        batch_data = json.load(f)

    # Load response metadata
    with open(response_file) as f:
        metadata_list = json.load(f)

    # Create hash lookup
    metadata_by_hash = {m["file_hash"]: m for m in metadata_list}

    progress = load_progress()
    created_count = 0

    for item in batch_data:
        file_hash = item["file_hash"]
        metadata = metadata_by_hash.get(file_hash)

        if not metadata:
            print(f"⚠️  No metadata found for {file_hash}")
            continue

        try:
            # Create note
            note_path = create_note(item, metadata)
            print(f"✅ Created: {note_path.name}")

            # Move files to Attachments
            move_to_attachments(item, file_hash)

            # Mark as processed
            progress["processed"].append(item["pdf_path"])
            created_count += 1

        except Exception as e:
            print(f"❌ Error processing {file_hash}: {e}")
            continue

    # Update progress
    progress["current_batch"] = batch_num
    save_progress(progress)

    print(f"\n✅ Batch {batch_num} complete: {created_count} notes created")
    return created_count


def create_note(item, metadata):
    """Create Obsidian note from metadata."""
    # Sanitize title for filename
    title = sanitize_title(metadata["title"])
    note_path = LIFEGAMES_DIR / f"{title}.md"

    # Build frontmatter
    frontmatter = f"""---
title: "{metadata['title']}"
source: "{metadata['source_name']}"
source_url: "{metadata['source_url']}"
date: {metadata['source_date']}
authors:
"""
    for author in metadata.get("authors", []):
        frontmatter += f"  - {author}\n"

    frontmatter += f"tags: {json.dumps(metadata.get('tags', []))}\n"
    frontmatter += f"filename: \"{item['file_hash']}\"\n"
    frontmatter += f"cssclass: article-note\n"
    frontmatter += f"file_hash: \"{item['file_hash']}\"\n"
    frontmatter += f"generated_by: claude-code\n"
    frontmatter += f"generated_model: claude-sonnet-4.5-20250929\n"
    frontmatter += f"generated_at: {datetime.now().isoformat()}\n"
    frontmatter += "---\n\n"

    # Build note body
    body = f"# {metadata['title']}\n\n"

    # Article Information callout
    body += "> [!info] Article Information\n"
    body += f"> **Source:** [{metadata['source_name']}]({metadata['source_url']})\n"
    body += f"> **Date:** {metadata['source_date']}\n"
    if metadata.get("authors"):
        body += "> **Authors:** " + ", ".join(metadata["authors"]) + "\n"
    body += "\n"

    # Summary
    body += "## Summary\n\n"
    body += metadata['summary'] + "\n\n"

    # Key Points
    body += "## Key Points\n\n"
    for point in metadata.get('key_points', []):
        body += f"- {point}\n"
    body += "\n"

    # Author Information (with URLs)
    if metadata.get("author_urls"):
        body += "## Author Information\n\n"
        for author, url in metadata["author_urls"].items():
            if url:
                body += f"- [{author}]({url})\n"
            else:
                body += f"- {author}\n"
        body += "\n"

    # Linked Concepts
    body += "## Linked Concepts\n\n"
    body += "_Add related notes and concepts here_\n\n"

    # Notes
    body += "## Notes\n\n"
    body += "_Add your personal notes and insights here_\n\n"

    # Attachments
    body += "## Attachments\n\n"
    body += f"- [[Attachments/{item['file_hash']}.pdf|PDF Version]]\n"
    if item.get("png_path"):
        body += f"- [[Attachments/{item['file_hash']}.png|Screenshot]]\n"
    body += f"- [[Attachments/{item['file_hash']}.json|Extracted Data]]\n"

    # Write note
    with open(note_path, "w") as f:
        f.write(frontmatter + body)

    return note_path


def move_to_attachments(item, file_hash):
    """Move PDF, PNG, and create JSON in Attachments."""
    # Move PDF
    pdf_src = Path(item["pdf_path"])
    pdf_dst = ATTACHMENTS_DIR / f"{file_hash}.pdf"
    shutil.copy2(pdf_src, pdf_dst)

    # Move PNG if exists
    if item.get("png_path"):
        png_src = Path(item["png_path"])
        if png_src.exists():
            png_dst = ATTACHMENTS_DIR / f"{file_hash}.png"
            shutil.copy2(png_src, png_dst)

    # Save JSON data
    json_dst = ATTACHMENTS_DIR / f"{file_hash}.json"
    with open(json_dst, "w") as f:
        json.dump(item["pdf_data"], f, indent=2)

    print(f"   📦 Moved to Attachments/: {file_hash}.{{pdf,png,json}}")


def cleanup_documents(batch_num):
    """Remove processed files from Documents/."""
    batch_file = REPO_ROOT / f"fireshot_batch_{batch_num}.json"
    with open(batch_file) as f:
        batch_data = json.load(f)

    for item in batch_data:
        pdf_path = Path(item["pdf_path"])
        if pdf_path.exists():
            pdf_path.unlink()

        if item.get("png_path"):
            png_path = Path(item["png_path"])
            if png_path.exists():
                png_path.unlink()

    print(f"🗑️  Cleaned up {len(batch_data)} file pairs from Documents/")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python src/process_fireshot.py prepare [batch_size]  - Prepare next batch")
        print("  python src/process_fireshot.py apply BATCH_NUM       - Apply metadata to batch")
        print("  python src/process_fireshot.py cleanup BATCH_NUM     - Clean up Documents/")
        print("  python src/process_fireshot.py status                - Show processing status")
        sys.exit(1)

    command = sys.argv[1]

    if command == "prepare":
        batch_size = int(sys.argv[2]) if len(sys.argv) > 2 else 10
        pairs = find_fireshot_pairs()
        print(f"📊 Found {len(pairs)} FireShot file pairs")
        prepare_batch(pairs, batch_size)

    elif command == "apply":
        if len(sys.argv) < 3:
            print("❌ Error: BATCH_NUM required")
            sys.exit(1)
        batch_num = int(sys.argv[2])
        response_file = REPO_ROOT / f"fireshot_batch_{batch_num}_response.json"
        if not response_file.exists():
            print(f"❌ Error: {response_file} not found")
            sys.exit(1)
        apply_batch_metadata(batch_num, response_file)

    elif command == "cleanup":
        if len(sys.argv) < 3:
            print("❌ Error: BATCH_NUM required")
            sys.exit(1)
        batch_num = int(sys.argv[2])
        cleanup_documents(batch_num)

    elif command == "status":
        pairs = find_fireshot_pairs()
        progress = load_progress()
        processed_count = len(progress["processed"])
        total_count = len(pairs)
        remaining = total_count - processed_count

        print(f"\n📊 FireShot Processing Status")
        print(f"{'='*50}")
        print(f"Total files: {total_count}")
        print(f"Processed: {processed_count}")
        print(f"Remaining: {remaining}")
        print(f"Current batch: {progress['current_batch']}")
        print(f"{'='*50}\n")

    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
