#!/usr/bin/env python3
"""
Apply Claude's analysis results to notes in batch.

This script takes Claude's JSON responses and updates the corresponding notes
while preserving user content and creating backups.
"""

import os
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional
import re

# Model version - MUST match batch_reprocess.py
CLAUDE_MODEL = "claude-sonnet-4.5-20250929"

class BatchUpdater:
    def __init__(self, vault_path: str = "Lifegames", backup_dir: str = "backups"):
        self.vault_path = Path(vault_path)
        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(exist_ok=True)
        self.progress_file = Path("reprocessing_progress.json")

    def load_progress(self) -> Dict:
        """Load processing progress."""
        if self.progress_file.exists():
            return json.loads(self.progress_file.read_text())
        return {'completed': [], 'failed': [], 'skipped': [], 'current_batch': 0}

    def save_progress(self, progress: Dict):
        """Save processing progress."""
        progress['updated_at'] = datetime.now().isoformat()
        self.progress_file.write_text(json.dumps(progress, indent=2))

    def extract_user_content(self, body: str) -> Dict[str, str]:
        """Extract user-added content sections."""
        sections = {}

        # Extract Linked Concepts
        linked_match = re.search(
            r'## Linked Concepts\s*\n(.*?)(?=\n## |$)',
            body,
            re.DOTALL
        )
        if linked_match:
            content = linked_match.group(1).strip()
            if content and '<!-- For manual wiki-linking' not in content:
                sections['linked_concepts'] = content

        # Extract Notes
        notes_match = re.search(
            r'## Notes\s*\n(.*?)(?=\n## |$)',
            body,
            re.DOTALL
        )
        if notes_match:
            content = notes_match.group(1).strip()
            if content and '<!-- For personal annotations' not in content:
                sections['notes'] = content

        return sections

    def generate_markdown(self, metadata: Dict, user_content: Dict, file_hash: str, pdf_path: str) -> str:
        """Generate complete markdown note from metadata."""

        # Format authors
        authors_yaml = '\n'.join(f"  - {author}" for author in metadata.get('authors', ['Unknown']))

        # Format tags
        tags_str = json.dumps(metadata.get('tags', []))

        # Build frontmatter
        frontmatter = f"""---
title: "{metadata.get('title', 'Unknown')}"
source: "{metadata.get('source_name', 'Unknown')}"
source_url: "{metadata.get('source_url', '')}"
date: {metadata.get('source_date', '')}
authors:
{authors_yaml}
tags: {tags_str}
filename: "{file_hash}"
cssclass: article-note
file_hash: "{file_hash}"
generated_by: "claude-code"
generated_model: "{CLAUDE_MODEL}"
generated_at: "{datetime.now().strftime('%Y-%m-%d')}"
---"""

        # Build body
        title = metadata.get('title', 'Unknown')
        source_name = metadata.get('source_name', 'Unknown')
        source_url = metadata.get('source_url', '')
        source_date = metadata.get('source_date', '')
        authors = metadata.get('authors', ['Unknown'])
        authors_str = ', '.join(authors)

        # Build source link
        if source_url:
            source_link = f"[{source_name}]({source_url})"
        else:
            source_link = source_name

        body = f"""
# {title}

> [!info]+ Article Information
> - **Source**: {source_link}
> - **Date**: {source_date}
> - **Authors**: {authors_str}

## Summary

{metadata.get('summary', '')}

## Key Points

"""

        # Add key points
        for point in metadata.get('key_points', []):
            body += f"- {point}\n"

        # Add user content sections
        body += "\n## Linked Concepts\n\n"
        if 'linked_concepts' in user_content:
            body += user_content['linked_concepts'] + "\n"
        else:
            body += "<!-- For manual wiki-linking later -->\n"

        body += "\n## Notes\n\n"
        if 'notes' in user_content:
            body += user_content['notes'] + "\n"
        else:
            body += "<!-- For personal annotations -->\n"

        # Add attachments
        body += f"""
## Attachments

- PDF: ![[{file_hash}.pdf]]
"""

        # Add JSON if it exists
        json_path = Path(pdf_path).parent / f"{file_hash}.json"
        if json_path.exists():
            body += f"- JSON: ![[{file_hash}.json]]\n"

        # Add PNG if it exists
        png_path = Path(pdf_path).parent / f"{file_hash}.png"
        if png_path.exists():
            body += f"- PNG: ![[{file_hash}.png]]\n"

        # Add external links if provided
        author_urls = metadata.get('author_urls', {})
        if author_urls:
            body += "\n## External Links\n\n"
            for name, url in author_urls.items():
                body += f"- [{name}]({url})\n"

        return frontmatter + body

    def update_note(self, note_path: Path, metadata: Dict, batch_data: Dict) -> bool:
        """Update a single note with new metadata."""
        try:
            # Backup original
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = self.backup_dir / f"{note_path.stem}_{timestamp}.md"
            shutil.copy2(note_path, backup_path)

            # Read original
            content = note_path.read_text(encoding='utf-8')

            # Parse frontmatter
            match = re.match(r'^---\n(.*?)\n---\n(.*)$', content, re.DOTALL)
            if match:
                body = match.group(2)
            else:
                body = content

            # Extract user content
            user_content = self.extract_user_content(body)

            # Find corresponding batch info
            file_hash = metadata['file_hash']
            note_info = next((n for n in batch_data['notes'] if n['file_hash'] == file_hash), None)

            if not note_info:
                print(f"⚠️  Could not find batch data for {file_hash}")
                return False

            # Generate new markdown
            new_content = self.generate_markdown(
                metadata,
                user_content,
                file_hash,
                note_info['pdf_path']
            )

            # Write updated note
            note_path.write_text(new_content, encoding='utf-8')

            print(f"✅ Updated: {note_path.name}")
            if user_content:
                print(f"   💾 Preserved: {', '.join(user_content.keys())}")

            return True

        except Exception as e:
            print(f"❌ Error updating {note_path.name}: {e}")
            return False

    def apply_batch(self, batch_num: int, claude_response: List[Dict]):
        """Apply Claude's responses to a batch of notes."""
        # Load batch data
        batch_file = Path(f"batch_{batch_num}.json")
        if not batch_file.exists():
            print(f"❌ Batch file not found: {batch_file}")
            return

        batch_data = json.loads(batch_file.read_text())

        # Load progress
        progress = self.load_progress()

        print(f"\n{'='*70}")
        print(f"APPLYING BATCH {batch_num}")
        print(f"{'='*70}")

        updated = 0
        failed = 0

        for metadata in claude_response:
            file_hash = metadata.get('file_hash')

            # Find corresponding note
            note_info = next((n for n in batch_data['notes'] if n['file_hash'] == file_hash), None)

            if not note_info:
                print(f"⚠️  No note found for hash: {file_hash}")
                continue

            note_path = Path(note_info['path'])

            if self.update_note(note_path, metadata, batch_data):
                updated += 1
                progress['completed'].append(note_path.name)
            else:
                failed += 1
                progress['failed'].append(note_path.name)

        # Increment batch counter
        progress['current_batch'] = batch_num + 1

        # Save progress
        self.save_progress(progress)

        print(f"\n{'='*70}")
        print(f"BATCH {batch_num} COMPLETE")
        print(f"  Updated: {updated}")
        print(f"  Failed:  {failed}")
        print(f"{'='*70}\n")

def main():
    import argparse

    parser = argparse.ArgumentParser(description='Apply Claude batch updates')
    parser.add_argument('batch_num', type=int, help='Batch number')
    parser.add_argument('response_file', help='JSON file with Claude responses')
    parser.add_argument('--vault', default='Lifegames', help='Vault path')
    args = parser.parse_args()

    updater = BatchUpdater(args.vault)

    # Load Claude's response
    response_path = Path(args.response_file)
    if not response_path.exists():
        print(f"❌ Response file not found: {response_path}")
        sys.exit(1)

    try:
        claude_response = json.loads(response_path.read_text())
    except Exception as e:
        print(f"❌ Error parsing response file: {e}")
        sys.exit(1)

    updater.apply_batch(args.batch_num, claude_response)

if __name__ == '__main__':
    main()
