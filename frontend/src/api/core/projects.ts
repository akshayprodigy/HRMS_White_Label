import { apiFetch } from '../client';

export type Project = {
  id: number;
  organization_id: number;
  site_id: number | null;
  code: string;
  name: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type ProjectCreate = {
  organization_id: number;
  site_id?: number | null;
  code: string;
  name: string;
  is_active?: boolean;
};

export function listProjects(): Promise<Project[]> {
  return apiFetch<Project[]>('/api/v1/core/projects');
}

export function createProject(payload: ProjectCreate): Promise<Project> {
  return apiFetch<Project>('/api/v1/core/projects', {
    method: 'POST',
    body: JSON.stringify({
      ...payload,
      site_id: payload.site_id ?? null,
      is_active: payload.is_active ?? true,
    }),
  });
}
