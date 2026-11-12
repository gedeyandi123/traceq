// Inspection certificate 3.1 (EN 10204) for product-contact parts: a printed vendor form,
// signed and stamped by hand, published as a scan.

#import "common.typ": page-header, place, rows-table, sig, stamp
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.vendor)
#set text(lang: "en", size: 9pt, hyphenate: false)
#set par(justify: false)
#set page(paper: "a4", margin: (x: 1.8cm, top: 2.6cm, bottom: 2cm), header: page-header(d.vendor, d.doc_id, d.rev))
#set table(stroke: 0.5pt, inset: 5pt)

#align(center, text(size: 14pt, weight: "bold")[Inspection Certificate 3.1])
#align(center, text(size: 10pt)[according to EN 10204 · Product-contact parts])
#v(0.6em)

#table(
  columns: (4cm, 1fr),
  [Certificate no.], [#d.doc_id],
  [Date of issue], [#d.issued_on],
  [Manufacturer], [#d.vendor],
  [Customer], [#d.customer],
  [Equipment], [#d.equipment],
  [Machine serial no.], [#d.serial#place("serial")],
)
#v(0.4em)

#rows-table(
  (1.1cm, 1fr, 2.6cm, 2.4cm, 2.6cm),
  ([Pos.], [Part], [Material grade], [Material no.], [Heat no.]),
  d.items.map(i => ([#i.pos], [#i.part], [#i.material#place(i.key)], [#i.number], [#i.heat])),
)
#v(0.6em)
#d.declaration

#v(1.2em)
#grid(
  columns: (1fr, auto),
  table(
    columns: (3.6cm, 4.2cm),
    [Authorised inspector], [#d.inspector],
    [Signature], sig(d.signature),
    [Date], [#d.issued_on],
  ),
  align(horizon, stamp(d.stamp)),
)
