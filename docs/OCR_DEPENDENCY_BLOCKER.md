# OCR Dependency Resolution

Date: 2026-08-02  
Status: **RESOLVED — V2 EXTRACTION MAY PROCEED**

## Resolution

Tesseract 5.4.0.20240606 is installed at `C:\Program Files\Tesseract-OCR\tesseract.exe`. Because the system installation directory is protected, the three official `tessdata_fast` files are stored in the user-scoped directory `C:\Users\abder\AppData\Local\DevoteamOCR\tessdata`. The repair pipeline sets `TESSDATA_PREFIX` explicitly and does not depend on the shell `PATH`.

The executable reports `ara`, `eng`, and `fra`, and a `pytesseract` smoke test using the combined `fra+eng+ara` language setting passed inside the project virtual environment.

The section below is retained as the original blocker record and recovery procedure.

---

## Original blocker record

## Blocking condition

The Tesseract executable is not installed or discoverable through `PATH`, `Get-Command`, or the standard Windows installation locations. Therefore the required French, English, and Arabic OCR packs cannot be verified or used.

The targeted repair manifest is valid, but no repaired page text, v2 chunks, embeddings, or indexes have been created. Creating them would require fabricating OCR availability or silently using incomplete language support, both of which are prohibited.

## Detected environment

| Dependency | Result |
|---|---|
| PyMuPDF | PASS — 1.26.4 |
| Pillow | PASS — 11.3.0 |
| pytesseract wrapper | PASS — 0.3.13 |
| Tesseract executable | **MISSING** |
| `fra` trained data | Unverifiable because executable is missing |
| `eng` trained data | Unverifiable because executable is missing |
| `ara` trained data | Unverifiable because executable is missing |
| Local E5 model | PASS — `intfloat/multilingual-e5-base` |
| Pinned model revision | PASS — `a114a4100c6714cf21651971eefe9191a4415dbb` |
| Embedding dimension | PASS — 768 |
| Free space on C: | 34,898,460,672 bytes (approximately 32.5 GiB) |

The local `winget` catalogue resolves `UB-Mannheim.TesseractOCR` version `5.4.0.20240606`.

## Windows installation

Open PowerShell. If Windows requests elevation, run PowerShell as Administrator.

```powershell
winget install --id UB-Mannheim.TesseractOCR --exact `
  --accept-package-agreements --accept-source-agreements
```

Start a new PowerShell session, then ensure the executable is visible:

```powershell
$TesseractRoot = 'C:\Program Files\Tesseract-OCR'
$env:Path = "$TesseractRoot;$env:Path"
& "$TesseractRoot\tesseract.exe" --version
```

Install or refresh the three required official `tessdata_fast` language files:

```powershell
$TesseractRoot = 'C:\Program Files\Tesseract-OCR'
$Tessdata = Join-Path $TesseractRoot 'tessdata'

Invoke-WebRequest `
  'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/eng.traineddata' `
  -OutFile (Join-Path $Tessdata 'eng.traineddata')

Invoke-WebRequest `
  'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/fra.traineddata' `
  -OutFile (Join-Path $Tessdata 'fra.traineddata')

Invoke-WebRequest `
  'https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/ara.traineddata' `
  -OutFile (Join-Path $Tessdata 'ara.traineddata')
```

If writing to `Program Files` is denied, rerun that PowerShell session as Administrator. Do not download trained data from an unverified third-party location.

## Required verification

Run:

```powershell
$TesseractRoot = 'C:\Program Files\Tesseract-OCR'
& "$TesseractRoot\tesseract.exe" --version
& "$TesseractRoot\tesseract.exe" --list-langs
```

The language list must explicitly contain all three entries:

```text
ara
eng
fra
```

Then verify the project environment:

```powershell
cd C:\Users\abder\Downloads\Devoteam_AI_Workspace\devoteam-reference-mvp
$env:TESSDATA_PREFIX = 'C:\Program Files\Tesseract-OCR\tessdata'
.\.venv\Scripts\python.exe -c "import pytesseract; print(pytesseract.get_tesseract_version()); print(pytesseract.get_languages(config=''))"
.\scripts\validate_environment.ps1
```

Do not continue unless `ara`, `eng`, and `fra` are all reported.

## Resume point

After installation, rerun dependency validation. If it passes, resume at targeted page re-extraction using `data/versions/v2/TARGETED_REPAIR_MANIFEST.csv`. Do not rerun the completed review import or alter the two imported XLSX files.
