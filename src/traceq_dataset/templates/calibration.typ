// Calibration certificate of a site test instrument, issued by an external lab: printed,
// signed and stamped by hand, published as a scan.

#import "common.typ": page-header, place, rows-table, sig, stamp
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.lab)
#set text(lang: "en", size: 9pt, hyphenate: false)
#set par(justify: false)
#set page(paper: "a4", margin: (x: 1.8cm, top: 2.6cm, bottom: 2cm), header: page-header(d.lab, d.doc_id, d.rev))
#set table(stroke: 0.5pt, inset: 5pt)

#align(center, text(size: 14pt, weight: "bold")[Calibration Certificate])
#v(0.6em)

#table(
  columns: (4.2cm, 1fr),
  [Certificate no.], [#d.doc_id],
  [Customer], [#d.customer],
  [Instrument], [#d.instrument],
  [Asset ID], [#d.asset#place("instrument")],
  [Serial no.], [#d.serial#place("serial")],
  [Date of calibration], [#d.calibrated_on#place("calibrated_on")],
  [Valid until], [#d.valid_until#place("valid_until")],
  [Date of issue], [#d.issued_on],
)

== Method
#d.method

== Results
#rows-table(
  (1fr, 1fr, 1fr, 1fr),
  d.header,
  d.results.map(r => ([#r.nominal], [#r.reading], [#r.error], [#r.uncertainty])),
)
#v(0.3em)
#d.statement

#v(1.2em)
#grid(
  columns: (1fr, auto),
  rows-table(
    (3cm, 4cm, 3.2cm),
    ([Role], [Name], [Signature]),
    d.signatures.map(s => ([#s.role], [#s.name], sig(s.signature))),
  ),
  align(horizon, pad(left: 10pt, stamp(d.stamp))),
)
