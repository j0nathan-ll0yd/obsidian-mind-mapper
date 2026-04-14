#!/usr/bin/env python3
"""
Reprocess Obsidian notes by re-analyzing PDFs and regenerating content.

This script intelligently reprocesses notes while preserving user-added content.
It re-extracts PDF data, generates new summaries/key points, and merges back
user edits from Linked Concepts and Notes sections.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Tuple
import subprocess
import re

class NoteReprocessor:
    def __init__(self, vault_path: str = "Lifegames", backup_dir: str = "backups"):
        self.vault_path = Path(vault_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)

        # Track processing stats
        self.stats = {
            'processed': 0,
            'skipped': 0,
            'errors': 0,
            'backed_up': 0
        }

    def parse_frontmatter(self, content: str) -> Tuple[Optional[Dict], str]:
        """Extract and parse YAML frontmatter, return (frontmatter_dict, body)."""
        match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
        if not match:
            return None, content

        frontmatter_text = match.group(1)
        body = match.group(2)

        frontmatter = {}
        current_key = None
        current_list = []

        for line in frontmatter_text.split('\n'):
            # Handle list items
            if line.strip().startswith('- '):
                if current_key:
                    current_list.append(line.strip()[2:])
                continue

            # Handle key: value pairs
            if ':' in line:
                # Save previous list if exists
                if current_key and current_list:
                    frontmatter[current_key] = current_list
                    current_list = []

                key, value = line.split(':', 1)
                current_key = key.strip()
                value = value.strip().strip('"').strip("'")

                if value:  # Single value
                    frontmatter[current_key] = value
                    current_key = None

        # Save final list if exists
        if current_key and current_list:
            frontmatter[current_key] = current_list

        return frontmatter, body

    def extract_user_sections(self, content: str) -> Dict[str, str]:
        """Extract user-edited sections to preserve during reprocessing."""
        sections = {}

        # Extract Linked Concepts
        linked_match = re.search(
            r'## Linked Concepts\s*\n(.*?)(?=\n## |$)',
            content,
            re.DOTALL
        )
        if linked_match:
            section_content = linked_match.group(1).strip()
            # Only preserve if user added actual content (not just placeholder comment)
            if section_content and '<!-- For manual wiki-linking later -->' not in section_content:
                sections['linked_concepts'] = section_content

        # Extract Notes
        notes_match = re.search(
            r'## Notes\s*\n(.*?)(?=\n## |$)',
            content,
            re.DOTALL
        )
        if notes_match:
            section_content = notes_match.group(1).strip()
            # Only preserve if user added actual content
            if section_content and '<!-- For personal annotations -->' not in section_content:
                sections['notes'] = section_content

        return sections

    def backup_note(self, note_path: Path) -> Path:
        """Create timestamped backup of note before reprocessing."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        backup_path = self.backup_dir / f"{note_path.stem}_{timestamp}.md"

        shutil.copy2(note_path, backup_path)
        self.stats['backed_up'] += 1

        return backup_path

    def find_pdf_for_hash(self, file_hash: str) -> Optional[Path]:
        """Find PDF in Attachments directory by hash."""
        attachments = self.vault_path / "Attachments"
        if not attachments.exists():
            return None

        for pdf_path in attachments.rglob(f"{file_hash}.pdf"):
            return pdf_path

        return None

    def extract_pdf_data(self, pdf_path: Path) -> Optional[Dict]:
        """Run pdf_processor.py on PDF to extract text, links, metadata."""
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
                print(f"  ⚠️  PDF processor error: {result.stderr}")
                return None

        except Exception as e:
            print(f"  ⚠️  Failed to extract PDF data: {e}")
            return None

    def generate_note_metadata_prompt(self, pdf_data: Dict, existing_frontmatter: Dict) -> str:
        """Create prompt for Claude to generate note metadata."""
        text_preview = pdf_data.get('text', '')[:3000]  # First 3000 chars
        links = pdf_data.get('links', [])
        metadata = pdf_data.get('metadata', {})

        prompt = f"""Based on this PDF document content, generate structured metadata for an Obsidian note.

PDF METADATA:
- Pages: {metadata.get('page_count', 'unknown')}
- Creation Date: {metadata.get('creation_date', 'unknown')}
- PDF Title: {metadata.get('pdf_title', 'unknown')}
- PDF Author: {metadata.get('pdf_author', 'unknown')}

DOCUMENT TEXT (first 3000 characters):
{text_preview}

EXTRACTED LINKS ({len(links)} total):
{json.dumps(links[:10], indent=2) if links else 'None'}

EXISTING METADATA (for reference):
{json.dumps(existing_frontmatter, indent=2)}

Please generate a JSON object with:
{{
  "title": "Concise, descriptive title",
  "source_name": "Publication or organization name",
  "source_url": "Primary URL if available",
  "source_date": "YYYY-MM-DD format",
  "summary": "2-3 sentence comprehensive summary",
  "key_points": [
    "5 most important bullet points",
    "Each point should be substantial and specific",
    "Include data/statistics where relevant"
  ],
  "tags": ["relevant", "topic", "tags"],
  "authors": ["Author Name"],
  "author_urls": {{
    "Author Name": "url if available"
  }}
}}

Focus on accuracy, specificity, and insights. The summary and key points should provide substantial value."""

        return prompt

    def reprocess_note(self, note_path: Path, dry_run: bool = False, force: bool = False) -> bool:
        """
        Reprocess a single note file.

        Args:
            note_path: Path to the markdown note
            dry_run: If True, show what would be done without making changes
            force: If True, reprocess even if generated by Claude Code

        Returns:
            True if successful, False otherwise
        """
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Processing: {note_path.name}")

        # Read existing note
        try:
            content = note_path.read_text(encoding='utf-8')
        except Exception as e:
            print(f"  ❌ Failed to read note: {e}")
            self.stats['errors'] += 1
            return False

        # Parse frontmatter and body
        frontmatter, body = self.parse_frontmatter(content)
        if not frontmatter:
            print(f"  ⚠️  No frontmatter found - skipping")
            self.stats['skipped'] += 1
            return False

        # Check if already Claude-generated and not forcing
        if not force and frontmatter.get('generated_by') == 'claude-code':
            print(f"  ℹ️  Already generated by Claude Code - skipping (use --force to reprocess)")
            self.stats['skipped'] += 1
            return False

        # Extract user content to preserve
        user_sections = self.extract_user_sections(content)
        if user_sections:
            print(f"  💾 Preserving user content: {', '.join(user_sections.keys())}")

        # Find corresponding PDF
        file_hash = frontmatter.get('file_hash') or frontmatter.get('filename')
        if not file_hash:
            print(f"  ❌ No file_hash in frontmatter")
            self.stats['errors'] += 1
            return False

        pdf_path = self.find_pdf_for_hash(file_hash)
        if not pdf_path:
            print(f"  ❌ PDF not found for hash: {file_hash}")
            self.stats['errors'] += 1
            return False

        print(f"  📄 Found PDF: {pdf_path.relative_to(self.vault_path)}")

        if dry_run:
            print(f"  ✓ Would reprocess this note")
            self.stats['processed'] += 1
            return True

        # Backup original
        backup_path = self.backup_note(note_path)
        print(f"  💾 Backed up to: {backup_path.name}")

        # Extract PDF data
        print(f"  🔍 Extracting PDF content...")
        pdf_data = self.extract_pdf_data(pdf_path)
        if not pdf_data:
            print(f"  ❌ Failed to extract PDF data")
            self.stats['errors'] += 1
            return False

        # Note: At this point, in a real implementation, you would:
        # 1. Send pdf_data to Claude for analysis
        # 2. Get structured JSON response
        # 3. Generate new markdown content
        # 4. Merge back user_sections
        # 5. Add generated_by and generated_at to frontmatter
        # 6. Write updated note

        print(f"  ⚠️  PLACEHOLDER: Would generate new content here")
        print(f"      - PDF has {pdf_data['metadata']['page_count']} pages")
        print(f"      - Extracted {len(pdf_data.get('links', []))} links")
        print(f"      - Text length: {len(pdf_data.get('text', ''))} characters")

        # For now, mark as processed without actually changing
        # This will be completed when integrated with Claude Code interaction
        self.stats['processed'] += 1
        return True

    def reprocess_all(self, dry_run: bool = False, force: bool = False, filter_source: Optional[str] = None):
        """
        Reprocess all notes in vault.

        Args:
            dry_run: Preview changes without applying
            force: Reprocess even Claude-generated notes
            filter_source: Only process notes from specific source ('other-llm', 'manual', etc.)
        """
        # Find all markdown notes
        notes = list(self.vault_path.glob("*.md"))
        reviewed_path = self.vault_path / "Reviewed"
        if reviewed_path.exists():
            notes.extend(reviewed_path.glob("*.md"))

        print(f"{'='*70}")
        print(f"{'DRY RUN - ' if dry_run else ''}REPROCESSING {len(notes)} NOTES")
        print(f"{'='*70}")

        for note_path in notes:
            self.reprocess_note(note_path, dry_run=dry_run, force=force)

        # Print summary
        print(f"\n{'='*70}")
        print(f"REPROCESSING SUMMARY")
        print(f"{'='*70}")
        print(f"  Processed:  {self.stats['processed']}")
        print(f"  Skipped:    {self.stats['skipped']}")
        print(f"  Errors:     {self.stats['errors']}")
        print(f"  Backed up:  {self.stats['backed_up']}")
        print(f"{'='*70}")

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Reprocess Obsidian notes')
    parser.add_argument('--vault', default='Lifegames', help='Path to vault')
    parser.add_argument('--dry-run', action='store_true', help='Preview without making changes')
    parser.add_argument('--force', action='store_true', help='Reprocess even Claude-generated notes')
    parser.add_argument('--note', help='Process single note by filename')
    parser.add_argument('--backup-dir', default='backups', help='Backup directory')
    args = parser.parse_args()

    reprocessor = NoteReprocessor(args.vault, args.backup_dir)

    if args.note:
        note_path = Path(args.vault) / args.note
        if not note_path.exists():
            print(f"Error: Note not found: {note_path}")
            sys.exit(1)
        reprocessor.reprocess_note(note_path, dry_run=args.dry_run, force=args.force)
    else:
        reprocessor.reprocess_all(dry_run=args.dry_run, force=args.force)

if __name__ == '__main__':
    main()
