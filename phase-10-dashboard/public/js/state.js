/** The actor name is remembered for this browser tab only. Everything else lives in the URL. */
const ACTOR = "p10.actor";

export function readActor() {
  try {
    return sessionStorage.getItem(ACTOR) || "";
  } catch {
    return "";
  }
}

export function writeActor(actor) {
  try {
    sessionStorage.setItem(ACTOR, actor);
  } catch {
    /* storage blocked: the field still works for this form */
  }
}
