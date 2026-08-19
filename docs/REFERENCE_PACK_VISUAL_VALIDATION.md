# Reference pack visual validation

`scripts/validate_reference_pack_visuals.py` reopens each PPTX, renders the PDF
with PyMuPDF, produces contact-sheet previews, and validates slide/page parity,
bounds, text-box overlap, titles, slide numbers, footer image, evidence minimum
font, selected/evidence linkage, source citations and Unicode.

| Case | Language | References | PPTX slides | PDF pages | Latency | Result |
|---|---:|---:|---:|---:|---:|---:|
| fr-one | French | 1 | 5 | 5 | 2.10 s | PASS |
| en-three | English | 3 | 8 | 8 | 2.96 s | PASS |
| ar-four | Arabic | 4 | 10 | 10 | 3.81 s | PASS |
| fr-ten | French | 10 | 21 | 21 | 7.28 s | PASS |

Previews are under `audit/reference_pack/previews/`; the machine-readable result
is `audit/reference_pack/VISUAL_VALIDATION.json`. Manual review also confirmed
readable card density, clean client-name fallback, preserved French accents,
safe Arabic RTL, and the absence of attestation boilerplate, signatures,
contacts, internal scores and local paths.

The authorized MVP contains no raw evidence documents locally, so all audited
annexes use evidence cards. PyMuPDF crop support remains fail-closed until an
approved hash-matched local source root is registered.

The presentation/PDF previews were rendered and inspected successfully. The
separate in-app browser runtime exposed no controllable browser instance for a
final UI screenshot; UI validation therefore relies on frontend tests,
lint/types/build and the live HTTP/API workflow.
