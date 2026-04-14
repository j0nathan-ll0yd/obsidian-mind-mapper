#!/usr/bin/env python3
"""
process_evernote.py - Evernote → Obsidian Note Processor

Reads Evernote's local storage directly (no API needed) to convert notes
into structured Obsidian markdown with Claude-generated metadata.

Storage locations (all read-only):
  Content:   conduit-fs/.../rte/Note/internal_rteDoc/{pfx1}/{pfx2}/{guid}.dat
  Metadata:  conduit-fs/.../cosm/storage/note/*.fdt  (Lucene index)
  Resources: resource-cache/User{userId}/{noteGuid}/{resourceHash}
  Res meta:  resource-cache/User{userId}/{noteGuid}/{resourceHash}.meta

Commands:
    status              Show processing statistics
    prepare [size]      Prepare next batch for Claude (default: 10)
    apply N [file]      Apply Claude JSON response to create notes
"""

import asyncio
import base64
import json
import os
import re
import hashlib
import shutil
import sqlite3
import subprocess
from pathlib import Path
from datetime import datetime

# ─── Paths ────────────────────────────────────────────────────────────────────

REPO_ROOT = Path(__file__).parent.parent
LIFEGAMES_DIR = REPO_ROOT / "Lifegames"
ATTACHMENTS_DIR = LIFEGAMES_DIR / "Attachments"
PROGRESS_FILE = REPO_ROOT / "evernote_progress.json"

EVERNOTE_CONTAINER = (
    Path.home() / "Library/Containers/com.evernote.Evernote/Data"
)
EVERNOTE_SUPPORT = EVERNOTE_CONTAINER / "Library/Application Support/Evernote"
RESOURCE_CACHE = EVERNOTE_SUPPORT / "resource-cache"

# Model tracking
CLAUDE_MODEL = "claude-opus-4-6"

# MIME type → file extension mapping
MIME_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "application/pdf": ".pdf",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "video/mp4": ".mp4",
}

# CSS / structural patterns that indicate non-content strings
CSS_KEYWORDS = [
    "box-sizing", "webkit", "font-size", "font-family", "font-weight",
    "display:", "margin", "padding", "position:", "background", "border",
    "rgba(", "rgb(", "px;", "em;", "overflow", "text-rendering",
    "pointer-events", "min-width", "min-height", "flex", "justify-content",
    "opacity:", "transform", "transition", "letter-spacing", "line-height",
    "cursor:", "word-break", "white-space", "z-index", "align-items",
    "vertical-align", "outline:", "border-radius", "text-decoration",
    "max-width", "max-height", "object-fit", "box-shadow", "text-align",
    "list-style", "clip-rule", "fill-rule", "stroke-", "fill:",
    "inherit;", "-webkit-", "sans-serif", "optimizelegibility",
    "antialiased", "currentcolor", "nowrap", "ellipsis", "break-word",
]

STRUCTURAL_STRINGS = {
    "div(", "span(", "blockquote(", "a(", "p(", "h1(", "h2(", "h3(",
    "h4(", "h5(", "h6(", "li(", "ul(", "ol(", "table(", "tr(", "td(",
    "th(", "img(", "figure(", "figcaption(", "header(", "footer(",
    "nav(", "section(", "article(", "main(", "aside(", "en-media(",
    "en-note", "style", "href", "target", "type", "hash", "width",
    "height", "class", "content", "noopener", "nofollow",
    "_blank", "_blank(", "noopener ugc nofollow",
    "image/jpeg(", "image/png(",
    # SVG/canvas structural
    "shape", "rect(", "circle(", "path(", "g(", "svg(",
    # common single-word attribute values
    "inherit", "none", "block", "inline", "flex", "grid", "auto",
    "hidden", "visible", "relative", "absolute", "fixed", "sticky",
}

# ─── Evernote path detection ──────────────────────────────────────────────────


def get_conduit_user_path():
    """Auto-detect the conduit-fs user path."""
    conduit_base = EVERNOTE_SUPPORT / "conduit-fs"
    server_dir = conduit_base / "https%3A%2F%2Fwww.evernote.com"
    if not server_dir.exists():
        raise RuntimeError(f"Evernote conduit-fs not found at {server_dir}")
    users = [d for d in server_dir.iterdir() if d.is_dir()]
    if not users:
        raise RuntimeError("No Evernote user found in conduit-fs")
    return users[0]  # single account assumed


def get_user_id():
    """Auto-detect numeric Evernote user ID from resource-cache."""
    dirs = [d.name for d in RESOURCE_CACHE.iterdir() if d.name.startswith("User")]
    if not dirs:
        raise RuntimeError("No User* directory found in resource-cache")
    return dirs[0].replace("User", "")


# ─── Progress tracking ────────────────────────────────────────────────────────


def load_progress():
    if PROGRESS_FILE.exists():
        with open(PROGRESS_FILE) as f:
            return json.load(f)
    return {"processed": [], "failed": [], "current_batch": 0}


def save_progress(progress):
    progress["processed"] = list(dict.fromkeys(progress["processed"]))
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# ─── Note enumeration ─────────────────────────────────────────────────────────


def get_all_note_dat_files(conduit_user):
    """Return dict: guid → Path for all .dat files in rteDoc."""
    rte_doc = conduit_user / "rte" / "Note" / "internal_rteDoc"
    if not rte_doc.exists():
        return {}
    notes = {}
    for dat_file in rte_doc.rglob("*.dat"):
        guid = dat_file.stem  # filename without extension is the full GUID
        notes[guid] = dat_file
    return notes


# ─── Metadata index (from Lucene .fdt files) ─────────────────────────────────


def build_metadata_index(conduit_user):
    """
    Parse Lucene .fdt files to build {guid: {title, notebook, created, updated}}.

    Record structure in .fdt strings:
      [count] [notebook] [$notebook_guid] [created_ms] [updated_ms]
      [title_with_prefix_byte] [optional_author] [user_id] [$note_guid]
    """
    fdt_dir = conduit_user / "cosm" / "storage" / "note"
    metadata = {}

    uuid_re = re.compile(
        r"^\$([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})$"
    )
    ts_re = re.compile(r"^(\d{13})$")

    # Process in segment order so later segments overwrite earlier ones
    for fdt_file in sorted(fdt_dir.glob("*.fdt")):
        with open(fdt_file, "rb") as f:
            data = f.read()
        raw_strings = re.findall(b"[ -~]{4,}", data)
        items = [s.decode("latin-1").strip() for s in raw_strings]

        for i, item in enumerate(items):
            m = uuid_re.match(item)
            if not m:
                continue
            guid = m.group(1)

            # Find two consecutive 13-digit timestamps before this GUID
            timestamps = []
            ts_indices = []
            for k in range(max(0, i - 10), i):
                if ts_re.match(items[k]):
                    timestamps.append(int(items[k]))
                    ts_indices.append(k)

            if len(timestamps) < 2:
                continue

            created_ms = timestamps[-2]
            updated_ms = timestamps[-1]
            first_ts_idx = ts_indices[-2]

            # Notebook name is 2 positions before first timestamp
            notebook = None
            if first_ts_idx >= 2:
                nb_candidate = items[first_ts_idx - 2]
                # Notebook names don't contain $ or digits-only
                if not nb_candidate.startswith("$") and not nb_candidate.isdigit():
                    notebook = nb_candidate

            # Title is one position after the second timestamp
            second_ts_idx = ts_indices[-1]
            title = None
            if second_ts_idx + 1 < i:
                raw_title = items[second_ts_idx + 1]
                # Strip the leading length-prefix byte (single non-alpha char)
                if raw_title and len(raw_title) > 1:
                    first_char = raw_title[0]
                    if not first_char.isalpha() and first_char not in ('"', "'"):
                        title = raw_title[1:]
                    else:
                        title = raw_title

            if title and len(title) > 2:
                metadata[guid] = {
                    "title": title.strip(),
                    "notebook": notebook or "Personal",
                    "created": created_ms // 1000,
                    "updated": updated_ms // 1000,
                }

    return metadata


# ─── Content extraction from .dat files ──────────────────────────────────────


def extract_note_content(dat_path, guid=None):
    """
    Extract content from an Evernote Yjs .dat file.

    Uses pycrdt → sqlite → strings fallback chain.

    Returns dict with:
      type: 'web_clip' | 'regular'
      source_url: str | None
      source_title: str | None
      text: str (cleaned article text / markdown)
      links: list of URLs
      extraction_method: str
      enml_html: str | None (raw ENML for Playwright preview rendering)
    """
    # Method 1: pycrdt (highest fidelity — real ENML with CSS)
    if guid:
        pycrdt_result = _extract_via_pycrdt(guid, dat_path)
        if pycrdt_result:
            text = pycrdt_result["markdown"]
            source_url = pycrdt_result.get("source_url")
            enml_html = pycrdt_result.get("enml_html")

            # If pycrdt didn't find a source URL, try SQLite
            if not source_url:
                sqlite_result = _extract_via_sqlite(guid)
                if sqlite_result:
                    source_url = sqlite_result.get("source_url")

            links = list(dict.fromkeys(re.findall(r'https?://[^\s\)\]"\'<>]+', text)))

            return {
                "type": "web_clip" if source_url else "regular",
                "source_url": source_url,
                "source_title": None,
                "text": text,
                "links": links,
                "extraction_method": "pycrdt",
                "enml_html": enml_html,
            }

    # Method 2: SQLite fallback
    if guid:
        sqlite_result = _extract_via_sqlite(guid)
        if sqlite_result:
            text = sqlite_result["markdown"]
            source_url = sqlite_result.get("source_url")
            links = list(dict.fromkeys(re.findall(r'https?://[^\s\)\]"\'<>]+', text)))

            return {
                "type": "web_clip" if source_url else "regular",
                "source_url": source_url,
                "source_title": None,
                "text": text,
                "links": links,
                "extraction_method": "sqlite",
                "enml_html": None,
            }

    # Method 3: strings command (legacy fallback)
    try:
        result = subprocess.run(
            ["strings", str(dat_path)],
            capture_output=True, text=True, timeout=30
        )
        lines = result.stdout.splitlines()
    except Exception:
        return {
            "type": "regular", "source_url": None, "source_title": None,
            "text": "", "links": [], "extraction_method": "strings", "enml_html": None,
        }

    source_url = None
    source_title = None
    links = []

    url_re = re.compile(r"https?://[^\s\"'<>)(]+")

    for line in lines:
        if "--en-clipped-source-url:" in line:
            m = re.search(r"--en-clipped-source-url:([^;\"]+)", line)
            if m:
                source_url = m.group(1).strip()
        if "--en-clipped-source-title:" in line:
            m = re.search(r"--en-clipped-source-title:([^;\"]+)", line)
            if m:
                source_title = m.group(1).strip()

        for url in url_re.findall(line):
            url = url.rstrip("()")
            if url not in links:
                links.append(url)

    note_type = "web_clip" if source_url else "regular"
    text = _clean_content_lines(lines)

    return {
        "type": note_type,
        "source_url": source_url,
        "source_title": source_title,
        "text": text,
        "links": links,
        "extraction_method": "strings",
        "enml_html": None,
    }


def _clean_content_lines(lines):
    """Filter strings output to extract human-readable text only."""
    content = []
    for line in lines:
        line = line.strip()
        if len(line) < 5:
            continue
        if line in STRUCTURAL_STRINGS:
            continue
        if any(kw in line for kw in CSS_KEYWORDS):
            continue
        # Skip lines that are mostly non-alpha characters
        alpha_ratio = sum(1 for c in line if c.isalpha()) / max(len(line), 1)
        if alpha_ratio < 0.35:
            continue
        # Skip lines starting with known Yjs/binary-artifact prefixes
        # These are Yjs length-prefixed strings: w + 1-2 control chars + content
        if re.match(r"^w[^a-zA-Z\s]{1,2}", line):
            continue
        # Skip bare URLs
        if re.match(r"^https?://", line):
            continue
        # Skip attribute-name-only lines
        if re.match(r"^(style|href|type|hash|class|target|content|width|height)$", line):
            continue
        # Skip en-clipped metadata lines (already extracted)
        if "--en-clipped-" in line:
            continue
        content.append(line)

    return "\n".join(content[:300])  # cap at 300 lines for prompt size



# ─── Evernote content extraction helpers ──────────────────────────────────────


def _get_sqlite_db_path():
    """Find the Evernote SQLite database (UDB-*.sql)."""
    conduit_fs = EVERNOTE_SUPPORT / "conduit-fs"
    dbs = list(conduit_fs.rglob("UDB-*.sql"))
    return dbs[0] if dbs else None


def _extract_via_pycrdt(guid, dat_path):
    """
    Decode a Yjs .dat file with pycrdt to get the raw ENML.

    Returns dict {markdown, enml_html, source_url} or None on failure.
    """
    try:
        import pycrdt
        from markdownify import markdownify as md_convert
    except ImportError:
        return None

    try:
        data = dat_path.read_bytes()
        doc = pycrdt.Doc()
        doc.apply_update(data)
        enml = str(doc.get("content", type=pycrdt.XmlFragment))
    except Exception:
        return None

    if not enml or len(enml) < 50:
        return None

    # Extract source URL embedded in ENML CSS custom properties
    source_url = None
    m = re.search(r'--en-clipped-source-url:\s*([^;"\s]+)', enml)
    if m:
        source_url = m.group(1).strip()

    # Convert ENML to clean Markdown (strip non-content tags)
    try:
        markdown_text = md_convert(
            enml,
            heading_style="ATX",
            strip=["script", "style", "en-media", "en-note"],
        )
        markdown_text = re.sub(r"\n{3,}", "\n\n", markdown_text).strip()
    except Exception:
        markdown_text = ""

    return {
        "markdown": markdown_text,
        "enml_html": enml,
        "source_url": source_url,
    }


def _extract_via_sqlite(guid):
    """
    Retrieve note text and source URL from Evernote's SQLite database.

    Returns dict {markdown, source_url} or None on failure.
    """
    db_path = _get_sqlite_db_path()
    if not db_path:
        return None

    try:
        conn = sqlite3.connect(str(db_path))
        conn.execute("PRAGMA query_only = ON")
        cur = conn.cursor()

        cur.execute("SELECT content FROM Offline_Search_Note_Content WHERE id = ?", (guid,))
        row = cur.fetchone()
        text = row[0] if row else ""

        source_url = None
        try:
            cur.execute("SELECT source_URL FROM Nodes_Note WHERE id = ?", (guid,))
            url_row = cur.fetchone()
            if url_row and url_row[0]:
                source_url = url_row[0]
        except Exception:
            pass

        conn.close()
    except Exception:
        return None

    if not text:
        return None

    return {"markdown": text, "source_url": source_url}


# ─── Resource handling ────────────────────────────────────────────────────────


def get_note_resources(note_guid, user_id):
    """
    Find all attachment resources for a note in resource-cache.

    Two metadata formats exist:
      - {hash}.mime  → plain text file containing MIME type
      - {hash}.meta  → JSON file with {"mime": "..."} field

    Returns list of dicts: {hash, mime, extension, path}
    """
    cache_dir = RESOURCE_CACHE / f"User{user_id}" / note_guid
    if not cache_dir.exists():
        return []

    resources = []
    seen = set()
    for path in cache_dir.iterdir():
        # Skip metadata companion files
        if path.suffix in (".meta", ".mime"):
            continue
        if path.name in seen:
            continue
        seen.add(path.name)

        mime = "application/octet-stream"

        # Try .mime first (plain text), then .meta (JSON)
        mime_path = path.with_suffix(".mime")
        meta_path = path.with_suffix(".meta")
        if mime_path.exists():
            try:
                mime = mime_path.read_text().strip()
            except Exception:
                pass
        elif meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                mime = meta.get("mime", mime)
            except Exception:
                pass

        ext = MIME_EXTENSIONS.get(mime, "")
        resources.append({
            "hash": path.name,
            "mime": mime,
            "extension": ext,
            "path": str(path),
        })
    return resources


def guid_to_hash(guid):
    """Generate 8-char hash from note GUID (consistent, reproducible)."""
    return hashlib.md5(guid.encode()).hexdigest()[:8]


# ─── Batch preparation ────────────────────────────────────────────────────────


def prepare_batch(batch_size=10, target_guid=None):
    """Prepare next batch of Evernote notes for Claude processing.

    Args:
        batch_size: Number of notes to include in the batch.
        target_guid: If set, prepare a single-note batch for this specific GUID,
                     ignoring whether it has been processed before.
    """
    conduit_user = get_conduit_user_path()
    user_id = get_user_id()

    print("🔍 Building metadata index from Lucene index...")
    metadata_index = build_metadata_index(conduit_user)
    print(f"   Found metadata for {len(metadata_index)} notes")

    print("📂 Enumerating note .dat files...")
    all_notes = get_all_note_dat_files(conduit_user)
    print(f"   Found {len(all_notes)} notes in rteDoc")

    progress = load_progress()
    processed = set(progress["processed"])

    if target_guid:
        if target_guid not in all_notes:
            print(f"❌ GUID not found in rteDoc: {target_guid}")
            return None
        batch = [target_guid]
        print(f"🎯 Targeting specific note: {target_guid}")
    else:
        unprocessed = [guid for guid in all_notes if guid not in processed]
        if not unprocessed:
            print("✅ All Evernote notes already processed!")
            return None
        print(f"   Remaining: {len(unprocessed)}")
        batch = unprocessed[:batch_size]
    batch_num = progress["current_batch"] + 1

    batch_data = []
    for guid in batch:
        dat_path = all_notes[guid]
        meta = metadata_index.get(guid, {})
        file_hash = guid_to_hash(guid)

        print(f"  📝 Extracting: {meta.get('title', guid)[:60]}")

        try:
            content = extract_note_content(dat_path, guid=guid)
            resources = get_note_resources(guid, user_id)

            batch_data.append({
                "guid": guid,
                "file_hash": file_hash,
                "user_id": user_id,
                "dat_path": str(dat_path),
                "title": meta.get("title", content.get("source_title") or "Untitled"),
                "notebook": meta.get("notebook", "Personal"),
                "created": meta.get("created"),
                "updated": meta.get("updated"),
                "content": content,
                "resources": resources,
            })
        except Exception as e:
            print(f"  ❌ Error processing {guid}: {e}")
            continue

    # Save batch data
    batch_file = REPO_ROOT / f"evernote_batch_{batch_num}.json"
    with open(batch_file, "w") as f:
        json.dump(batch_data, f, indent=2)

    # Generate prompt
    prompt = _generate_batch_prompt(batch_data, batch_num)
    prompt_file = REPO_ROOT / f"evernote_batch_{batch_num}_prompt.txt"
    with open(prompt_file, "w") as f:
        f.write(prompt)

    print(f"\n✅ Batch {batch_num} prepared: {len(batch_data)} notes")
    print(f"   Data:   evernote_batch_{batch_num}.json")
    print(f"   Prompt: evernote_batch_{batch_num}_prompt.txt")
    print(f"\n📋 Next: Analyze prompt → save response as evernote_batch_{batch_num}_response.json")
    print(f"         Then: python src/process_evernote.py apply {batch_num}")

    return batch_num


def _generate_batch_prompt(batch_data, batch_num):
    """Generate Claude prompt for the batch."""
    total = len(batch_data)
    web_clips = [n for n in batch_data if n["content"]["type"] == "web_clip"]
    regular = [n for n in batch_data if n["content"]["type"] == "regular"]

    prompt = f"""I need you to analyze {total} Evernote notes ({len(web_clips)} web clips, {len(regular)} personal notes) and generate structured metadata for Obsidian notes.

For EACH note, provide a JSON object with:
{{
  "guid": "the note GUID",
  "title": "Concise, accurate title (from content; for web clips use article title not Evernote title)",
  "source_name": "Publication/site name (for web clips) | null for personal notes",
  "source_url": "Primary URL (for web clips) | null for personal notes",
  "source_date": "YYYY-MM-DD (article date if available, else creation date)",
  "summary": "2-3 sentence summary with specific insights (for web clips) | brief description for personal notes",
  "key_points": [
    "5 specific, substantive bullet points for web clips",
    "Fewer/shorter for personal notes — just capture the essence"
  ],
  "tags": ["Topic", "Subtopic", "Tag"],
  "authors": ["Author Name"],
  "author_urls": {{"Author Name": "profile-url-or-null"}}
}}

Return a JSON array with one object per note. Provide ONLY the JSON array, no other text.

NOTES TO ANALYZE:
"""

    for i, note in enumerate(batch_data, 1):
        content = note["content"]
        created_str = (
            datetime.fromtimestamp(note["created"]).strftime("%Y-%m-%d")
            if note.get("created")
            else "unknown"
        )
        note_type = "WEB CLIP" if content["type"] == "web_clip" else "PERSONAL NOTE"

        prompt += f"\n\n{'='*70}\n"
        prompt += f"NOTE {i}/{total} — {note_type}\n"
        prompt += f"{'='*70}\n"
        prompt += f"GUID:      {note['guid']}\n"
        prompt += f"File Hash: {note['file_hash']}\n"
        prompt += f"Notebook:  {note['notebook']}\n"
        prompt += f"Created:   {created_str}\n"

        if content.get("source_url"):
            prompt += f"Source URL:   {content['source_url']}\n"
        if content.get("source_title"):
            prompt += f"Source Title: {content['source_title']}\n"

        if note.get("resources"):
            res_summary = ", ".join(
                f"{r['hash'][:8]}{r['extension']}" for r in note["resources"]
            )
            prompt += f"Resources: {res_summary}\n"

        method = content.get("extraction_method", "strings")
        text = content.get("text", "").strip()
        if text:
            prompt += f"\nCONTENT [{method}] (first 6000 chars):\n{text[:6000]}\n"
        else:
            prompt += "\nCONTENT: (empty or unreadable)\n"

        links = content.get("links", [])
        if links:
            prompt += f"\nLINKS ({len(links)} total):\n"
            for url in links[:20]:
                prompt += f"  {url}\n"

    prompt += f"\n\n{'='*70}\n"
    prompt += "Provide ONLY the JSON array. No markdown code fences, no extra text.\n"

    return prompt


# ─── Apply batch (create Obsidian notes) ─────────────────────────────────────


def apply_batch(batch_num, response_file=None):
    """Apply Claude's JSON response to create Obsidian notes."""
    batch_file = REPO_ROOT / f"evernote_batch_{batch_num}.json"
    if not batch_file.exists():
        print(f"❌ Batch file not found: {batch_file}")
        return

    if response_file is None:
        response_file = REPO_ROOT / f"evernote_batch_{batch_num}_response.json"
    response_file = Path(response_file)

    if not response_file.exists():
        print(f"❌ Response file not found: {response_file}")
        return

    with open(batch_file) as f:
        batch_data = json.load(f)
    with open(response_file) as f:
        metadata_list = json.load(f)

    # Index metadata by guid
    metadata_by_guid = {m["guid"]: m for m in metadata_list}

    progress = load_progress()
    created = 0
    failed = 0

    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)

    for note in batch_data:
        guid = note["guid"]
        meta = metadata_by_guid.get(guid)

        if not meta:
            print(f"⚠️  No metadata for {guid}")
            failed += 1
            continue

        try:
            _copy_resources(note)
            preview_path = _render_preview(note, meta)
            note_path = _create_note(note, meta, has_preview=preview_path is not None)
            print(f"✅ {note_path.name}")
            progress["processed"].append(guid)
            created += 1
        except Exception as e:
            print(f"❌ {guid}: {e}")
            progress["failed"].append(guid)
            failed += 1

    progress["current_batch"] = batch_num
    save_progress(progress)

    total = len(batch_data)
    print(f"\n✅ Batch {batch_num}: {created}/{total} created, {failed} failed")
    return created


def _copy_resources(note):
    """Copy all resources for a note to Lifegames/Attachments/."""
    file_hash = note["file_hash"]
    resources = note.get("resources", [])
    if not resources:
        return

    # Primary resource gets base hash name; additional ones get suffixes
    for idx, res in enumerate(resources):
        src = Path(res["path"])
        if not src.exists():
            continue
        ext = res.get("extension", "")
        if not ext:
            continue
        suffix = "" if idx == 0 else f"_{idx}"
        dst = ATTACHMENTS_DIR / f"{file_hash}{suffix}{ext}"
        shutil.copy2(src, dst)


def _create_note(note, meta, has_preview=False):
    """Create an Obsidian markdown note from note data and Claude metadata."""
    title = sanitize_title(meta.get("title") or note.get("title") or "Untitled")
    note_path = LIFEGAMES_DIR / f"{title}.md"

    file_hash = note["file_hash"]
    guid = note["guid"]
    notebook = note.get("notebook", "Personal")
    note_type = note["content"]["type"]

    created_date = (
        datetime.fromtimestamp(note["created"]).strftime("%Y-%m-%d")
        if note.get("created")
        else datetime.now().strftime("%Y-%m-%d")
    )
    source_date = meta.get("source_date") or created_date
    today = datetime.now().strftime("%Y-%m-%d")

    # ── Frontmatter ──────────────────────────────────────────────────────────
    fm = f'---\ntitle: "{meta.get("title", title)}"\n'

    if meta.get("source_name"):
        fm += f'source: "{meta["source_name"]}"\n'
    if meta.get("source_url"):
        fm += f'source_url: "{meta["source_url"]}"\n'

    fm += f"date: {source_date}\n"

    authors = meta.get("authors") or []
    if authors:
        fm += "authors:\n"
        for a in authors:
            fm += f"  - {a}\n"

    tags = meta.get("tags") or []
    fm += f"tags: {json.dumps(tags)}\n"
    fm += f'filename: "{file_hash}"\n'
    fm += f"cssclass: article-note\n"
    fm += f'file_hash: "{file_hash}"\n'
    fm += f'evernote_guid: "{guid}"\n'
    fm += f'evernote_notebook: "{notebook}"\n'
    fm += f'generated_by: "claude-code"\n'
    fm += f'generated_model: "{CLAUDE_MODEL}"\n'
    fm += f'generated_at: "{today}"\n'
    fm += "---\n\n"

    # ── Body ─────────────────────────────────────────────────────────────────
    body = f"# {meta.get('title', title)}\n\n"

    if note_type == "web_clip" and meta.get("source_url"):
        source_name = meta.get("source_name", "Source")
        body += "> [!info] Article Information\n"
        body += f"> - **Source**: [{source_name}]({meta['source_url']})\n"
        body += f"> - **Date**: {source_date}\n"
        if authors:
            author_urls = meta.get("author_urls") or {}
            linked = []
            for a in authors:
                url = author_urls.get(a)
                linked.append(f"[{a}]({url})" if url else a)
            body += f"> - **Authors**: {', '.join(linked)}\n"
        body += "\n"

    if meta.get("summary"):
        body += "## Summary\n\n"
        body += meta["summary"] + "\n\n"

    key_points = meta.get("key_points") or []
    if key_points:
        body += "## Key Points\n\n"
        for pt in key_points:
            body += f"- {pt}\n"
        body += "\n"

    author_urls = meta.get("author_urls") or {}
    if authors and any(author_urls.get(a) for a in authors):
        body += "## Author Information\n\n"
        for a in authors:
            url = author_urls.get(a)
            body += f"- [{a}]({url})\n" if url else f"- {a}\n"
        body += "\n"

    body += "## Linked Concepts\n\n"
    body += "<!-- For manual wiki-linking later -->\n\n"

    body += "## Notes\n\n\n\n"

    # ── Attachments ───────────────────────────────────────────────────────────
    body += "## Attachments\n\n"
    if has_preview:
        body += f"- ![[{file_hash}_preview.png]]\n"

    with open(note_path, "w", encoding="utf-8") as f:
        f.write(fm + body)

    return note_path


_YJS_NOISE = re.compile(
    r"^https?://"                   # bare URLs
    r"|^w[a-f0-9]{6,}"             # Yjs resource ref (w + hex hash)
    r"|noopener|ugc|nofollow"       # link rel attributes
    r"|^shape$|^rect\(|^_blank"    # CSS/structural tokens
    r"|^div\(|^span\(",
    re.IGNORECASE,
)


def _text_to_html(raw_text):
    """Convert Yjs-extracted raw text into clean HTML paragraphs.

    The strings-extracted Yjs content has control-char prefixes and apostrophes
    split across lines (e.g. "doesn" / "t mean").  We strip obvious noise and
    join short continuation lines into their surrounding paragraph.
    """
    lines = raw_text.split("\n")
    paras = []
    current = []

    for line in lines:
        s = line.strip()
        if not s:
            if current:
                paras.append(" ".join(current))
                current = []
            continue
        if len(s) < 3:
            continue
        if _YJS_NOISE.search(s):
            continue
        # Strip leading single non-word char (Yjs operation prefix)
        s = re.sub(r"^[^\w\"'(#\[\-]{1,3}", "", s).strip()
        if len(s) < 3:
            continue
        # Markdown-style headings from the article
        if s.startswith("#"):
            if current:
                paras.append(" ".join(current))
                current = []
            paras.append(f'<h3 style="margin-top:1.4em;">{s.lstrip("#").strip()}</h3>')
            continue
        current.append(s)

    if current:
        paras.append(" ".join(current))

    parts = []
    for p in paras:
        if p.startswith("<h"):
            parts.append(p)
        else:
            parts.append(f"<p>{p}</p>")
    return "\n".join(parts)


_FONT_CSS_CACHE_PATH = Path("/tmp/medium_font_css_v1.cache")
_GOOGLE_FONTS_URL = (
    "https://fonts.googleapis.com/css2?family=Source+Serif+4"
    ":ital,opsz,wght@0,8..60,300;0,8..60,400;0,8..60,600;0,8..60,700"
    ";1,8..60,300;1,8..60,400;1,8..60,600&display=swap"
)
# System-font fallback CSS for sohne (proprietary Klim font — no free equivalent)
_SOHNE_FALLBACK = """
@font-face { font-family: 'sohne'; src: local('SF Pro Text'), local('Helvetica Neue'), local('Arial'); }
@font-face { font-family: 'medium-content-sans-serif-font'; src: local('SF Pro Text'), local('Helvetica Neue'), local('Arial'); }
@font-face { font-family: 'medium-content-title-font'; src: local('SF Pro Text'), local('Helvetica Neue'), local('Arial'); }
"""


def _get_medium_font_css():
    """Return <style> block that maps Medium's font names to real fonts.

    Source Serif 4 (Google Fonts) is the same Adobe font family as
    source-serif-pro used by Medium.  We fetch the Google Fonts CSS,
    rename every occurrence of 'Source Serif 4' → 'source-serif-pro',
    and cache the result so subsequent renders are instant.
    """
    import urllib.request

    if _FONT_CSS_CACHE_PATH.exists():
        return _FONT_CSS_CACHE_PATH.read_text()

    try:
        req = urllib.request.Request(
            _GOOGLE_FONTS_URL,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            },
        )
        with urllib.request.urlopen(req, timeout=8) as r:
            css = r.read().decode("utf-8")
        # Rename so the browser serves these WOFF2s under Medium's font-family name
        css = css.replace("'Source Serif 4'", "'source-serif-pro'")
        css = css.replace('"Source Serif 4"', '"source-serif-pro"')
        result = f"<style>\n{css}\n{_SOHNE_FALLBACK}\n</style>\n"
        _FONT_CSS_CACHE_PATH.write_text(result)
        return result
    except Exception:
        # Network unavailable — fall back to Georgia which is in Medium's fallback stack
        return f"<style>{_SOHNE_FALLBACK}</style>\n"


def _enml_to_html(enml, note, user_id):
    """Convert raw ENML to standalone HTML with base64 images, font injection, and CSS fixes."""

    # pycrdt serializes style attributes with unescaped double quotes for CSS font names:
    #   style="...font-family: Cambria, "Times New Roman", Times..."
    # The inner " terminates the HTML attribute early, truncating the CSS.
    # Fix: convert CSS-context quoted strings to single quotes before HTML parsing.
    enml = re.sub(r'(?<=[;,:\s])"([A-Z][A-Za-z\s]+)"(?=[;,\s>])', r"'\1'", enml)

    def replace_en_media(m):
        tag = m.group(0)
        hash_match = re.search(r'hash="([^"]+)"', tag)
        type_match = re.search(r'type="([^"]+)"', tag)
        if not hash_match:
            return ""
        resource_hash = hash_match.group(1)
        mime_type = type_match.group(1) if type_match else "image/jpeg"

        cache_dir = RESOURCE_CACHE / f"User{user_id}" / note["guid"]
        resource_path = cache_dir / resource_hash
        if not resource_path.exists() and cache_dir.exists():
            for f in cache_dir.iterdir():
                if f.name.startswith(resource_hash[:8]) and f.suffix not in (".meta", ".mime"):
                    resource_path = f
                    break

        if resource_path.exists():
            try:
                img_data = base64.b64encode(resource_path.read_bytes()).decode()
                return f'<img src="data:{mime_type};base64,{img_data}" style="max-width:100%;height:auto;" />'
            except Exception:
                pass
        return ""

    html = re.sub(r"<en-media[^>]+>", replace_en_media, enml)

    # Wrap in full HTML document if needed, injecting font CSS into <head>
    if "<html" not in html.lower():
        html = (
            f'<!DOCTYPE html><html><head><meta charset="utf-8">'
            f'{_get_medium_font_css()}</head><body>{html}</body></html>'
        )
    else:
        # Inject font CSS just before </head>
        html = html.replace("</head>", f"{_get_medium_font_css()}</head>", 1)

    # CSS fixes for Chromium rendering
    html = re.sub(r"min-height:\s*[\d.]+px;?\s*", "", html)
    html = re.sub(r"top:calc\(100vh[^;\"]+\)", "top:-9999px", html)
    html = re.sub(r"bottom:calc\(100vh[^;\"]+\)", "bottom:-9999px", html)
    html = re.sub(r"position:absolute;", "position:relative;", html)

    return html


async def _playwright_render(html_path, out_png):
    """Async Playwright renderer — serves via localhost so external fonts load.

    Using file:// blocks cross-origin requests (Google Fonts CDN).
    A local HTTP server gives the page a real origin so @import and
    <link rel=stylesheet> requests to fonts.googleapis.com succeed.
    """
    import socket
    import threading
    from http.server import HTTPServer, SimpleHTTPRequestHandler

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        raise RuntimeError(
            "playwright not installed — run: pip install playwright && playwright install chromium"
        )

    html_dir = os.path.dirname(os.path.abspath(html_path))
    html_file = os.path.basename(html_path)

    # Find a free port
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    class _SilentHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=html_dir, **kwargs)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", port), _SilentHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch()
            page = await browser.new_page(
                viewport={"width": 748, "height": 900},
                device_scale_factor=2,
            )
            await page.goto(f"http://127.0.0.1:{port}/{html_file}")
            await page.wait_for_load_state("domcontentloaded")

            # Explicitly trigger loading for all registered @font-face variants.
            # Browsers are lazy — fonts stay 'unloaded' until an element actually
            # needs them.  Force-loading ensures gstatic WOFF2 downloads happen
            # before we measure layout or capture the screenshot.
            await page.evaluate(
                """async () => {
                    const loads = [];
                    document.fonts.forEach(f => {
                        if (f.status !== 'loaded') loads.push(f.load());
                    });
                    await Promise.allSettled(loads);
                    await document.fonts.ready;
                }"""
            )
            # Allow a layout reflow after font swap
            await page.wait_for_timeout(500)

            content_height = await page.evaluate(
                """() => {
                    const all = document.body.querySelectorAll('*');
                    let maxBottom = 0;
                    all.forEach(el => {
                        const rect = el.getBoundingClientRect();
                        const bottom = rect.bottom + window.scrollY;
                        if (bottom > maxBottom && rect.width > 0) maxBottom = bottom;
                    });
                    return Math.ceil(maxBottom) + 40;
                }"""
            )
            content_height = max(content_height, 100)

            await page.set_viewport_size({"width": 748, "height": content_height})
            await page.screenshot(
                path=out_png,
                full_page=False,
                clip={"x": 0, "y": 0, "width": 748, "height": content_height},
            )
            await browser.close()
    finally:
        server.shutdown()


def _render_preview(note, meta):
    """Render the full clipped web content as a PNG via Playwright/Chromium.

    Uses the original ENML with real CSS and base64-embedded images for a
    near-identical reproduction of the original Evernote web clip.
    Falls back to a plain PyMuPDF summary card when ENML is unavailable.
    Saves as {file_hash}_preview.png in ATTACHMENTS_DIR.
    Returns the output Path, or None on failure.
    """
    enml_html = note.get("content", {}).get("enml_html")
    if not enml_html:
        return _render_preview_fallback(note, meta)

    user_id = note.get("user_id", "")
    file_hash = note["file_hash"]
    out_path = ATTACHMENTS_DIR / f"{file_hash}_preview.png"

    try:
        html = _enml_to_html(enml_html, note, user_id)
        html_tmp = f"/tmp/webclip_{file_hash}.html"
        with open(html_tmp, "w", encoding="utf-8") as f:
            f.write(html)
        asyncio.run(_playwright_render(html_tmp, str(out_path)))
        return out_path if out_path.exists() else None
    except Exception as e:
        print(f"   ⚠️  Playwright render failed: {e}")
        return _render_preview_fallback(note, meta)


def _render_preview_fallback(note, meta):
    """PyMuPDF summary card fallback when ENML is unavailable."""
    try:
        import fitz
        import io as _io
    except ImportError:
        return None

    file_hash = note["file_hash"]
    title = meta.get("title", "Untitled")
    source_name = meta.get("source_name", "")
    source_date = meta.get("source_date", "")
    authors = meta.get("authors") or []

    parts = []
    if authors:
        parts.append(", ".join(authors))
    if source_name:
        parts.append(source_name)
    if source_date:
        parts.append(source_date)
    meta_line = " · ".join(parts)

    img_tag = ""
    for res in note.get("resources") or []:
        if res.get("mime", "").startswith("image/"):
            img_filename = f"{file_hash}{res.get('extension', '.jpg')}"
            img_tag = (
                f'<img src="{img_filename}" '
                f'style="width:100%;max-height:320px;object-fit:cover;'
                f'border-radius:6px;margin:16px 0 20px;"/>'
            )
            break

    raw_text = note.get("content", {}).get("text", "")
    content_html = _text_to_html(raw_text)

    html = f"""<!DOCTYPE html>
<html><body style="font-family:Georgia,serif;margin:40px 48px;max-width:840px;color:#1a1a1a;line-height:1.75;">
<h1 style="font-size:26px;border-bottom:2px solid #333;padding-bottom:10px;margin-bottom:6px;">{title}</h1>
<p style="color:#888;font-size:13px;margin:0 0 4px;">{meta_line}</p>
{img_tag}
{content_html}
</body></html>"""

    try:
        archive = fitz.Archive(str(ATTACHMENTS_DIR))
        story = fitz.Story(html=html, archive=archive)
        buf = _io.BytesIO()
        writer = fitz.DocumentWriter(buf)
        mediabox = fitz.Rect(0, 0, 940, 20000)
        device = writer.begin_page(mediabox)
        _, filled = story.place(mediabox)
        story.draw(device)
        writer.end_page()
        writer.close()

        content_height = filled[3] + 48
        buf.seek(0)
        doc = fitz.open("pdf", buf.read())
        clip = fitz.Rect(0, 0, 940, content_height)
        pix = doc[0].get_pixmap(dpi=120, clip=clip)
        out_path = ATTACHMENTS_DIR / f"{file_hash}_preview.png"
        pix.save(str(out_path))
        doc.close()
        return out_path
    except Exception as e:
        print(f"   ⚠️  Preview render failed: {e}")
        return None


def sanitize_title(title):
    """Sanitize title for use as Obsidian filename."""
    sanitized = re.sub(r'[\[\]#^|\\/:?*<>"]', "", title)
    sanitized = sanitized.strip()
    if len(sanitized) > 100:
        sanitized = sanitized[:97] + "..."
    return sanitized or "Untitled"


# ─── Status ───────────────────────────────────────────────────────────────────


def show_status():
    """Show processing statistics."""
    try:
        conduit_user = get_conduit_user_path()
        user_id = get_user_id()
    except RuntimeError as e:
        print(f"❌ {e}")
        return

    all_notes = get_all_note_dat_files(conduit_user)
    progress = load_progress()
    processed = set(progress["processed"])
    total = len(all_notes)
    done = len([g for g in all_notes if g in processed])
    remaining = total - done
    pct = (done / total * 100) if total else 0

    resource_notes = len(list(RESOURCE_CACHE.glob(f"User{user_id}/*"))) if RESOURCE_CACHE.exists() else 0

    print(f"\n📊 Evernote Processing Status")
    print(f"{'='*50}")
    print(f"Total notes:      {total}")
    print(f"Processed:        {done}")
    print(f"Remaining:        {remaining}")
    print(f"Progress:         {pct:.1f}%")
    print(f"Notes w/ assets:  {resource_notes}")
    print(f"Current batch:    {progress['current_batch']}")
    print(f"Failed:           {len(progress.get('failed', []))}")
    print(f"{'='*50}")
    print(f"Evernote user:    {conduit_user.name}")
    print(f"User ID:          {user_id}")
    print(f"{'='*50}\n")


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print(__doc__)
        print("\nUsage:")
        print("  python src/process_evernote.py status")
        print("  python src/process_evernote.py prepare [batch_size]")
        print("  python src/process_evernote.py apply BATCH_NUM [response_file]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "status":
        show_status()

    elif command == "prepare":
        # Support: prepare [batch_size] [--guid GUID]
        args = sys.argv[2:]
        target_guid = None
        batch_size = 10
        i = 0
        while i < len(args):
            if args[i] == "--guid" and i + 1 < len(args):
                target_guid = args[i + 1]
                i += 2
            else:
                try:
                    batch_size = int(args[i])
                except ValueError:
                    pass
                i += 1
        prepare_batch(batch_size, target_guid=target_guid)

    elif command == "apply":
        if len(sys.argv) < 3:
            print("❌ BATCH_NUM required")
            sys.exit(1)
        batch_num = int(sys.argv[2])
        response_file = sys.argv[3] if len(sys.argv) > 3 else None
        apply_batch(batch_num, response_file)

    else:
        print(f"❌ Unknown command: {command}")
        sys.exit(1)
