// ESLint 9 flat config. The `--ext` flag no longer exists; file selection
// happens here instead.
//
// Deliberately built from `typescript-eslint` alone rather than pulling in
// `@eslint/js`. @eslint/js is only present as a transitive dependency of
// eslint, and depending on a transitive is how a lockfile refresh breaks lint
// with no warning. Adding it as a direct dependency would change the approved
// EXT-001 set, which needs its own decision.

import tseslint from "typescript-eslint";

export default tseslint.config(
  {
    ignores: ["dist/**", "node_modules/**", "design/**"],
  },
  ...tseslint.configs.recommended,
  {
    files: ["src/**/*.{ts,tsx}"],
    languageOptions: {
      parserOptions: {
        ecmaFeatures: { jsx: true },
      },
    },
    rules: {
      // Contract shapes must stay typed. frontend/CLAUDE.md: "no `any` on
      // contract shapes".
      "@typescript-eslint/no-explicit-any": "error",
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
    },
  },
);
