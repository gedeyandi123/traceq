// FAT protocol and report (vendor document, English). All text comes from render.py
// via sys.inputs.data; this file only lays it out.

#import "common.typ": place, rows-table
#let d = json(bytes(sys.inputs.data))

#set document(title: d.doc_id + " rev " + str(d.rev), author: d.vendor)
#set text(lang: "en", size: 9.5pt, hyphenate: false)
#set par(justify: false)
#set page(
  paper: "a4",
  margin: (x: 1.8cm, top: 2.8cm, bottom: 2cm),
  header: grid(
    columns: (1fr, auto),
    [*#d.vendor*],
    context [#d.doc_id · Rev. #d.rev · Page #counter(page).get().first() of #counter(page).final().first()],
  ),
)
#set table(stroke: 0.5pt, inset: 5pt)
#show heading: set block(above: 1.2em, below: 0.6em)
#show heading: set text(size: 11pt)
#set heading(numbering: "1.")

#align(center, text(size: 14pt, weight: "bold")[Factory Acceptance Test – Protocol and Report])
#align(center, text(size: 12pt)[#d.title])
#v(0.5em)

#table(
  columns: (4cm, 1fr),
  [Document no.], [#d.doc_id],
  [Revision], [#d.rev],
  [Issue date], [#d.issued_on],
  [Equipment], [#d.equipment],
  [Serial no.], [#d.serial],
  [Manufacturer], [#d.vendor],
)

= Purpose
#d.purpose

= Approval before execution
#rows-table(
  (2.6cm, 1fr, 1fr, 1fr, 2.4cm),
  ([Role], [Name], [Company], [Signature], [Date]),
  d.approvals.map(a => ([#a.role], [#a.name], [#a.company], [#emph[#a.signature]], [#a.date])),
)

= Test results
Pass/Fail is recorded against the acceptance criterion of each step.
#rows-table(
  (2cm, 1fr, 2.6cm, 2.4cm, 1.4cm),
  ([Step], [Test], [Acceptance criterion], [Result], [Pass/Fail]),
  d.steps.map(s => (
    [#s.step],
    [#s.description],
    [#s.acceptance#place(s.step + ".acceptance")],
    [#s.observed#place(s.step + ".observed")],
    [#s.result],
  )),
)

= Deviations
#d.deviations

= Execution
#rows-table(
  (2.6cm, 1fr, 1fr, 1fr, 2.4cm),
  ([Role], [Name], [Company], [Signature], [Date]),
  d.execution.map(a => ([#a.role], [#a.name], [#a.company], [#emph[#a.signature]], [#a.date])),
)
