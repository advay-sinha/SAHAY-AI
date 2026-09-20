---
description: Change a frozen interface correctly — schemas, docs, dependent code, approvals
argument-hint: "<what you need to change and why>"
allowed-tools: Read, Write, Edit, Bash, Glob, Grep
---

# Contract change: $ARGUMENTS

Frozen contracts live in `docs/contracts/CONTRACTS.md`. Changing one breaks other teams silently. Follow this exactly.

## 1. Establish whether it's really needed
Read the current contract. Can the requirement be met without changing it — an optional field, a new event type, a separate endpoint? If yes, do that instead and stop here. Say which you chose and why.

## 2. Blast radius
Grep for every consumer across `backend/`, `frontend/`, `mobile/`, `ml/`. List every file that breaks. If the list is long, that is itself an argument against the change — say so.

## 3. Write the proposal
```
CONTRACT CHANGE PROPOSAL
Contract:     <endpoint / event / module signature>
Current:      <exact current shape>
Proposed:     <exact new shape>
Reason:       <what is blocked without it>
Breaks:       <files, per team>
Migration:    <additive? or does existing data/code need changing?>
Alternative:  <what we do if this is rejected>
```

## 4. Get approval — do not skip
This needs an issue labelled `type:contract` and approval from **all four leads** (D-11: AI/ML and Safety, Backend, Executive Web, Mobile/Victim Experience). Tell the user to obtain it. **Do not edit the contract before they confirm.**

## 5. Apply it, all in one PR
`docs/contracts/CONTRACTS.md` → `backend/app/core/enums.py` and backend Pydantic schemas → `backend/app/ws/events.py` → `frontend/src/types/contracts.ts` → `mobile/src/types/events.ts` → ml module signatures → `backend/tests/test_contract_mirror.py` and `mobile/tests/contract-gap.test.js` → every consumer.

Never in a feature PR. Never partially. Contract drift is the most expensive category of bug in a three-team sprint.
