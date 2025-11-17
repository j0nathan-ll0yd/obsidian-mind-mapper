#!/usr/bin/env python3
"""
PDF Processing Utility for Obsidian Mind Mapper

Extracts text, links, and metadata from PDF files (FireShot captures or standalone PDFs)
Outputs structured JSON for Claude Code to analyze and process.

Usage:
    python src/pdf_processor.py <path/to/file.pdf>

Output (JSON):
    {
        "text": "Full text content of the PDF",
        "links": [
            {
                "url": "https://example.com",
                "context": "Link anchor text or surrounding text",
                "page": 1
            }
        ],
        "metadata": {
            "page_count": 5,
            "creation_date": "2025-01-15",
            "file_size_bytes": 1024000
        }
    }
"""

import sys
import json
import os
from pathlib import Path
from datetime import datetime

try:
    import fitz  # PyMuPDF
except ImportError:
    print(json.dumps({
        "error": "PyMuPDF not installed. Run: pip install -r requirements.txt"
    }), file=sys.stderr)
    sys.exit(1)


# Domains to skip when extracting links
SKIP_DOMAINS = [
    "getfireshot.com",
    "youtube.com",
    "youtu.be"
]


def should_skip_link(url: str) -> bool:
    """Check if a URL should be skipped based on domain filters."""
    url_lower = url.lower()
    return any(domain in url_lower for domain in SKIP_DOMAINS)


def extract_pdf_data(pdf_path: str) -> dict:
    """
    Extract text, links, and metadata from a PDF file.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Dictionary with text, links, and metadata
    """
    if not os.path.exists(pdf_path):
        return {
            "error": f"File not found: {pdf_path}"
        }

    if not os.path.isfile(pdf_path):
        return {
            "error": f"Not a file: {pdf_path}"
        }

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        return {
            "error": f"Failed to open PDF: {str(e)}"
        }

    # Extract full text
    full_text = ""
    for page in doc:
        full_text += page.get_text()

    # Extract links with context
    links = []
    seen_urls = set()  # Avoid duplicates

    for page_num, page in enumerate(doc, start=1):
        page_links = page.get_links()

        for link in page_links:
            # Only process URI links (not internal PDF links)
            if "uri" not in link:
                continue

            url = link["uri"]

            # Skip filtered domains
            if should_skip_link(url):
                continue

            # Skip duplicates
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # Get the rectangle for this link
            rect = fitz.Rect(link["from"])

            # Expand rectangle to capture surrounding text
            expanded_rect = fitz.Rect(
                rect.x0 - 5,  # left
                rect.y0 - 5,  # top
                rect.x1 + 5,  # right
                rect.y1 + 5   # bottom
            )

            # Extract text from the link area
            context = page.get_text("text", clip=expanded_rect).strip()

            # If no text found, try a larger area
            if not context:
                larger_rect = fitz.Rect(
                    rect.x0 - 20,
                    rect.y0 - 20,
                    rect.x1 + 20,
                    rect.y1 + 20
                )
                context = page.get_text("text", clip=larger_rect).strip()

            # If still no text, use first 100 chars of page text
            if not context:
                page_text = page.get_text().strip()
                context = page_text[:100] + "..." if len(page_text) > 100 else page_text

            links.append({
                "url": url,
                "context": context,
                "page": page_num
            })

    # Extract metadata
    metadata = {
        "page_count": len(doc),
        "file_size_bytes": os.path.getsize(pdf_path)
    }

    # Try to get creation date from PDF metadata
    pdf_metadata = doc.metadata
    if pdf_metadata and "creationDate" in pdf_metadata:
        try:
            # PyMuPDF date format: D:YYYYMMDDHHmmSSOHH'mm'
            date_str = pdf_metadata["creationDate"]
            if date_str.startswith("D:"):
                date_str = date_str[2:10]  # Extract YYYYMMDD
                creation_date = datetime.strptime(date_str, "%Y%m%d").strftime("%Y-%m-%d")
                metadata["creation_date"] = creation_date
        except:
            pass  # If parsing fails, just skip the date

    # Add PDF metadata if available
    if pdf_metadata:
        if "title" in pdf_metadata and pdf_metadata["title"]:
            metadata["pdf_title"] = pdf_metadata["title"]
        if "author" in pdf_metadata and pdf_metadata["author"]:
            metadata["pdf_author"] = pdf_metadata["author"]

    doc.close()

    return {
        "text": full_text.strip(),
        "links": links,
        "metadata": metadata
    }


def main():
    """Main entry point for CLI usage."""
    if len(sys.argv) != 2:
        print(json.dumps({
            "error": "Usage: python src/pdf_processor.py <path/to/file.pdf>"
        }), file=sys.stderr)
        sys.exit(1)

    pdf_path = sys.argv[1]
    result = extract_pdf_data(pdf_path)

    # Output JSON to stdout
    print(json.dumps(result, indent=2, ensure_ascii=False))

    # Exit with error code if there was an error
    if "error" in result:
        sys.exit(1)


if __name__ == "__main__":
    main()
