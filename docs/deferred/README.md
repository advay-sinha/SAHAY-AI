# Deferred infrastructure

`ci.yml` is retained here as a future reference and is intentionally outside `.github/workflows`, so GitHub Actions will not run it. Docker, CI/CD, PostgreSQL, Redis, RQ and pgvector require explicit approval before activation. Update the configuration to match the completed local application rather than copying it blindly.
