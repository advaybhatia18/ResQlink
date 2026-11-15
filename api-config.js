// Use local backend during localhost development; use deployed Render backend elsewhere.
// GitHub Actions also overwrites _site/api-config.js from RESQLINK_API_URL.
(function () {
    const host = typeof window !== "undefined" && window.location ? window.location.hostname : "";
    const isLocal = host === "localhost" || host === "127.0.0.1";
    window.RESQLINK_API_URL = isLocal
        ? "http://127.0.0.1:8000"
        : "https://resqlink-ji0g.onrender.com";
})();
