// The guard of ADR 0011: a CSS Module uses tokens, never a colour value. Only declaration
// values are read, so a property such as `white-space` or a selector such as `.a:hover`
// never matches. `transparent` and `currentColor` are allowed.

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

/** The colour literals in the declaration values of a stylesheet, in order of appearance. */
export function colourLiterals(css: string): string[] {
  const found: string[] = [];
  const code = css.replace(/\/\*[\s\S]*?\*\//g, "");
  for (const [, , raw = ""] of code.matchAll(DECLARATION)) {
    // Strings (font names) and custom-property names (tokens) are not colours.
    const value = raw.replace(/"[^"]*"|'[^']*'/g, "").replace(/--[-\w]+/g, "");
    for (const [m] of value.matchAll(HEX)) found.push(m.toLowerCase());
    for (const [, fn = ""] of value.matchAll(FUNCTION)) found.push(`${fn.toLowerCase()}(`);
    for (const [w] of value.replace(HEX, "").matchAll(WORD)) {
      if (NAMED.has(w.toLowerCase())) found.push(w.toLowerCase());
    }
  }
  return found;
}
