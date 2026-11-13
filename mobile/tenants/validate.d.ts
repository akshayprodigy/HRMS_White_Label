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
    /** Marketing version (default 1.0.0). */
    version?: string;
    /** Increment per store upload: iOS buildNumber and Android versionCode (default 1). */
    buildNumber?: number;
    features: Record<string, boolean>;
};
/** Validate a parsed tenant.json; throws one Error listing every problem. */
export declare function validateTenant(raw: unknown, tenantName?: string): Tenant;
export declare function isLocalHost(url: string): boolean;
export declare function apiHost(url: string): string | null;
