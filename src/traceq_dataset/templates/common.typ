// Shared helpers for all document templates.

// Records the page of a string the answer key relies on; render.py queries <placed>.
#let place(key) = context [#metadata((key: key, page: here().page()))<placed>]

// A handwritten entry: OFL handwriting font in pen ink. Records the page and the bounding
// box (pt, top-left origin, glyph ascender to descender) for the OCR answer key.
#let ink = rgb("#1b2a72")
#let hand(key, body, size: 12.5pt) = box({
  set text(font: "Caveat", size: size, fill: ink, top-edge: "ascender", bottom-edge: "descender")
  context {
    let p = here().position()
    let s = measure(body)
    [#metadata((key: key, page: p.page, x: p.x.pt(), y: p.y.pt(), w: s.width.pt(), h: s.height.pt()))<placed>]
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
