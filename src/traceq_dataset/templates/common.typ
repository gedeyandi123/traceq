// Shared helpers for all document templates.

// Records the page of a string the answer key relies on; render.py queries <placed>.
#let place(key) = context [#metadata((key: key, page: here().page()))<placed>]

// A handwritten entry: OFL handwriting font in pen ink. Records the page and the bounding
// box (pt, top-left origin, glyph ascender to descender) for the OCR answer key.
// measure() gives advance widths; slanted handwriting glyphs overhang them, so the box is
// padded by `overhang` on the left and twice that on the right.
#let ink = rgb("#1b2a72")
#let overhang = 0.15em
#let hand(key, body, size: 12.5pt) = box({
  set text(font: "Caveat", size: size, fill: ink, top-edge: "ascender", bottom-edge: "descender")
  context {
    let p = here().position()
    let s = measure(body)
    let pad = overhang.to-absolute().pt()
    [#metadata((
      key: key,
      page: p.page,
      x: p.x.pt() - pad,
      y: p.y.pt(),
      w: s.width.pt() + 3 * pad,
      h: s.height.pt(),
    ))<placed>]
  }
  body
})

// A handwritten value written over an earlier one in the same place (no strike-through).
#let overwrite(key, original, final) = box[#std.place(hand(key + ".original", original))#hand(key, final)]

// A rubber stamp: rotated outline box with ink of reduced opacity.
#let stamp(lines, angle: -8deg, color: rgb(170, 30, 40, 190)) = rotate(angle, reflow: true, box(
  stroke: 1.6pt + color,
  inset: (x: 7pt, y: 5pt),
  radius: 2pt,
  align(center, text(size: 8.5pt, weight: "bold", fill: color, lines.join(linebreak()))),
))

// A table whose rows are arrays of cells.
#let rows-table(columns, header, rows) = table(
  columns: columns,
  table.header(..header.map(h => strong(h))),
  ..rows.flatten(),
)

// A handwritten signature (not placed: the answer key does not rely on it).
#let sig(name) = text(font: "Caveat", size: 15pt, fill: ink, skew(ax: -10deg, name))

// Page set-up shared by the vendor and lab documents: issuer left, number and page right.
#let page-header(issuer, doc_id, rev) = grid(
  columns: (1fr, auto),
  [*#issuer*],
  context [#doc_id · Rev. #rev · Page #counter(page).get().first() of #counter(page).final().first()],
)
