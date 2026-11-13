// Plain CommonJS on purpose: expo only transpiles app.config.ts itself, not its local imports.
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.validateTenant = validateTenant;
const COLOR_KEYS = [
    'primary',
    'primaryText',
    'background',
    'surface',
    'text',
    'mutedText',
    'border',
    'danger',
];
const HEX = /^#([0-9a-fA-F]{6}|[0-9a-fA-F]{8})$/;
const BUNDLE = /^[A-Za-z][A-Za-z0-9_-]*(\.[A-Za-z0-9_-]+)+$/;
const PACKAGE = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/;
function isObj(v) {
    return typeof v === 'object' && v !== null && !Array.isArray(v);
}
/** Validate a parsed tenant.json; throws one Error listing every problem. */
function validateTenant(raw, tenantName = 'tenant') {
    const errors = [];
    const t = isObj(raw) ? raw : {};
    if (!isObj(raw))
        errors.push('tenant.json must be a JSON object');
    const str = (key, v, re) => {
        if (typeof v !== 'string' || v.trim() === '')
            errors.push(`${key} is required (non-empty string)`);
        else if (re && !re.test(v))
            errors.push(`${key} has an invalid format: "${v}"`);
    };
    str('name', t.name);
    str('slug', t.slug, /^[a-z0-9][a-z0-9-]*$/);
    str('scheme', t.scheme, /^[a-z][a-z0-9+.-]*$/);
    str('ios.bundleIdentifier', isObj(t.ios) ? t.ios.bundleIdentifier : undefined, BUNDLE);
    str('android.package', isObj(t.android) ? t.android.package : undefined, PACKAGE);
    str('apiBaseUrl', t.apiBaseUrl, /^https?:\/\/[^\s]+$/);
    if (!isObj(t.colors))
        errors.push('colors is required (object)');
    else {
        for (const k of COLOR_KEYS) {
            const v = t.colors[k];
            if (typeof v !== 'string' || !HEX.test(v))
                errors.push(`colors.${k} must be a hex colour like #RRGGBB`);
        }
    }
    if (t.colorsDark !== undefined) {
        if (!isObj(t.colorsDark))
            errors.push('colorsDark must be an object');
        else
            for (const [k, v] of Object.entries(t.colorsDark))
                if (!COLOR_KEYS.includes(k) || typeof v !== 'string' || !HEX.test(v))
                    errors.push(`colorsDark.${k} is invalid`);
    }
    if (!isObj(t.features))
        errors.push('features is required (object, may be empty)');
    else
        for (const [k, v] of Object.entries(t.features))
            if (typeof v !== 'boolean')
                errors.push(`features.${k} must be boolean`);
    if (errors.length) {
        throw new Error(`Invalid tenant "${tenantName}":\n - ${errors.join('\n - ')}`);
    }
    return t;
}
