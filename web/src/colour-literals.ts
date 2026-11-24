// The guard of ADR 0014: no colour literals in `.css` or `.tsx` outside `@theme` in
// `globals.css`. `transparent` and `currentColor` are allowed.

/** CSS named colours (CSS Color 4) and system colours, lower case. */
const NAMED = new Set(
  (
    "aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue " +
    "blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk " +
    "crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki " +
    "darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen " +
    "darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue " +
    "dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite " +
    "gold goldenrod gray green greenyellow grey honeydew hotpink indianred indigo ivory khaki " +
    "lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan " +
    "lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen " +
    "lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen " +
    "magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen " +
    "mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream " +
    "mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid " +
    "palegoldenrod palegreen paleturquoise palevioletred papayawhip peachpuff peru pink plum " +
    "powderblue purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown " +
    "seagreen seashell sienna silver skyblue slateblue slategray slategrey snow springgreen " +
    "steelblue tan teal thistle tomato turquoise violet wheat white whitesmoke yellow " +
    "yellowgreen " +
    "accentcolor accentcolortext activetext buttonborder buttonface buttontext canvas " +
    "canvastext field fieldtext graytext highlight highlighttext linktext mark marktext " +
    "selecteditem selecteditemtext visitedtext"
  ).split(" "),
);

const DECLARATION = /([-\w]+)\s*:\s*([^;{}]+)(?=[;}])/g;
const FUNCTION = /(?<![-\w])(rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\(/gi;
const HEX = /#[0-9a-f]{3,8}(?![-\w])/gi;
const WORD = /-?[a-z_][-\w]*/gi;

const TW_ARBITRARY_COLOUR =
  /\b(?:bg|text|border|border-[trblxy]|ring|ring-offset|outline|divide|fill|stroke|from|via|to|accent|caret|decoration|placeholder|shadow)-\[(#[0-9a-f]{3,8}|(?:rgba?|hsla?|hwb|lab|lch|oklab|oklch|color)\([^)\]]*\)|[a-z]+)\]/gi;

const INLINE_STYLE_COLOUR =
  /\b(?:color|background|backgroundColor|borderColor|borderTopColor|borderRightColor|borderBottomColor|borderLeftColor|outlineColor|fill|stroke|caretColor|accentColor)\s*:\s*(['"`])([^'"`]+)\1/g;

const SVG_COLOUR_ATTR = /\b(?:fill|stroke)\s*=\s*(?:\{\s*)?(['"`])([^'"`]+)\1/g;

function stripCssBlock(css: string, headerRe: RegExp): string {
  let result = css;
  let match: RegExpExecArray | null;
  while ((match = headerRe.exec(result)) !== null) {
    const start = match.index;
    const openBrace = result.indexOf("{", start);
    if (openBrace === -1) break;
    let depth = 1;
    let pos = openBrace + 1;
    while (pos < result.length && depth > 0) {
      if (result[pos] === "{") depth++;
      else if (result[pos] === "}") depth--;
      pos++;
    }
    result = result.slice(0, start) + result.slice(pos);
    headerRe.lastIndex = 0;
  }
  return result;
}

/** Remove `@theme` from `app/globals.css` before scanning CSS (zero legacy `:root` exemptions). */
export function stripAllowedCssBlocks(css: string, isGlobalsCss: boolean): string {
  if (!isGlobalsCss) return css;
  return stripCssBlock(css, /@theme\s*\{/g);
}

function scanValueForColours(raw: string): string[] {
  const found: string[] = [];
  const value = raw.replace(/--[-\w]+/g, "");
  for (const [m] of value.matchAll(HEX)) found.push(m.toLowerCase());
  for (const [, fn = ""] of value.matchAll(FUNCTION)) found.push(`${fn.toLowerCase()}(`);
  for (const [w] of value.replace(HEX, "").matchAll(WORD)) {
    if (NAMED.has(w.toLowerCase())) found.push(w.toLowerCase());
  }
  return found;
}

/** The colour literals in the declaration values of a stylesheet, in order of appearance. */
export function colourLiterals(css: string): string[] {
  const found: string[] = [];
  const code = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const [, , raw = ""] of code.matchAll(DECLARATION)) {
    // Strings (font names) and custom-property names (tokens) are not colours.
    const value = raw.replace(/"[^"]*"|'[^']*'/g, "");
    found.push(...scanValueForColours(value));
  }
  return found;
}

/** Colour literals in `.tsx` files: arbitrary Tailwind colour classes, inline styles, SVG fill/stroke. */
export function tsxColourLiterals(source: string): string[] {
  const found: string[] = [];
  for (const [full, inner = ""] of source.matchAll(TW_ARBITRARY_COLOUR)) {
    if (inner.startsWith("#") || FUNCTION.test(inner)) {
      FUNCTION.lastIndex = 0;
      found.push(full);
    } else if (NAMED.has(inner.toLowerCase())) {
      found.push(full);
    }
    FUNCTION.lastIndex = 0;
  }
  for (const [, , val = ""] of source.matchAll(INLINE_STYLE_COLOUR)) {
    const trimmed = val.trim();
    if (/^(?:transparent|currentColor|inherit|none|initial|unset|var\()/i.test(trimmed)) {
      continue;
    }
    found.push(...scanValueForColours(trimmed));
  }
  for (const [, , val = ""] of source.matchAll(SVG_COLOUR_ATTR)) {
    const trimmed = val.trim();
    if (/^(?:none|currentColor|transparent|inherit|url\()/i.test(trimmed)) {
      continue;
    }
    found.push(...scanValueForColours(trimmed));
  }
  return found;
}
