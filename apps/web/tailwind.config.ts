import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        band: {
          low: "#15803d",
          weak: "#65a30d",
          mixed: "#ca8a04",
          strong: "#ea580c",
          "very-strong": "#b91c1c",
        },
      },
    },
  },
  plugins: [],
} satisfies Config;
