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

> Some sections below are only required for breach reviews. These are marked _(breach review only)_.

---

### SP Details
- **SP ID:**  
- **SP Name (optional):**

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
- [ ] **Unapproved** _(breach review)_

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
