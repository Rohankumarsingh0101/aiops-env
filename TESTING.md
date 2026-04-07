# 🧪 TESTING GUIDE — AIOps Environment

Deterministic test cases for all scenarios. All expected values assume a fresh `/reset` before each test.

---

## 🟢 EASY — CPU Spike on Search

### Reset
```json
POST /reset   { "task_id": "easy" }
```
**Expected:**
- `search` status = `degraded`, cpu = 95, errors = 50
- `auth` and `payments` status = `healthy`, errors = 0
- logs contains `"Search CPU at 95% — likely scaling bottleneck"`

---

### Step 1 — scale_up (correct, resolves cpu_spike)
```json
POST /step   { "action_type": "scale_up", "target_service": "search" }
```
**Expected:**
- `search` status → `healthy`, cpu = 40, errors = 0
- reward ≈ 0.9–1.0 (optimal path possible in next step)
- done = false (only 1 step elapsed, minimum is 2)

---

### Step 2 — ignore (wrong, penalty)
```json
POST /step   { "action_type": "ignore", "target_service": "auth" }
```
**Expected:**
- reward decreases due to wrong-service (`ignore` targets auth not search) and ignore penalties
- log includes: `"Warning: Targeted auth, but payments is more critical"` (or similar)
- done = true (step 2 reached, all services healthy — minimum threshold met)

---

### Optimal path
```
reset → scale_up search → restart_service search
```
- reward = 1.0 if system healthy at step 2 with correct sequence

---

## 🟡 MEDIUM — Memory Leak + Cascade

### Reset
```json
POST /reset   { "task_id": "medium" }
```
**Expected:**
- `auth` degraded (memory=98, errors=100), root_cause=`memory_leak`
- `payments` degraded (cpu=80, errors=50), no root_cause (cascade victim)
- `search` healthy (cpu=30, memory=30, errors=0)
- logs: `"Auth latency spike + memory 98% — possible memory leak"` + `"Payments reporting elevated error rate."`

---

### Step 1 — restart auth (correct)
```json
POST /step   { "action_type": "restart_service", "target_service": "auth" }
```
**Expected:**
- `auth` → healthy, errors=0, memory normalized
- reward ≈ 0.5–0.7
- done = false

---

### Step 2 — restart payments (correct)
```json
POST /step   { "action_type": "restart_service", "target_service": "payments" }
```
**Expected:**
- all services healthy, errors = 0
- done = true
- reward = 1.0 (optimal 2-step correct sequence)

---

## 🔴 HARD — Deceptive Cascade (DB Pool Exhaustion on Auth)

### Reset
```json
POST /reset   { "task_id": "hard" }
```
**Expected:**
- `payments` degraded (cpu=90, errors=500) — appears most critical
- `auth` appears healthy but has hidden root_cause=db_connection_pool_exhausted
- logs mention payments SLA breach and occasional DB drops

---

### Step 1 — scale_up payments (deceptive — CPU drops but errors persist)
```json
POST /step   { "action_type": "scale_up", "target_service": "payments" }
```
**Expected:**
- `payments` cpu drops ~40 points
- `payments` errors remain high (no root_cause to fix)
- log: "CPU reduced but errors persisting"
- reward low (~0.2–0.4)
- done = false

---

### Step 2 — run_diagnostics auth (reveals hidden cause)
```json
POST /step   { "action_type": "run_diagnostics", "target_service": "auth" }
```
**Expected:**
- log: "100% DB connections active. Pool exhausted."
- reward decreases slightly (diagnostics penalty)
- done = false

---

### Step 3 — restart auth (resolves actual root cause)
```json
POST /step   { "action_type": "restart_service", "target_service": "auth" }
```
**Expected:**
- `auth` root_cause cleared — metrics normalize to cpu=30, memory=30, errors=0
- cascade on `payments` clears: errors drop toward 0
- `payments` status becomes `healthy` once errors=0 and no active root causes
- done = true (3 steps hit, or system fully resolved)
- reward ≈ 0.4–0.7 (multi-step, non-optimal, but resolved)

---

## 🔁 DETERMINISM TEST

Run the same sequence twice without restarting the server:

**Run A:**
```
POST /reset {"task_id":"easy"}
POST /step  {"action_type":"scale_up","target_service":"search"}
```

**Run B (immediately after):**
```
POST /reset {"task_id":"easy"}
POST /step  {"action_type":"scale_up","target_service":"search"}
```

**Expected:** Identical rewards, observations, logs across both runs.

---

## ❌ INVALID INPUT HANDLING

### Unknown task_id
```json
POST /reset   { "task_id": "extreme" }
```
**Expected:** HTTP 400 with message about valid tasks.

### Missing action field
```json
POST /step   { "target_service": "auth" }
```
**Expected:** HTTP 422 Unprocessable Entity (Pydantic validation error).

### Unknown service name
```json
POST /step   { "action_type": "restart_service", "target_service": "database" }
```
**Expected:** HTTP 422 Unprocessable Entity (Enum validation error).

### Step before reset
```json
POST /step   { "action_type": "restart_service", "target_service": "auth" }
```
*(on fresh startup, before any /reset)*  
**Expected:** HTTP 400 — "Environment not initialized. Call /reset first."

---

## ✅ SUCCESS CRITERIA

| Criterion                         | Requirement                          |
| --------------------------------- | ------------------------------------ |
| Deterministic outputs             | Same input → same output, always     |
| Reward range                      | Always within [0.05, 1.0]           |
| Multi-step resolution             | `done=true` only after ≥2 steps      |
| Critical service logged           | Every step response includes `"Critical service: <name>"` |
| Correct prioritization rewarded   | Targeting highest-error service → positive signal |
| Valid termination                 | `done=true` only when healthy or max_steps hit |
