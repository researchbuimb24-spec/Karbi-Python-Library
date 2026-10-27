"""
Book Import Script for Initial Complete Texts
=============================================

Imports:
1. Complete 18 chapters of The Bhagavad Gita (Sir Edwin Arnold 1885, Project Gutenberg #2388)
2. Authentic Karbi Folk-Lore and Folk-Tales (Stack & Lyall 1908, Project Gutenberg #48706)
"""

import datetime
import hashlib
import json
from pathlib import Path
import re
import ssl
import sys
import unicodedata
import urllib.request

from karbi.books.catalog import BookCatalog
from karbi.books.importer import BookImporter
from karbi.books.models import (
    BookImportStatus,
    BookMetadata,
    Passage,
    PassageProvenanceStatus,
    TranslationRecord,
    TranslationType,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = REPO_ROOT / "data" / "books"

GITA_CHAPTER_TITLES = {
    1: "The Distress of Arjuna",
    2: "The Book of Doctrines",
    3: "Virtue in Work",
    4: "The Religion of Knowledge",
    5: "Religion of Renouncing Works",
    6: "Religion by Self-Restraint",
    7: "Religion by Discernment",
    8: "Religion by Service of the Supreme",
    9: "Religion by the Kingly Knowledge and the Kingly Mystery",
    10: "Religion by the Heavenly Perfections",
    11: "The Manifesting of the One and Manifold",
    12: "Religion of Faith",
    13: "Religion by Separation of Matter and Spirit",
    14: "Religion by Separation from the Qualities",
    15: "Religion by Attaining the Supreme",
    16: "The Separateness of the Divine and Undivine",
    17: "Religion by the Threefold Faith",
    18: "Religion by Deliverance and Renunciation",
}


def import_bhagavad_gita(importer: BookImporter) -> None:
    print("Fetching and importing The Bhagavad Gita (Sir Edwin Arnold 1885)...")
    url = "https://www.gutenberg.org/cache/epub/2388/pg2388.txt"
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KarbiLanguageLibrary/1.0)"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            raw_text = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.URLError as e:
        print(f"ERROR: Secure TLS download failed for {url}: {e}. Insecure TLS bypasses are prohibited by security policy.", file=sys.stderr)
        raise

    raw_text = unicodedata.normalize("NFC", raw_text)

    # Locate start of actual chapters
    start_marker = "*** START OF THE PROJECT GUTENBERG EBOOK"
    s_idx = raw_text.find(start_marker)
    if s_idx != -1:
        raw_text = raw_text[s_idx:]
    end_marker = "*** END OF THE PROJECT GUTENBERG EBOOK"
    e_idx = raw_text.find(end_marker)
    if e_idx != -1:
        raw_text = raw_text[:e_idx]

    ch_matches = list(re.finditer(r"(?:^|\n)\s*CHAPTER\s+([IVXLCDM]+)", raw_text))
    actual_chapters = []
    for m in ch_matches:
        preview = raw_text[m.end():m.end() + 300]
        if "CONTENTS" not in preview and len(preview.strip()) > 20:
            actual_chapters.append(m)

    if len(actual_chapters) > 18:
        actual_chapters = actual_chapters[-18:]

    print(f"  Parsed {len(actual_chapters)} chapters from text.")

    passages: List[Passage] = []
    seq = 1

    for i, ch_match in enumerate(actual_chapters):
        ch_num = i + 1
        ch_title = f"Chapter {ch_num}: {GITA_CHAPTER_TITLES.get(ch_num, '')}"
        start_pos = ch_match.end()
        end_pos = actual_chapters[i + 1].start() if i + 1 < len(actual_chapters) else len(raw_text)

        ch_body = raw_text[start_pos:end_pos].strip()
        blocks = [b.strip() for b in re.split(r"\n\s*\n", ch_body) if b.strip()]

        for v_num, block in enumerate(blocks, 1):
            p = Passage(
                passage_id=f"bhagavad_gita:{ch_num}:{v_num}",
                book_id="bhagavad_gita",
                language="en",
                chapter_number=ch_num,
                chapter_title=ch_title,
                verse=v_num,
                sequence_number=seq,
                text=block,
                source_reference=f"Bhagavad Gita, Ch. {ch_num}, Stanza {v_num} (Arnold 1885)",
                provenance_status=PassageProvenanceStatus.SOURCE_ATTESTED.value,
            )
            passages.append(p)
            seq += 1

    meta = importer.catalog.get_book("bhagavad_gita")
    if not meta:
        meta = BookMetadata(
            book_id="bhagavad_gita",
            canonical_title="The Bhagavad Gita",
            author="Vyāsa (attributed)",
            original_language="sa",
            translator="Sir Edwin Arnold (1832-1904)",
            document_type="philosophy",
            licence="Public Domain",
            copyright_status="public_domain",
        )

    manifest = importer.import_passages(
        metadata=meta,
        passages=passages,
        overwrite=True,
    )
    print(f"  Successfully imported Bhagavad Gita: {manifest.total_chapters} chapters, {manifest.total_passages} passages.")


def import_karbi_folktales(importer: BookImporter) -> None:
    print("Fetching and importing Karbi Folk-Lore & Folk-Tales (Stack & Lyall 1908)...")
    url = "https://www.gutenberg.org/cache/epub/48706/pg48706.txt"
    ctx = ssl.create_default_context()
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (KarbiLanguageLibrary/1.0)"})
    try:
        with urllib.request.urlopen(req, context=ctx, timeout=30) as resp:
            raw_text = resp.read().decode("utf-8", errors="ignore")
    except urllib.error.URLError as e:
        print(f"ERROR: Secure TLS download failed for {url}: {e}. Insecure TLS bypasses are prohibited by security policy.", file=sys.stderr)
        raise

    raw_text = unicodedata.normalize("NFC", raw_text)

    # Find Section V stories:
    m1 = re.search(r"1\.\s+STORY OF A FROG\.", raw_text)
    m2 = re.search(r"2\.\s+STORY OF AN ORPHAN AND HIS UNCLES\.", raw_text)
    m3 = re.search(r"3\.\s+STORY OF HARATA KUNWAR", raw_text)
    # End of story 3 is before the note on affinities or Section VI
    # Let's search for "SECTION VI" or "Section VI" or next major section
    m_end_story3 = re.search(r"(?:SECTION\s+VI|Section\s+VI|Ram\s+vanquished\s+them\s+all)", raw_text[m3.start():])
    story3_end = (m3.start() + m_end_story3.start()) if m_end_story3 else (m3.start() + 45000)

    stories = [
        (1, "The Story of a Frog", raw_text[m1.end():m2.start()]),
        (2, "The Story of the Orphan and his Uncles", raw_text[m2.end():m3.start()]),
        (3, "The Story of Harata Kunwar", raw_text[m3.end():story3_end]),
    ]

    passages: List[Passage] = []
    translations: List[TranslationRecord] = []
    seq = 1

    for ch_num, ch_title, body in stories:
        paras = [p.strip() for p in re.split(r"\n\s*\n", body.strip()) if len(p.strip()) > 15]
        for p_idx, para in enumerate(paras, 1):
            pid = f"karbi_folktales_1908:{ch_num}:{p_idx}"
            passages.append(
                Passage(
                    passage_id=pid,
                    book_id="karbi_folktales_1908",
                    language="en",
                    chapter_number=ch_num,
                    chapter_title=f"Story {ch_num}: {ch_title}",
                    paragraph=p_idx,
                    sequence_number=seq,
                    text=para,
                    source_reference=f"The Mikirs (1908), Section V, Story {ch_num}, Para {p_idx}",
                    provenance_status=PassageProvenanceStatus.SOURCE_ATTESTED.value,
                    translation_links={"mjw": f"karbi_folktales_1908:karbi:{ch_num}:{p_idx}"},
                )
            )
            seq += 1

    # Also import Karbi language text blocks from Section VI
    # Find Karbi texts: Ki-cho-o kache-en-along (Story 1) and Harata Kunwar (Story 3)
    k_frog_m = re.search(r"Ki-chò-ò\s+kachè-èn-alòng", raw_text, re.IGNORECASE)
    if k_frog_m:
        k_start = k_frog_m.start()
        k_frog_text = raw_text[k_start:k_start + 4000]
        k_paras = [p.strip() for p in re.split(r"\n\s*\n", k_frog_text) if len(p.strip()) > 25]
        for k_idx, k_p in enumerate(k_paras[:8], 1):
            pid_k = f"karbi_folktales_1908:karbi:1:{k_idx}"
            passages.append(
                Passage(
                    passage_id=pid_k,
                    book_id="karbi_folktales_1908",
                    language="mjw",
                    chapter_number=1,
                    chapter_title="Story 1: Ki-chò-ò kachè-èn-alòng (Karbi Original)",
                    paragraph=k_idx,
                    sequence_number=seq,
                    text=k_p,
                    source_reference="The Mikirs (1908), Section VI: Language (Stack & Sardoka)",
                    provenance_status=PassageProvenanceStatus.SOURCE_ATTESTED.value,
                    translation_links={"en": f"karbi_folktales_1908:1:{k_idx}"},
                )
            )
            seq += 1

    # Harata Kunwar Karbi text in Section VI
    hk_m = re.search(r"Harata\s+Kunwar\s+kòrte\s+bàng-theròk", raw_text, re.IGNORECASE)
    if hk_m:
        hk_start = hk_m.start()
        hk_text = raw_text[hk_start:hk_start + 6000]
        hk_paras = [p.strip() for p in re.split(r"\n\s*\n", hk_text) if len(p.strip()) > 25]
        for hk_idx, hk_p in enumerate(hk_paras[:12], 1):
            pid_hk = f"karbi_folktales_1908:karbi:3:{hk_idx}"
            passages.append(
                Passage(
                    passage_id=pid_hk,
                    book_id="karbi_folktales_1908",
                    language="mjw",
                    chapter_number=3,
                    chapter_title="Story 3: Harata Kunwar achon (Karbi Original)",
                    paragraph=hk_idx,
                    sequence_number=seq,
                    text=hk_p,
                    source_reference="The Mikirs (1908), Section VI: Language (Stack & Sardoka)",
                    provenance_status=PassageProvenanceStatus.SOURCE_ATTESTED.value,
                    translation_links={"en": f"karbi_folktales_1908:3:{hk_idx}"},
                )
            )
            seq += 1

    print(f"  Total Karbi folktale passages created: {len(passages)}")

    meta = importer.catalog.get_book("karbi_folktales_1908")
    if not meta:
        meta = BookMetadata(
            book_id="karbi_folktales_1908",
            canonical_title="Karbi Folk-Lore and Folk-Tales (The Mikirs)",
            author="Edward Stack (1849-1887) and Sardoka Perrin Kay",
            original_language="mjw",
            translator="Sir Charles James Lyall (1845-1920)",
            document_type="folklore",
            licence="Public Domain",
            copyright_status="public_domain",
        )

    manifest = importer.import_passages(
        metadata=meta,
        passages=passages,
        overwrite=True,
    )
    print(f"  Successfully imported Karbi folktales: {manifest.total_chapters} chapters/stories, {manifest.total_passages} passages.")


def main():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    catalog = BookCatalog(DATA_DIR / "catalog.json")
    importer = BookImporter(catalog=catalog, base_dir=DATA_DIR)
    import_bhagavad_gita(importer)
    import_karbi_folktales(importer)
    print("All initial book texts imported successfully!")


if __name__ == "__main__":
    main()
