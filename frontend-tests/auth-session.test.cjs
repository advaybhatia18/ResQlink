const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const authSource = fs.readFileSync(
    path.join(__dirname, "..", "auth-session.js"),
    "utf8"
);

function createAuth(fetchImplementation, initialStorage = {}) {
    const values = new Map(Object.entries(initialStorage));
    const sessionStorage = {
        getItem(key) {
            return values.has(key) ? values.get(key) : null;
        },
        setItem(key, value) {
            values.set(key, String(value));
        },
        removeItem(key) {
            values.delete(key);
        }
    };
    const window = {
        RESQLINK_API_URL: "https://api.example.test",
        setTimeout,
        clearTimeout
    };

    vm.runInNewContext(authSource, {
        window,
        sessionStorage,
        fetch: fetchImplementation,
        Headers,
        AbortController
    });

    return { auth: window.ResqlinkAuth, sessionStorage };
}

test("401 API response expires the session and clears the token", async () => {
    const { auth, sessionStorage } = createAuth(
        async () => ({
            status: 401,
            ok: false,
            json: async () => ({ detail: "Expired" })
        }),
        { resqlink_token: "unit-test-token" }
    );

    await assert.rejects(auth.request("/me"), error => {
        assert.equal(error.code, "expired");
        assert.equal(error.status, 401);
        return true;
    });
    assert.equal(sessionStorage.getItem("resqlink_token"), null);
});

test("403 API response is reported without clearing a valid session", async () => {
    const { auth, sessionStorage } = createAuth(
        async () => ({
            status: 403,
            ok: false,
            json: async () => ({ detail: "Administrator role required" })
        }),
        { resqlink_token: "unit-test-token" }
    );

    await assert.rejects(auth.request("/emergencies"), error => {
        assert.equal(error.code, "api_error");
        assert.equal(error.status, 403);
        assert.match(error.message, /Administrator role required/);
        return true;
    });
    assert.equal(sessionStorage.getItem("resqlink_token"), "unit-test-token");
});

test("network failure returns an explicit network error", async () => {
    const { auth } = createAuth(
        async () => {
            throw new Error("offline");
        },
        { resqlink_token: "unit-test-token" }
    );

    await assert.rejects(auth.request("/emergencies"), error => {
        assert.equal(error.code, "network");
        assert.match(error.message, /Could not reach the ResQlink API/);
        return true;
    });
});
