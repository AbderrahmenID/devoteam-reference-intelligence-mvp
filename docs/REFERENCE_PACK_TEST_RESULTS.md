# Reference pack test results

## Focused implementation gate

- Backend reference-pack suite: 12 passed.
- Frontend selection/generation state suite: 7 passed.
- Frontend ESLint: pass, zero warnings.
- Frontend production build/type check: pass.
- Real LibreOffice PPTX-to-PDF conversion: pass.
- Visual validation matrix: 4/4 packs pass.

Covered cases include empty, one, three, four and ordered selections; duplicate,
unknown and quarantined IDs; retrieval-only/display-prohibited evidence; missing
pages; French and Arabic Unicode; logo fallback; summary/evidence pagination;
PPTX/PDF creation; manifest fields and hashes; traversal prevention; prohibited
score/path scans; API create/status/download routes; progress, downloads and
recoverable frontend errors.

The complete repository/lifecycle gate is run with:

```powershell
.\scripts\test.ps1
.\start.ps1
.\scripts\demo_check.ps1
.\stop.ps1
```

The test runner also preserves the human-judgment guard: no relevance metric is
reported when qualified qrels are absent.

Final complete result on 2026-08-03: 87/87 Python tests passed in 60.74 s,
7/7 frontend tests passed, seven dedicated v2 integrity tests passed, frontend
lint/types/build passed, live multilingual/demo generation passed, and ports
3000/8000 were closed after controlled shutdown.

The in-app browser runtime exposed no controllable browser instance during the
final UI inspection attempt. No unrelated browser surface was substituted;
frontend behavior is covered by the seven state tests, ESLint/type/build gate,
live page HTTP 200 and end-to-end API/download smoke flow.
