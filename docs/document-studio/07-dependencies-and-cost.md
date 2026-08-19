# Dependencies and Cost

## Dependency classification

| Dependency | V1 status | Blocker to development | Blocker to production |
| --- | --- | --- | --- |
| Flask/Gunicorn/PostgreSQL | Existing | No | Must remain healthy/current |
| ReportLab | Existing | No | Multilingual/layout acceptance required |
| `python-docx` | Add and pin | No | Required if DOCX is promised |
| Jinja2/controlled template engine | Existing foundation | No | Arbitrary template execution prohibited |
| Amazon S3 `ap-south-1` | Provision after design | No; use local fake/adapter | Yes for retained production files |
| S3-only IAM credential | New | No | Yes; separate from SES/root |
| Razorpay | Existing test integration | No | Live/ReKYC and exact product payment flow |
| Advocate template/review operation | Business dependency | Yes for final catalogue content | Yes |
| WhatsApp outbound templates | Optional in V1 | No | No when manual/in-window delivery is used |
| Amazon SES production access | Optional | No | No; do not email attachments in V1 |
| Generative AI | Excluded | No | No |
| OCR/malware scan | Excluded with uploads | No | Only if customer uploads enter scope |
| Managed e-sign/DSC | Optional future | No | Only if marketed as automated e-sign |
| Render worker | Optional future | No | Only when measured render load requires it |

## Current fixed baseline

The user's selected Render configuration is approximately:

- Starter web service: USD 7/month.
- PostgreSQL Basic 1 GB: USD 19/month.
- PostgreSQL 5 GB storage: USD 1.50/month.
- Baseline: USD 27.50/month before tax, card and currency effects.

Document Studio should not require another database or continuously running
service for the pilot.

## S3 planning model

Planning assumptions last reviewed: 19 August 2026. Provider prices, taxes and
exchange rates are external inputs and must be rechecked before procurement.

Assume each completed order retains about 2 MB across preview, review, final
PDF and DOCX. At 100 orders/month and a three-month steady retention window,
about 600 MB is stored. Storage and ordinary request charges should be only a
few rupees at this scale. The internal INR 100-INR 300 monthly allowance covers
versions, repeated downloads, logs, tests, tax/currency variation and mistakes
rather than predicting the raw storage charge.

Recommended controls:

- AWS budget alert at INR 300 equivalent and investigation threshold at INR 500.
- Cost allocation tags for project/environment/data class.
- Monthly object count, GB, request and transfer review.
- Lifecycle for incomplete uploads, temporary, unpaid and expired versions.
- No Intelligent-Tiering or archival complexity until measured volume warrants
  it; small-object monitoring/transition charges can outweigh savings.

## Cost scenarios

| Scenario | Incremental infrastructure planning range |
| --- | --- |
| Local design/development with synthetic files | INR 0 |
| Pilot S3 storage/downloads | Likely INR 0-INR 25; reserve INR 100-INR 300/month |
| Optional customer-managed KMS key | About USD 1/month plus requests |
| Additional Render cron | Minimum/provider runtime billing applies |
| Dedicated Render worker | New paid service; defer until measured |
| Managed OCR/malware/e-sign | Vendor/usage quote; not V1 |
| Advocate review | Professional/business operating cost, not cloud cost |
| Razorpay | Account-specific successful-transaction fee and tax |
| WhatsApp | Existing Meta conversation/template charging where applicable |

All prices are planning inputs and must be reconfirmed from the account/provider
before procurement or production approval.

## Alternatives considered

### Cloudflare R2

S3-compatible and attractive at pilot volume because its published Standard
allowance includes 10 GB-month storage, one million Class A operations, ten
million Class B operations and free direct egress. It likely costs INR 0 initially.
It adds another vendor, credential model, region/data-governance decision and
operational surface. Keep it as the preferred cost-driven fallback.

### Backblaze B2

Low storage cost and an S3-compatible API, with published free allowances. It
also adds a separate vendor and requires a region, privacy, operational and
recovery assessment. Suitable as a later backup/alternative after review, not
the initial primary store.

### Render persistent disk

Rejected for primary document storage. A disk is attached to one service,
prevents horizontal scaling/zero-downtime deployment, and is unavailable to
separate pre-deploy/one-off jobs. It is not a shared object-delivery service.

### PostgreSQL binary storage

Rejected. It consumes expensive database capacity, enlarges backups and
recovery, and couples relational availability to file download load. Store
metadata/hashes only.

### Generate, deliver and immediately delete

Cheapest but rejected as the only mechanism because users lose re-download,
support cannot recover delivery, and signed/reviewed artifacts cannot safely be
recreated without preserving exact bytes. It remains useful for temporary
previews combined with a bounded final-artifact retention period.

## Recommended procurement sequence

1. Approve the design and one pilot product; cost INR 0.
2. Implement against a storage interface/local synthetic adapter; cost INR 0.
3. Create a private non-production S3 bucket and S3-only IAM identity.
4. Configure an AWS budget before volume testing.
5. Measure 100 synthetic lifecycle operations and forecast production use.
6. Provision the separate production bucket only after security/UAT approval.

Do not create a worker, KMS customer key, OCR service, malware SaaS, e-sign
subscription or additional cron merely because it appears in a future diagram.
Each must be justified by an approved requirement or observed operating limit.

## Provider references

- [Amazon S3 pricing](https://aws.amazon.com/s3/pricing/)
- [Cloudflare R2 pricing](https://developers.cloudflare.com/r2/pricing/)
- [Backblaze B2 pricing](https://www.backblaze.com/cloud-storage/pricing)
- [Render persistent disk constraints](https://render.com/docs/disks)

These links support provider characteristics only. The account invoice and
region-specific provider calculator remain authoritative for a purchase.
