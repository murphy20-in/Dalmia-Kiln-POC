/** DOM builder. Children are nodes or text. innerHTML is ignored. */

export const UNSAFE_URL = /^\s*(javascript|data|vbscript):/i;

export function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) {
    for (const [key, value] of Object.entries(props)) {
      if (value == null || value === false) continue;
      if (key === "class") el.className = value;
      else if (key === "dataset") Object.assign(el.dataset, value);
      else if (key.startsWith("on")) { if (typeof value === "function") el.addEventListener(key.slice(2).toLowerCase(), value); }
      else if ((key === "href" || key === "src") && UNSAFE_URL.test(String(value))) continue;
      else if (key === "htmlFor") el.htmlFor = value;
      else if (key === "innerHTML" || key === "outerHTML") continue;
      else el.setAttribute(key, value === true ? "" : String(value));
    }
  }
  for (const kid of kids.flat()) append(el, kid);
  return el;
}

export function append(parent, kid) {
  if (kid == null || kid === false) return;
  parent.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
}
