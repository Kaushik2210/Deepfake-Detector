import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";

export default tseslint.config(
  {
    ignores: [".output/**", ".wxt/**", "node_modules/**"],
  },
  ...tseslint.configs.recommended,
  {
    plugins: { "react-hooks": reactHooks },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // WXT auto-imports `browser`, `defineBackground`, `defineContentScript`,
      // etc. from generated types rather than explicit imports; the linter
      // running outside WXT's own context doesn't see those globals.
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_" }],
    },
  },
);
