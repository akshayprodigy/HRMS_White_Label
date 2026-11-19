import React, { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Badge, Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Modal } from './modal';
import { AssetFormDialog } from './asset-form-dialog';
import { ActionKind, AssetActionDialog } from './allocate-return-dialogs';
import { MaintenanceSection } from './maintenance-section';
import {
  AssetDetail, AssetStatus, STATUS_BADGE, STATUS_LABEL, expiringSoon, fmtDate, fmtInr, holderText,
} from './asset-utils';

const ACTIONS: Record<AssetStatus, { kind: ActionKind; label: string }[]> = {
  in_stock: [
    { kind: 'allocate', label: 'Allocate' }, { kind: 'to_in_repair', label: 'Send to repair' },
    { kind: 'to_retired', label: 'Retire' }, { kind: 'lost', label: 'Mark lost' },
  ],
  allocated: [{ kind: 'return', label: 'Return' }, { kind: 'lost', label: 'Mark lost' }],
  in_repair: [
    { kind: 'to_in_stock', label: 'Back to stock' }, { kind: 'to_retired', label: 'Retire' },
    { kind: 'lost', label: 'Mark lost' },
  ],
  retired: [{ kind: 'to_in_stock', label: 'Reinstate' }],
  lost: [{ kind: 'to_in_stock', label: 'Reinstate' }],
};

const esc = (s: string) => s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c] as string));

const Field: React.FC<{ k: string; v: React.ReactNode; warn?: boolean }> = ({ k, v, warn }) => (
  <div>
    <div className="text-xs text-gray-500">{k}</div>
    <div className={`text-sm ${warn ? 'text-amber-700 font-medium' : 'text-gray-900'}`}>{v || '—'}</div>
  </div>
);

export const AssetDetailDialog: React.FC<{
  assetId: number; onClose: () => void; onChanged: () => void;
}> = ({ assetId, onClose, onChanged }) => {
  const [a, setA] = useState<AssetDetail | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [editing, setEditing] = useState(false);
  const [action, setAction] = useState<ActionKind | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await client.get<AssetDetail>(ENDPOINTS.ASSETS.DETAIL(assetId));
      setA(r.data);
      setErr(null);
    } catch (e: any) {
      setErr(errMsg(e, 'Could not load the asset'));
    }
  }, [assetId]);
  useEffect(() => { load(); }, [load]);

  useEffect(() => {
    let live = true;
    client.get(ENDPOINTS.ASSETS.QR(assetId), { responseType: 'text', transformResponse: (d) => d })
      .then((r) => { if (live) setQr(String(r.data)); })
      .catch(() => { if (live) setQr(null); });
    return () => { live = false; };
  }, [assetId]);

  const refresh = async () => { await load(); onChanged(); };

  const printLabel = () => {
    if (!a || !qr) return toast.error('QR code not available yet');
    const w = window.open('', '_blank', 'width=360,height=460');
    if (!w) return toast.error('Allow pop-ups to print the label');
    w.document.write(`<!doctype html><title>${esc(a.asset_tag)}</title>
<body style="font-family:sans-serif;text-align:center;margin:16px">
<div style="width:180px;margin:0 auto">${qr.replace(/<\?xml[^>]*\?>/, '')}</div>
<div style="font-size:18px;font-weight:700;margin-top:8px">${esc(a.asset_tag)}</div>
<div style="font-size:13px">${esc(a.name)}</div></body>`);
    w.document.close();
    w.focus();
    w.print();
  };

  if (!a) {
    return (
      <Modal title="Asset" label="Asset details" onClose={onClose}>
        {err ? <p role="alert" className="text-sm text-red-700">{err}</p> : <p className="text-sm text-gray-500">Loading…</p>}
        <div className="flex justify-end"><Button variant="outline" onClick={onClose}>Close</Button></div>
      </Modal>
    );
  }
  const d = a.depreciation;
  return (
    <>
      <Modal
        title={<span className="flex items-center gap-2 flex-wrap">{a.asset_tag} · {a.name}
          <Badge variant={STATUS_BADGE[a.status]}>{STATUS_LABEL[a.status]}</Badge></span>}
        label="Asset details" onClose={onClose} wide
      >
        <div className="flex gap-4 flex-wrap">
          <div className="w-28 flex-shrink-0 text-center">
            {qr
              ? <img alt={`QR code for ${a.asset_tag}`} className="w-28 h-28 border border-gray-200 rounded-lg"
                  src={`data:image/svg+xml;utf8,${encodeURIComponent(qr)}`} />
              : <div className="w-28 h-28 border border-gray-200 rounded-lg" />}
            <Button size="sm" variant="outline" className="mt-2" onClick={printLabel}>Print label</Button>
          </div>
          <div className="flex-1 grid grid-cols-2 md:grid-cols-3 gap-3">
            <Field k="Category" v={a.category.name} />
            <Field k="Model" v={a.model} />
            <Field k="Serial no" v={a.serial_no} />
            <Field k="Holder" v={a.holder ? holderText(a.holder) : null} />
            <Field k="Vendor" v={a.vendor} />
            <Field k="Invoice no" v={a.invoice_no} />
            <Field k="Purchase date" v={fmtDate(a.purchase_date)} />
            <Field k="Purchase cost" v={fmtInr(a.purchase_cost_paise)} />
            <Field k="Salvage value" v={fmtInr(a.salvage_value_paise)} />
            <Field k="Useful life" v={a.useful_life_months ? `${a.useful_life_months} months` : null} />
            <Field k="Warranty expiry" v={fmtDate(a.warranty_expiry)} warn={expiringSoon(a.warranty_expiry)} />
            <Field k="AMC" v={a.amc_vendor ? `${a.amc_vendor} · ${fmtDate(a.amc_expiry)}` : fmtDate(a.amc_expiry)} warn={expiringSoon(a.amc_expiry)} />
            <div className="col-span-2 md:col-span-3"><Field k="Notes" v={a.notes} /></div>
          </div>
        </div>

        <div className="flex gap-2 flex-wrap">
          <Button size="sm" variant="outline" onClick={() => setEditing(true)}>Edit</Button>
          {ACTIONS[a.status].map((x) => (
            <Button key={x.kind + x.label} size="sm" variant={x.kind === 'lost' ? 'danger' : 'primary'} onClick={() => setAction(x.kind)}>
              {x.label}
            </Button>
          ))}
        </div>

        <section className="space-y-2">
          <h4 className="text-sm font-semibold text-gray-900">Depreciation</h4>
          {d ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Field k="Cost" v={fmtInr(d.cost_paise)} />
              <Field k="Accumulated" v={fmtInr(d.accumulated_paise)} />
              <Field k="Book value" v={fmtInr(d.book_value_paise)} />
              <Field k="Months elapsed" v={`${d.months_elapsed} / ${d.life_months ?? '—'}`} />
            </div>
          ) : (
            <p className="text-sm text-gray-500">Needs purchase date, cost and useful life.</p>
          )}
        </section>

        <section className="space-y-2">
          <h4 className="text-sm font-semibold text-gray-900">Allocation history</h4>
          {a.history.length === 0 ? <p className="text-sm text-gray-500">Never allocated.</p> : (
            <ol className="border-l-2 border-gray-200 pl-4 space-y-3">
              {a.history.map((h) => (
                <li key={h.id} className="text-sm">
                  <div className="font-medium text-gray-900">
                    {h.employee_name}{h.emp_code ? ` (${h.emp_code})` : ''}
                    <span className="ml-2 text-xs font-normal text-gray-500">{h.status}</span>
                  </div>
                  <div className="text-xs text-gray-500">
                    {fmtDate(h.issued_date)} → {h.returned_date ? fmtDate(h.returned_date) : 'present'}
                    {h.allocated_by ? ` · issued by ${h.allocated_by}` : ''}
                    {h.condition ? ` · ${h.condition}` : ''}
                    {h.returned_condition ? ` → ${h.returned_condition}` : ''}
                  </div>
                  {h.remarks && <div className="text-xs text-gray-600">{h.remarks}</div>}
                </li>
              ))}
            </ol>
          )}
        </section>

        <MaintenanceSection asset={a} onChanged={refresh} />

        <div className="flex justify-end"><Button variant="outline" onClick={onClose}>Close</Button></div>
      </Modal>
      {editing && <AssetFormDialog asset={a} onClose={() => setEditing(false)} onSaved={() => { setEditing(false); refresh(); }} />}
      {action && <AssetActionDialog asset={a} kind={action} onClose={() => setAction(null)} onDone={() => { setAction(null); refresh(); }} />}
    </>
  );
};
