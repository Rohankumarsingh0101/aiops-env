# 🧪 TESTING GUIDE — AIOps Environment

This document validates deterministic behavior, reward shaping, and multi-step reasoning.

---

# 🟢 EASY

## Reset

```json
{ "task_id": "easy" }
```

### Expected

* search degraded (errors ~50)

---

## Step 1

```json
{ "action_type": "scale_up", "target_service": "search" }
```

Expected:

* reward ≈ 0.5–0.6
* done = false

---

## Step 2 (wrong)

```json
{ "action_type": "ignore", "target_service": "auth" }
```

Expected:

* warning log
* reward decreases
* done = false

---

## Step 3 (correct)

```json
{ "action_type": "restart_service", "target_service": "search" }
```

Expected:

* errors = 0
* done = true
* reward ≈ 0.9–1.0

---

# 🟡 MEDIUM

## Reset

```json
{ "task_id": "medium" }
```

Expected:

* auth + payments degraded

---

## Step 1

```json
{ "action_type": "restart_service", "target_service": "auth" }
```

Expected:

* reward ≈ 0.6
* done = false

---

## Step 2

```json
{ "action_type": "restart_service", "target_service": "payments" }
```

Expected:

* all healthy
* done = true
* reward ≈ 0.9–1.0

---

# 🔴 HARD

## Reset

```json
{ "task_id": "hard" }
```

Expected:

* payments heavily degraded (errors ~500)

---

## Step 1 (wrong)

```json
{ "action_type": "restart_service", "target_service": "auth" }
```

Expected:

* reward ≈ 0.05
* done = false

---

## Step 2 (correct)

```json
{ "action_type": "restart_service", "target_service": "payments" }
```

Expected:

* system healthy
* reward ≈ 0.9–0.95
* done = true

---

# 🔁 DETERMINISM TEST

Repeat:

```text
reset → step → step
```

Expected:

* identical output each run

---

# ✅ SUCCESS CRITERIA

* deterministic outputs
* reward range [0.05, 1.0]
* multi-step resolution
* correct prioritization
* valid termination conditions

---
