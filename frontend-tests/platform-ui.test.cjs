"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

function loadUiShell() {
    const code = fs.readFileSync(path.join(__dirname, "..", "ui-shell.js"), "utf8");
    const createdNodes = [];
    const fakeDoc = {
        getElementById: () => null,
        createTextNode: text => ({ nodeType: 3, textContent: String(text) }),
        createElement: tag => {
            const node = {
                tagName: tag.toUpperCase(),
                attributes: {},
                dataset: {},
                children: [],
                listeners: {},
                _textContent: "",
                setAttribute(k, v) {
                    this.attributes[k] = String(v);
                },
                addEventListener(evt, fn) {
                    this.listeners[evt] = fn;
                },
                append(...items) {
                    this.children.push(...items);
                },
                replaceChildren(...items) {
                    this.children = [...items];
                },
                get textContent() {
                    return this._textContent;
                },
                set textContent(val) {
                    this._textContent = String(val);
                },
            };
            createdNodes.push(node);
            return node;
        },
    };
    const context = {
        window: {
            ResqlinkAuth: {
                getAccessToken: () => null,
                getCurrentUser: async () => null,
            },
            location: { replace: () => {} },
        },
        document: fakeDoc,
        console,
    };
    vm.runInNewContext(code, context, { filename: "ui-shell.js" });
    return { ui: context.window.ResqlinkUI, createdNodes };
}

test("ui-shell.js formats categories/services and renders text safely without innerHTML", () => {
    const { ui } = loadUiShell();
    assert.equal(ui.categoryLabel("ROAD_ACCIDENT"), "Road Accident");
    assert.equal(ui.serviceLabel("AMBULANCE_MEDICAL"), "Ambulance / Medical");
    assert.equal(ui.formatDate("invalid-date"), "Time unavailable");

    const xssPayload = "<img src=x onerror=alert(1)>";
    const node = ui.el("p", { className: "rq-muted", text: xssPayload });
    assert.equal(node.tagName, "P");
    assert.equal(node.textContent, xssPayload);
});

test("auth-pages.js allows all authenticated member and admin redirect targets", () => {
    const authPagesSource = fs.readFileSync(
        path.join(__dirname, "..", "auth-pages.js"),
        "utf8"
    );
    for (const target of [
        "sos.html",
        "user-dashboard.html",
        "history.html",
        "contacts.html",
        "settings.html",
        "dashboard.html",
        "simulator.html",
    ]) {
        assert.match(authPagesSource, new RegExp(`"${target.replace(".", "\\.")}"`));
    }
});

test("emergency-api.js reads window.RESQLINK_API_URL and sets idempotency header", async () => {
    const code = fs.readFileSync(path.join(__dirname, "..", "emergency-api.js"), "utf8");
    const calls = [];
    const context = {
        window: {
            RESQLINK_API_URL: "https://resqlink-ji0g.onrender.com/",
            ResqlinkAuth: {
                getAccessToken: () => "tok-123",
                clearSession: () => {},
            },
        },
        AbortController,
        setTimeout,
        clearTimeout,
        fetch: async (url, init) => {
            calls.push({ url, init });
            return {
                ok: true,
                status: 201,
                headers: { get: () => "application/json" },
                json: async () => ({ alert_id: 42, status: "ACTIVE", duplicate: false }),
            };
        },
    };
    vm.runInNewContext(code, context, { filename: "emergency-api.js" });
    const res = await context.window.ResqlinkApi.submitEmergency(
        { severity: 4, category: "MEDICAL", requested_services: ["AMBULANCE_MEDICAL"] },
        "idem-key-1"
    );
    assert.equal(res.alert_id, 42);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].url, "https://resqlink-ji0g.onrender.com/emergency");
    assert.equal(calls[0].init.headers["Idempotency-Key"], "idem-key-1");
});
