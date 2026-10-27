# Karbi Community Gloss Review & Lexical Correction Guide

This document outlines the protocol for Karbi community members, native speakers, bilingual educators, and linguistic researchers to review, validate, correct, or reject lexical entries and multilingual translations in the Karbi Language Library (`karbi`).

---

## 1. Context and Current Status

The `karbi` lexical database contains **516 historical source-attested entries** compiled from primary published documentation (*The Mikirs* 1908, *Linguistic Survey of India* 1903, *A Vocabulary in English and Mikir* 1878, and *An English-Mikir Vocabulary* 1904).

### Key Facts:
* **Source Attestation:** 515 entries have verified page citations from published historical literature (`SOURCE_ATTESTED`).
* **Citation Mismatch:** 1 entry (`KB-LEX-0000382`, `kāthē` vs. source printed `kārlē-sārpō` on p. 88) is flagged as `CITATION_MISMATCH` and requires native-speaker clarification.
* **Unverified Multilingual Translations (562 Backlog):** While English definitions are extracted directly from primary historical sources, the corresponding Hindi (206), Assamese (186), and Bengali (169) translations are provisional working candidates (`is_verified=False`).
* **Current Native-Speaker Verifications: 0.** No contemporary native-speaker endorsements have been recorded. No entries will be marked as verified without genuine community input.

---

## 2. Review Workflow

Reviewers can audit existing entries or propose corrections using the template provided at:
[`docs/community_gloss_review_template.csv`](file:///C:/Users/Hp/Documents/Arunachal-Pradesh-Lang-Python-Library/docs/community_gloss_review_template.csv)

### Review Decisions
Reviewers must assign one of the following decisions for each audited gloss:
* **`accepted`**: The proposed translation or definition accurately conveys the Karbi headword meaning in the specified language and dialect.
* **`corrected`**: The translation is partially accurate or uses non-standard phrasing; a specific correction is provided in the `correction` column.
* **`rejected`**: The translation is inaccurate, culturally inappropriate, or misleading; an explanation is required in the `notes` column.
* **`awaiting_review`**: Default state for candidate translations pending native-speaker assessment.

---

## 3. CSV Template Schema

Each row in `docs/community_gloss_review_template.csv` contains the following fields:

| Field Name | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `entry_id` | String | Yes | Unique entry identifier (e.g., `KB-LEX-0000001`). |
| `source_language` | String | Yes | ISO code of the reviewed gloss language (`hi`, `as`, `bn`, `en`, `mr`, `kha`). |
| `source_word` | String | Yes | The source language term or candidate translation under review. |
| `proposed_karbi_form` | String | Yes | The canonical Karbi headword or recommended spelling. |
| `proposed_gloss` | String | Yes | The definition or equivalent term in the reviewed language. |
| `source_evidence` | String | Yes | Basis of review: native speaker usage, oral tradition, published dictionary, or community body. |
| `reviewer_name_or_pseudonym`| String | Yes | Pseudonym, initials, elder title, or organization name (real legal name NOT required). |
| `reviewer_consent_or_attribution`| String | Optional | Consent and attribution preference (e.g., `Pseudonym consented`, `Anonymous / Community Elder`, `Institutional attribution consented`). |
| `dialect_or_community` | String | Optional | Dialect variety (e.g., Rongkhang, Chinthong, Amri, Dumrali/Plains). |
| `decision` | String | Yes | One of: `accepted`, `corrected`, `rejected`, `awaiting_review`. |
| `correction` | String | If corrected| The corrected translation string if decision is `corrected`. |
| `notes` | String | If rejected | Detailed explanation, cultural context, or dialectal reasoning. |
| `review_date` | String | Yes | Date of review in ISO-8601 format (`YYYY-MM-DD`). Cannot be a future date. |

---

## 4. Maintainer Evaluation & Evidence Guidelines

When evaluating submitted reviews, repository maintainers must follow strict standards:

1. **Authenticity First & Distinguishing Sources:**
   - Contemporary community review is strictly distinguished from colonial historical print citations (`SRC-PUB-*`).
   - Do not manufacture reviewer identities, review events, or consensus where none exists.
   - Genuine native-speaker feedback takes precedence over historical colonial glosses for contemporary spoken usage.
2. **Privacy and Attribution Consent:**
   - Community reviewers are **never required to disclose their legal name**. Pseudonyms, anonymous elder designations, and community group attributions are fully supported and respected.
3. **Dialect-Sensitive & Culturally Sensitive Entries:**
   - **Dialect Sensitivity:** Karbi has regional varieties (Rongkhang as the standard literary variety, alongside Chinthong, Amri, and Dumrali/Plains Karbi). Dialect-specific submissions are automatically flagged and must be attributed to their specific regional variety.
   - **Cultural Sensitivity:** Entries involving sacred rituals (e.g., *Chomangkan*), death rites, deity veneration, or traditional taboos must be routed for community elder consultation before changes are merged.
4. **Audit Trail Preservation:**
   - Approved reviews are recorded as `GlossReviewRecord` objects in the entry's provenance.
   - Status elevation to `is_verified=True` occurs only when an `accepted` or `corrected` review has verified reviewer attribution and valid date/locator metadata.
5. **Preserving Safeguards:**
   - Until a candidate gloss is formally reviewed, it must remain `is_verified=False`.
   - `verified_only=True` queries must continue to exclude all unverified glosses.

---

## 5. Validating and Submitting Reviews

Review submissions can be validated directly before submission using the built-in CLI:

```bash
karbi validate --review-csv docs/community_gloss_review_template.csv
```

Or via Python:
```python
import karbi

result = karbi.validate_community_review_csv("docs/community_gloss_review_template.csv")
print(result.report())
```

### Submission Steps:
1. Copy `docs/community_gloss_review_template.csv`.
2. Add your reviews, corrections, and preferred attribution.
3. Run `karbi validate --review-csv <your_file.csv>` to ensure syntax, IDs, and dates are valid.
4. Submit the completed CSV via a GitHub Issue or Pull Request to:
   `https://github.com/researchbuimb24-spec/Karbi-Assam-Lang-Python-Library`
