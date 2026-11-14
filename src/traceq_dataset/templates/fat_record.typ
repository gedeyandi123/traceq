// FAT as a test-record document (TP-202 vendor layout, English): as-built machine data,
// the customer's release, one record block per test, deviations and attachments. All text
// comes from render.py via sys.inputs.data; this file only lays it out.

#import "common.typ": place
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.vendor)
#set text(lang: "en", size: 9pt, hyphenate: false)
#set par(justify: false)
#set page(
  paper: "a4",
  margin: (x: 1.6cm, top: 2.4cm, bottom: 2.4cm),
  header: grid(
    columns: (1fr, auto),
    text(weight: "bold", size: 10pt)[#upper(d.vendor)],
    [#d.doc_id / #d.rev],
  ),
  footer: context [
    #set text(size: 8pt)
    Factory acceptance test record #h(1fr) Sheet #counter(page).get().first() of #counter(page).final().first()
  ],
)
#set table(stroke: 0.4pt + luma(90), inset: 4pt)
#show heading: set block(above: 1.1em, below: 0.5em)
#show heading: it => block(fill: luma(225), width: 100%, inset: 4pt, text(size: 10pt, it.body))

#text(size: 16pt, weight: "bold")[FACTORY ACCEPTANCE TEST RECORD]
#linebreak()
#text(size: 11pt)[#d.title]
#v(0.4em)
#grid(
  columns: (1fr, 1fr),
  gutter: 8pt,
  table(
    columns: (3cm, 1fr),
    [Record no.], [#d.doc_id],
    [Revision], [#d.rev],
    [Date of issue], [#d.issued_on],
  ),
  table(
    columns: (3cm, 1fr),
    [Customer], [#d.customer],
    [Machine], [#d.equipment],
  ),
)

= A. Machine data (as built)
#table(
  columns: (6cm, 1fr),
  ..d.as_built.map(r => ([#r.label], if "key" in r [#r.value#place(r.key)] else [#r.value])).flatten(),
)

= B. Release of the test procedure
#table(
  columns: (4.4cm, 1fr, 1fr, 1fr, 2.2cm),
  [*Step*], [*Name*], [*Company*], [*Signature*], [*Date*],
  ..d.release.map(a => ([#a.role], [#a.name], [#a.company], [#emph[#a.signature]], [#a.date])).flatten(),
)

= C. Test records
#for r in d.records {
  block(breakable: false, table(
    columns: (3.4cm, 1fr),
    table.cell(colspan: 2, fill: luma(240))[*Test case #r.step*],
    [Procedure], [#r.description],
    [Required], [#r.acceptance#place(r.step + ".acceptance")],
    [Measured], [#r.observed#place(r.step + ".observed")],
    [Verdict], [*#r.result*#place(r.step + ".result")],
  ))
}

= D. Deviations
#d.deviations#place("deviations")

= E. Attachments
#for a in d.attachments [
  - #a.text#place(a.key)
]

= F. Test execution
#table(
  columns: (4.4cm, 1fr, 1fr, 1fr, 2.2cm),
  [*Role*], [*Name*], [*Company*], [*Signature*], [*Date*],
  ..d.execution.map(a => ([#a.role], [#a.name], [#a.company], [#emph[#a.signature]], [#a.date])).flatten(),
)
