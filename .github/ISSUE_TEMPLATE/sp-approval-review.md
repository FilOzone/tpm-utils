---
name: SP Approval Review
about: Track an SP approval decision — new approval, breach review, or periodic check
title: "[SP Approval] f0xxxx"
labels: ["sp-approval-review"]
assignees: []
---

## SP Approval Review

### Review Type

- [ ] **New approval** — SP is being approved for the first time
- [ ] **Breach review** — approved SP has breached SLA thresholds
- [ ] **Periodic check** — routine re-verification of an approved SP
- [ ] **Endorsement removal** — SP has been removed from the endorsed list, which requires removal from the approved list (see Outcome)

> Some sections below are only required for breach reviews. These are marked _(breach review only)_.

---

### SP Details
- **SP ID:**  
- **SP Name (optional):**
- **Endorsed SP?** Yes / No

---

### Review Trigger
- **Time review started (UTC):**  
- **Trigger:**  
  <!-- New approval: e.g. SP met sustained thresholds, requested approval -->
  <!-- Breach review: e.g. Storage success <97%, Retrieval failures, Retention faults -->
  <!-- Periodic check: e.g. Quarterly review, post-incident re-verification -->

---

### Metrics

<!-- For new approvals: record observed performance against thresholds. -->
<!-- For breach reviews: record the failing metric(s). -->

**Metric(s):**
- 

**Observed value(s):**
- 

**Threshold(s):**

| Metric | Threshold | Minimum Sample Size |
|--------|-----------|---------------------|
| [Data Storage Success Rate](#data-storage-success-rate) | ≥ 97% | 200 |
| [Data Retention Fault Rate](#data-retention-fault-rate) | ≤ 0.2% | 500 |
| [Retrieval Success Rate](#retrieval-success-rate) | ≥ 97% | 200 |

---

### Investigation Window _(breach review only)_
- **Investigation deadline (UTC):**  
- **Within maintenance window?** Yes / No  

---

### Communication

- **SP notified / engaged?** Yes / No  
- **Channel used:**  
  <!-- #pdp-endorsed-sp OR #fil-pdp-mainnet-launch -->

- **SP response (if any):**
  <!-- Brief summary -->

---

### Diagnosis _(breach review only)_

**Current assessment:**
- [ ] SP-side issue  
- [ ] Dealbot / tooling issue  
- [ ] Network / external issue  
- [ ] Unknown  

**Notes:**
<!-- What do we think is happening? -->

---

### Outcome

- [ ] **Approved** — SP added to approved list _(new approval / periodic check)_
- [ ] **Not approved** — SP did not meet requirements _(new approval)_
- [ ] **Recovered** within investigation window _(breach review)_
- [ ] **Unapproved** _(breach review / endorsement removal)_

> **Endorsed/approved cascade:** Endorsed is a strict subset of approved. An SP cannot be endorsed without being approved, so removal from the endorsed list also requires removal from the approved list in the same action. If this SP is endorsed and the outcome is unapproval, remove it from both lists.

- **Decision time (UTC):**
- **Decision owner:**  
  <!-- The approver responsible for this decision -->

---

### Actions Taken

- [ ] SP newly approved  
- [ ] SP remained approved  
- [ ] SP unapproved  
- [ ] Follow-up issue created  
- [ ] Escalated  
- [ ] Added to approved list / Notion record updated  

---

### Links & Evidence

- Dashboard (spdash):  
- Dealbot runs:  
- Logs / errors:  
- Related issues:  

---

### Notes

<!-- Anything else useful for future reference -->