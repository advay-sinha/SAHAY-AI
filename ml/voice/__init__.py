"""Local speech-to-text service for the backend ASR adapter (plan M11, EXT-120, PC-11).

ML-only tooling: it runs in the private model environment and is reached by the backend over
127.0.0.1. No application module imports it. Nothing loads on import.
"""
