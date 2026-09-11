# Advocate identity and legal-decision boundary

**Status:** Accepted

Advocate-issued products reuse the existing named password-plus-TOTP identity
infrastructure with an `ADVOCATE` role linked one-to-one to a verified Advocate
record, rather than treating an operator account or a reusable signature image
as advocate authority. Only that linked identity may clear conflicts, accept a
matter, create its immutable quote, submit the candidate and approve the exact
issued PDF; operators retain assignment, payment exception, redelivery and
dispatch duties but cannot make those legal decisions. This preserves one
authentication system while keeping professional authority, attribution and
artifact approval fail-closed; a dedicated scoped advocate interface may be
exposed only in a later gated phase.
