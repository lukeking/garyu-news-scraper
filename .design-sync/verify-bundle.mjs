// Static verification for the hand-authored style-foundation bundle.
// Gates: (1) every preview starts with an @dsCard marker; (2) every class a
// preview uses resolves in _ds_bundle.css or the preview's own <style>;
// (3) every var(--x) consumed anywhere is defined in tokens.css (or is a
// documented fallback pattern); (4) styles.css @import closure reaches
// tokens, vendor normalize and _ds_bundle.css; (5) conventions/README names
// verify against the built CSS.
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

const ROOT = new URL("../ds-bundle/", import.meta.url).pathname;
const fail = [];
const read = (p) => readFileSync(join(ROOT, p), "utf8");

const bundleCss = read("_ds_bundle.css");
const tokensCss = read("tokens/tokens.css");
const stylesCss = read("styles.css");

// (4) import closure
for (const need of ["_vendor/modern-normalize.css", "tokens/tokens.css", "_ds_bundle.css"])
  if (!stylesCss.includes(`@import "${need}"`)) fail.push(`styles.css missing @import ${need}`);

// token definitions
const defined = new Set([...tokensCss.matchAll(/(--[\w-]+)\s*:/g)].map((m) => m[1]));

// (3) var() usage in bundle css
for (const [, v] of bundleCss.matchAll(/var\((--[\w-]+)/g))
  if (!defined.has(v)) fail.push(`_ds_bundle.css uses undefined ${v}`);

// css class index (handles escaped/unicode class names)
const cssClasses = new Set(
  [...bundleCss.matchAll(/\.([^\s\x00-\x2c\x2e\x2f\x3a-\x40\x5b-\x5e\x60\x7b-\x7e]+)/gu)].map((m) => m[1])
);
// css id index (#theme-toggle is styled as an id, not a class)
const cssIds = new Set([...bundleCss.matchAll(/#([\w-]+)/g)].map((m) => m[1]));
// Production state-marker classes that app.js toggles but CSS never styles —
// collapse visuals ride on the [hidden] attribute; these are allowed verbatim
// because previews reuse production markup faithfully.
const stateMarkers = new Set(["collapsed"]);

// walk previews
const groups = readdirSync(join(ROOT, "components"));
let previews = 0;
for (const g of groups)
  for (const name of readdirSync(join(ROOT, "components", g))) {
    const html = read(`components/${g}/${name}/${name}.html`);
    previews++;
    // (1) marker
    if (!/^<!-- @dsCard group="[^"]+" -->/.test(html))
      fail.push(`${name}.html missing @dsCard first line`);
    // preview-local classes from its own <style>
    const local = new Set(
      [...html.matchAll(/<style>([\s\S]*?)<\/style>/g)].flatMap(([, css]) =>
        [...css.matchAll(/\.([^\s\x00-\x2c\x2e\x2f\x3a-\x40\x5b-\x5e\x60\x7b-\x7e]+)/gu)].map((m) => m[1])
      )
    );
    // (2) class resolution
    for (const [, list] of html.matchAll(/class="([^"]+)"/g))
      for (const cls of list.trim().split(/\s+/))
        if (!cssClasses.has(cls) && !local.has(cls) && !stateMarkers.has(cls))
          fail.push(`${name}.html uses class "${cls}" not in _ds_bundle.css`);
    // (3) var() usage in preview markup
    for (const [, v] of html.matchAll(/var\((--[\w-]+)/g))
      if (!defined.has(v)) fail.push(`${name}.html uses undefined ${v}`);
    // prompt.md exists & its backticked .classes verify
    const prompt = read(`components/${g}/${name}/${name}.prompt.md`);
    for (const [, cls] of prompt.matchAll(/`\.?([a-z][a-z0-9-]{2,})`/g))
      if (/-/.test(cls) && !cssClasses.has(cls) && !cssIds.has(cls) && !defined.has(`--${cls}`) && !stateMarkers.has(cls))
        if (!["prompt-md", "ds-bundle"].includes(cls) && !cls.endsWith(".css") && !cls.endsWith(".html"))
          fail.push(`${name}.prompt.md names "${cls}" not found in CSS`);
  }

// (5) conventions class/token claims
const readme = read("README.md");
for (const [, cls] of readme.matchAll(/`([a-z][a-z0-9-]+(?:-[高中低])?)`/g)) {
  if (!/-/.test(cls) || cls.includes(".") || cls.includes("/")) continue;
  if (["ds-bundle", "zh-hant", "style-foundation"].includes(cls)) continue;
  if (!cssClasses.has(cls) && !defined.has(`--${cls}`))
    fail.push(`README names "${cls}" not found in CSS`);
}
for (const [, tok] of readme.matchAll(/`(--[\w-]+)`/g))
  if (!defined.has(tok)) fail.push(`README names token ${tok} not defined`);
// Chinese-suffix class claims
for (const cls of ["card-高", "card-中", "card-低", "imp-高", "imp-中", "imp-低"])
  if (!cssClasses.has(cls)) fail.push(`expected Chinese-variant class .${cls} missing from CSS`);

console.log(`previews checked: ${previews}`);
if (fail.length) {
  console.error(`FAIL (${fail.length}):`);
  for (const f of fail) console.error("  - " + f);
  process.exit(1);
}
console.log("OK — all gates clean");
