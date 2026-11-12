import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';

export interface OnCallRule {
  id: number;
  name: string;
  payout_model: 'flat_per_day' | 'hourly';
  flat_amount: number;
  hourly_rate: number;
  is_active: boolean;
}
export interface OnCallDay {
  id: number;
  user_id?: number;
  user_name?: string | null;
  work_date: string;
  start_time: string;
  end_time: string;
  is_overnight: boolean;
  rule_id: number;
  rule_name: string | null;
  amount: number | null;
  paid: boolean;
  note: string | null;
}
export interface OnCallInput {
  user_id: number;
  work_date: string;
  start_time: string;
  end_time: string;
  rule_id: number;
  note?: string | null;
}

const E = ENDPOINTS.ROSTER;
const data = async <T,>(p: Promise<{ data: T }>): Promise<T> => (await p).data;

export const onCallApi = {
  rules: () => data<OnCallRule[]>(client.get(E.ON_CALL_RULES)),
  createRule: (b: Omit<OnCallRule, 'id'>) => data<OnCallRule>(client.post(E.ON_CALL_RULES, b)),
  updateRule: (id: number, b: Partial<Omit<OnCallRule, 'id'>>) =>
    data<OnCallRule>(client.patch(E.ON_CALL_RULE(id), b)),
  deleteRule: (id: number) => client.delete(E.ON_CALL_RULE(id)),
  list: (start: string, end: string, department?: string) =>
    data<OnCallDay[]>(
      client.get(E.ON_CALL, { params: { start, end, ...(department ? { department } : {}) } })
    ),
  create: (b: OnCallInput) => data<OnCallDay>(client.post(E.ON_CALL, b)),
  remove: (id: number) => client.delete(E.ON_CALL_DETAIL(id)),
  mine: () => data<OnCallDay[]>(client.get(E.MY_ON_CALL)),
};
