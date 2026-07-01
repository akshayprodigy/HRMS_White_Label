import React, { useState, useEffect } from 'react';
import {
  FileSignature,
  Download,
  Search,
  Plus,
  FileText,
  User,
  Calendar,
  Building2,
  Briefcase,
  Clock,
  ChevronDown,
} from 'lucide-react';
import { Card, Button, Badge, cn } from './ui-elements';
import { toast } from 'sonner';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogFooter,
} from './ui/dialog';
import { client } from '../api/client';
import { ENDPOINTS } from '../api/endpoints';

interface LetterRecord {
  id: number;
  employee_id: number;
  letter_type: string;
  reference_number: string | null;
  generated_at: string;
  generated_by_id: number;
  file_url: string | null;
  status: string;
}

interface EmployeeOption {
  id: number;
  employee_id: string;
  designation: string;
  department: string;
  date_of_joining: string;
  user: {
    id: number;
    full_name: string;
    email: string;
  };
}

const LETTER_TYPE_META: Record<
  string,
  { label: string; description: string; color: string; icon: React.ReactNode }
> = {
  offer_letter: {
    label: 'Offer Letter',
    description: 'Pre-joining offer of employment',
    color: 'bg-blue-50 text-blue-700 border-blue-200',
    icon: <FileText className="w-5 h-5 text-blue-600" />,
  },
  appointment_letter: {
    label: 'Appointment Letter',
    description: 'Detailed terms & conditions of employment',
    color: 'bg-indigo-50 text-indigo-700 border-indigo-200',
    icon: <Briefcase className="w-5 h-5 text-indigo-600" />,
  },
  confirmation_letter: {
    label: 'Confirmation Letter',
    description: 'Post-probation confirmation of service',
    color: 'bg-green-50 text-green-700 border-green-200',
    icon: <FileSignature className="w-5 h-5 text-green-600" />,
  },
  release_experience_order: {
    label: 'Release & Experience Order',
    description: 'Service certificate with experience details',
    color: 'bg-amber-50 text-amber-700 border-amber-200',
    icon: <Calendar className="w-5 h-5 text-amber-600" />,
  },
  relieving_letter: {
    label: 'Relieving Letter',
    description: 'Formal relieving upon resignation',
    color: 'bg-rose-50 text-rose-700 border-rose-200',
    icon: <User className="w-5 h-5 text-rose-600" />,
  },
};

const LETTER_TYPES = Object.keys(LETTER_TYPE_META);

export const LettersHR = () => {
  const [letters, setLetters] = useState<LetterRecord[]>([]);
  const [employees, setEmployees] = useState<EmployeeOption[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState('');

  // Generate dialog state
  const [showGenerate, setShowGenerate] = useState(false);
  const [selectedType, setSelectedType] = useState('');
  const [selectedEmployeeId, setSelectedEmployeeId] = useState<number | ''>('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [empSearch, setEmpSearch] = useState('');
  const [empDropdown, setEmpDropdown] = useState<EmployeeOption[]>([]);
  const [isSearchingEmp, setIsSearchingEmp] = useState(false);

  // Form fields for letter-specific data
  const [formData, setFormData] = useState<Record<string, string>>({});

  useEffect(() => {
    fetchLetters();
    fetchEmployees();
  }, []);

  // Debounced employee search via API
  useEffect(() => {
    if (empSearch.length < 3) {
      setEmpDropdown([]);
      return;
    }
    const timer = setTimeout(async () => {
      setIsSearchingEmp(true);
      try {
        const res = await client.get<{ items: EmployeeOption[] }>(
          ENDPOINTS.HR.EMPLOYEES + `?search=${encodeURIComponent(empSearch)}&size=15`
        );
        setEmpDropdown(res.data.items || []);
      } catch {
        setEmpDropdown([]);
      } finally {
        setIsSearchingEmp(false);
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [empSearch]);

  const fetchLetters = async () => {
    setIsLoading(true);
    try {
      const res = await client.get<LetterRecord[]>(ENDPOINTS.HR.LETTERS);
      setLetters(res.data);
    } catch {
      toast.error('Failed to load letters');
    } finally {
      setIsLoading(false);
    }
  };

  const fetchEmployees = async () => {
    try {
      const res = await client.get<{ items: EmployeeOption[] }>(
        ENDPOINTS.HR.EMPLOYEES + '?size=500'
      );
      setEmployees(res.data.items || []);
    } catch {
      // silently fail — employees list is for dropdown
    }
  };

  const selectedEmployee = employees.find(
    (e) => e.id === selectedEmployeeId
  ) || empDropdown.find((e) => e.id === selectedEmployeeId);

  const handleGenerate = async () => {
    if (!selectedType || !selectedEmployeeId) {
      toast.error('Select an employee and letter type');
      return;
    }
    setIsGenerating(true);
    try {
      const body: Record<string, any> = {
        employee_id: selectedEmployeeId,
        letter_type: selectedType,
        ...formData,
      };
      // Clean empty strings
      Object.keys(body).forEach((k) => {
        if (body[k] === '') delete body[k];
      });

      const res = await client.post(ENDPOINTS.HR.LETTER_GENERATE, body, {
        responseType: 'blob',
      });

      // Download the PDF
      const blob = new Blob([res.data as any], {
        type: 'application/pdf',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      const disposition =
        res.headers?.['content-disposition'] || '';
      const filenameMatch = disposition.match(/filename="(.+?)"/);
      link.download = filenameMatch
        ? filenameMatch[1]
        : `${selectedType}_${selectedEmployeeId}.pdf`;
      link.click();
      window.URL.revokeObjectURL(url);

      toast.success('Letter generated and downloaded');
      setShowGenerate(false);
      setSelectedType('');
      setSelectedEmployeeId('');
      setFormData({});
      fetchLetters();
    } catch (err: any) {
      toast.error(
        err?.response?.data?.detail || 'Failed to generate letter'
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleDownload = async (letter: LetterRecord) => {
    try {
      const res = await client.get(
        ENDPOINTS.HR.LETTER_DOWNLOAD(letter.id),
        { responseType: 'blob' }
      );
      const blob = new Blob([res.data as any], {
        type: 'application/pdf',
      });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `${(letter.reference_number || 'letter').replace(/\//g, '_')}.pdf`;
      link.click();
      window.URL.revokeObjectURL(url);
    } catch {
      toast.error('Failed to download letter');
    }
  };

  const filteredLetters = letters.filter((l) => {
    if (filterType && l.letter_type !== filterType) return false;
    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const emp = employees.find((e) => e.id === l.employee_id);
      const empName = emp?.user?.full_name?.toLowerCase() || '';
      const ref = (l.reference_number || '').toLowerCase();
      return empName.includes(q) || ref.includes(q);
    }
    return true;
  });

  const filteredEmployees = employees.filter((e) => {
    if (!empSearch) return true;
    const q = empSearch.toLowerCase();
    return (
      e.user?.full_name?.toLowerCase().includes(q) ||
      e.employee_id?.toLowerCase().includes(q) ||
      e.user?.email?.toLowerCase().includes(q)
    );
  });

  const getLetterFields = (type: string) => {
    switch (type) {
      case 'offer_letter':
        return [
          { key: 'phone', label: 'Phone Number' },
          { key: 'email', label: 'Email Address' },
          { key: 'joining_date', label: 'Date of Joining', type: 'date' },
        ];
      case 'appointment_letter':
        return [
          { key: 'ctc', label: 'CTC (Annual)', placeholder: 'e.g., 6,00,000' },
          { key: 'posting_location', label: 'Posting Location', placeholder: 'Kolkata' },
          { key: 'joining_date', label: 'Date of Joining', type: 'date' },
        ];
      case 'confirmation_letter':
        return [
          { key: 'confirmation_date', label: 'Confirmation Date', type: 'date' },
        ];
      case 'release_experience_order':
        return [
          { key: 'last_working_date', label: 'Last Working Date', type: 'date' },
          { key: 'cessation_cause', label: 'Cause of Cessation', placeholder: 'Resignation' },
          { key: 'performance_rating', label: 'Performance Rating', placeholder: 'Satisfactory' },
        ];
      case 'relieving_letter':
        return [
          { key: 'resignation_date', label: 'Resignation Date', type: 'date' },
          { key: 'relieving_date', label: 'Relieving Date', type: 'date' },
        ];
      default:
        return [];
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-semibold text-gray-900">
            Employee Letters
          </h2>
          <p className="text-sm text-gray-500 mt-0.5">
            Generate and manage official employee letters with UEIPL branding
          </p>
        </div>
        <Button
          onClick={() => setShowGenerate(true)}
          className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
        >
          <Plus className="w-4 h-4" />
          Generate Letter
        </Button>
      </div>

      {/* Letter Type Cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {LETTER_TYPES.map((type) => {
          const meta = LETTER_TYPE_META[type];
          const count = letters.filter(
            (l) => l.letter_type === type
          ).length;
          return (
            <button
              key={type}
              onClick={() =>
                setFilterType(filterType === type ? '' : type)
              }
              className={cn(
                'p-3 rounded-lg border text-left transition-all',
                filterType === type
                  ? meta.color + ' ring-2 ring-offset-1'
                  : 'bg-white border-gray-200 hover:border-gray-300'
              )}
            >
              <div className="flex items-center gap-2 mb-1">
                {meta.icon}
                <span className="text-xs font-medium">{meta.label}</span>
              </div>
              <div className="text-lg font-bold">{count}</div>
            </button>
          );
        })}
      </div>

      {/* Search & Filter */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
          <input
            type="text"
            placeholder="Search by employee name or reference..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
          />
        </div>
      </div>

      {/* Letters Table */}
      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-gray-50 border-b">
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  Reference
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  Type
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  Employee
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  Generated
                </th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">
                  Status
                </th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-gray-400">
                    Loading letters...
                  </td>
                </tr>
              ) : filteredLetters.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-12 text-center text-gray-400">
                    <FileSignature className="w-8 h-8 mx-auto mb-2 opacity-40" />
                    {letters.length === 0
                      ? 'No letters generated yet. Click "Generate Letter" to create one.'
                      : 'No letters match your search.'}
                  </td>
                </tr>
              ) : (
                filteredLetters.map((letter) => {
                  const meta =
                    LETTER_TYPE_META[letter.letter_type] ||
                    LETTER_TYPE_META.offer_letter;
                  const emp = employees.find(
                    (e) => e.id === letter.employee_id
                  );
                  return (
                    <tr
                      key={letter.id}
                      className="border-b hover:bg-gray-50 transition-colors"
                    >
                      <td className="px-4 py-3 font-mono text-xs text-gray-600">
                        {letter.reference_number || '-'}
                      </td>
                      <td className="px-4 py-3">
                        <Badge
                          className={cn(
                            'text-xs font-medium',
                            meta.color
                          )}
                        >
                          {meta.label}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="font-medium text-gray-900">
                          {emp?.user?.full_name || `Employee #${letter.employee_id}`}
                        </div>
                        {emp && (
                          <div className="text-xs text-gray-500">
                            {emp.employee_id} &middot; {emp.designation}
                          </div>
                        )}
                      </td>
                      <td className="px-4 py-3 text-gray-500">
                        {new Date(letter.generated_at).toLocaleDateString(
                          'en-IN',
                          {
                            day: '2-digit',
                            month: 'short',
                            year: 'numeric',
                          }
                        )}
                      </td>
                      <td className="px-4 py-3">
                        <Badge className="bg-green-50 text-green-700 border-green-200 text-xs">
                          {letter.status}
                        </Badge>
                      </td>
                      <td className="px-4 py-3 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleDownload(letter)}
                          className="text-indigo-600 hover:text-indigo-800 gap-1"
                        >
                          <Download className="w-3.5 h-3.5" />
                          Download
                        </Button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* Generate Letter Dialog */}
      <Dialog open={showGenerate} onOpenChange={setShowGenerate}>
        <DialogContent className="max-w-lg max-h-[90vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileSignature className="w-5 h-5 text-indigo-600" />
              Generate Employee Letter
            </DialogTitle>
          </DialogHeader>

          <div className="space-y-4 py-2">
            {/* Step 1: Select Letter Type */}
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Letter Type
              </label>
              <div className="grid grid-cols-1 gap-2">
                {LETTER_TYPES.map((type) => {
                  const meta = LETTER_TYPE_META[type];
                  return (
                    <button
                      key={type}
                      onClick={() => {
                        setSelectedType(type);
                        setFormData({});
                      }}
                      className={cn(
                        'flex items-center gap-3 p-3 rounded-lg border text-left transition-all',
                        selectedType === type
                          ? meta.color + ' ring-2 ring-offset-1'
                          : 'bg-white border-gray-200 hover:border-gray-300'
                      )}
                    >
                      {meta.icon}
                      <div>
                        <div className="text-sm font-medium">
                          {meta.label}
                        </div>
                        <div className="text-xs text-gray-500">
                          {meta.description}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Step 2: Select Employee */}
            {selectedType && (
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  Select Employee
                </label>

                {/* Selected employee chip */}
                {selectedEmployeeId && selectedEmployee ? (
                  <div className="flex items-center gap-3 px-3 py-2.5 bg-indigo-50 border border-indigo-200 rounded-lg">
                    <div className="w-8 h-8 rounded-full bg-indigo-200 flex items-center justify-center text-xs font-bold text-indigo-700">
                      {selectedEmployee.user?.full_name?.charAt(0) || '?'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-indigo-900 truncate">
                        {selectedEmployee.user?.full_name}
                      </div>
                      <div className="text-xs text-indigo-600">
                        {selectedEmployee.employee_id} &middot; {selectedEmployee.designation} &middot;{' '}
                        {selectedEmployee.department}
                      </div>
                    </div>
                    <button
                      onClick={() => {
                        setSelectedEmployeeId('');
                        setEmpSearch('');
                      }}
                      className="text-indigo-400 hover:text-indigo-600 p-1"
                    >
                      <span className="text-lg leading-none">&times;</span>
                    </button>
                  </div>
                ) : (
                  /* Typeahead search input */
                  <div className="relative">
                    <div className="relative">
                      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                      <input
                        type="text"
                        placeholder="Type at least 3 characters to search..."
                        value={empSearch}
                        onChange={(e) => setEmpSearch(e.target.value)}
                        className="w-full pl-10 pr-4 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                        autoFocus
                      />
                    </div>

                    {/* Dropdown results — only show after 3+ chars */}
                    {empSearch.length >= 3 && (
                      <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto divide-y">
                        {isSearchingEmp ? (
                          <div className="px-4 py-3 text-sm text-gray-400 text-center">
                            Searching...
                          </div>
                        ) : empDropdown.length === 0 ? (
                          <div className="px-4 py-3 text-sm text-gray-400 text-center">
                            No employees found
                          </div>
                        ) : (
                          empDropdown.map((emp) => (
                            <button
                              key={emp.id}
                              onClick={() => {
                                setSelectedEmployeeId(emp.id);
                                setEmpSearch('');
                              }}
                              className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-indigo-50 transition-colors"
                            >
                              <div className="w-8 h-8 rounded-full bg-gray-200 flex items-center justify-center text-xs font-bold text-gray-600">
                                {emp.user?.full_name?.charAt(0) || '?'}
                              </div>
                              <div className="flex-1 min-w-0">
                                <div className="text-sm font-medium truncate">
                                  {emp.user?.full_name}
                                </div>
                                <div className="text-xs text-gray-500">
                                  {emp.employee_id} &middot; {emp.designation} &middot;{' '}
                                  {emp.department}
                                </div>
                              </div>
                            </button>
                          ))
                        )}
                      </div>
                    )}

                    {empSearch.length > 0 && empSearch.length < 3 && (
                      <p className="text-xs text-gray-400 mt-1">
                        Type {3 - empSearch.length} more character{3 - empSearch.length > 1 ? 's' : ''} to search...
                      </p>
                    )}
                  </div>
                )}
              </div>
            )}

            {/* Step 3: Letter-specific fields */}
            {selectedType && selectedEmployeeId && (
              <div className="space-y-3">
                {selectedEmployee && (
                  <div className="bg-gray-50 rounded-lg p-3 text-sm border border-gray-200">
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1.5">
                      <div>
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Name</span>
                        <div className="text-gray-900 font-medium">{selectedEmployee.user?.full_name}</div>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Email</span>
                        <div className="text-gray-900">{selectedEmployee.user?.email}</div>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Designation</span>
                        <div className="text-gray-900">{selectedEmployee.designation}</div>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Department</span>
                        <div className="text-gray-900">{selectedEmployee.department}</div>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Employee ID</span>
                        <div className="text-gray-900">{selectedEmployee.employee_id}</div>
                      </div>
                      <div>
                        <span className="text-[10px] uppercase tracking-wider text-gray-400 font-semibold">Date of Joining</span>
                        <div className="text-gray-900">{selectedEmployee.date_of_joining}</div>
                      </div>
                    </div>
                  </div>
                )}

                <div className="text-sm font-medium text-gray-700">
                  Additional Details <span className="text-gray-400 font-normal">(pre-filled from employee record, edit if needed)</span>
                </div>
                {getLetterFields(selectedType).map((field) => {
                  // Auto-resolve default value from employee data
                  const empDefaults: Record<string, string> = selectedEmployee ? {
                    email: selectedEmployee.user?.email || '',
                    phone: '',
                    designation: selectedEmployee.designation || '',
                    department: selectedEmployee.department || '',
                    joining_date: selectedEmployee.date_of_joining || '',
                    posting_location: 'Kolkata',
                    ctc: '',
                    confirmation_date: '',
                    last_working_date: '',
                    resignation_date: '',
                    relieving_date: '',
                    cessation_cause: 'Resignation',
                    performance_rating: 'Satisfactory',
                  } : {};
                  const value = formData[field.key] ?? empDefaults[field.key] ?? '';
                  return (
                    <div key={field.key}>
                      <label className="block text-xs font-medium text-gray-600 mb-1">
                        {field.label}
                      </label>
                      <input
                        type={field.type || 'text'}
                        placeholder={
                          (field as any).placeholder || ''
                        }
                        value={value}
                        onChange={(e) =>
                          setFormData((prev) => ({
                            ...prev,
                            [field.key]: e.target.value,
                          }))
                        }
                        className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                      />
                    </div>
                  );
                })}

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Letter Date
                  </label>
                  <input
                    type="date"
                    value={formData.date || new Date().toISOString().split('T')[0]}
                    onChange={(e) =>
                      setFormData((prev) => ({
                        ...prev,
                        date: e.target.value,
                      }))
                    }
                    className="w-full px-3 py-2 border rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                  />
                </div>
              </div>
            )}
          </div>

          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                setShowGenerate(false);
                setSelectedType('');
                setSelectedEmployeeId('');
                setFormData({});
                setEmpSearch('');
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={handleGenerate}
              disabled={
                !selectedType || !selectedEmployeeId || isGenerating
              }
              className="bg-indigo-600 hover:bg-indigo-700 text-white gap-2"
            >
              {isGenerating ? (
                <>
                  <Clock className="w-4 h-4 animate-spin" />
                  Generating...
                </>
              ) : (
                <>
                  <FileSignature className="w-4 h-4" />
                  Generate & Download
                </>
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
};
