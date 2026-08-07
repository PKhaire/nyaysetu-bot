# Legal Content Review Checklist

## Release under review

- Content version: `legal-content-2026-08-r5`
- Supported experiences: free-text local guidance and the two-level Legal
  Guides menu
- Supported languages: English, conversational Hindi/Hinglish (`hi`), and
  Marathi (`mr`)
- Production gates: `LEGAL_CONTENT_REVIEWED_VERSION` must equal the approved
  `LEGAL_CONTENT_VERSION`, and `LEGAL_CONTENT_REVIEWED_ON=YYYY-MM-DD` must be
  the approval date.

Do not set either production review value until a qualified reviewer has
approved this exact content version. A later wording change requires a new
version and a new review.

## Reviewer scope

Review every category in `services/legal_knowledge.py`:

- Family
- Criminal
- Accident
- Property
- Business
- Job
- Consumer
- Banking and finance
- Other/document help

For each category, review:

- the summary;
- guided intake questions;
- immediate action steps;
- document checklist;
- urgent-escalation language;
- location-routing explanation;
- disclaimer;
- English, conversational Hindi/Hinglish, and Marathi meaning equivalence.

The category tree also exposes every subcategory in
`CATEGORY_SUBCATEGORIES`. Confirm that each label routes to an appropriate
category guide and does not imply specialised advice that the guide does not
provide. Separately review every entry in `_ISSUE_OVERLAYS`; these high-risk
issue notes can replace the category-level urgency wording.

For revision `legal-content-2026-08-r5`, specifically review the new rent or
tenancy, housing-society, and inheritance or will issue overlays, their
English/Hindi/Marathi labels, and the privacy warning shown in every guide.

## Required legal checks

- Content is general information and does not create an advocate-client
  relationship.
- No answer predicts a legal outcome.
- No answer invents a statute, authority, address, filing method, or limitation
  period.
- No answer tells a user to ignore a notice, summons, arrest risk, medical need,
  safety risk, or approaching deadline.
- Evidence-preservation guidance never encourages unlawful access, recording,
  removal, fabrication, alteration, or destruction.
- Criminal, domestic-violence, child-safety, accident, cyber-fraud, banking,
  dispossession, and other urgent scenarios contain safe escalation language.
- Document lists request only information reasonably necessary for preparation.
- No guide requests OTP, PIN, CVV, password, Aadhaar, PAN, full bank details, or
  other unnecessary identifiers in chat.
- The location message accurately describes NyaySetu's state/district
  consultation-routing process.
- Booking wording does not guarantee advocate availability, representation,
  resolution, refund, or outcome.
- Privacy, terms, cancellation, and refund policies are consistent with the
  guide and booking wording.

## Product checks

- A user can select a legal area and a category-specific issue without typing a
  private case narrative.
- `Not Sure` remains available in every category.
- Every guide fits within the WhatsApp 4,096-character text limit.
- Helpful/not-helpful feedback records only the selected guide and boolean
  response, not a new case narrative.
- A user can reopen guides, contact support, or start booking after feedback.
- Booking continues to collect state and district before payment.
- The local knowledge engine remains available when OpenAI, Claude, and Ollama
  are absent.

## Sign-off record

Record the following outside the source repository:

- reviewer name and professional role;
- content version reviewed;
- review date;
- languages personally reviewed;
- corrections requested and evidence that they were applied;
- approval owner;
- next scheduled review date.

After approval, configure:

```text
LEGAL_CONTENT_VERSION=legal-content-2026-08-r5
LEGAL_CONTENT_REVIEWED_VERSION=legal-content-2026-08-r5
LEGAL_CONTENT_REVIEWED_ON=YYYY-MM-DD
```

Never place reviewer personal documents, signatures, credentials, or private
client information in Git.
