if ("serviceWorker" in navigator) addEventListener("load", () => navigator.serviceWorker.register("/administracion/sw.js", { scope: "/administracion/" }).catch(() => {}));
