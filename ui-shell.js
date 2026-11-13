"use strict";

(() => {
    const auth = window.ResqlinkAuth;

    const CATEGORY_LABELS = {
        MEDICAL: "Medical Emergency",
        ROAD_ACCIDENT: "Road Accident",
        FIRE: "Fire & Rescue",
        THEFT: "Theft / Intrusion",
        PERSONAL_SAFETY: "Personal Safety",
        NATURAL_DISASTER: "Natural Disaster",
        OTHER: "Other Urgent Situation",
    };

    const SERVICE_LABELS = {
        POLICE: "Police",
        FIRE_RESCUE: "Fire & Rescue",
        AMBULANCE_MEDICAL: "Ambulance / Medical",
    };

    function el(tag, attrs = {}, ...children) {
        const node = document.createElement(tag);
        if (attrs) {
            for (const [key, value] of Object.entries(attrs)) {
                if (value === undefined || value === null || value === false) continue;
                if (key === "className") {
                    node.className = value;
                } else if (key === "dataset" && typeof value === "object") {
                    for (const [dKey, dVal] of Object.entries(value)) {
                        node.dataset[dKey] = String(dVal);
                    }
                } else if (key.startsWith("on") && typeof value === "function") {
                    node.addEventListener(key.slice(2).toLowerCase(), value);
                } else if (key === "text") {
                    node.textContent = String(value);
                } else {
                    node.setAttribute(key, value === true ? "" : String(value));
                }
            }
        }
        for (const child of children) {
            if (child === null || child === undefined || child === false) continue;
            node.append(typeof child === "string" ? document.createTextNode(child) : child);
        }
        return node;
    }

    function formatDate(isoString) {
        if (!isoString || typeof isoString !== "string") return "Time unavailable";
        const d = new Date(isoString);
        if (Number.isNaN(d.getTime())) return "Time unavailable";
        return d.toLocaleString();
    }

    function categoryLabel(code) {
        return CATEGORY_LABELS[String(code || "PERSONAL_SAFETY").toUpperCase()] || String(code || "Personal Safety");
    }

    function serviceLabel(code) {
        return SERVICE_LABELS[String(code || "").toUpperCase()] || String(code || "");
    }

    function showBanner(container, text, kind = "error") {
        if (!container) return;
        if (!text) {
            container.hidden = true;
            container.textContent = "";
            container.className = "rq-banner";
            return;
        }
        container.hidden = false;
        container.className = `rq-banner ${kind}`;
        container.textContent = text;
    }

    function buildHeader(activePage) {
        const header = document.getElementById("rqHeader");
        if (!header) return null;

        const links = [
            { id: "index", href: "index.html", label: "Home" },
            { id: "sos", href: "sos.html", label: "SOS", extraClass: "sos-nav" },
            { id: "user-dashboard", href: "user-dashboard.html", label: "Dashboard" },
            { id: "history", href: "history.html", label: "History" },
            { id: "contacts", href: "contacts.html", label: "Contacts" },
            { id: "settings", href: "settings.html", label: "Settings" },
            { id: "dashboard", href: "dashboard.html", label: "Admin Center", adminOnly: true },
            { id: "simulator", href: "simulator.html", label: "Simulator", adminOnly: true },
        ];

        const nav = el("nav", { className: "rq-nav", id: "rqMainNav", "aria-label": "Primary navigation" });
        const navLinks = [];
        for (const item of links) {
            const a = el("a", {
                href: item.href,
                className: `rq-nav-link ${item.extraClass || ""} ${activePage === item.id ? "active" : ""}`.trim(),
                hidden: Boolean(item.adminOnly),
                text: item.label,
            });
            if (item.adminOnly) a.dataset.adminLink = "1";
            navLinks.push(a);
            nav.append(a);
        }

        const userBadge = el("span", { className: "rq-user-chip", id: "rqHeaderUserChip", hidden: true },
            el("span", { className: "rq-user-avatar", id: "rqHeaderAvatar", text: "—" }),
            el("span", { id: "rqHeaderUserName", text: "Signed in" })
        );
        const loginLink = el("a", {
            href: "login.html",
            className: "rq-btn rq-btn-sm rq-btn-primary",
            id: "rqHeaderLoginLink",
            text: "Sign in",
        });
        const logoutBtn = el("button", {
            type: "button",
            className: "rq-btn rq-btn-sm",
            id: "rqHeaderLogoutBtn",
            hidden: true,
            text: "Sign out",
        });

        const toggleBtn = el("button", {
            type: "button",
            className: "rq-menu-toggle",
            "aria-expanded": "false",
            "aria-controls": "rqMainNav",
            text: "Menu",
        });
        toggleBtn.addEventListener("click", () => {
            const open = nav.classList.toggle("open");
            toggleBtn.setAttribute("aria-expanded", String(open));
        });

        logoutBtn.addEventListener("click", async () => {
            logoutBtn.disabled = true;
            try {
                await auth.logout();
                window.location.replace("login.html");
            } catch (_error) {
                try {
                    auth.clearSession();
                } catch (_err) {
                    // ignore
                }
                window.location.replace("login.html?logout=local");
            }
        });

        const brand = el("a", { href: "index.html", className: "rq-brand", "aria-label": "ResQlink home" },
            el("span", { className: "rq-brand-mark", "aria-hidden": "true", text: "R" }),
            el("span", {},
                el("span", { text: "ResQlink" }),
                el("span", { className: "rq-brand-sub", text: "Emergency Platform" })
            )
        );

        const actions = el("div", { className: "rq-header-actions" },
            userBadge,
            loginLink,
            logoutBtn,
            toggleBtn
        );

        header.replaceChildren(
            el("div", { className: "rq-header-inner" }, brand, actions, nav)
        );
        return { userBadge, loginLink, logoutBtn, navLinks };
    }

    async function initNav(activePage, { requireAuth = false, requireAdmin = false, nextPage = null } = {}) {
        const refs = buildHeader(activePage);
        let token = null;
        try {
            token = auth.getAccessToken();
        } catch (error) {
            if (requireAuth || requireAdmin) {
                throw error;
            }
            return null;
        }

        if (!token) {
            if (requireAuth || requireAdmin) {
                const target = nextPage || `${activePage}.html`;
                const dest = requireAdmin ? `admin-login.html?next=${encodeURIComponent(target)}` : `login.html?next=${encodeURIComponent(target)}`;
                window.location.replace(dest);
                return null;
            }
            return null;
        }

        try {
            const user = await auth.getCurrentUser();
            if (refs) {
                refs.userBadge.hidden = false;
                refs.loginLink.hidden = true;
                refs.logoutBtn.hidden = false;
                const displayName = (user.name || "User").trim();
                document.getElementById("rqHeaderUserName").textContent = `${displayName} (${user.role})`;
                document.getElementById("rqHeaderAvatar").textContent = (Array.from(displayName)[0] || "U").toUpperCase();
                if (user.role === "ADMIN") {
                    refs.navLinks.forEach(link => {
                        if (link.dataset.adminLink === "1") link.hidden = false;
                    });
                }
            }
            if (requireAdmin && user.role !== "ADMIN") {
                return { ...user, _forbiddenAdmin: true };
            }
            return user;
        } catch (error) {
            if (error.code === "expired" || error.code === "unauthenticated") {
                if (requireAuth || requireAdmin) {
                    const target = nextPage || `${activePage}.html`;
                    const dest = requireAdmin
                        ? `admin-login.html?next=${encodeURIComponent(target)}&expired=1`
                        : `login.html?next=${encodeURIComponent(target)}&expired=1`;
                    window.location.replace(dest);
                    return null;
                }
            }
            if (requireAuth || requireAdmin) {
                throw error;
            }
            return null;
        }
    }

    window.ResqlinkUI = Object.freeze({
        CATEGORY_LABELS,
        SERVICE_LABELS,
        categoryLabel,
        el,
        formatDate,
        initNav,
        serviceLabel,
        showBanner,
    });
})();
