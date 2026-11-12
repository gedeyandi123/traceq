// Functional design specification (vendor document, English, born-digital). All text comes
// from render.py via sys.inputs.data; this file only lays it out.

#import "common.typ": page-header, place, rows-table
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.vendor)
#set text(lang: "en", size: 9.5pt, hyphenate: false)
#set par(justify: false)
#set page(paper: "a4", margin: (x: 1.8cm, top: 2.6cm, bottom: 2cm), header: page-header(d.vendor, d.doc_id, d.rev))
#set table(stroke: 0.5pt, inset: 5pt)
#show heading: set block(above: 1.2em, below: 0.6em)
#show heading.where(level: 1): set text(size: 11pt)
#show heading.where(level: 2): set text(size: 10pt)
#set heading(numbering: "1.1")

#align(center, text(size: 14pt, weight: "bold")[Functional Design Specification])
#align(center, text(size: 11pt)[Control system])
#v(0.5em)

#table(
  columns: (4cm, 1fr),
  [Document no.], [#d.doc_id],
  [Revision], [#d.rev],
  [Issue date], [#d.issued_on],
  [Equipment], [#d.equipment],
  [Model / serial no.], [#d.model / #d.serial],
  [Customer], [#d.customer],
  [Manufacturer], [#d.vendor],
)

= Purpose
#d.purpose

= System overview
#d.overview

= Operating modes
#rows-table((3cm, 1fr), ([Mode], [Behaviour]), d.modes.map(m => ([#m.name], [#m.text])))

#for s in d.sections [
  = #s.title
  #for f in s.functions [
    == #f.label#place(f.key)
    #f.description
  ]
]

= Approval
#rows-table(
  (2.6cm, 3.6cm, 1fr, 1fr, 2.4cm),
  ([Role], [Company], [Name], [Signature], [Date]),
  d.approvals.map(a => ([#a.role], [#a.company], [#a.name], [#emph[#a.signature]], [#a.date])),
)
