import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

// Mirrors the `@/*` -> `./src/*` path alias from tsconfig.json. Vitest (unlike Next's own
// bundler) does not read tsconfig paths on its own, so without this any test importing via
// `@/...` fails to resolve rather than failing its assertions.
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
