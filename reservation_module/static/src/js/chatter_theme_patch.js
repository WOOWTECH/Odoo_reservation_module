/** @odoo-module **/

/**
 * Portal Chatter Theme Bridge
 * ─────────────────────────────────────────
 * Portal Chatter is mounted into a Shadow DOM (see
 * portal.chatter.frontend.PortalChatterService.createShadow),
 * and its stylesheet is compiled from the BACKEND SCSS pipeline
 * (`portal.assets_chatter_style` bundle), which means the website
 * theme's brand colour, font-family and border-radius NEVER reach
 * the chatter — it always renders in the neutral Odoo backend look.
 *
 * This patch injects a stylesheet inside the shadow root that
 * re-uses the website theme's CSS custom properties (which DO
 * inherit through shadow boundaries), so the chatter picks up:
 *   - the theme's primary button colour (--o-cc1-btn-primary)
 *   - the theme's body font-family and text colour
 *   - the theme's link colour
 * ...without giving up the Shadow DOM's protection against theme
 * CSS accidentally breaking chatter layout.
 */
import { patch } from "@web/core/utils/patch";
import { PortalChatterService } from "@portal/chatter/frontend/portal_chatter_service";

patch(PortalChatterService.prototype, {
    async createShadow(root) {
        const shadow = await super.createShadow(root);
        if (!shadow) return shadow;

        const style = document.createElement("style");
        style.setAttribute("data-source", "reservation_module.chatter_theme_bridge");
        style.textContent = `
/* ── Inherit website theme brand colour + font on all chatter content ── */
/* --o-mail-Chatter-font-family is populated at runtime after theme CSS
   has loaded (see requestAnimationFrame block below). Until then this
   falls back to Chatter's own default. */
:host {
    --o-mail-Chatter-body-color: var(--body-color, #212529);
    --o-mail-Chatter-primary: var(--o-cc1-btn-primary, var(--o-color-primary, #714b67));
    --o-mail-Chatter-primary-text: var(--o-cc1-btn-primary-text, #ffffff);
    --o-mail-Chatter-primary-border: var(--o-cc1-btn-primary-border, var(--o-color-primary, #714b67));
    --o-mail-Chatter-link: var(--o-cc1-link, var(--o-color-primary, #714b67));
    color: var(--o-mail-Chatter-body-color);
    background-color: transparent;
}
.o-mail-Chatter,
.o-portal-Chatter,
.o-mail-Composer,
.o-mail-Message,
.o-mail-Thread {
    font-family: var(--o-mail-Chatter-font-family) !important;
    color: var(--o-mail-Chatter-body-color);
}
/* ── Transparent surfaces so the surrounding page theme shows through ──
   The chatter shadow root is a WHITE island when embedded on dark theme
   sections (e.g. theme_nano). Force chatter surfaces to inherit from the
   parent page instead of forcing white. */
.o-mail-Chatter,
.o-mail-Chatter-top,
.o-portal-Chatter,
.o-mail-Thread,
.o-mail-Thread-empty,
.o-mail-Composer,
.o-mail-Composer-coreMain,
.o-mail-Composer-coreHeader,
.o-mail-Composer-bg,
.o-mail-Message,
.o-mail-Message-body,
.o-mail-Message-content {
    background-color: transparent !important;
}
.o-mail-Composer-input,
.o-mail-Composer textarea,
.o-mail-Composer .form-control {
    background-color: rgba(255, 255, 255, 0.08) !important;
    color: var(--o-mail-Chatter-body-color) !important;
    border-color: rgba(128, 128, 128, 0.3) !important;
}
.o-mail-Composer-input::placeholder,
.o-mail-Composer textarea::placeholder {
    color: var(--o-mail-Chatter-body-color);
    opacity: 0.55;
}
/* Primary CTA button — align with website theme */
.o-mail-Chatter .btn-primary,
.o-mail-Composer .btn-primary,
.o-mail-Composer-send.btn-primary {
    background-color: var(--o-mail-Chatter-primary) !important;
    border-color: var(--o-mail-Chatter-primary-border) !important;
    color: var(--o-mail-Chatter-primary-text) !important;
}
.o-mail-Chatter .btn-primary:hover,
.o-mail-Composer .btn-primary:hover {
    filter: brightness(0.92);
}
/* Links (message links, mention chips, load-more) */
.o-mail-Chatter a,
.o-mail-Message a {
    color: var(--o-mail-Chatter-link);
}
        `.trim();
        shadow.appendChild(style);

        // Website theme CSS is loaded via <link> tags in <head>; on early
        // createShadow calls the outer <body> still reports the browser default
        // font. Defer the snapshot until after the next paint, when the theme
        // stylesheet is guaranteed to have applied. Set the CSS custom property
        // on the shadow host — it inherits into the shadow tree.
        const syncFontFromTheme = () => {
            const outerFont = getComputedStyle(document.body).fontFamily;
            if (outerFont) {
                shadow.host.style.setProperty("--o-mail-Chatter-font-family", outerFont);
            }
        };
        // Try immediately (fine if theme CSS already loaded) then again after
        // paint (catches slow theme bundles). document.fonts.ready flushes when
        // custom @font-face declarations settle — extra insurance for CJK fonts.
        syncFontFromTheme();
        requestAnimationFrame(syncFontFromTheme);
        if (document.fonts && document.fonts.ready) {
            document.fonts.ready.then(syncFontFromTheme).catch(() => {});
        }
        return shadow;
    },
});
