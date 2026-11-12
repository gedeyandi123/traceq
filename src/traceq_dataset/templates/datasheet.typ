// Vendor technical datasheet (English): dense key-value tables for one machine.
// All text comes from render.py via sys.inputs.data; this file only lays it out.

#import "common.typ": page-header, place
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.vendor)
#set text(lang: "en", size: 8pt, hyphenate: false)
#set par(justify: false, leading: 0.5em)
#set page(paper: "a4", margin: (x: 1.5cm, top: 2.4cm, bottom: 1.8cm), header: page-header(d.vendor, d.doc_id, d.rev))
#set table(stroke: 0.4pt + luma(120), inset: (x: 4pt, y: 3pt))

#let section(s) = table(
  columns: (1fr, 3.2cm),
  fill: (_, y) => if y == 0 { luma(215) } else if calc.even(y) { luma(245) } else { none },
  table.header(table.cell(colspan: 2)[*#s.title*]),
  ..s.rows.map(r => ([#r.label], [#r.value#place(r.key)])).flatten(),
)

#text(size: 13pt, weight: "bold")[Technical Datasheet]
#h(1fr)
#text(size: 10pt)[#d.subtitle]
#v(0.3em)

#table(
  columns: (3.4cm, 1fr, 3.4cm, 1fr),
  fill: (x, _) => if calc.even(x) { luma(235) } else { none },
  [Manufacturer], [#d.vendor], [Document no.], [#d.doc_id],
  [Model], [#d.model], [Revision], [#d.rev],
  [Machine serial no.], [#d.serial#place("serial")], [Issue date], [#d.issued_on],
  [Customer], [#d.customer], [Customer equipment tag], [#d.tag],
)
#v(0.4em)

#grid(
  columns: (1fr, 1fr),
  column-gutter: 8pt,
  row-gutter: 6pt,
  stack(spacing: 6pt, ..d.left.map(section)),
  stack(spacing: 6pt, ..d.right.map(section)),
)

#v(0.6em)
#text(size: 7pt)[#d.note]

#v(0.6em)
#table(
  columns: (2.6cm, 1fr, 1fr, 2.4cm),
  [*Prepared by*], [#d.prepared.name], [#d.prepared.signature], [#d.prepared.date],
)
