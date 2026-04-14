#!/usr/bin/env python3
"""
Batch reprocessing script for Obsidian notes with Claude Code.

This script orchestrates the reprocessing of multiple notes efficiently:
- Extracts PDF data for all notes needing reprocessing
- Prepares batches for Claude analysis
- Manages the interactive workflow with Claude
- Tracks progress and handles resume capability
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple
import subprocess
import re

# Model version constant - UPDATE THIS WHEN MODEL CHANGES
CLAUDE_MODEL = "claude-sonnet-4.5-20250929"

class BatchReprocessor:
    def __init__(self, vault_path: str = "Lifegames", batch_size: int = 10):
        self.vault_path = Path(vault_path)
        self.batch_size = batch_size
        self.progress_file = Path("reprocessing_progress.json")

        # Load or initialize progress
        self.progress = self.load_progress()

    def load_progress(self) -> Dict:
        """Load processing progress from file."""
        if self.progress_file.exists():
            return json.loads(self.progress_file.read_text())
        return {
            'completed': [],
            'failed': [],
            'skipped': [],
            'current_batch': 0,
            'started_at': datetime.now().isoformat()
        }

    def save_progress(self):
        """Save processing progress to file."""
        self.progress['updated_at'] = datetime.now().isoformat()
        self.progress_file.write_text(json.dumps(self.progress, indent=2))

    def get_notes_to_process(self) -> List[Path]:
        """Get list of all notes that need processing."""
        notes = []

        # Top-level notes
        for md_file in self.vault_path.glob("*.md"):
            if md_file.name not in self.progress['completed']:
                notes.append(md_file)

        # Reviewed subfolder
        reviewed_path = self.vault_path / "Reviewed"
        if reviewed_path.exists():
            for md_file in reviewed_path.glob("*.md"):
                relative_name = f"Reviewed/{md_file.name}"
                if relative_name not in self.progress['completed']:
                    notes.append(md_file)

        return notes

    def parse_frontmatter(self, content: str) -> Tuple[Optional[Dict], str]:
        """Extract frontmatter and body from markdown."""
        match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
        if not match:
            return None, content

        frontmatter_text = match.group(1)
        body = match.group(2)

        frontmatter = {}
        current_key = None
        current_list = []

        for line in frontmatter_text.split('\n'):
            if line.strip().startswith('- '):
                if current_key:
                    current_list.append(line.strip()[2:])
                continue

            if ':' in line:
                if current_key and current_list:
                    frontmatter[current_key] = current_list
                    current_list = []

                key, value = line.split(':', 1)
                current_key = key.strip()
                value = value.strip().strip('"').strip("'")

                if value:
                    frontmatter[current_key] = value
                    current_key = None

        if current_key and current_list:
            frontmatter[current_key] = current_list

        return frontmatter, body

    def find_pdf_for_hash(self, file_hash: str) -> Optional[Path]:
        """Find PDF in Attachments by hash."""
        attachments = self.vault_path / "Attachments"
        if not attachments.exists():
            return None

        for pdf_path in attachments.rglob(f"{file_hash}.pdf"):
            return pdf_path

        return None

    def extract_pdf_data(self, pdf_path: Path) -> Optional[Dict]:
        """Extract data from PDF using pdf_processor.py."""
        try:
            result = subprocess.run(
                [sys.executable, 'src/pdf_processor.py', str(pdf_path)],
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode == 0:
                return json.loads(result.stdout)
            else:
                return None
        except Exception as e:
            print(f"Error extracting PDF: {e}")
            return None

    def prepare_batch(self, notes: List[Path]) -> Dict:
        """Prepare a batch of notes for processing."""
        batch_data = {
            'notes': [],
            'ready_for_claude': []
        }

        for note_path in notes[:self.batch_size]:
            try:
                content = note_path.read_text(encoding='utf-8')
                frontmatter, body = self.parse_frontmatter(content)

                if not frontmatter:
                    print(f"⚠️  No frontmatter: {note_path.name}")
                    continue

                file_hash = frontmatter.get('file_hash') or frontmatter.get('filename')
                if not file_hash:
                    print(f"⚠️  No file_hash: {note_path.name}")
                    continue

                pdf_path = self.find_pdf_for_hash(file_hash)
                if not pdf_path:
                    print(f"⚠️  PDF not found: {note_path.name} (hash: {file_hash})")
                    continue

                print(f"📄 Extracting: {note_path.name}")
                pdf_data = self.extract_pdf_data(pdf_path)

                if pdf_data:
                    note_info = {
                        'path': str(note_path),
                        'name': note_path.name,
                        'file_hash': file_hash,
                        'frontmatter': frontmatter,
                        'pdf_data': pdf_data,
                        'pdf_path': str(pdf_path)
                    }
                    batch_data['notes'].append(note_info)
                    batch_data['ready_for_claude'].append(self.format_for_claude(note_info))

            except Exception as e:
                print(f"❌ Error processing {note_path.name}: {e}")

        return batch_data

    def format_for_claude(self, note_info: Dict) -> str:
        """Format note data for Claude analysis."""
        pdf_data = note_info['pdf_data']
        text_preview = pdf_data.get('text', '')[:2500]
        links = pdf_data.get('links', [])[:10]
        metadata = pdf_data.get('metadata', {})

        return f"""
NOTE: {note_info['name']}
FILE HASH: {note_info['file_hash']}

PDF METADATA:
- Pages: {metadata.get('page_count', 'unknown')}
- Creation Date: {metadata.get('creation_date', 'unknown')}
- Title: {metadata.get('pdf_title', 'unknown')}

TEXT (first 2500 chars):
{text_preview}

LINKS ({len(pdf_data.get('links', []))} total):
{json.dumps(links, indent=2)}

---
"""

    def generate_batch_prompt(self, batch_data: Dict) -> str:
        """Generate prompt for Claude to process a batch."""
        prompt = f"""I need you to analyze {len(batch_data['notes'])} PDF documents and generate structured metadata for Obsidian notes.

For EACH document below, provide a JSON object with:
{{
  "file_hash": "the hash from the note info",
  "title": "Concise, descriptive title",
  "source_name": "Publication/organization",
  "source_url": "Primary URL if available",
  "source_date": "YYYY-MM-DD",
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

DOCUMENTS TO ANALYZE:
{''.join(batch_data['ready_for_claude'])}

Please provide ONLY the JSON array, no additional text."""

        return prompt

    def print_stats(self):
        """Print processing statistics."""
        print("\n" + "="*70)
        print("BATCH PROCESSING STATISTICS")
        print("="*70)
        print(f"  Completed: {len(self.progress['completed'])}")
        print(f"  Failed:    {len(self.progress['failed'])}")
        print(f"  Skipped:   {len(self.progress['skipped'])}")
        print(f"  Current Batch: {self.progress['current_batch']}")
        print("="*70 + "\n")

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Batch reprocess Obsidian notes')
    parser.add_argument('--vault', default='Lifegames', help='Vault path')
    parser.add_argument('--batch-size', type=int, default=10, help='Notes per batch')
    parser.add_argument('--prepare-only', action='store_true', help='Only prepare batches, dont process')
    parser.add_argument('--reset-progress', action='store_true', help='Reset progress tracking')
    args = parser.parse_args()

    processor = BatchReprocessor(args.vault, args.batch_size)

    if args.reset_progress:
        processor.progress_file.unlink(missing_ok=True)
        print("✅ Progress reset")
        return

    notes_to_process = processor.get_notes_to_process()
    print(f"📊 Found {len(notes_to_process)} notes to process")

    if args.prepare_only:
        print("\n🔍 Preparing next batch...")
        batch_data = processor.prepare_batch(notes_to_process)

        # Save batch data for review
        batch_file = Path(f"batch_{processor.progress['current_batch']}.json")
        batch_file.write_text(json.dumps(batch_data, indent=2))
        print(f"\n✅ Batch prepared: {batch_file}")
        print(f"   {len(batch_data['notes'])} notes ready for Claude analysis")

        # Generate Claude prompt
        prompt = processor.generate_batch_prompt(batch_data)
        prompt_file = Path(f"batch_{processor.progress['current_batch']}_prompt.txt")
        prompt_file.write_text(prompt)
        print(f"   Prompt saved: {prompt_file}")
        print(f"\n📋 Next: Send prompt to Claude, save response, then run update script")

    processor.print_stats()

if __name__ == '__main__':
    main()
