import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Briefcase, Loader2 } from 'lucide-react';
import { Card, Button, Badge, cn } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { REQ_BADGE, AssetRequest, fmtDate } from './asset-utils';
import { RequestAssetDialog } from './request-asset-dialog';

type MyRequest = Omit<AssetRequest, 'employee'>;

const tone: Record<string, string> = {
  allocated: 'bg-blue-50 text-blue-700 border-blue-200',
  returned: 'bg-emerald-50 text-emerald-700 border-emerald-200',
  lost: 'bg-red-50 text-red-700 border-red-200',
};

export const MyAssetsSection: React.FC = () => {
  const [assets, setAssets] = useState<any[]>([]);
  const [requests, setRequests] = useState<MyRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [reqErr, setReqErr] = useState<string | null>(null);
  const [showReq, setShowReq] = useState(false);
  const [confirmId, setConfirmId] = useState<number | null>(null);
  const [cancelling, setCancelling] = useState<number | null>(null);

  const load = useCallback(async () => {
    const [a, r] = await Promise.allSettled([
      client.get(ENDPOINTS.HR.MY_ASSETS),
      client.get<MyRequest[]>(ENDPOINTS.ASSETS.REQUESTS_MY),
    ]);
    if (a.status === 'fulfilled') setAssets(a.value.data || []);
    else {
      if ((a.reason as any)?.response?.status !== 404) toast.error(errMsg(a.reason, 'Failed to load assets'));
      setAssets([]);
    }
    if (r.status === 'fulfilled') { setRequests(r.value.data || []); setReqErr(null); }
    else {
      setRequests([]);
      setReqErr((r.reason as any)?.response?.status === 404 ? null : errMsg(r.reason, 'Failed to load requests'));
    }
  }, []);

  useEffect(() => {
    let live = true;
    load().finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [load]);

  const cancel = async (id: number) => {
    setCancelling(id);
    try {
      await client.post(ENDPOINTS.ASSETS.REQUEST_CANCEL(id));
      toast.success('Request cancelled');
      setConfirmId(null);
      await load();
    } catch (e: any) {
      toast.error(errMsg(e, 'Could not cancel the request'));
      await load();
      setConfirmId(null);
    } finally {
      setCancelling(null);
    }
  };

  return (
    <div className="space-y-8">
      <section className="flex items-start justify-between gap-4 flex-wrap">
        <div>
          <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em]">My Assigned Assets</h3>
          <p className="text-xs text-slate-400 mt-1">Hardware and equipment issued to you. Need something? Raise a request below.</p>
        </div>
        <Button onClick={() => setShowReq(true)}>Request an asset</Button>
      </section>

      {loading ? (
        <div className="p-12 flex justify-center"><Loader2 className="w-6 h-6 text-blue-600 animate-spin" /></div>
      ) : (
        <>
          {assets.length === 0 ? (
            <div className="p-12 bg-slate-50 rounded-3xl border border-dashed border-slate-200 text-center">
              <Briefcase size={36} className="mx-auto text-slate-300 mb-3" />
              <p className="text-sm font-black text-slate-500 uppercase tracking-widest">No assets on record</p>
              <p className="text-xs text-slate-400 mt-1 font-medium">When HR issues you hardware, it will appear here.</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
              {assets.map(a => (
                <Card key={a.id} className="p-6 border-slate-200 bg-white">
                  <div className="flex justify-between items-start mb-4">
                    <div className="p-3 bg-blue-50 text-blue-600 rounded-xl"><Briefcase size={18} /></div>
                    <span className={cn('text-[9px] font-black uppercase tracking-widest px-2 py-1 rounded-full border', tone[a.status] || 'bg-slate-100 text-slate-700 border-slate-200')}>
                      {a.status}
                    </span>
                  </div>
                  {a.identifier && <p className="text-lg font-black text-blue-700" data-testid="asset-tag">{a.identifier}</p>}
                  <p className="text-base font-black text-[#0F172A]">{a.model}</p>
                  <p className="text-[10px] font-bold text-blue-600 uppercase tracking-widest mt-1">{a.asset_type}</p>
                  <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-2 gap-3 text-[11px] font-bold text-slate-500">
                    <div>
                      <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Serial</p>
                      <p className="text-slate-700 mt-0.5">{a.serial_no || '—'}</p>
                    </div>
                    <div>
                      <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Issued</p>
                      <p className="text-slate-700 mt-0.5">{fmtDate(a.issued_date)}</p>
                    </div>
                    {a.condition && (
                      <div>
                        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Condition</p>
                        <p className="text-slate-700 mt-0.5">{a.condition}</p>
                      </div>
                    )}
                    {a.returned_date && (
                      <div>
                        <p className="text-[9px] font-black text-slate-400 uppercase tracking-widest">Returned</p>
                        <p className="text-slate-700 mt-0.5">{fmtDate(a.returned_date)}</p>
                      </div>
                    )}
                  </div>
                  {a.remarks && <p className="mt-4 text-[10px] text-slate-500 italic truncate" title={a.remarks}>{a.remarks}</p>}
                </Card>
              ))}
            </div>
          )}

          <section>
            <h3 className="text-[10px] font-black text-[#94A3B8] uppercase tracking-[0.2em] mb-3">My Requests</h3>
            {reqErr && <p role="alert" className="text-sm text-red-700 mb-2">{reqErr}</p>}
            {!reqErr && requests.length === 0 ? (
              <p className="text-xs text-slate-400">You have not requested any assets yet.</p>
            ) : (
              <ul className="space-y-3">
                {requests.map(r => (
                  <li key={r.id} className="p-4 bg-white rounded-xl border border-slate-200" data-testid="my-request">
                    <div className="flex items-start justify-between gap-3 flex-wrap">
                      <div className="min-w-0">
                        <p className="text-sm font-black text-[#0F172A]">{r.category.name}</p>
                        <p className="text-xs text-slate-600 mt-1 truncate max-w-md" title={r.reason}>{r.reason}</p>
                      </div>
                      <Badge variant={REQ_BADGE[r.status]}>{r.status}</Badge>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
                      <span>Needed by: {fmtDate(r.needed_by)}</span>
                      <span>Requested: {fmtDate(r.created_at)}</span>
                      {r.fulfilled_asset && <span className="font-bold text-emerald-700">Issued: {r.fulfilled_asset.asset_tag} · {r.fulfilled_asset.name}</span>}
                    </div>
                    {r.decision_note && <p className="mt-1 text-xs text-slate-600">Note: {r.decision_note}</p>}
                    {r.status === 'pending' && (
                      <div className="mt-3 flex items-center gap-2">
                        {confirmId === r.id ? (
                          <>
                            <span className="text-xs text-slate-600">Cancel this request?</span>
                            <Button variant="danger" onClick={() => cancel(r.id)} isLoading={cancelling === r.id}>Yes, cancel</Button>
                            <Button variant="outline" onClick={() => setConfirmId(null)} disabled={cancelling === r.id}>Keep</Button>
                          </>
                        ) : (
                          <Button variant="outline" onClick={() => setConfirmId(r.id)}>Cancel request</Button>
                        )}
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}

      {showReq && (
        <RequestAssetDialog
          onClose={() => setShowReq(false)}
          onDone={() => { setShowReq(false); load(); }}
        />
      )}
    </div>
  );
};
