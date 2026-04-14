#!/usr/bin/env python3
"""
Automated batch reprocessing script.

This script automates the full workflow:
1. Prepares a batch of notes
2. Reads the prompt
3. Calls Claude API to generate metadata (requires API setup)
4. Applies updates to notes

NOTE: This is a template. The actual Claude API integration
would require anthropic Python SDK and API key setup.

For now, this script prepares batches and shows what would be automated.
"""

import os
import sys
import json
from pathlib import Path
from datetime import datetime
import subprocess

# Model version
CLAUDE_MODEL = "claude-sonnet-4.5-20250929"


class AutoBatchProcessor:
    def __init__(self, vault_path: str = "Lifegames", batch_size: int = 10):
        self.vault_path = Path(vault_path)
        self.batch_size = batch_size
        self.progress_file = Path("reprocessing_progress.json")

    def load_progress(self):
        """Load processing progress."""
        if self.progress_file.exists():
            return json.loads(self.progress_file.read_text())
        return {
            'completed': [],
            'failed': [],
            'skipped': [],
            'current_batch': 0,
            'started_at': datetime.now().isoformat()
        }

    def count_remaining_notes(self):
        """Count how many notes remain to be processed."""
        progress = self.load_progress()

        # Count all notes
        total_notes = 0
        vault = Path(self.vault_path)

        # Top-level notes
        for md_file in vault.glob("*.md"):
            total_notes += 1

        # Reviewed subfolder
        reviewed = vault / "Reviewed"
        if reviewed.exists():
            for md_file in reviewed.glob("*.md"):
                total_notes += 1

        completed = len(progress['completed'])
        remaining = total_notes - completed

        return remaining, completed, total_notes

    def run_batch_reprocess(self, batch_num: int):
        """Run batch_reprocess.py to prepare a batch."""
        try:
            result = subprocess.run(
                [sys.executable, 'src/batch_reprocess.py', '--prepare-only', '--batch-size', str(self.batch_size)],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                print(f"❌ Error preparing batch {batch_num}:")
                print(result.stderr)
                return False

            print(result.stdout)
            return True

        except Exception as e:
            print(f"❌ Exception preparing batch {batch_num}: {e}")
            return False

    def manual_process_batch(self, batch_num: int):
        """
        Placeholder for manual processing of a batch.

        In a fully automated version, this would:
        1. Read batch_{batch_num}_prompt.txt
        2. Call Claude API with the prompt
        3. Save response to batch_{batch_num}_response.json
        4. Apply updates using apply_batch_updates.py

        For now, this requires manual Claude interaction.
        """
        prompt_file = Path(f"batch_{batch_num}_prompt.txt")
        response_file = Path(f"batch_{batch_num}_response.json")

        if not prompt_file.exists():
            print(f"❌ Prompt file not found: {prompt_file}")
            return False

        print(f"\n{'='*70}")
        print(f"BATCH {batch_num} READY FOR MANUAL PROCESSING")
        print(f"{'='*70}")
        print(f"\n📝 Next steps:")
        print(f"   1. Read the prompt in: {prompt_file}")
        print(f"   2. Analyze the PDFs using Claude")
        print(f"   3. Save response to: {response_file}")
        print(f"   4. Run: python src/apply_batch_updates.py {batch_num} {response_file}")
        print(f"\n{'='*70}\n")

        return True

    def apply_batch_updates(self, batch_num: int):
        """Apply updates for a batch."""
        response_file = Path(f"batch_{batch_num}_response.json")

        if not response_file.exists():
            print(f"⚠️  Response file not found: {response_file}")
            print(f"   Batch {batch_num} needs manual Claude analysis first")
            return False

        try:
            result = subprocess.run(
                [sys.executable, 'src/apply_batch_updates.py', str(batch_num), str(response_file)],
                capture_output=True,
                text=True,
                timeout=300
            )

            if result.returncode != 0:
                print(f"❌ Error applying batch {batch_num}:")
                print(result.stderr)
                return False

            print(result.stdout)
            return True

        except Exception as e:
            print(f"❌ Exception applying batch {batch_num}: {e}")
            return False

    def run_auto_batch_workflow(self, num_batches: int = None):
        """
        Run automated batch workflow.

        If num_batches is None, process all remaining notes.
        Otherwise, process specified number of batches.
        """
        remaining, completed, total = self.count_remaining_notes()

        print(f"\n{'='*70}")
        print(f"AUTOMATED BATCH REPROCESSING")
        print(f"{'='*70}")
        print(f"  Total notes: {total}")
        print(f"  Completed: {completed}")
        print(f"  Remaining: {remaining}")

        if num_batches is None:
            num_batches = (remaining + self.batch_size - 1) // self.batch_size

        print(f"  Batches to process: {num_batches}")
        print(f"{'='*70}\n")

        progress = self.load_progress()
        start_batch = progress['current_batch']

        for i in range(num_batches):
            batch_num = start_batch + i

            print(f"\n{'='*70}")
            print(f"PROCESSING BATCH {batch_num}")
            print(f"{'='*70}\n")

            # Step 1: Prepare batch
            print(f"📦 Preparing batch {batch_num}...")
            if not self.run_batch_reprocess(batch_num):
                print(f"❌ Failed to prepare batch {batch_num}")
                break

            # Step 2: Check if response exists (already analyzed)
            response_file = Path(f"batch_{batch_num}_response.json")
            if response_file.exists():
                print(f"✅ Response file exists: {response_file}")

                # Step 3: Apply updates
                print(f"\n📝 Applying updates for batch {batch_num}...")
                if not self.apply_batch_updates(batch_num):
                    print(f"❌ Failed to apply batch {batch_num}")
                    break

                print(f"✅ Batch {batch_num} complete!\n")
            else:
                # Manual processing required
                print(f"\n⚠️  Batch {batch_num} requires manual Claude analysis")
                self.manual_process_batch(batch_num)
                print(f"\n⏸️  Pausing automation. Resume after completing batch {batch_num}")
                break

        # Final stats
        remaining, completed, total = self.count_remaining_notes()
        print(f"\n{'='*70}")
        print(f"PROGRESS UPDATE")
        print(f"{'='*70}")
        print(f"  Total notes: {total}")
        print(f"  Completed: {completed}")
        print(f"  Remaining: {remaining}")
        print(f"{'='*70}\n")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Automated batch reprocessing')
    parser.add_argument('--vault', default='Lifegames', help='Vault path')
    parser.add_argument('--batch-size', type=int, default=10, help='Notes per batch')
    parser.add_argument('--num-batches', type=int, help='Number of batches to process (default: all)')
    parser.add_argument('--stats-only', action='store_true', help='Just show stats')
    args = parser.parse_args()

    processor = AutoBatchProcessor(args.vault, args.batch_size)

    if args.stats_only:
        remaining, completed, total = processor.count_remaining_notes()
        print(f"\nREPROCESSING STATISTICS")
        print(f"{'='*70}")
        print(f"  Total notes: {total}")
        print(f"  Completed: {completed}")
        print(f"  Remaining: {remaining}")
        print(f"  Progress: {completed/total*100:.1f}%")
        print(f"{'='*70}\n")
    else:
        processor.run_auto_batch_workflow(args.num_batches)


if __name__ == '__main__':
    main()
