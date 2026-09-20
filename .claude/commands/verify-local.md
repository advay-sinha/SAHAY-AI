---
description: Run the local manual verification gate without Docker or CI
allowed-tools: Read, Bash, Glob, Grep
---

# Verify local

Read the current phase and team instructions. Run only commands supported by already-installed, approved dependencies.

Check pure ML tests, backend tests, frontend typecheck/lint/build, mobile typecheck, FastAPI health, WebSocket echo, assessment fan-out isolation, crisis interrupt, consent gate and victim-safe timeline. Skip a check only when its dependency is not installed; report it as BLOCKED with the exact decision ID. Never install during verification.

Return PASS, FAIL or BLOCKED for each item and name the current gate result.
