"use strict";

(() => {
    const PENDING_ATTEMPT_KEY = "resqlink_pending_emergency";
    const GPS_TIMEOUT_MS = 15000;
    const MAX_ACCEPTABLE_ACCURACY_M = 100;
    const severityDescriptions = {
        "1": "Non-urgent issue; follow safety guidance or request manual assistance.",
        "2": "Needs attention; primary service recommended with optional additions.",
        "3": "Serious situation requiring timely response and targeted services.",
        "4": "Urgent situation with significant risk; coordinated services recommended.",
        "5": "Immediate danger or urgent threat to life."
    };

    const SERVICE_ICONS = {
        shield: "🛡",
        flame: "🔥",
        medical: "✚"
    };

    const elements = {
        button: document.getElementById("sosButton"),
        category: document.getElementById("emergencyCategory"),
        severity: document.getElementById("severity"),
        notes: document.getElementById("emergencyNotes"),
        severityDescription: document.getElementById("severityDescription"),
        safetyGuidanceText: document.getElementById("safetyGuidanceText"),
        classificationSummaryPill: document.getElementById("classificationSummaryPill"),
        serviceCardsGrid: document.getElementById("serviceCardsGrid"),
        dispatchDisclaimer: document.getElementById("dispatchDisclaimer"),
        progressPanel: document.querySelector(".progress-panel"),
        progressState: document.getElementById("progressState"),
        progressFill: document.getElementById("progressFill"),
        status: document.getElementById("statusMessage"),
        successPanel: document.getElementById("successPanel"),
        successAlertId: document.getElementById("successAlertId"),
        successTimestamp: document.getElementById("successTimestamp"),
        newAlertButton: document.getElementById("newAlertButton"),
        locationActions: document.getElementById("locationActions"),
        retryAuth: document.getElementById("retryAuthButton"),
        retryLocation: document.getElementById("retryLocationButton"),
        useApproximate: document.getElementById("useApproximateLocationButton"),
        withoutLocation: document.getElementById("submitWithoutLocationButton"),
        discardPending: document.getElementById("discardPendingButton"),
        signInLink: document.getElementById("signInLink"),
        gpsIndicator: document.getElementById("gpsIndicator"),
        locationStatus: document.getElementById("locationStatus"),
        latitude: document.getElementById("latitude"),
        longitude: document.getElementById("longitude"),
        accuracyWrap: document.getElementById("accuracyWrap"),
        accuracy: document.getElementById("locationAccuracy"),
        accuracyMeter: document.getElementById("accuracyMeterFill"),
        mapElement: document.getElementById("locationMap"),
        mapOverlay: document.getElementById("mapOverlay"),
        mapMessage: document.getElementById("mapMessage"),
        sosContactsStatus: document.getElementById("sosContactsStatus"),
        sosContactsList: document.getElementById("sosContactsList")
    };

    let currentUser = null;
    let map = null;
    let locationMarker = null;
    let accuracyCircle = null;
    let approximateLocation = null;
    let pendingAttempt = null;
    let pendingAttemptCorrupt = false;
    let flowBusy = false;
    let currentClassification = null;
    let customRequestedServices = null;
    let classifyTimer = null;

    function el(tag, attrs = {}, ...children) {
        return window.ResqlinkUI.el(tag, attrs, ...children);
    }

    function setProgress(state, message, label) {
        elements.progressPanel.dataset.state = state;
        elements.progressState.dataset.state = state;
        elements.progressFill.dataset.state = state;
        elements.progressState.textContent = label;
        elements.status.textContent = message;
        elements.successPanel.hidden = state !== "success";
    }

    function showRecoveryActions({
        auth = false,
        location = false,
        approximate = false,
        discard = false
    } = {}) {
        elements.locationActions.hidden = !(
            auth || location || approximate || discard
        );
        elements.retryAuth.hidden = !auth;
        elements.retryLocation.hidden = !location;
        elements.useApproximate.hidden = !approximate;
        elements.withoutLocation.hidden = !location;
        elements.discardPending.hidden = !discard;
    }

    function renderServiceCards(classification) {
        currentClassification = classification;
        if (!elements.serviceCardsGrid) return;
        elements.serviceCardsGrid.replaceChildren();

        if (!classification) return;

        elements.safetyGuidanceText.textContent = classification.safety_guidance || "";
        elements.classificationSummaryPill.textContent =
            `Priority ${classification.priority} · ${classification.label}`;
        elements.classificationSummaryPill.className = `rq-pill sev-${classification.severity}`;
        if (elements.dispatchDisclaimer && classification.dispatch_notice) {
            elements.dispatchDisclaimer.textContent = classification.dispatch_notice;
        }

        const cards = classification.service_cards || [];
        cards.forEach(card => {
            const statusText = card.selection_status === "RECOMMENDED_AND_SELECTED"
                ? "Recommended & Selected"
                : card.selection_status === "RECOMMENDED_REMOVED"
                    ? "Recommended (Deselected)"
                    : card.selection_status === "MANUALLY_SELECTED"
                        ? "Manually Selected"
                        : "Optional";

            const toggleBtn = el("button", {
                type: "button",
                className: "service-toggle-btn",
                "aria-pressed": String(Boolean(card.requested)),
                text: card.requested ? "Selected for Request (Click to Remove)" : "Add to Request"
            });

            toggleBtn.addEventListener("click", () => {
                if (pendingAttempt) return;
                const currentSet = new Set(
                    customRequestedServices !== null
                        ? customRequestedServices
                        : classification.requested_services
                );
                if (currentSet.has(card.id)) {
                    currentSet.delete(card.id);
                } else {
                    currentSet.add(card.id);
                }
                customRequestedServices = Array.from(currentSet);
                refreshClassification();
            });

            const article = el(
                "article",
                {
                    className: `service-card${card.recommended ? " recommended" : ""}${card.requested ? " selected" : ""}`
                },
                el("div", { className: "service-card-head" },
                    el("span", { className: "service-card-title" },
                        el("span", { "aria-hidden": "true", text: SERVICE_ICONS[card.icon] || "•" }),
                        el("span", { text: card.name })
                    ),
                    el("span", {
                        className: `rq-pill sev-${card.severity}`,
                        text: `Lvl ${card.severity} · P${card.priority}`
                    })
                ),
                el("div", { className: "service-card-meta" },
                    el("span", {
                        className: `rq-pill ${card.requested ? "status-ACTIVE" : ""}`,
                        text: statusText
                    }),
                    card.recommended
                        ? el("span", { className: "rq-pill status-ACKNOWLEDGED", text: "Recommended" })
                        : null
                ),
                el("p", { className: "service-card-reason", text: card.reason }),
                el("p", {
                    className: "service-card-info",
                    text: `${card.emergency_info} (${card.fallback_number})`
                }),
                toggleBtn
            );
            elements.serviceCardsGrid.append(article);
        });
    }

    async function refreshClassification() {
        const category = elements.category ? elements.category.value : "PERSONAL_SAFETY";
        const severity = Number(elements.severity.value);
        elements.severityDescription.textContent = severityDescriptions[String(severity)] || "";

        try {
            const baseUrl = (window.RESQLINK_API_URL || "").replace(/\/+$/, "");
            if (!baseUrl) return;
            const body = { category, severity };
            if (customRequestedServices !== null) {
                body.requested_services = customRequestedServices;
            }
            const response = await fetch(`${baseUrl}/classification/recommend`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(body)
            });
            if (!response.ok) return;
            const data = await response.json();
            renderServiceCards(data);
        } catch (_err) {
            // Keep UI responsive even when preview endpoint is temporarily unreachable.
        }
    }

    function scheduleClassificationRefresh(resetCustom = false) {
        if (resetCustom) customRequestedServices = null;
        window.clearTimeout(classifyTimer);
        classifyTimer = window.setTimeout(refreshClassification, 80);
    }

    async function loadSosContacts() {
        if (!elements.sosContactsList || !elements.sosContactsStatus) return;
        elements.sosContactsList.replaceChildren();
        if (!currentUser) {
            elements.sosContactsStatus.textContent = "Sign in to view and call your saved emergency contacts.";
            return;
        }
        elements.sosContactsStatus.textContent = "Loading saved contacts…";
        try {
            const data = await window.ResqlinkApi.request("/contacts", { method: "GET" });
            const contacts = (data && Array.isArray(data.contacts)) ? data.contacts : [];
            if (contacts.length === 0) {
                elements.sosContactsStatus.textContent = "No emergency contacts saved yet. Add one on the Contacts page.";
                return;
            }
            elements.sosContactsStatus.textContent = `${contacts.length} saved emergency contact${contacts.length === 1 ? "" : "s"} ready for manual call or fallback log.`;
            contacts.slice(0, 4).forEach(contact => {
                const callLink = el("a", {
                    href: `tel:${contact.phone}`,
                    className: "rq-btn rq-btn-sm rq-btn-danger",
                    text: "Call"
                });
                const copyBtn = el("button", {
                    type: "button",
                    className: "rq-btn rq-btn-sm",
                    text: "Copy"
                });
                copyBtn.addEventListener("click", async () => {
                    try {
                        await navigator.clipboard.writeText(`${contact.name} (${contact.relationship}): ${contact.phone}`);
                        copyBtn.textContent = "Copied";
                        window.setTimeout(() => { copyBtn.textContent = "Copy"; }, 1600);
                    } catch (_e) {
                        copyBtn.textContent = contact.phone;
                    }
                });
                const notifyBtn = el("button", {
                    type: "button",
                    className: "rq-btn rq-btn-sm",
                    text: "Notify"
                });
                notifyBtn.addEventListener("click", async () => {
                    notifyBtn.disabled = true;
                    try {
                        const res = await window.ResqlinkApi.request(
                            `/contacts/${encodeURIComponent(contact.id)}/notify`,
                            {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                    channel: "SMS",
                                    consent_confirmed: true,
                                    message_preview: "SOS alert check-in from ResQlink"
                                })
                            }
                        );
                        elements.sosContactsStatus.textContent = res.sent
                            ? `Notification sent to ${contact.name}.`
                            : `${res.detail}`;
                    } catch (err) {
                        elements.sosContactsStatus.textContent = err.message;
                    } finally {
                        notifyBtn.disabled = false;
                    }
                });

                elements.sosContactsList.append(
                    el("div", { className: "contact-mini-row" },
                        el("div", {},
                            el("strong", { text: contact.name }),
                            contact.is_primary ? el("span", { className: "rq-pill status-DISPATCHED", style: "margin-left:6px;", text: "Primary" }) : null,
                            el("div", { className: "rq-muted", style: "font-size:12px;", text: `${contact.relationship} · ${contact.phone}` })
                        ),
                        el("div", { className: "contact-mini-actions" }, callLink, copyBtn, notifyBtn)
                    )
                );
            });
        } catch (error) {
            elements.sosContactsStatus.textContent = `Contacts unavailable: ${error.message}`;
        }
    }

    function discardPendingRetry() {
        try {
            sessionStorage.removeItem(PENDING_ATTEMPT_KEY);
        } catch (_error) {
            setProgress(
                "error",
                "The saved retry could not be cleared. No new alert was sent.",
                "RETRY NOT CLEARED"
            );
            return;
        }
        pendingAttempt = null;
        pendingAttemptCorrupt = false;
        elements.severity.disabled = false;
        if (elements.category) elements.category.disabled = false;
        elements.button.disabled = !currentUser;
        elements.button.querySelector(".sos-button-label").textContent = "SOS";
        elements.button.querySelector(".sos-button-subtitle").textContent = "SEND ALERT";
        showRecoveryActions();
        setProgress(
            "ready",
            "The saved retry was cleared. Its previous submission status is unknown, so a new alert may create a second record.",
            "PREVIOUS UNKNOWN"
        );
    }

    function updateLocationStatus(state, message) {
        elements.gpsIndicator.dataset.state = state;
        elements.locationStatus.textContent = message;
    }

    function clearMapLocation(message) {
        approximateLocation = null;
        if (locationMarker) {
            map.removeLayer(locationMarker);
            locationMarker = null;
        }
        if (accuracyCircle) {
            map.removeLayer(accuracyCircle);
            accuracyCircle = null;
        }
        elements.latitude.textContent = "—";
        elements.longitude.textContent = "—";
        elements.accuracyWrap.hidden = true;
        elements.mapOverlay.hidden = false;
        elements.mapMessage.textContent = message;
        elements.mapElement.setAttribute("aria-label", `Map preview. ${message}`);
    }

    function initializeMap() {
        if (!window.L) {
            elements.mapMessage.textContent =
                "Map preview unavailable. GPS and alert submission still work.";
            return;
        }

        map = L.map(elements.mapElement, {
            zoomControl: false,
            scrollWheelZoom: false,
            dragging: false,
            doubleClickZoom: false,
            touchZoom: false,
            keyboard: false,
            attributionControl: true
        }).setView([0, 0], 1);
        L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
            maxZoom: 19,
            attribution: "&copy; OpenStreetMap contributors"
        }).addTo(map);
        window.setTimeout(() => map.invalidateSize(), 0);
    }

    function isValidCoordinates(coords) {
        return coords
            && typeof coords.latitude === "number"
            && Number.isFinite(coords.latitude)
            && coords.latitude >= -90
            && coords.latitude <= 90
            && typeof coords.longitude === "number"
            && Number.isFinite(coords.longitude)
            && coords.longitude >= -180
            && coords.longitude <= 180
            && typeof coords.accuracy === "number"
            && Number.isFinite(coords.accuracy)
            && coords.accuracy >= 0;
    }

    function showLocationOnMap(coords) {
        if (!map) return;
        const position = [coords.latitude, coords.longitude];
        const radius = Math.max(coords.accuracy, 5);
        if (locationMarker) map.removeLayer(locationMarker);
        if (accuracyCircle) map.removeLayer(accuracyCircle);
        locationMarker = L.circleMarker(position, {
            radius: 6,
            color: "#fff",
            weight: 2,
            fillColor: "#e84a48",
            fillOpacity: 1
        }).addTo(map);
        accuracyCircle = L.circle(position, {
            radius,
            color: "#ed6a64",
            weight: 1,
            fillColor: "#ed6a64",
            fillOpacity: 0.13
        }).addTo(map);
        map.setView(position, coords.accuracy > 1000 ? 11 : 15, { animate: false });
        elements.mapOverlay.hidden = true;
        elements.mapElement.setAttribute(
            "aria-label",
            `Map preview of the provided GPS location with an estimated accuracy radius of ${Math.round(coords.accuracy)} metres.`
        );
    }

    function showCoordinates(coords) {
        elements.latitude.textContent = coords.latitude.toFixed(5);
        elements.longitude.textContent = coords.longitude.toFixed(5);
        elements.accuracyWrap.hidden = false;
        elements.accuracy.textContent = `±${Math.round(coords.accuracy)} m`;
        const meterScale = Math.max(
            0.08,
            Math.min(1, 100 / Math.max(coords.accuracy, 1))
        );
        elements.accuracyMeter.style.transform = `scaleX(${meterScale})`;
        elements.accuracyMeter.style.background =
            coords.accuracy > MAX_ACCEPTABLE_ACCURACY_M
                ? "var(--amber)"
                : "var(--green)";
        updateLocationStatus(
            "located",
            coords.accuracy > MAX_ACCEPTABLE_ACCURACY_M
                ? "Location found · approximate"
                : "Location found"
        );
        showLocationOnMap(coords);
    }

    function locationErrorMessage(error) {
        if (!navigator.geolocation) {
            return "This browser does not support GPS location.";
        }
        if (error && error.code === 1) {
            return "Location permission was denied. Allow location access in your browser, or submit without location.";
        }
        if (error && error.code === 2) {
            return "Your device could not determine a location. Check location services or submit without location.";
        }
        if (error && error.code === 3) {
            return "GPS timed out before a fix was available. Try again or submit without location.";
        }
        return "GPS is unavailable. Try again or submit without location.";
    }

    function getCurrentLocation() {
        return new Promise((resolve, reject) => {
            if (!navigator.geolocation) {
                reject({ code: 2 });
                return;
            }
            navigator.geolocation.getCurrentPosition(
                position => resolve(position.coords),
                reject,
                {
                    enableHighAccuracy: true,
                    timeout: GPS_TIMEOUT_MS,
                    maximumAge: 0
                }
            );
        });
    }

    function readPendingAttempt() {
        try {
            const serialized = sessionStorage.getItem(PENDING_ATTEMPT_KEY);
            if (!serialized) return null;
            const attempt = JSON.parse(serialized);
            const payload = attempt && attempt.payload;
            const hasCoordinates = payload
                && payload.latitude !== null
                && payload.longitude !== null;
            const coordinatePairValid = hasCoordinates
                ? typeof payload.latitude === "number"
                    && Number.isFinite(payload.latitude)
                    && payload.latitude >= -90
                    && payload.latitude <= 90
                    && typeof payload.longitude === "number"
                    && Number.isFinite(payload.longitude)
                    && payload.longitude >= -180
                    && payload.longitude <= 180
                : payload
                    && payload.latitude === null
                    && payload.longitude === null;
            const accuracyValid = payload
                && (
                    payload.location_accuracy_m === null
                    || (
                        hasCoordinates
                        && typeof payload.location_accuracy_m === "number"
                        && Number.isFinite(payload.location_accuracy_m)
                        && payload.location_accuracy_m >= 0
                    )
                );
            if (
                attempt
                && typeof attempt.key === "string"
                && /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(attempt.key)
                && typeof attempt.userId === "string"
                && payload
                && Number.isInteger(payload.severity)
                && payload.severity >= 1
                && payload.severity <= 5
                && coordinatePairValid
                && accuracyValid
                && typeof payload.location_accuracy_confirmed === "boolean"
                && (hasCoordinates || !payload.location_accuracy_confirmed)
                && (
                    payload.location_accuracy_m === null
                    || payload.location_accuracy_m <= MAX_ACCEPTABLE_ACCURACY_M
                    || payload.location_accuracy_confirmed
                )
            ) {
                return attempt;
            }
            pendingAttemptCorrupt = true;
        } catch (_error) {
            pendingAttemptCorrupt = true;
        }
        return null;
    }

    function makeIdempotencyKey() {
        if (!window.crypto || !window.crypto.getRandomValues) {
            throw new Error(
                "Secure retry protection is unavailable in this browser. Use a modern browser and try again."
            );
        }
        if (window.crypto.randomUUID) return window.crypto.randomUUID();

        const bytes = new Uint8Array(16);
        window.crypto.getRandomValues(bytes);
        bytes[6] = (bytes[6] & 0x0f) | 0x40;
        bytes[8] = (bytes[8] & 0x3f) | 0x80;
        const hex = Array.from(bytes, value => value.toString(16).padStart(2, "0"));
        return [
            hex.slice(0, 4).join(""),
            hex.slice(4, 6).join(""),
            hex.slice(6, 8).join(""),
            hex.slice(8, 10).join(""),
            hex.slice(10).join("")
        ].join("-");
    }

    function showAuthError(error) {
        currentUser = null;
        elements.button.disabled = true;
        showRecoveryActions({ auth: error.code !== "unauthenticated" });
        elements.signInLink.hidden = false;
        setProgress(
            "auth-error",
            error.code === "unauthenticated"
                ? "Sign in to submit an alert. Your session is verified with the ResQlink API before GPS is requested."
                : `${error.message} Check your connection, then verify your session again.`,
            error.code === "unauthenticated" ? "SIGN IN" : "SESSION ERROR"
        );
        loadSosContacts();
    }

    async function verifySession() {
        elements.button.disabled = true;
        setProgress("checking", "Verifying your ResQlink session…", "VERIFYING");
        try {
            const user = await window.ResqlinkUI.initNav("sos", { requireAuth: false });
            if (!user) {
                throw { code: "unauthenticated", message: "Sign in to submit an alert." };
            }
            currentUser = user;
            elements.signInLink.hidden = true;
            elements.button.disabled = false;
            loadSosContacts();

            if (pendingAttemptCorrupt) {
                elements.severity.disabled = true;
                if (elements.category) elements.category.disabled = true;
                showRecoveryActions({ discard: true });
                setProgress(
                    "error",
                    "A saved alert retry could not be verified. No new alert will be sent to avoid creating a duplicate. You can clear the saved retry only if you accept that its previous submission status will remain unknown.",
                    "RETRY CHECK"
                );
                elements.button.disabled = true;
                return;
            }
            if (pendingAttempt && pendingAttempt.userId !== user.id) {
                elements.severity.disabled = true;
                if (elements.category) elements.category.disabled = true;
                elements.button.disabled = true;
                showRecoveryActions();
                elements.signInLink.textContent = "Switch to the original account to retry";
                elements.signInLink.hidden = false;
                setProgress(
                    "error",
                    "A previous alert belongs to a different account and its result is unconfirmed. Sign in with the original account to retry it safely; a new account cannot reuse that request.",
                    "ACCOUNT MISMATCH"
                );
                return;
            }
            if (pendingAttempt) {
                elements.severity.value = String(pendingAttempt.payload.severity);
                elements.severity.disabled = true;
                if (elements.category && pendingAttempt.payload.category) {
                    elements.category.value = pendingAttempt.payload.category;
                    elements.category.disabled = true;
                }
                if (Array.isArray(pendingAttempt.payload.requested_services)) {
                    customRequestedServices = pendingAttempt.payload.requested_services;
                }
                if (pendingAttempt.payload.latitude === null) {
                    elements.latitude.textContent = "Not provided";
                    elements.longitude.textContent = "Not provided";
                    elements.mapMessage.textContent =
                        "This pending alert was intentionally submitted without location";
                } else {
                    const coords = {
                        latitude: pendingAttempt.payload.latitude,
                        longitude: pendingAttempt.payload.longitude,
                        accuracy: pendingAttempt.payload.location_accuracy_m || 0
                    };
                    showCoordinates(coords);
                }
                elements.button.querySelector(".sos-button-label").textContent = "RETRY";
                elements.button.querySelector(".sos-button-subtitle").textContent = "SAME ALERT";
                setProgress(
                    "error",
                    "A previous submission was not confirmed. Press SOS to retry the same alert safely.",
                    "AWAITING RETRY"
                );
                refreshClassification();
                return;
            }
            setProgress(
                "ready",
                "Ready when you are. Your alert will be sent to the ResQlink API.",
                "READY"
            );
        } catch (error) {
            showAuthError(error);
        }
    }

    async function sendAttempt(attempt) {
        if (flowBusy || !currentUser || attempt.userId !== currentUser.id) return;
        flowBusy = true;
        elements.button.disabled = true;
        elements.button.querySelector(".sos-button-label").textContent = "SENDING";
        elements.button.querySelector(".sos-button-subtitle").textContent = "PLEASE WAIT";
        showRecoveryActions();
        setProgress("submitting", "Sending your report securely to the ResQlink API…", "SENDING");
        try {
            const result = await window.ResqlinkApi.submitEmergency(
                attempt.payload,
                attempt.key
            );
            const submittedAt = new Date();
            elements.successAlertId.textContent = `Alert #${result.alert_id}`;
            elements.successTimestamp.dateTime = submittedAt.toISOString();
            elements.successTimestamp.textContent = `Recorded ${submittedAt.toLocaleString()}`;
            pendingAttempt = null;
            try {
                sessionStorage.removeItem(PENDING_ATTEMPT_KEY);
                elements.severity.disabled = false;
                if (elements.category) elements.category.disabled = false;
            } catch (_error) {
                pendingAttempt = attempt;
            }
            showRecoveryActions();
            const duplicate = result.submission_status === "already_submitted";
            setProgress(
                "success",
                `${duplicate ? "This alert was already recorded" : "Alert recorded"} as #${result.alert_id} (${result.status}). Public emergency services were not contacted.`,
                duplicate ? "ALREADY SAVED" : "RECORDED"
            );
            elements.button.querySelector(".sos-button-label").textContent = "SENT";
            elements.button.querySelector(".sos-button-subtitle").textContent = "RECORDED";
            if (pendingAttempt) {
                elements.button.disabled = true;
                elements.newAlertButton.hidden = true;
                setProgress(
                    "success",
                    "The alert is confirmed, but its retry key could not be cleared. Close this tab before starting another alert.",
                    "RECORDED"
                );
            } else {
                elements.button.disabled = true;
                elements.newAlertButton.hidden = false;
            }
        } catch (error) {
            if (error.code === "expired" || error.code === "unauthenticated") {
                currentUser = null;
                elements.button.querySelector(".sos-button-label").textContent = "SIGN IN";
                elements.button.querySelector(".sos-button-subtitle").textContent = "TO RETRY";
                elements.signInLink.hidden = false;
                showRecoveryActions();
                setProgress(
                    "auth-error",
                    `${error.message} The exact alert remains saved in this tab for retry after sign-in.`,
                    "SESSION EXPIRED"
                );
            } else {
                elements.button.querySelector(".sos-button-label").textContent = "RETRY";
                elements.button.querySelector(".sos-button-subtitle").textContent = "SAME ALERT";
                showRecoveryActions();
                setProgress(
                    "error",
                    `${error.message} The alert is not confirmed. Press SOS to retry the same request safely.`,
                    error.code === "timeout" ? "NO CONFIRMATION" : "NOT CONFIRMED"
                );
            }
        } finally {
            flowBusy = false;
            elements.button.disabled = !currentUser || !elements.successPanel.hidden;
        }
    }

    async function createAttempt(coords) {
        let attempt;
        try {
            const severity = Number(elements.severity.value);
            const category = elements.category ? elements.category.value : "PERSONAL_SAFETY";
            const requested = customRequestedServices !== null
                ? customRequestedServices
                : (currentClassification ? currentClassification.requested_services : null);
            const notes = elements.notes ? elements.notes.value.trim() : "";

            const payload = {
                severity,
                category,
                latitude: coords ? coords.latitude : null,
                longitude: coords ? coords.longitude : null,
                location_accuracy_m: coords ? coords.accuracy : null,
                location_accuracy_confirmed: Boolean(
                    coords && coords.accuracy > MAX_ACCEPTABLE_ACCURACY_M
                )
            };
            if (Array.isArray(requested)) {
                payload.requested_services = requested;
            }
            if (notes) {
                payload.notes = notes;
            }

            attempt = {
                key: makeIdempotencyKey(),
                userId: currentUser.id,
                payload
            };
            sessionStorage.setItem(PENDING_ATTEMPT_KEY, JSON.stringify(attempt));
        } catch (error) {
            showRecoveryActions();
            setProgress(
                "error",
                `${error.message || "The retry key could not be saved."} No alert was sent.`,
                "NOT SENT"
            );
            elements.button.disabled = false;
            return;
        }
        pendingAttempt = attempt;
        elements.severity.disabled = true;
        if (elements.category) elements.category.disabled = true;
        await sendAttempt(attempt);
    }

    async function requestLocationAndSubmit() {
        if (flowBusy || !currentUser) return;
        if (pendingAttempt) {
            await sendAttempt(pendingAttempt);
            return;
        }
        flowBusy = true;
        elements.button.disabled = true;
        elements.button.querySelector(".sos-button-label").textContent = "LOCATING";
        elements.button.querySelector(".sos-button-subtitle").textContent = "PLEASE WAIT";
        showRecoveryActions();
        clearMapLocation("Waiting for a fresh GPS location");
        updateLocationStatus("locating", "Requesting device location…");
        setProgress(
            "locating",
            "Requesting a fresh GPS fix. If location is unavailable, you can retry or deliberately continue without it.",
            "LOCATING"
        );

        try {
            const coords = await getCurrentLocation();
            if (!isValidCoordinates(coords)) {
                throw new Error(
                    "The browser returned invalid location data. Try GPS again or submit without location."
                );
            }
            approximateLocation = {
                latitude: coords.latitude,
                longitude: coords.longitude,
                accuracy: coords.accuracy
            };
            showCoordinates(approximateLocation);
            if (coords.accuracy > MAX_ACCEPTABLE_ACCURACY_M) {
                flowBusy = false;
                elements.button.disabled = false;
                elements.button.querySelector(".sos-button-label").textContent = "SOS";
                elements.button.querySelector(".sos-button-subtitle").textContent = "SEND ALERT";
                elements.locationActions.hidden = false;
                elements.useApproximate.hidden = false;
                elements.withoutLocation.hidden = false;
                elements.retryLocation.hidden = false;
                setProgress(
                    "error",
                    `GPS accuracy is approximately ±${Math.round(coords.accuracy)} m. Retry for a better fix, explicitly use this approximate location, or submit without location.`,
                    "LOCATION CHECK"
                );
                return;
            }
            flowBusy = false;
            await createAttempt(approximateLocation);
        } catch (error) {
            clearMapLocation("Location unavailable; no coordinates will be guessed");
            updateLocationStatus("error", "Location unavailable");
            flowBusy = false;
            elements.button.disabled = false;
            elements.button.querySelector(".sos-button-label").textContent = "SOS";
            elements.button.querySelector(".sos-button-subtitle").textContent = "SEND ALERT";
            elements.locationActions.hidden = false;
            elements.retryLocation.hidden = false;
            elements.useApproximate.hidden = true;
            elements.withoutLocation.hidden = false;
            setProgress("error", error.message || locationErrorMessage(error), "GPS UNAVAILABLE");
        }
    }

    async function submitWithoutLocation() {
        if (flowBusy || !currentUser) return;
        clearMapLocation("No coordinates will be included in this alert");
        updateLocationStatus("error", "Submitting without location by choice");
        elements.locationActions.hidden = true;
        await createAttempt(null);
    }

    async function retryLocation() {
        if (flowBusy || !currentUser) return;
        await requestLocationAndSubmit();
    }

    async function useApproximateLocation() {
        if (
            flowBusy
            || !currentUser
            || !approximateLocation
            || approximateLocation.accuracy <= MAX_ACCEPTABLE_ACCURACY_M
        ) {
            return;
        }
        elements.locationActions.hidden = true;
        await createAttempt(approximateLocation);
    }

    function prepareAnotherAlert() {
        if (flowBusy || pendingAttempt) return;
        elements.successPanel.hidden = true;
        elements.newAlertButton.hidden = true;
        elements.severity.disabled = false;
        if (elements.category) elements.category.disabled = false;
        customRequestedServices = null;
        if (elements.notes) elements.notes.value = "";
        elements.button.disabled = false;
        elements.button.querySelector(".sos-button-label").textContent = "SOS";
        elements.button.querySelector(".sos-button-subtitle").textContent = "SEND ALERT";
        clearMapLocation("Map preview appears after GPS is available");
        updateLocationStatus("idle", "Not requested");
        setProgress("ready", "Ready when you are. Your alert will be sent to the ResQlink API.", "READY");
        refreshClassification();
    }

    elements.button.addEventListener("click", requestLocationAndSubmit);
    elements.retryLocation.addEventListener("click", retryLocation);
    elements.useApproximate.addEventListener("click", useApproximateLocation);
    elements.withoutLocation.addEventListener("click", submitWithoutLocation);
    elements.discardPending.addEventListener("click", discardPendingRetry);
    elements.retryAuth.addEventListener("click", verifySession);
    elements.newAlertButton.addEventListener("click", prepareAnotherAlert);
    elements.severity.addEventListener("change", () => scheduleClassificationRefresh(true));
    if (elements.category) {
        elements.category.addEventListener("change", () => scheduleClassificationRefresh(true));
    }

    initializeMap();
    pendingAttempt = readPendingAttempt();
    if (pendingAttemptCorrupt) {
        setProgress(
            "error",
            "A saved alert retry could not be verified. No new alert will be sent to avoid creating a duplicate. Contact your ResQlink administrator.",
            "RETRY CHECK"
        );
    }
    refreshClassification();
    verifySession();
})();
