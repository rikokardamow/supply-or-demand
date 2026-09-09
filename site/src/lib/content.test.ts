import { describe, expect, it } from "vitest";

import { decodeEntities, httpUrlOrNull } from "@/lib/content";

/**
 * The feed is not trusted input.
 *
 * It is fetched over the network from a third party and rendered straight onto a public
 * page, so it has to be treated the way any other remote input is — even though the third
 * party is the author's own Substack. The threat is not that Substack turns hostile; it is
 * that a compromised account, a tampering proxy, or a CDN serving someone else's response
 * would put attacker-controlled strings into an `href`.
 */

describe("httpUrlOrNull", () => {
  it("accepts the real thing", () => {
    expect(
      httpUrlOrNull("https://kardamow.substack.com/p/nobody-built-that-diesel"),
    ).toBe("https://kardamow.substack.com/p/nobody-built-that-diesel");
    expect(httpUrlOrNull("http://example.com/x")).toBe("http://example.com/x");
    expect(httpUrlOrNull("  https://example.com/x  ")).toBe(
      "https://example.com/x",
    );
  });

  it("rejects javascript: — the reason this function exists", () => {
    // React escapes text content but does NOT block a javascript: URI in href; it logs a
    // development warning and renders the attribute anyway. So a feed item carrying
    // <link>javascript:...</link> would produce a link that executes script on click.
    expect(httpUrlOrNull("javascript:alert(1)")).toBeNull();
    expect(httpUrlOrNull("JavaScript:alert(1)")).toBeNull();
    // Whitespace and control characters inside the scheme are ignored by browsers when
    // they parse a URL, so they cannot be allowed to hide the scheme from this check.
    expect(httpUrlOrNull("java\tscript:alert(1)")).toBeNull();
    expect(httpUrlOrNull("java\nscript:alert(1)")).toBeNull();
    expect(httpUrlOrNull(" javascript:alert(1)")).toBeNull();
  });

  it("rejects every other scheme that can carry a payload", () => {
    expect(httpUrlOrNull("data:text/html;base64,PHNjcmlwdD4=")).toBeNull();
    expect(httpUrlOrNull("vbscript:msgbox(1)")).toBeNull();
    expect(httpUrlOrNull("file:///etc/passwd")).toBeNull();
    expect(httpUrlOrNull("//evil.example.com")).toBeNull();
  });

  it("rejects nothing-at-all rather than returning a broken href", () => {
    expect(httpUrlOrNull("")).toBeNull();
    expect(httpUrlOrNull("   ")).toBeNull();
    expect(httpUrlOrNull(undefined)).toBeNull();
    expect(httpUrlOrNull("not a url")).toBeNull();
  });
});

describe("decodeEntities", () => {
  it("decodes the entities Substack actually emits", () => {
    expect(decodeEntities("Europe&#8217;s winter")).toBe("Europe’s winter");
    expect(decodeEntities("a build &#8212; not a draw")).toBe(
      "a build — not a draw",
    );
    expect(decodeEntities("crude &amp; products")).toBe("crude & products");
    expect(decodeEntities("&quot;quoted&quot;")).toBe('"quoted"');
  });

  it("decodes the opening curly quote, not only its closing twin", () => {
    // The earlier version handled &#8217; but not &#8216;, so an opening quote rendered
    // as the literal text "&#8216;" on the public page.
    expect(decodeEntities("&#8216;spot&#8217;")).toBe("‘spot’");
    expect(decodeEntities("&lsquo;spot&rsquo;")).toBe("‘spot’");
  });

  it("decodes any numeric entity rather than a hand-listed few", () => {
    expect(decodeEntities("caf&#233;")).toBe("café");
    expect(decodeEntities("&#x2014;")).toBe("—");
    expect(decodeEntities("&#39;")).toBe("'");
  });

  it("decodes &amp; last, so &amp;lt; does not become a tag", () => {
    // Decoding &amp; first would turn "&amp;lt;script&amp;gt;" into "<script>" — the
    // classic double-decode mistake.
    expect(decodeEntities("&amp;lt;script&amp;gt;")).toBe("&lt;script&gt;");
  });

  it("leaves ordinary text alone", () => {
    expect(decodeEntities("Midwest plants ran at 101.8 per cent")).toBe(
      "Midwest plants ran at 101.8 per cent",
    );
  });
});
