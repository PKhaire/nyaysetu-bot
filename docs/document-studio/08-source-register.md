# Source Register: Maharashtra Residential Leave and Licence

Status: research baseline for advocate review, retrieved 27 August 2026. This
register is not a legal opinion. The advocate approving a Template Version must
verify current text, commencement, amendments and Maharashtra registration
practice before activation.

## Source status labels

- `AUTHORITATIVE_TEXT`: legislation published through India Code or Gazette.
- `OFFICIAL_GUIDANCE`: an official process/notification source that may change.
- `OFFICIAL_REFERENCE_ONLY`: useful official sample, not an approved NyaySetu
  template and not a substitute for advice.
- `PROVIDER_CONTRACT`: platform capability or provider rule.
- `ADVOCATE_INTERPRETATION_REQUIRED`: a conclusion that must not be automated
  until the approving advocate records it.

## Register

| ID | Source and publisher | Status | Product control / implication | Approval action |
| --- | --- | --- | --- | --- |
| SRC-MH-RCA-55 | [Maharashtra Rent Control Act, 1999](https://www.indiacode.nic.in/bitstream/123456789/15817/1/the_maharashtra_rent_control_act_1999.pdf), India Code, especially section 55 | `AUTHORITATIVE_TEXT` | Agreement must be in writing and registered; responsibility and evidentiary consequences must be explained accurately. | Confirm current section text and product instructions. |
| SRC-MH-RCA-24 | Same Act, section 24 | `AUTHORITATIVE_TEXT` and `ADVOCATE_INTERPRETATION_REQUIRED` | May affect licence-expiry/possession drafting; software must not promise recovery or enforceability. | Approve or reject each related clause and explanation. |
| SRC-MH-STAMP-36A | [Maharashtra Stamp Act](https://www.indiacode.nic.in/bitstream/123456789/16251/1/the_maharashtra_stamp_act.pdf), Article 36A | `AUTHORITATIVE_TEXT` | Stamp-duty inputs include licence fee, non-refundable consideration and refundable deposit treatment. Do not hard-code a payable amount without a current official calculation. | Approve input mapping, formula explanation and disclaimer. |
| SRC-MH-IGR-CHARTER | [IGR Citizen Charter](https://grievanceigr.maharashtra.gov.in/pdf/Citizen_Charter_English.pdf), Maharashtra IGR | `OFFICIAL_GUIDANCE` | A checklist may describe typical registration inputs, but must direct the user to current IGR requirements. | Verify current process and document list. |
| SRC-MH-IGR-NOTICES | [IGR notifications](https://grievanceigr.maharashtra.gov.in/publication/notifications), Maharashtra IGR | `OFFICIAL_GUIDANCE` | Release review checks relevant e-registration, fee and procedure notifications. | Record URLs/date/decision in approval evidence. |
| SRC-MH-LJ-SAMPLE | [Official reference agreement](https://lj.maharashtra.gov.in/Site/Upload/Pdf/Leave-and-License-Agreement.pdf), Maharashtra Law and Judiciary | `OFFICIAL_REFERENCE_ONLY` | Drafting reference only. Do not copy blindly or describe it as government approval. | Clause-by-clause comparison by advocate. |
| SRC-IEA-LICENCE | [Indian Easements Act, 1882](https://www.indiacode.nic.in/bitstream/123456789/2349/1/A1882-05.pdf), Chapter VI | `AUTHORITATIVE_TEXT` and `ADVOCATE_INTERPRETATION_REQUIRED` | Product must not imply automatic tenancy or enforceability conclusions. | Approve definitions, possession/use and termination language. |
| SRC-REG-ACT | [Registration Act, 1908](https://www.indiacode.nic.in/bitstream/123456789/18914/1/a1908-16.pdf), India Code | `AUTHORITATIVE_TEXT` | Registration remains outside NyaySetu delivery; the customer gets current-process instructions. | Verify execution/presentation implications. |
| SRC-CONTRACT-ACT | [Indian Contract Act, 1872](https://www.indiacode.nic.in/bitstream/123456789/2187/2/A187209.pdf), especially capacity and consent provisions | `AUTHORITATIVE_TEXT` | V1 is restricted to competent adult individuals acting for themselves; coercion/uncertainty routes out. | Approve eligibility wording. |
| SRC-DPDP-ACT | [Digital Personal Data Protection Act, 2023](https://www.indiacode.nic.in/bitstream/123456789/22037/2/a2023-22.pdf), India Code | `AUTHORITATIVE_TEXT` | Clear notice, purpose limitation, correction/erasure and grievance handling are designed in now. | Privacy review against provisions then in force. |
| SRC-DPDP-RULES | [Digital Personal Data Protection Rules, 2025](https://www.meity.gov.in/documents/act-and-policies/digital-personal-data-protection-rules-2025-gDOxUjMtQWa?hl=en-US), MeitY | `AUTHORITATIVE_TEXT` with phased commencement | Gazette G.S.R. 846(E) provides immediate, one-year and eighteen-month commencement groups. Notice, safeguards, breach, retention and contact controls in the later group must be mapped before they commence, even if the first launch precedes that date. | Record provisions in force and the scheduled next gate at every release. |
| SRC-INDIAPOST-PIN | [All India Pincode Directory](https://www.data.gov.in/catalog/all-india-pincode-directory-through-webservice), Department of Posts via data.gov.in; packaged from [IndiaPost/pin](https://github.com/IndiaPost/pin/tree/9903190eb2073826f869f0c384bb83a34a21ebd5) | `OFFICIAL_GUIDANCE` | A deterministic Maharashtra subset suggests district, taluka and post-office names after PIN entry. It is never treated as the customer's legal address or evidence of title/authority. | Refresh by reviewed source revision; confirm fallback and exact customer address confirmation. |
| SRC-WA-INTERACTIVE | [WhatsApp interactive messages](https://whatsapp.github.io/WhatsApp-Nodejs-SDK/api-reference/messages/interactive/), Meta-owned archived SDK reference | `PROVIDER_CONTRACT` | Reply buttons allow three actions; use a list for the four-item home menu with numbered fallback. | Provider smoke test before activation. |
| SRC-WA-DOCUMENT | [WhatsApp Business Platform media reference](https://www.postman.com/meta/whatsapp-business-platform/folder/13382743-ecb27be5-4d27-4763-bbee-6a8002c04bf3), Meta Postman workspace | `PROVIDER_CONTRACT` | PDF/DOCX is supported, but V1 sends a short-lived NyaySetu link so authorization and expiry remain server-controlled. | Confirm current media/link/template rules. |

### DPDP commencement checkpoint

G.S.R. 846(E), published 13 November 2025, states that Rules 1, 2 and
17-21 commenced on publication, Rule 4 commences one year after publication,
and Rules 3, 5-16, 22 and 23 commence eighteen months after publication. On
the 27 August 2026 research date, the one-year and eighteen-month groups had
not yet reached their stated commencement dates. Release review must verify
the Gazette/corrigendum and current legal position rather than relying only on
this calculated timeline.

## Change monitoring

The template owner performs a source check before every new Template Version
and at least every six months while active. A relevant legal, IGR or provider
change suspends new sales until impact is recorded. A source change never
silently alters an already-paid order.
