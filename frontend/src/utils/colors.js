/**
 * Helper to generate a lighter version of a hex color for CSS properties.
 */
export function hexToRgb(hex) {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result ? {
    r: parseInt(result[1], 16),
    g: parseInt(result[2], 16),
    b: parseInt(result[3], 16)
  } : { r: 107, g: 158, b: 138 };
}

const toHex = ({ r, g, b }) => `#${[r, g, b].map((v) => Math.round(v).toString(16).padStart(2, '0')).join('')}`;

const mix = (color, target, amount) => ({
  r: color.r + (target.r - color.r) * amount,
  g: color.g + (target.g - color.g) * amount,
  b: color.b + (target.b - color.b) * amount,
});

function luminance({ r, g, b }) {
  const channel = (v) => {
    const c = v / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

/** WCAG contrast ratio between two hex colours. */
export function contrast(a, b) {
  const [x, y] = [luminance(hexToRgb(a)), luminance(hexToRgb(b))].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}

const WHITE = { r: 255, g: 255, b: 255 };

function toHsl({ r, g, b }) {
  const [R, G, B] = [r / 255, g / 255, b / 255];
  const max = Math.max(R, G, B);
  const min = Math.min(R, G, B);
  const l = (max + min) / 2;
  if (max === min) return { h: 0, s: 0, l };
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h = max === R ? (G - B) / d + (G < B ? 6 : 0) : max === G ? (B - R) / d + 2 : (R - G) / d + 4;
  return { h: h / 6, s, l };
}

function fromHsl({ h, s, l }) {
  if (s === 0) return { r: l * 255, g: l * 255, b: l * 255 };
  const q = l < 0.5 ? l * (1 + s) : l + s - l * s;
  const p = 2 * l - q;
  const channel = (t) => {
    const u = t < 0 ? t + 1 : t > 1 ? t - 1 : t;
    if (u < 1 / 6) return p + (q - p) * 6 * u;
    if (u < 1 / 2) return q;
    if (u < 2 / 3) return p + (q - p) * (2 / 3 - u) * 6;
    return p;
  };
  return { r: channel(h + 1 / 3) * 255, g: channel(h) * 255, b: channel(h - 1 / 3) * 255 };
}

/**
 * The shades of a learner's colour used by the UI: `strong` is darkened just
 * enough to read as text on white (4.5:1), `soft` is a light fill behind it.
 * Darkening lowers lightness only, so the colour keeps its vividness.
 * Learner colours are family data, so any colour a parent picks stays usable.
 */
export function learnerTones(hex) {
  const base = hexToRgb(hex);
  const hsl = toHsl(base);
  let strong = base;
  while (contrast(toHex(strong), '#ffffff') < 4.5 && hsl.l > 0) {
    hsl.l = Math.max(0, hsl.l - 0.01);
    strong = fromHsl(hsl);
  }
  return { base: toHex(base), strong: toHex(strong), soft: toHex(mix(base, WHITE, 0.86)) };
}
