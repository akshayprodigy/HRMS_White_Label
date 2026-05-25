import React, { useState, useEffect } from 'react';
import {
  Calendar,
  Plus,
  Trash2,
  MapPin,
  Pencil
} from 'lucide-react';
import { Card, Button } from './ui-elements';
import { toast } from 'sonner@2.0.3';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from './ui/dialog';
import { Input } from './ui/input';

const EMPTY_FORM = { name: '', date: '', location: 'All', is_optional: false, description: '' };

export const HolidayManagement = () => {
    const [holidays, setHolidays] = useState<any[]>([]);
    const [isLoading, setIsLoading] = useState(true);
    const [isModalOpen, setIsModalOpen] = useState(false);
    const [editingId, setEditingId] = useState<number | null>(null);
    const [formData, setFormData] = useState({ ...EMPTY_FORM });

    useEffect(() => {
        fetchHolidays();
    }, []);

    const fetchHolidays = async () => {
        setIsLoading(true);
        try {
            const res = await client.get(ENDPOINTS.HR.HOLIDAYS);
            setHolidays(res.data.sort((a: any, b: any) => a.date.localeCompare(b.date)));
        } catch {
            toast.error("Failed to load holiday calendar");
        } finally {
            setIsLoading(false);
        }
    };

    const openAdd = () => {
        setEditingId(null);
        setFormData({ ...EMPTY_FORM });
        setIsModalOpen(true);
    };

    const openEdit = (holiday: any) => {
        setEditingId(holiday.id);
        setFormData({
            name: holiday.name,
            date: holiday.date,
            location: holiday.location,
            is_optional: holiday.is_optional,
            description: holiday.description || ''
        });
        setIsModalOpen(true);
    };

    const handleSave = async () => {
        if (!formData.name || !formData.date) {
            toast.error("Name and date are required");
            return;
        }
        try {
            if (editingId !== null) {
                await client.put(ENDPOINTS.HR.HOLIDAY_DETAIL(editingId), formData);
                toast.success("Holiday updated");
            } else {
                await client.post(ENDPOINTS.HR.HOLIDAYS, formData);
                toast.success("Holiday added");
            }
            setIsModalOpen(false);
            fetchHolidays();
        } catch {
            toast.error(editingId ? "Failed to update holiday" : "Failed to add holiday");
        }
    };

    const handleDelete = async (id: number) => {
        if (!confirm("Remove this holiday from the corporate calendar?")) return;
        try {
            await client.delete(ENDPOINTS.HR.HOLIDAY_DETAIL(id));
            toast.success("Holiday removed");
            fetchHolidays();
        } catch {
            toast.error("Deletion failed");
        }
    };

    const confirmed = holidays.filter(h => !h.is_optional);
    const optional = holidays.filter(h => h.is_optional);

    return (
        <div className="p-8 space-y-10 max-w-[1400px] mx-auto animate-in fade-in duration-500">
            <div className="flex justify-between items-end">
                <div>
                    <h2 className="text-3xl font-black text-[#0F172A] tracking-tighter uppercase">Corporate Holiday Calendar</h2>
                    <p className="text-[#64748B] font-bold uppercase tracking-widest text-[10px] mt-1">Multi-Location Observance & Optional Leave Manifest</p>
                </div>
                <Button
                    onClick={openAdd}
                    className="h-12 px-8 bg-[#0F172A] text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-slate-800 transition-all shadow-xl shadow-slate-200"
                >
                    <Plus size={16} className="mr-2"/> Register Holiday
                </Button>
            </div>

            {isLoading ? (
                <div className="py-20 text-center font-black uppercase text-slate-400 tracking-widest animate-pulse">Accessing Calendar Data...</div>
            ) : (
                <>
                    {/* Confirmed Holidays */}
                    <section className="space-y-4">
                        <div className="flex items-center gap-3">
                            <span className="text-[10px] font-black text-blue-600 uppercase tracking-widest">Company Holidays</span>
                            <span className="bg-blue-50 text-blue-600 text-[9px] font-black px-2 py-0.5 rounded-full border border-blue-100">{confirmed.length}</span>
                        </div>
                        {confirmed.length === 0 ? (
                            <div className="py-10 text-center bg-white rounded-3xl border border-dashed border-slate-200 text-slate-400 font-bold uppercase tracking-widest text-xs">No confirmed holidays</div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                                {confirmed.map(holiday => (
                                    <HolidayCard key={holiday.id} holiday={holiday} onEdit={openEdit} onDelete={handleDelete} />
                                ))}
                            </div>
                        )}
                    </section>

                    {/* Optional Holidays */}
                    <section className="space-y-4">
                        <div className="flex items-center gap-3">
                            <span className="text-[10px] font-black text-amber-600 uppercase tracking-widest">Optional / Restricted Holidays</span>
                            <span className="bg-amber-50 text-amber-600 text-[9px] font-black px-2 py-0.5 rounded-full border border-amber-100">{optional.length}</span>
                        </div>
                        {optional.length === 0 ? (
                            <div className="py-10 text-center bg-white rounded-3xl border border-dashed border-slate-200 text-slate-400 font-bold uppercase tracking-widest text-xs">No optional holidays</div>
                        ) : (
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-5">
                                {optional.map(holiday => (
                                    <HolidayCard key={holiday.id} holiday={holiday} onEdit={openEdit} onDelete={handleDelete} />
                                ))}
                            </div>
                        )}
                    </section>
                </>
            )}

            {/* Add / Edit Modal */}
            <Dialog open={isModalOpen} onOpenChange={setIsModalOpen}>
                <DialogContent className="max-w-md p-0 overflow-hidden rounded-3xl border-none max-h-[90vh] min-h-[240px] flex flex-col">
                    <DialogHeader className="p-8 bg-[#0F172A] text-white">
                        <DialogTitle className="text-2xl font-black uppercase tracking-tighter">
                            {editingId ? 'Edit Holiday' : 'Register New Holiday'}
                        </DialogTitle>
                        <p className="text-slate-400 text-[10px] font-bold uppercase tracking-widest mt-1">
                            {editingId ? 'Changes will be visible to all employees immediately' : 'Add to the corporate holiday calendar'}
                        </p>
                    </DialogHeader>
                    <div className="p-8 space-y-6 flex-1 overflow-y-auto min-h-0">
                        <div className="space-y-2">
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Holiday Name</label>
                            <Input
                                value={formData.name}
                                onChange={(e) => setFormData({...formData, name: e.target.value})}
                                placeholder="e.g. Republic Day"
                                className="h-12 rounded-xl bg-slate-50 border-slate-100 font-bold"
                            />
                        </div>
                        <div className="grid grid-cols-2 gap-4">
                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Date</label>
                                <Input
                                    type="date"
                                    value={formData.date}
                                    onChange={(e) => setFormData({...formData, date: e.target.value})}
                                    className="h-12 rounded-xl bg-slate-50 border-slate-100 font-bold"
                                />
                            </div>
                            <div className="space-y-2">
                                <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Location</label>
                                <select
                                    value={formData.location}
                                    onChange={(e) => setFormData({...formData, location: e.target.value})}
                                    className="w-full h-12 rounded-xl bg-slate-50 border border-slate-100 px-4 text-xs font-bold outline-none focus:ring-2 focus:ring-blue-600/10"
                                >
                                    <option value="All">All Locations</option>
                                    <option value="HQ">HQ-Kolkata</option>
                                    <option value="Remote">Remote</option>
                                    <option value="Zonal">Zonal Offices</option>
                                </select>
                            </div>
                        </div>
                        <div className="space-y-2">
                            <label className="text-[10px] font-black text-slate-400 uppercase tracking-widest">Description (optional)</label>
                            <Input
                                value={formData.description}
                                onChange={(e) => setFormData({...formData, description: e.target.value})}
                                placeholder="Brief note about the holiday"
                                className="h-12 rounded-xl bg-slate-50 border-slate-100 font-bold"
                            />
                        </div>
                        <div className="flex items-center gap-3 p-4 bg-slate-50 rounded-2xl border border-slate-100">
                            <input
                                type="checkbox"
                                checked={formData.is_optional}
                                onChange={(e) => setFormData({...formData, is_optional: e.target.checked})}
                                id="is_optional"
                                className="w-5 h-5 rounded-lg border-slate-300 text-blue-600"
                            />
                            <label htmlFor="is_optional" className="text-[10px] font-black text-[#0F172A] uppercase tracking-widest">Optional / Restricted Holiday</label>
                        </div>
                    </div>
                    <DialogFooter className="p-8 bg-slate-50/50 border-t border-slate-100">
                        <Button variant="ghost" onClick={() => setIsModalOpen(false)} className="h-12 text-[10px] font-black uppercase tracking-widest">Cancel</Button>
                        <Button onClick={handleSave} className="h-12 px-8 bg-blue-600 text-white rounded-xl text-[10px] font-black uppercase tracking-widest hover:bg-blue-700">
                            {editingId ? 'Save Changes' : 'Add Holiday'}
                        </Button>
                    </DialogFooter>
                </DialogContent>
            </Dialog>
        </div>
    );
};

const HolidayCard = ({ holiday, onEdit, onDelete }: { holiday: any, onEdit: (h: any) => void, onDelete: (id: number) => void }) => {
    const isOptional = holiday.is_optional;
    return (
        <Card className={`p-6 bg-white border-slate-200 hover:shadow-lg transition-all group relative ${isOptional ? 'hover:border-amber-300' : 'hover:border-blue-300'}`}>
            <div className="absolute top-4 right-4 flex gap-1 opacity-0 group-hover:opacity-100 transition-all">
                <button
                    onClick={() => onEdit(holiday)}
                    className="p-2 text-slate-300 hover:text-blue-600 transition-colors"
                >
                    <Pencil size={14} />
                </button>
                <button
                    onClick={() => onDelete(holiday.id)}
                    className="p-2 text-slate-300 hover:text-red-600 transition-colors"
                >
                    <Trash2 size={14} />
                </button>
            </div>
            <div className="flex items-center gap-3 mb-4">
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${isOptional ? 'bg-amber-50 text-amber-400' : 'bg-blue-50 text-blue-400'}`}>
                    <Calendar size={18} />
                </div>
                <div>
                    <p className={`text-[10px] font-black uppercase tracking-widest ${isOptional ? 'text-amber-500' : 'text-blue-500'}`}>
                        {isOptional ? 'Optional Holiday' : 'Company Holiday'}
                    </p>
                    <h3 className="text-sm font-black text-[#0F172A] tracking-tight">{holiday.date}</h3>
                </div>
            </div>
            <h4 className="text-base font-black text-[#0F172A] mb-3 uppercase tracking-tight leading-tight">{holiday.name}</h4>
            <div className="flex items-center gap-2">
                <MapPin size={11} className="text-slate-400" />
                <span className="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{holiday.location}</span>
            </div>
            {holiday.description && (
                <p className="text-[10px] font-medium text-slate-400 bg-slate-50 p-3 rounded-lg border border-slate-100 italic mt-3">"{holiday.description}"</p>
            )}
        </Card>
    );
};
