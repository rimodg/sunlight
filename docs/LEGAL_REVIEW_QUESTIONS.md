# Questions for a future legal reviewer

## LEGAL-001: section 53 contract entry versus the published signature field

Recorded November 13, 2026; issue #20. Open legal interpretation question.

What evidence establishes that a particular FTS `contracts[].dateSigned`
value is the date of entering into a contract for PA section 53(1), and what
must be checked where those events differ? Does any applicable primary
instrument establish a universal order between entry and signature, rather
than describing circumstances in which they coincide?

The enacted section 53 uses entry, not signature. Cabinet Office Contract
Details Notices guidance, paragraph 24, states:

> When all of those elements have been satisfied will be fact-specific.

The same paragraph gives signature as one possible event and gives other
possible bases, including an event occurring or services/works starting. It
leaves the relevant date to the contracting authority based on circumstances.
No universal ordering between entry and signature was found in the provisions
and official guidance read. That is a bounded reading, not a legal opinion
that no such principle exists anywhere. The full Act XML was also searched
for signed/signature/signing; the matches concerned international agreements,
not a section-53 ordering rule. No one-sided inference has been built.

[Official guidance](https://www.gov.uk/government/publications/procurement-act-2023-guidance-documents-procure-phase/guidance-contract-details-notices-html),
paragraphs 23-24; [section 53](https://www.legislation.gov.uk/ukpga/2023/54/section/53);
[hashed guidance receipts](../research/section53_2026-11-13/guidance-sources.json);
[full Act search receipt](../research/section53_2026-11-13/order-check.json).

Owner decision, November 13: require cited evidence explicitly confirming the
contract-entry date. Never substitute `dateSigned`. A signature-to-publication
gap may be a plain measurement, clearly labelled as not a legal assessment.
This conservatively resolves implementation scope; it does not answer the
underlying legal mapping question. Revisit only with the owner's decision on
cited primary evidence, under COLLABORATION section 6.
