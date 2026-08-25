import { defineConfig } from "wxt";

// See https://wxt.dev/api/config.html
export default defineConfig({
  modules: ["@wxt-dev/module-react"],
  srcDir: "src",

  manifest: {
    name: "VeriFrame",
    description:
      "Check any image or video on a page for signs of AI generation or manipulation, right where you found it.",
    version: "0.1.0",

    // Deliberately minimal. No <all_urls> or broad host permissions: the
    // content script only needs to see the page the user is already on
    // (activeTab), nothing runs until they click something on it, and no
    // network host is contacted from the extension except the inference
    // service origin declared below.
    permissions: ["activeTab", "contextMenus", "storage", "offscreen"],

    // The extension calls the inference service directly (see
    // services/inference's CORS config) rather than through the
    // Clerk-gated web app, since it has to work without a signed-in web
    // session. Declared explicitly rather than left to a wildcard.
    host_permissions: ["http://localhost:8000/*"],

    action: {
      default_popup: "popup.html",
      default_title: "VeriFrame",
    },

    icons: {
      16: "icon/16.png",
      32: "icon/32.png",
      48: "icon/48.png",
      128: "icon/128.png",
    },
  },
});
