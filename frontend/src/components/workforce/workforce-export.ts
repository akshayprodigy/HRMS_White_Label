import { toast } from 'sonner';
import { formatRangeLabel, type DateRange } from '../period-picker';
import type { RosterRow, EmployeeBasic, EmployeeHeatmapDay } from './workforce-data';

function dateStamp(): string {
  const d = new Date();
  return `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
}

function rangeStamp(r: DateRange): string {
  const fmt = (d: Date) =>
    `${d.getFullYear()}${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
  return `${fmt(r.from)}-${fmt(r.to)}`;
}

export async function exportRosterPdf(roster: RosterRow[], range: DateRange): Promise<void> {
  try {
    const [{ default: jsPDF }, { default: autoTable }] = await Promise.all([
      import('jspdf'),
      import('jspdf-autotable'),
    ]);
    const doc = new jsPDF({ orientation: 'landscape', unit: 'pt', format: 'a4' });
    doc.setFontSize(16);
    doc.text('Workforce Attendance Report', 40, 40);
    doc.setFontSize(10);
    doc.setTextColor(100);
    doc.text(`Period: ${formatRangeLabel(range)}`, 40, 58);
    doc.text(`Generated: ${new Date().toLocaleString()}`, 40, 72);
    doc.text(`Employees: ${roster.length}`, 40, 86);

    autoTable(doc, {
      startY: 110,
      head: [
        ['Employee', 'Dept', 'Manager', 'Present', 'Working', 'Attn %', 'Late', 'Avg Hrs', 'Sick', 'Casual', 'Earned', 'Pending', 'Status'],
      ],
      body: roster.map(r => [
        r.user_name,
        r.department || '',
        r.manager_name || '',
        r.presentDays,
        r.workingDays,
        `${(r.presentPct * 100).toFixed(1)}%`,
        r.lateCount,
        r.avgHours > 0 ? r.avgHours.toFixed(1) : '',
        r.leaveByType.sick,
        r.leaveByType.casual,
        r.leaveByType.earned,
        r.pendingCorrections,
        r.status === 'on_track' ? 'On Track' : r.status === 'review' ? 'Review' : 'Flag',
      ]),
      styles: { fontSize: 8, cellPadding: 4 },
      headStyles: { fillColor: [15, 23, 42], textColor: [255, 255, 255] },
      alternateRowStyles: { fillColor: [248, 250, 252] },
    });

    doc.save(`workforce-attendance-${rangeStamp(range)}-${dateStamp()}.pdf`);
    toast.success('PDF exported');
  } catch (e: any) {
    console.error(e);
    toast.error('PDF export failed');
  }
}

export async function exportRosterXlsx(roster: RosterRow[], range: DateRange): Promise<void> {
  try {
    const XLSX = await import('xlsx');
    const wb = XLSX.utils.book_new();

    const meta = [
      ['Workforce Attendance Report'],
      [`Period`, formatRangeLabel(range)],
      [`Generated`, new Date().toLocaleString()],
      [`Employees`, roster.length],
      [],
    ];
    const header = [
      'Employee',
      'Email',
      'Department',
      'Manager',
      'Present Days',
      'Working Days',
      'Attendance %',
      'Late Count',
      'Avg Hours',
      'Sick',
      'Casual',
      'Earned',
      'Other',
      'Pending Corrections',
      'Status',
    ];
    const rows = roster.map(r => [
      r.user_name,
      r.user_email,
      r.department || '',
      r.manager_name || '',
      r.presentDays,
      r.workingDays,
      Number((r.presentPct * 100).toFixed(2)),
      r.lateCount,
      r.avgHours > 0 ? r.avgHours : null,
      r.leaveByType.sick,
      r.leaveByType.casual,
      r.leaveByType.earned,
      r.leaveByType.other,
      r.pendingCorrections,
      r.status === 'on_track' ? 'On Track' : r.status === 'review' ? 'Review' : 'Flag',
    ]);
    const ws = XLSX.utils.aoa_to_sheet([...meta, header, ...rows]);
    ws['!cols'] = [
      { wch: 24 }, { wch: 28 }, { wch: 18 }, { wch: 20 },
      { wch: 12 }, { wch: 12 }, { wch: 14 }, { wch: 10 },
      { wch: 10 }, { wch: 8 }, { wch: 8 }, { wch: 8 }, { wch: 8 },
      { wch: 18 }, { wch: 12 },
    ];
    XLSX.utils.book_append_sheet(wb, ws, 'Roster');

    XLSX.writeFile(wb, `workforce-attendance-${rangeStamp(range)}-${dateStamp()}.xlsx`);
    toast.success('Excel exported');
  } catch (e: any) {
    console.error(e);
    toast.error('Excel export failed');
  }
}

export async function exportEmployeePdf(
  employee: EmployeeBasic,
  range: DateRange,
  heatmap: EmployeeHeatmapDay[],
  summary: { presentDays: number; working: number; late: number; pct: number; avgHours: number; leaveDays: number },
): Promise<void> {
  try {
    const [{ default: jsPDF }, { default: autoTable }] = await Promise.all([
      import('jspdf'),
      import('jspdf-autotable'),
    ]);
    const doc = new jsPDF({ orientation: 'portrait', unit: 'pt', format: 'a4' });
    doc.setFontSize(16);
    doc.text('Employee Attendance Report', 40, 40);
    doc.setFontSize(11);
    doc.setTextColor(15, 23, 42);
    doc.text(employee.full_name, 40, 60);
    doc.setFontSize(9);
    doc.setTextColor(100);
    const meta = [employee.department, employee.designation, employee.email, employee.employee_id ? `ID #${employee.employee_id}` : null]
      .filter(Boolean)
      .join('  ·  ');
    doc.text(meta, 40, 74);
    doc.text(`Period: ${formatRangeLabel(range)}`, 40, 90);

    autoTable(doc, {
      startY: 110,
      head: [['Metric', 'Value']],
      body: [
        ['Present Days', `${summary.presentDays} / ${summary.working}`],
        ['Attendance %', `${(summary.pct * 100).toFixed(1)}%`],
        ['Late Count', summary.late.toString()],
        ['Leave Days', summary.leaveDays.toString()],
        ['Avg Hours / Day', summary.avgHours > 0 ? `${summary.avgHours.toFixed(1)}h` : '—'],
      ],
      styles: { fontSize: 9, cellPadding: 4 },
      headStyles: { fillColor: [15, 23, 42], textColor: [255, 255, 255] },
      columnStyles: { 0: { cellWidth: 140 } },
    });

    autoTable(doc, {
      startY: (doc as any).lastAutoTable.finalY + 16,
      head: [['Date', 'Status', 'Punch In', 'Punch Out', 'Hours', 'Note']],
      body: heatmap.map(d => [
        d.date,
        d.status,
        d.punchIn || '',
        d.punchOut || '',
        d.hours ? d.hours.toFixed(1) : '',
        d.holidayName || d.leaveType || '',
      ]),
      styles: { fontSize: 8, cellPadding: 3 },
      headStyles: { fillColor: [15, 23, 42], textColor: [255, 255, 255] },
      alternateRowStyles: { fillColor: [248, 250, 252] },
    });

    const safeName = employee.full_name.replace(/[^a-z0-9]+/gi, '-').toLowerCase();
    doc.save(`employee-${safeName}-${rangeStamp(range)}-${dateStamp()}.pdf`);
    toast.success('PDF exported');
  } catch (e: any) {
    console.error(e);
    toast.error('PDF export failed');
  }
}
