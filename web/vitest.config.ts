import { fileURLToPath } from "node:url";

import { defineConfig } from "vitest/config";

/**
 * Vitest needs the same `@/` alias `tsconfig.json` gives the app.
 *
 * Without it a test can only import modules that themselves import nothing via the alias,
 * which quietly limits the suite to leaf utilities — `format` and `staleness` were
 * testable, but any component was not, because reaching one meant resolving its own
 * `@/lib/...` imports. That is a bad reason for a component to go untested.
 */
export default defineConfig({
  resolve: {
    alias: {
      "@": fileURLToPath(new URL("./src", import.meta.url)),
    },
  },
});
