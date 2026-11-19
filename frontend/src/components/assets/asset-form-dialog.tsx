import React, { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '../ui-elements';
import { client } from '../../api/client';
import { ENDPOINTS } from '../../api/endpoints';
import { errMsg } from '../schedule-delegations-utils';
import { Modal } from './modal';
import {
  AssetCategory, AssetDetail, inputCls, labelCls, paiseToRupees, rupeesToPaise, todayIso,
} from './asset-utils';

interface Props {
  asset?: AssetDetail | null; // present = edit
  onClose: () => void;
  onSaved: (a: AssetDetail) => void;
}

const orNull = (s: string) => s.trim() || null;

export const AssetFormDialog: React.FC<Props> = ({ asset, onClose, onSaved }) => {
  const edit = !!asset;
  const [cats, setCats] = useState<AssetCategory[]>([]);
  const [f, setF] = useState({
    category_id: asset ? String(asset.category.id) : '',
    name: asset?.name ?? '',
    model: asset?.model ?? '',
    serial_no: asset?.serial_no ?? '',
    asset_tag: '',
    vendor: asset?.vendor ?? '',
    invoice_no: asset?.invoice_no ?? '',
    purchase_date: asset?.purchase_date ?? '',
    cost: paiseToRupees(asset?.purchase_cost_paise),
    salvage: asset ? paiseToRupees(asset.salvage_value_paise) : '0',
    life: asset?.useful_life_months != null ? String(asset.useful_life_months) : '',
    warranty_expiry: asset?.warranty_expiry ?? '',
    amc_vendor: asset?.amc_vendor ?? '',
    amc_expiry: asset?.amc_expiry ?? '',
    notes: asset?.notes ?? '',
  });
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const set = (k: keyof typeof f) => (e: React.ChangeEvent<any>) => setF((p) => ({ ...p, [k]: e.target.value }));

  useEffect(() => {
    client.get<AssetCategory[]>(ENDPOINTS.ASSETS.CATEGORIES)
      .then((r) => setCats(r.data.filter((c) => c.is_active || c.id === asset?.category.id)))
      .catch((e) => setErr(errMsg(e, 'Could not load categories')));
  }, [asset]);

  const save = async () => {
    if (!f.category_id) return setErr('Category is required.');
    if (!f.name.trim()) return setErr('Name is required.');
    const cost = rupeesToPaise(f.cost);
    const salvage = rupeesToPaise(f.salvage);
    if (Number.isNaN(cost) || Number.isNaN(salvage)) return setErr('Cost and salvage value must be non-negative amounts.');
    if (f.life.trim() && (!/^\d+$/.test(f.life.trim()) || Number(f.life) <= 0)) {
      return setErr('Useful life must be a whole number of months greater than 0.');
    }
    if (f.purchase_date && f.purchase_date > todayIso()) return setErr('Purchase date cannot be in the future.');
    const body: Record<string, unknown> = {
      category_id: Number(f.category_id),
      name: f.name.trim(),
      model: orNull(f.model),
      serial_no: orNull(f.serial_no),
      vendor: orNull(f.vendor),
      invoice_no: orNull(f.invoice_no),
      purchase_date: f.purchase_date || null,
      purchase_cost_paise: cost,
      salvage_value_paise: salvage ?? 0,
      useful_life_months: f.life.trim() ? Number(f.life) : null,
      warranty_expiry: f.warranty_expiry || null,
      amc_vendor: orNull(f.amc_vendor),
      amc_expiry: f.amc_expiry || null,
      notes: orNull(f.notes),
    };
    if (!edit && f.asset_tag.trim()) body.asset_tag = f.asset_tag.trim();
    setSaving(true);
    setErr(null);
    try {
      const r = edit
        ? await client.patch<AssetDetail>(ENDPOINTS.ASSETS.DETAIL(asset!.id), body)
        : await client.post<AssetDetail>(ENDPOINTS.ASSETS.LIST, body);
      toast.success(edit ? 'Asset updated' : `Asset ${r.data.asset_tag} created`);
      onSaved(r.data);
    } catch (e: any) {
      setErr(errMsg(e, 'Could not save the asset'));
    } finally {
      setSaving(false);
    }
  };

  const field = (id: string, label: string, k: keyof typeof f, extra: React.InputHTMLAttributes<HTMLInputElement> = {}) => (
    <div>
      <label className={labelCls} htmlFor={`af-${id}`}>{label}</label>
      <input id={`af-${id}`} className={`${inputCls} w-full`} value={f[k]} onChange={set(k)} {...extra} />
    </div>
  );

  return (
    <Modal title={edit ? `Edit ${asset!.asset_tag}` : 'Add asset'} label={edit ? 'Edit asset' : 'Add asset'} onClose={onClose} busy={saving} wide>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div>
          <label className={labelCls} htmlFor="af-category">Category *</label>
          <select id="af-category" className={`${inputCls} w-full`} value={f.category_id} onChange={set('category_id')}>
            <option value="">Select category…</option>
            {cats.map((c) => <option key={c.id} value={c.id}>{c.name} ({c.code})</option>)}
          </select>
        </div>
        {field('name', 'Name *', 'name', { maxLength: 150 })}
        {field('model', 'Model', 'model', { maxLength: 150 })}
        {field('serial', 'Serial no', 'serial_no', { maxLength: 100 })}
        {!edit && field('tag', 'Asset tag', 'asset_tag', { placeholder: 'auto', maxLength: 32 })}
        {field('vendor', 'Vendor', 'vendor', { maxLength: 150 })}
        {field('invoice', 'Invoice no', 'invoice_no', { maxLength: 64 })}
        {field('pdate', 'Purchase date', 'purchase_date', { type: 'date', max: todayIso() })}
        {field('cost', 'Purchase cost (₹)', 'cost', { type: 'number', min: 0, step: '0.01' })}
        {field('salvage', 'Salvage value (₹)', 'salvage', { type: 'number', min: 0, step: '0.01' })}
        {field('life', 'Useful life (months)', 'life', { type: 'number', min: 1, step: 1 })}
        {field('warranty', 'Warranty expiry', 'warranty_expiry', { type: 'date' })}
        {field('amcv', 'AMC vendor', 'amc_vendor', { maxLength: 150 })}
        {field('amce', 'AMC expiry', 'amc_expiry', { type: 'date' })}
      </div>
      <div>
        <label className={labelCls} htmlFor="af-notes">Notes</label>
        <textarea id="af-notes" rows={2} className={`${inputCls} w-full h-auto py-2`} value={f.notes} onChange={set('notes')} />
      </div>
      {err && <p role="alert" className="text-sm text-red-700">{err}</p>}
      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onClose} disabled={saving}>Cancel</Button>
        <Button onClick={save} isLoading={saving}>{edit ? 'Save' : 'Create'}</Button>
      </div>
    </Modal>
  );
};
