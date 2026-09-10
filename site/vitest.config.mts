import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Vitest needs the same `@/` alias `tsconfig.json` gives the app — otherwise a test can
 * only reach modules that themselves import nothing via the alias, which in practice
 * means nothing worth testing.
 */
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
});
