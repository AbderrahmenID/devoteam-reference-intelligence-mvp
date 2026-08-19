# Reference pack template analysis

## Source and inspection method

- Source: `templates/reference_pack/source/OT_DVT_SDSI__OrangeBANK.pdf`
- SHA-256: `bc01334088c95c3796f1b98586e4980c66fd084c45174eec23ff03195bb39334`
- Inspected pages: 10–29, rendered locally with Poppler and reviewed at native
  16:9 proportions.
- PDF canvas: 960 × 540 points, equivalent to 13.333 × 7.5 inches, 16:9.

The PDF is a visual reference only. Generated presentations do not copy entire
source pages or use them as slide backgrounds.

## Visual system

The deck uses a white canvas, near-black headings, medium-gray body copy, and a
coral accent sampled directly from editable PDF elements as `#F8475E`. The
dominant source font is Verdana around 10.7–11 pt for dense body areas. New
slides retain Verdana for Latin text and use Arial for Arabic glyph coverage.

Top-level headings sit at the upper-left with a short, thick coral underline.
The small Devoteam footer is aligned near the lower-left edge and the page
number is aligned near the lower-right edge. The outer horizontal margin is
approximately 0.55 inches.

## Page 10 — section divider

Page 10 is intentionally sparse: an oversized coral section number occupies the
left, a two-line dark heading is centered in the middle third, and a cropped
rounded visual anchors the lower-right corner. The footer and slide number are
kept small. The programmatic divider preserves this hierarchy using editable
text and geometric coral shapes.

## Pages 11–17 — reference summaries

Summary pages contain up to three horizontal reference cards. Each row has:

- a coral mission-title block on the left;
- a narrow coral directional wedge;
- a light service-bullet area in the center;
- a bordered client/logo area on the right;
- coral square bullets and compact gray copy.

The readable source density is three cards per slide, normally three to six
short bullets per card. The generated layout uses a minimum 10 pt body size and
will paginate rather than shrink below that threshold. Missing client logos are
represented by a clean client-name card.

## Pages 18–29 — evidence and justification annex

The annex uses a bold upper-left title, coral underline, and one of two content
patterns inside thin coral frames:

- one full-width evidence item, sometimes containing several portrait pages;
- two side-by-side evidence items, usually one portrait page each.

Several source examples contain signatures, contact details, stamps and legal
boilerplate. Those elements are explicitly prohibited in generated output.
Because the authorized MVP does not contain the raw evidence documents locally,
the safe default is one or two professional evidence cards per slide. A source
crop may be used only when a future approved local source is registered and the
crop passes display, lineage and confidentiality checks.

## Implemented density and safety limits

- Summary: maximum three references per slide, 3–6 bullets per reference.
- Detail: one reference per slide with separated metadata, service, rationale
  and citation regions.
- Evidence: one or two cards per slide; never below 10 pt.
- No raw OCR, full-page backgrounds, local paths, signatures, contacts,
  internal retrieval scores or unapproved logos.
- Long source content is selected at sentence/bullet boundaries and paginated;
  unsupported replacement facts are never generated.
