import { apiFetch } from '../client';

export type Site = {
  id: number;
  organization_id: number;
  code: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type SiteCreate = {
  organization_id: number;
  code: string;
  name: string;
  is_active?: boolean;
};

export function listSites(): Promise<Site[]> {
  return apiFetch<Site[]>('/api/v1/core/sites');
}

export function createSite(payload: SiteCreate): Promise<Site> {
  return apiFetch<Site>('/api/v1/core/sites', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      is_active: payload.is_active ?? true,
    }),
  });
}
