import { THEME_STORAGE_KEY } from "./theme-constants";

/**
 * Runs before first paint (inlined in <head>) so a saved light/dark choice
 * never flashes the wrong theme.
 */
export const themeInitScript = `(function(){try{var t=localStorage.getItem(${JSON.stringify(
  THEME_STORAGE_KEY,
)});if(t==="light"||t==="dark")document.documentElement.setAttribute("data-theme",t);}catch(e){}})();`;
