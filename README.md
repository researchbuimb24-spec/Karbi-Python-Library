# Karbi Language Python Library (`karbi`)

A lightweight Python library and curated reference repository for the **Karbi language** (*Arleng alam*), primarily spoken in the Karbi Anglong and West Karbi Anglong regions of Assam, India *(demographic and geographic descriptions subject to formal verification against census and scholarly sources)*.

> [!IMPORTANT]
> **Verification & Provenance Notice:** All linguistic classifications, orthographic standards, dialect designations, and cultural narratives in this project are preliminary working outlines that require formal verification against authorized academic publications, recognized community bodies, or native speaker authorities. Unverified claims, synthetic data, or AI-generated candidates will not be treated as established facts.

---

## Project Purpose & Current Limitations

### Purpose
The `karbi` library provides a lightweight, zero-external-dependency Python interface and curated knowledge base for the Karbi language. It enables:
* Direct Karbi headword lookup and automatic modern spelling-variant resolution.
* Multilingual translation into Karbi from English, Hindi, Assamese, and Bengali.
* Unified search across headwords, variants, and definition glosses.
* Phonetic pronunciations in International Phonetic Alphabet (IPA) for entries where phonetic notation is documented in source records.
* Transparent bibliographic source citations linking every attested entry to primary historical or academic records.
* Strict filtering to separate authentic, attested records from unverified translations.

### Current Limitations
* **Pre-Alpha Status (`0.1.0`):** The project is in active initial development.
* **Lexicon Scope:** The lexical database contains **516 historical source-attested headwords** (IDs `KB-LEX-0000001` through `KB-LEX-0000516`) with 100% citation coverage across primary historical sources: Edward Stack & Sir Charles Lyall's *The Mikirs* (1908, `SRC-PUB-00001`), Sir George Abraham Grierson's *Linguistic Survey of India*, Vol. III, Part II (1903, `SRC-PUB-00002`), Rev. R. E. Neighbor's *A Vocabulary in English and Mikir* (1878, `SRC-PUB-00003`), and Sardoka Perrin Kay & Edward Stack's *An English-Mikir Vocabulary* (1904, `SRC-PUB-00004`).
  * **515 entries** are attested directly from primary sources (`SOURCE_ATTESTED`).
  * **1 entry** has an identified citation discrepancy (`KB-LEX-0000382`, `kāthē` vs. source printed `karle`/`karle-sarpo` on p. 88, marked `CITATION_MISMATCH`).
  * **0 entries** are verified by contemporary native speakers (Current native-speaker verification count: 0).
  * It provides an authentic, scholarly foundation rather than an exhaustive dictionary of contemporary spoken Karbi.
* **Unverified Translation Glosses:** While English glosses are source-attested from published documentation, all corresponding Hindi, Assamese, and Bengali translations are unverified candidate glosses (561 Indic glosses: Hindi 206, Assamese 186, Bengali 169), alongside 1 unverified English gloss on citation-mismatch record `KB-LEX-0000382` (total 562 unverified glosses across the dataset) that await formal review and native speaker corroboration. These are automatically excluded whenever `verified_only=True` is requested.
* **Structured Gloss Review Workflow:** The data model includes `GlossReviewRecord` in entry provenance to systematically record gloss-level audit decisions (`accepted`, `corrected`, `rejected`, `awaiting_review`), source locators, reviewer roles, dates, and revision histories.
* **Extensible Language Architecture:** The library supports lookup and translation across 4 active languages (`en`, `hi`, `as`, `bn`), and includes registry configurations for Marathi (`mr`) and Khasi (`kha`) marked as `awaiting_sourced_entries` to facilitate future evidence-backed expansion without manufacturing unverified data.
* **Orthography & Colonial-Era Sourced Limitations:** Orthographic conventions in this library represent primary historical source attestations alongside common contemporary Roman-script representations. Colonial-era orthography and phonetic transcriptions (such as those in Stack & Lyall 1908 or Grierson 1903) reflect external missionary and administrative recording conventions of their era; they are distinct from ongoing orthographic standardization by contemporary Karbi literary bodies (such as *Karbi Lammet Amei*).
* **Cultural Knowledge:** Folklore, rituals, and deity outlines in `karbi.culture` are preliminary summaries accompanied by cultural sensitivity guidelines and require further community consent and elder validation.

---

## Installation for Local Development

The library requires **Python 3.9** or higher and has **zero external runtime dependencies** (it uses only standard library modules such as `sqlite3`, `dataclasses`, `json`, `argparse`, and `pathlib`).

### 1. Clone the repository
```bash
git clone https://github.com/researchbuimb24-spec/Karbi-Assam-Lang-Python-Library.git
cd Karbi-Assam-Lang-Python-Library
```

### 2. Create and activate a virtual environment
```bash
python -m venv .venv

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# On Windows (Command Prompt):
.venv\Scripts\activate.bat

# On Linux or macOS:
source .venv/bin/activate
```

### 3. Install in editable mode
```bash
# Basic editable install:
pip install -e .

# Editable install with development dependencies (pytest):
pip install -e ".[dev]"
```

---

## Python API Usage

All core functions and classes can be imported directly from the top-level `karbi` package.

```python
import karbi
```

### 1. Unified Search with `search()`
`karbi.search(query, lang="auto", verified_only=False)` searches across Karbi headwords, contemporary spelling variants, and definition glosses in all supported languages. *(Note: IPA pronunciation is available only for entries that document phonetic notation in primary source records; otherwise `r.phonetics_ipa` is `None`.)*

```python
import karbi

# Auto-detect language (Karbi headword lookup)
results = karbi.search("arlèng")
for r in results:
    print(f"Lemma: {r.karbi_lemma} ({r.part_of_speech})")
    print(f"Pronunciation (IPA): {r.phonetics_ipa or 'N/A'}")
    print(f"English: {r.get_meanings('en')}")
    print(f"Verified: {r.is_verified} (Status: {r.status})")
    print(f"Source(s): {r.source_citations}")

# Search from a specific source language (e.g. English into Karbi)
matches = karbi.search("water", lang="en")
for m in matches:
    print(f"Karbi Lemma: {m.karbi_lemma}, Matched from: {m.matched_language}")
```

### 2. Karbi Headword & Variant Lookup with `lookup()`
`karbi.lookup(karbi_word)` retrieves a `DictionaryEntry` for a canonical Karbi headword or resolves an alternative spelling variant.

```python
import karbi

# Canonical headword lookup
entry = karbi.lookup("arlèng")
if entry:
    print(f"Headword: {entry.lemma} [Dialect: {entry.dialect}]")
    print(f"Meanings (EN): {entry.get_meanings('en')}")
    print(f"Spelling Variants: {entry.get_spelling_variants()}")

# Automatic spelling-variant resolution (e.g., 'hem' -> 'hèm')
variant_entry = karbi.lookup("hem")
if variant_entry:
    print(f"Resolved to canonical lemma: {variant_entry.lemma}")
    print(f"Meanings (EN): {variant_entry.get_meanings('en')}")

# Retrieve all homonyms for a word with lookup_all() (e.g., verb 'cho' vs noun 'cho')
homonyms = karbi.lookup_all("cho")
for h in homonyms:
    print(f"[{h.entry_id}] {h.lemma} ({h.senses[0]['part_of_speech']}): {h.get_meanings('en')}")
```

### 3. Multilingual Translation with `translate()`
`karbi.translate(text, from_lang="en", verified_only=False)` translates words or concepts into Karbi.

```python
import karbi

# Translate from English into Karbi
matches = karbi.translate("water", from_lang="en")
for match in matches:
    print(f"Karbi: {match.karbi_lemma}")
    print(f"Pronunciation (IPA): {match.phonetics_ipa or 'N/A'}")
    print(f"Verification: {match.is_verified} ({match.status})")
    print(f"Citations: {match.source_citations}")

# Translate from Hindi (using unverified working glosses)
hi_matches = karbi.translate("पानी", from_lang="hi", verified_only=False)
for match in hi_matches:
    print(f"Karbi: {match.karbi_lemma}, Gloss Verified: {match.is_verified}")
```

### 4. Batch Operations
For processing multiple queries efficiently, use the batch functions:

#### `batch_search()`
```python
import karbi

queries = ["water", "arlèng", "hem"]
results = karbi.batch_search(queries)

for query, matches in results.items():
    lemmas = [m.karbi_lemma for m in matches]
    print(f"Query '{query}' -> Found Lemmas: {lemmas}")
```

#### `batch_lookup()`
```python
import karbi

words = ["arlèng", "hem", "làng", "unknown_word"]
entries = karbi.batch_lookup(words)

for word, entry in entries.items():
    if entry:
        print(f"'{word}' -> Lemma: {entry.lemma} (Status: {entry.status})")
    else:
        print(f"'{word}' -> Not found")
```

#### `batch_translate()`
```python
import karbi

terms = ["water", "house"]
translations = karbi.batch_translate(terms, from_lang="en")

for term, matches in translations.items():
    lemmas = [m.karbi_lemma for m in matches]
    print(f"English '{term}' -> Karbi: {lemmas}")
```

---

## Supported Language Codes & Spelling-Variant Behaviour

### Supported Language Codes
The library supports the following ISO language codes:

| Code | Language | Script | Data Status |
| :--- | :--- | :--- | :--- |
| `karbi` | Karbi (*Arleng alam*) | Latin | Active headwords & spelling variants |
| `en` | English | Latin | Active data (primarily source-attested) |
| `hi` | Hindi | Devanagari | Active data (working candidate glosses) |
| `as` | Assamese | Bengali-Assamese | Active data (working candidate glosses) |
| `bn` | Bengali | Bengali | Active data (working candidate glosses) |
| `mr` | Marathi | Devanagari | Registry placeholder (awaiting sourced entries) |

The `search()` and `batch_search()` functions also accept `lang="auto"` (default), which searches Karbi headwords first and then falls back to translating across active source languages.

### Spelling-Variant Behaviour
Karbi words have variations in orthography between historical texts, phonetic records, and modern everyday writing (notably presence or absence of diacritics, such as grave accents indicating vowel qualities).

* `karbi.lookup()` resolves spelling variants transparently: querying `"hem"` matches the registered variant for `"hèm"` and returns the canonical `DictionaryEntry`.
* `karbi.search()` flags variant matches: querying `"hem"` returns a `SearchResult` with `query_type="spelling_variant"`, while `karbi_lemma` correctly references `"hèm"`.

---

## Verification Levels & `verified_only`

To maintain scientific rigor and prevent unverified or synthetic data from contaminating research, every entry and translation gloss carries an explicit status:

* **`SOURCE_ATTESTED`:** The entry or translation gloss is attested in published academic literature or primary historical documentation (e.g., Stack & Lyall 1908). It includes verifiable bibliographic citations and page locators.
* **`VERIFIED`:** Confirmed by recognized native speaker authorities, linguists, or institutional community bodies (e.g., *Karbi Lammet Amei*).
* **`unverified` / `COMMUNITY_SUBMITTED`:** Preliminary candidate entries or working translations that have not yet undergone formal native-speaker or community review.
* **`AI_CANDIDATE`:** Automated candidate data. **Never treated as established linguistic fact.**

### How `verified_only` Works
When `verified_only=True` is passed to `search()`, `translate()`, `batch_search()`, `batch_translate()`, or `entry.get_meanings(lang, verified_only=True)`:
* Any entry or definition whose status is unverified (such as candidate Hindi, Assamese, or Bengali glosses) is filtered out.
* Only entries and glosses confirmed as `SOURCE_ATTESTED` or `VERIFIED` are returned.

Example:
```python
import karbi

# Unfiltered translation: returns working glosses even if unverified
all_matches = karbi.translate("पानी", from_lang="hi", verified_only=False)
print("Unfiltered matches:", len(all_matches))  # e.g., 1 (status: 'unverified')

# Filtered translation: returns only verified or source-attested glosses
verified_matches = karbi.translate("पानी", from_lang="hi", verified_only=True)
print("Verified matches:", len(verified_matches))  # 0 (filtered out)
```

---

## Command-Line Interface (CLI)

The library installs a command-line tool `karbi` (also executable as `python -m karbi`).

### Subcommands

#### 1. Quick Search / Direct Query
Passing a word directly searches across headwords, variants, and translations:
```bash
karbi arlèng
karbi water
karbi hem
```

#### 2. Headword Lookup (`lookup`)
```bash
# Look up a Karbi headword
karbi lookup arlèng

# Look up with modern spelling variant
karbi lookup hem

# Output in JSON format
karbi lookup arlèng --json
```

#### 3. Multilingual Translation (`translate`)
```bash
# Translate English into Karbi
karbi translate water --from en

# Translate Hindi into Karbi
karbi translate पानी --from hi

# Restrict to verified translations only
karbi translate water --from en --verified-only
```

#### 4. Unified Search (`search`)
```bash
# Search across all languages
karbi search làng

# Search in a specific language
karbi search "human being" --lang en

# Restrict to verified entries
karbi search water --verified-only --json
```

#### 5. List Supported Languages (`languages`)
```bash
karbi languages
karbi languages --json
```

#### 6. Dataset Validation & Contributor Audit (`validate`)
Audits JSONL lexicon files, source registrations, unique identifiers, and cross-references without silently modifying data:
```bash
# Validate default repository dataset
karbi validate

# Show verbose details (scanned files and breakdown)
karbi validate --verbose

# Strict mode: fail if unverified glosses are present
karbi validate --strict

# Output audit report in machine-readable JSON
karbi validate --json

# Validate specific or staged data files
karbi validate --lexicon data/lexicon/core_lexicon.jsonl --sources data/sources/sources.jsonl
```

---

## Contributing & Adding Lexical Entries

We welcome contributions of attested Karbi vocabulary, corrections, and cultural documentation!

For a full step-by-step guide on registering sources, formatting lexical entries, adhering to cultural ethics, and running pre-submission checks, please see **[CONTRIBUTING.md](CONTRIBUTING.md)**.

Key contributor rules:
* **No invented Karbi words:** Every entry must have a valid bibliographic or archival source citation.
* **Preserve unverified status:** Indic translations and AI-suggested glosses must remain explicitly marked `unverified` unless approved by authorized community reviewers.
* **Always run validation before opening a PR:** Run `karbi validate` and `pytest`.

---

## Running the Automated Tests

The test suite covers public API exports, multilingual translation, FTS5 database indices, spelling-variant resolution, CLI behaviors, and packaging configuration.

```bash
# Run all tests using pytest
pytest

# Run tests with verbose output
pytest -v

# Run a specific test module
pytest tests/test_api.py
pytest tests/test_packaging.py
pytest tests/test_cli.py
pytest tests/test_translation.py
```

---

## Source Citations & Community-Review Limitations

### Bibliographic Citations
Attested records cite verifiable historical sources registered in `data/sources/sources.jsonl`:
* **`SRC-PUB-00001`**: **Stack, Edward & Lyall, Sir Charles (1908).** *The Mikirs*. London: David Nutt.
* **`SRC-PUB-00002`**: **Grierson, Sir George Abraham (1903).** *Linguistic Survey of India*, Vol. III: Tibeto-Burman Family, Part II: Specimens of the Bodo, Naga, and Kachin Groups. Calcutta: Superintendent of Government Printing.
* **`SRC-PUB-00003`**: **Neighbor, Rev. R. E. (1878).** *A Vocabulary in English and Mikir: With Sentences Illustrating the Use of Words*. Calcutta: Baptist Mission Press.
* **`SRC-PUB-00004`**: **Kay, Sardoka Perrin & Stack, Edward (1904).** *An English-Mikir Vocabulary, with Assamese Equivalents, to which have been added a few Mikir phrases*. Shillong: Assam Secretariat Press.

Primary source IDs and exact page locators (e.g. `SRC-PUB-00001`, `p. 74, 80` or `SRC-PUB-00003`, `p. 5`) are stored in `data/sources/sources.jsonl` and embedded in `karbi.db`.

### Historical Source Attestation vs. Independent Linguistic Verification
A fundamental principle of this library is the distinction between **historical source attestation** and **independent linguistic/native-speaker verification**:
* **Source Attestation:** Demonstrates that a lexical item, spelling, or gloss was printed in an identified historical or academic document (such as Stack & Lyall 1908 or Grierson 1903). In our second-pass audit, 429 of 481 entries were confirmed verbatim from source context, 51 were partially confirmed as orthographic/morphological variants, and 1 citation mismatch was identified (`KB-LEX-0000382`).
* **Linguistic Verification:** Requires confirmation by contemporary native Karbi speakers, qualified language specialists, or recognized community organizations (such as *Karbi Lammet Amei*). **Currently, 0 entries possess native-speaker verification status.**

### Unverified Translation Glosses (562 Backlog)
While primary English definitions originate directly from source texts, the Indic glosses (Hindi: 206, Assamese: 186, Bengali: 169; total 561) are provisional working candidate glosses, alongside 1 unverified English gloss on citation-mismatch record `KB-LEX-0000382` (total 562 unverified glosses across the dataset).
* In both Python API outputs and CLI tools, unverified glosses are strictly excluded whenever `verified_only=True` (or `--verified-only`) is specified.
* Unverified entries are explicitly marked (`is_verified=False`, `gloss_provenance="unverified"`). Users and researchers must not cite unverified candidate translations as verified Karbi language facts.
* Strict validation (`karbi validate --strict`) intentionally fails with exit code 1 to surface these 562 unverified glosses until they are confirmed by authentic evidence or native speaker review.

### Community Review & Submitting Corrections
Linguistic and cultural documentation of indigenous communities requires ethical collaboration and respect for community ownership:
* All vocabulary expansions, orthography decisions, and dialect notations are subject to ongoing review by native Karbi speakers and representative community bodies.
* Folklore narratives and traditional cultural entries in `karbi.culture` are governed by cultural sensitivity guidelines and consent protocols.
* **How to submit corrections & review glosses:**
  - Complete review instructions: see [COMMUNITY_REVIEW.md](docs/COMMUNITY_REVIEW.md).
  - Review CSV template: see [community_gloss_review_template.csv](docs/community_gloss_review_template.csv).
  - Contributors can submit evidence-backed reviews or corrections by providing:
    1. The entry ID (e.g., `KB-LEX-0000382`).
    2. The source language code (`hi`, `as`, `bn`, `en`).
    3. The modern standard Karbi form or corrected gloss.
    4. Verifiable citation locator or recorded native speaker attribution.
    5. Running `karbi validate` and `pytest` prior to submitting pull requests.

---

---

## Digital Book Library Subsystem (`karbi.books`)

The Karbi Language Library features an extensible, offline-capable digital book library subsystem located in `src/karbi/books/`. It enables researchers, linguists, and community members to store, organize, read, search, and align complete literary works with strict provenance tracking.

### 1. Initial Collection & Catalogue (20 Works)
The library catalogue (`data/books/catalog.json`) tracks 20 foundational Indian literary, philosophical, and folklore works with transparent bibliographic citations and copyright status:

| Book ID | Canonical Title | Author / Source | Status | Imported | Licence |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `bhagavad_gita` | **The Bhagavad Gita** | Vyāsa / Sir Edwin Arnold (1885) | `FULLY_IMPORTED` | 18 ch / 295 pass | Public Domain (Gutenberg #2388) |
| `karbi_folktales_1908` | **Karbi Folk-Lore & Tales** | Stack, Sardoka & Lyall (1908) | `FULLY_IMPORTED` | 3 ch / 44 pass | Public Domain (Gutenberg #48706) |
| `ramayana` | **The Ramayana of Valmiki** | Vālmīki / R. T. H. Griffith (1870) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (Gutenberg #24869) |
| `mahabharata` | **The Mahabharata of Vyasa** | Vyāsa / K. M. Ganguli (1883) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (Gutenberg #7864) |
| `panchatantra` | **The Panchatantra** | Vishnu Sharma / A. W. Ryder (1925) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (US 1925) |
| `hitopadesha` | **The Hitopadesha** | Narayana / Sir Edwin Arnold (1861) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (Gutenberg #13268) |
| `upanishads` | **The Upanishads** | Vedic Sages / F. Max Müller (1879) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (Gutenberg #3296) |
| `rigveda` | **The Hymns of the Rigveda** | Vedic Rishis / R. T. H. Griffith (1896) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain |
| `dhammapada` | **The Dhammapada** | Buddhist Canon / F. Max Müller (1881) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (Gutenberg #2017) |
| `jataka_tales` | **The Jataka Tales** | Buddhist Canon / E. B. Cowell (1895) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain |
| `arthashastra` | **Kautilya's Arthashastra** | Kauṭilya / R. Shamasastry (1915) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain |
| `indian_fairy_tales` | **Indian Fairy Tales** | Joseph Jacobs (1892) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (Gutenberg #7128) |
| `folk_tales_of_bengal` | **Folk-Tales of Bengal** | Rev. Lal Behari Day (1883) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (Gutenberg #38488) |
| `old_deccan_days` | **Old Deccan Days** | Mary Frere (1868) | `FULLY_IMPORTED` | 24 ch / 772 pass | Public Domain (Gutenberg #36696) |
| `aesop_fables` | **Aesop's Fables** | Aesop / V. S. Vernon Jones (1912) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (Gutenberg #11339) |
| `history_of_assam_1906` | **A History of Assam** | Sir Edward Gait (1906) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain |
| `buddhist_records_western_world` | **Si-Yu-Ki: Buddhist Records** | Xuanzang / Samuel Beal (1884) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain |
| `shakuntala` | **Shakuntala** | Kālidāsa / Arthur W. Ryder (1912) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain (Gutenberg #16655) |
| `history_of_hindu_chemistry` | **History of Hindu Chemistry** | Sir P. C. Ray (1902) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain |
| `english_mikir_vocabulary_sentences_1878` | **Vocabulary & Sentences** | Rev. R. E. Neighbor (1878) | `CATALOG_ONLY` | 0 ch / 0 pass | Public Domain |

* **Catalogue Integrity:** Books marked `CATALOG_ONLY` contain verified bibliographic and rights metadata, with explicit notes on missing acquisition portions. They never claim passage counts until the full text is verified and imported.
* **Complete Texts Imported:**
  * **The Bhagavad Gita:** Complete 18 chapters and 295 stanzas/passages with chapter titles, verse structure, and full-text search indexing.
  * **Karbi Folk-Lore & Folk-Tales:** 3 complete traditional narratives (The Story of a Frog, The Story of the Orphan and his Uncles, and The Story of Harata Kunwar) featuring 44 passages, including authentic Karbi language passages and parallel English translations.

---

### 2. Digital Book CLI Usage

All book operations are accessible via `karbi books`:

```bash
# 1. List registered books in the catalogue
karbi books list
karbi books list --status FULLY_IMPORTED
karbi books list --language sa

# 2. Inspect detailed book metadata and rights
karbi books info bhagavad_gita
karbi books info ramayana

# 3. Read passages and chapters
karbi books read bhagavad_gita --chapter 1 --limit 5
karbi books read karbi_folktales_1908 --chapter 1

# 4. Search book passages using SQLite FTS5 full-text search
karbi books search "Kurukshetra"
karbi books search "frog" --book karbi_folktales_1908

# 5. Import an authorized local book file (.jsonl, .json, .txt, .md)
karbi books import path/to/text.txt --book-id my_book --title "My Book" --dry-run
karbi books import path/to/text.txt --book-id my_book --title "My Book"

# 6. Validate book integrity and passage sequences
karbi books validate
karbi books validate --book-id bhagavad_gita

# 7. Display aggregated book library statistics
karbi books stats
```

---

### 3. Digital Book Python API

```python
import karbi

# List registered books
books = karbi.list_books(import_status="FULLY_IMPORTED")
for b in books:
    print(f"{b.book_id}: {b.canonical_title} ({b.imported_passages_count} passages)")

# Retrieve book metadata
meta = karbi.get_book_metadata("bhagavad_gita")
print(f"Title: {meta['canonical_title']}, Translator: {meta['translator']}")

# Read passages with chapter filtering and pagination
passages = karbi.get_book_passages("bhagavad_gita", chapter=1, limit=3)
for p in passages:
    print(f"[{p.passage_id}] Verse {p.verse}: {p.text[:60]}...")

# Full-text search across book passages
results = karbi.search_book_text("Kurukshetra")
for r in results:
    print(f"[{r.passage_id}] Match in {r.book_title}: \"{r.matched_snippet}\"")

# Check library statistics
stats = karbi.get_book_statistics()
print(f"Total Books: {stats['total_books']}, Fully Imported: {stats['fully_imported_books']}")
```

---

### 4. Multilingual Translation Alignment & Vocabulary Extraction

* **Bidirectional Passage Alignment (`karbi.books.translation`):**
  Passages support multi-directional translation linking (Karbi ↔ English, Hindi, Assamese, Bengali, Sanskrit, Urdu, and extensible regional languages). Every alignment records provenance (`published_translation`, `community_reviewed`, `machine_draft`, `unverified`) and translation citations.
* **Vocabulary Candidate Extraction (`karbi.books.vocabulary`):**
  A dedicated candidate workflow extracts words and phrases from book passages, links candidates to their exact book and passage locator, and checks against the core lexicon. **Unreviewed candidates remain isolated in `data/books/candidates/` and never enter the authoritative lexicon automatically.**

---

## Directory Structure

```
.
├── .gitignore          # Git exclusion rules
├── pyproject.toml      # Standard Python package configuration (setuptools + pytest)
├── LICENSE             # MIT License (software source code only)
├── DATA-LICENSE.md     # Terms of use for language data and cultural knowledge
├── README.md           # Project developer documentation
├── docs/               # Community review guidelines and templates
│   ├── COMMUNITY_REVIEW.md
│   └── community_gloss_review_template.csv
├── karbi.db            # Compiled SQLite runtime database with FTS5 (lexicon + book tables)
├── data/               # Source JSON Lines data
│   ├── books/          # Digital Book Library data
│   │   ├── catalog.json       # Master book catalogue (20 registered works)
│   │   ├── sources.jsonl      # Bibliographic source registry for books
│   │   ├── texts/             # Complete imported texts (.jsonl)
│   │   │   ├── bhagavad_gita.jsonl
│   │   │   └── karbi_folktales_1908.jsonl
│   │   ├── translations/      # Bidirectional translation alignments
│   │   ├── manifests/         # Atomic import manifests with SHA-256 checksums
│   │   └── candidates/        # Extracted vocabulary candidate queue
│   ├── lexicon/        # Sharded dictionary entries
│   ├── culture/        # Cultural records (rituals, folklore, deities)
│   └── sources/        # Bibliographic references and citations
├── src/
│   └── karbi/          # Python library source code
│       ├── __init__.py # Top-level package exports
│       ├── __main__.py # Executable module entry point (python -m karbi)
│       ├── api.py      # High-level search, lookup, and book operations
│       ├── cli.py      # Command-line interface (lookup, translate, search, books)
│       ├── dictionary.py # Headword lookup and spelling variants
│       ├── translator.py # Multilingual translation engine
│       ├── alphabet.py # Karbi orthography and phonetics
│       ├── grammar.py  # Classifiers, pronouns, numbers
│       ├── culture.py  # Cultural records and ethics policy
│       ├── books/      # Digital Book Library Subsystem
│       │   ├── __init__.py
│       │   ├── models.py      # BookMetadata, Passage, TranslationRecord, VocabularyCandidate
│       │   ├── catalog.py     # BookCatalog manager
│       │   ├── importer.py    # Formats parser, atomic writer, FTS5 indexer
│       │   ├── reader.py      # Passage streaming and pagination
│       │   ├── search.py      # FTS5 search across passages and metadata
│       │   ├── translation.py # Multilingual bidirectional alignment
│       │   ├── validation.py  # Book integrity and sequence validation
│       │   └── vocabulary.py  # Candidate extraction workflow
│       └── core/       # Database compilation, models, and validation
└── tests/              # Automated unit, integration, and packaging tests
    ├── test_alphabet_and_grammar.py
    ├── test_api.py
    ├── test_books.py   # Comprehensive digital book library test suite
    ├── test_cli.py
    ├── test_contributor_workflow.py
    ├── test_dataset.py
    ├── test_loader.py
    ├── test_packaging.py
    ├── test_resources.py
    ├── test_review.py
    ├── test_session.py
    ├── test_translation.py
    └── test_validation.py
```

---

## License & Data Terms

* **Software Code:** The original Python library code, CLI tools, and test suites are licensed under the [MIT License](LICENSE).
* **Language Data & Cultural Assets:** Lexical entries, historical citations, translation glosses, and cultural records are governed separately under [DATA-LICENSE.md](DATA-LICENSE.md). The software's MIT license applies only to original code and does not automatically grant rights to third-party source material or cultural data. Licensing and reuse permissions for the dataset are under review and not yet determined. Anyone considering reuse is advised to obtain legal advice and consult relevant Karbi community representatives.
