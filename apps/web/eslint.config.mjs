import { FlatCompat } from "@eslint/eslintrc";

// `next lint` is deprecated and prompts interactively, which would hang CI, so
// ESLint is invoked directly. eslint-config-next is still eslintrc-format, hence
// the compat wrapper.
const compat = new FlatCompat({ baseDirectory: import.meta.dirname });

const config = [
  {
    ignores: [".next/**", "node_modules/**", "drizzle/**", "next-env.d.ts"],
  },
  ...compat.extends("next/core-web-vitals"),
];

export default config;
