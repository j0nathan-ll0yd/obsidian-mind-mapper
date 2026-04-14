#!/usr/bin/env python3
"""
Tag Taxonomy Designer

Based on tag analysis, proposes:
- Capitalization standardization (Title-Case-With-Hyphens)
- Tag consolidation mappings
- Tag renaming for consistency

Part of Phase 3a: Tag Taxonomy Optimization (Normalization Only)
"""

import json
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Set, Tuple
import re

class TaxonomyDesigner:
    def __init__(self, analysis_file: Path):
        """Load tag analysis data."""
        with open(analysis_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        self.report = data
        self.tag_counts = {tag: count for tag, count in self.report['top_tags']}

        # Add rare tags to counts
        for tag, count in self.report.get('rare_tags', []):
            self.tag_counts[tag] = count

    def standardize_capitalization(self) -> Dict[str, str]:
        """
        Create mappings for capitalization standardization.

        Convention: Title-Case-With-Hyphens
        - Each word starts with capital letter
        - Words separated by hyphens
        - Exceptions: AI, LLM, CEO, etc. (all caps acronyms)
        """
        mappings = {}
        inconsistencies = self.report.get('naming_inconsistencies', {})

        # Known acronyms that should stay uppercase
        ACRONYMS = {
            'ai', 'llm', 'api', 'ui', 'ux', 'ceo', 'cto', 'hr',
            'sf', 'us', 'uk', 'eu', 'nyc', 'la', 'lgbtq', 'rto',
            'wfh', 'rtl', 'owasp', 'gdpr', 'hipaa', 'jama', 'fda',
            'rfc', 'ietf', 'bgp', 'css', 'html', 'js', 'ts', 'gpu'
        }

        for normalized, variants in inconsistencies.items():
            # Find the canonical form (most used variant)
            canonical = max(variants, key=lambda v: self.tag_counts.get(v, 0))

            # Convert to Title-Case-With-Hyphens
            parts = canonical.replace('_', '-').split('-')
            title_parts = []

            for part in parts:
                if part.lower() in ACRONYMS:
                    title_parts.append(part.upper())
                else:
                    title_parts.append(part.capitalize())

            standardized = '-'.join(title_parts)

            # Map all variants to standardized form
            for variant in variants:
                if variant != standardized:
                    mappings[variant] = standardized

        return mappings

    def identify_consolidations(self, min_similarity: float = 0.8) -> Dict[str, str]:
        """
        Identify tags that should be consolidated.

        Returns mapping of old_tag -> new_tag for consolidation.
        """
        mappings = {}
        similar_pairs = self.report.get('similar_tags', [])

        for tag1, tag2, similarity in similar_pairs:
            if similarity >= min_similarity:
                # Skip if one is just a capitalization variant (handled elsewhere)
                if tag1.lower() == tag2.lower():
                    continue

                # Use the more frequently used tag as canonical
                count1 = self.tag_counts.get(tag1, 0)
                count2 = self.tag_counts.get(tag2, 0)

                if count1 > count2:
                    mappings[tag2] = tag1
                else:
                    mappings[tag1] = tag2

        return mappings

    def generate_taxonomy(self) -> Dict:
        """Generate complete taxonomy with normalization mappings."""
        print("🏗️  Designing tag taxonomy...")

        taxonomy = {
            'metadata': {
                'version': '1.0',
                'created_from_analysis': str(Path('tag_analysis.json')),
                'total_unique_tags_before': len(self.tag_counts),
                'total_usages_before': sum(self.tag_counts.values())
            },
            'capitalization_mappings': self.standardize_capitalization(),
            'consolidation_mappings': self.identify_consolidations()
        }

        # Calculate impact
        cap_mappings = taxonomy['capitalization_mappings']
        cons_mappings = taxonomy['consolidation_mappings']

        taxonomy['metadata']['capitalization_fixes'] = len(cap_mappings)
        taxonomy['metadata']['consolidations'] = len(cons_mappings)

        # Estimate new unique tag count
        all_mappings = {**cap_mappings, **cons_mappings}
        unique_after = len(set(
            all_mappings.get(tag, tag) for tag in self.tag_counts.keys()
        ))
        taxonomy['metadata']['estimated_unique_tags_after'] = unique_after
        taxonomy['metadata']['estimated_reduction'] = (
            taxonomy['metadata']['total_unique_tags_before'] - unique_after
        )

        print("   ✅ Taxonomy designed\n")
        return taxonomy

    def print_taxonomy(self, taxonomy: Dict):
        """Print human-readable taxonomy design."""
        print("\n" + "="*80)
        print("TAG TAXONOMY DESIGN")
        print("="*80)

        meta = taxonomy['metadata']
        print(f"\n📊 IMPACT SUMMARY")
        print(f"   Unique tags before: {meta['total_unique_tags_before']}")
        print(f"   Estimated unique tags after: {meta['estimated_unique_tags_after']}")
        print(f"   Estimated reduction: {meta['estimated_reduction']} tags ({meta['estimated_reduction']/meta['total_unique_tags_before']*100:.1f}%)")
        print(f"   Total tag usages: {meta['total_usages_before']} (unchanged)")

        print(f"\n🔧 CHANGES")
        print(f"   Capitalization fixes: {meta['capitalization_fixes']}")
        print(f"   Consolidations: {meta['consolidations']}")

        # Capitalization mappings
        cap_maps = taxonomy['capitalization_mappings']
        if cap_maps:
            print(f"\n📝 CAPITALIZATION STANDARDIZATION ({len(cap_maps)} mappings)")
            print(f"   Showing first 30:")
            for i, (old, new) in enumerate(list(cap_maps.items())[:30]):
                print(f"   {old} → {new}")

        # Consolidation mappings
        cons_maps = taxonomy['consolidation_mappings']
        if cons_maps:
            print(f"\n🔄 TAG CONSOLIDATIONS ({len(cons_maps)} mappings)")
            for old, new in list(cons_maps.items())[:20]:
                old_count = self.tag_counts.get(old, 0)
                new_count = self.tag_counts.get(new, 0)
                print(f"   {old} ({old_count}) → {new} ({new_count})")

        print("\n" + "="*80 + "\n")


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description='Design tag taxonomy from analysis'
    )
    parser.add_argument(
        '--analysis-file',
        type=Path,
        default=Path('tag_analysis.json'),
        help='Tag analysis JSON file (default: tag_analysis.json)'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('tag_taxonomy.json'),
        help='Output taxonomy JSON file (default: tag_taxonomy.json)'
    )

    args = parser.parse_args()

    if not args.analysis_file.exists():
        print(f"❌ Error: Analysis file not found: {args.analysis_file}")
        print(f"   Run 'python src/analyze_tags.py --json-output tag_analysis.json' first")
        return 1

    # Design taxonomy
    designer = TaxonomyDesigner(args.analysis_file)
    taxonomy = designer.generate_taxonomy()

    # Print summary
    designer.print_taxonomy(taxonomy)

    # Save taxonomy
    with open(args.output, 'w', encoding='utf-8') as f:
        json.dump(taxonomy, f, indent=2, ensure_ascii=False)

    print(f"💾 Taxonomy saved to: {args.output}")
    print(f"\nNext step: Review the taxonomy and adjust as needed.")
    print(f"Then run: python src/migrate_tags.py --taxonomy {args.output}")

    return 0


if __name__ == '__main__':
    exit(main())
