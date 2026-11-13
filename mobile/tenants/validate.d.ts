export type TenantColors = {
    primary: string;
    primaryText: string;
    background: string;
    surface: string;
    text: string;
    mutedText: string;
    border: string;
    danger: string;
};
export type Tenant = {
    name: string;
    slug: string;
    scheme: string;
    ios: {
        bundleIdentifier: string;
    };
    android: {
        package: string;
    };
    colors: TenantColors;
    /** Optional overrides applied in dark mode. */
    colorsDark?: Partial<TenantColors>;
    apiBaseUrl: string;
    features: Record<string, boolean>;
};
/** Validate a parsed tenant.json; throws one Error listing every problem. */
export declare function validateTenant(raw: unknown, tenantName?: string): Tenant;
