import type { ChangeEvent } from 'react';
import { useEffect, useMemo, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import {
  Box,
  Button,
  Paper,
  Stack,
  Tab,
  Tabs,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';

import type { ApiError } from '../api/client';
import type { Employee } from '../api/hr/employees';
import { deleteEmployee, getEmployee, updateEmployee } from '../api/hr/employees';
import type { EmployeeDocument } from '../api/hr/documents';
import {
  createEmployeeDocument,
  deleteEmployeeDocument,
  listEmployeeDocuments,
} from '../api/hr/documents';
import type { EmployeeAsset } from '../api/hr/assets';
import {
  assignEmployeeAsset,
  deleteEmployeeAsset,
  listEmployeeAssets,
  updateEmployeeAsset,
} from '../api/hr/assets';

type TabKey = 'profile' | 'documents' | 'assets';

export function HrEmployeeDetailPage() {
  const { employeeId } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const employeeIdNum = useMemo(() => {
    const n = Number(employeeId);
    return Number.isFinite(n) ? n : NaN;
  }, [employeeId]);

  const [tab, setTab] = useState<TabKey>('profile');

  const employeeQuery = useQuery({
    queryKey: ['hr', 'employees', employeeIdNum],
    queryFn: () => getEmployee(employeeIdNum),
    enabled: Number.isFinite(employeeIdNum),
  });

  const docsQuery = useQuery({
    queryKey: ['hr', 'employees', employeeIdNum, 'documents'],
    queryFn: () => listEmployeeDocuments(employeeIdNum),
    enabled: Number.isFinite(employeeIdNum) && tab === 'documents',
  });

  const assetsQuery = useQuery({
    queryKey: ['hr', 'employees', employeeIdNum, 'assets'],
    queryFn: () => listEmployeeAssets(employeeIdNum),
    enabled: Number.isFinite(employeeIdNum) && tab === 'assets',
  });

  const employee = employeeQuery.data;

  // Profile form state
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [employmentType, setEmploymentType] = useState('');
  const [employmentStatus, setEmploymentStatus] = useState('');
  const [joiningDate, setJoiningDate] = useState('');
  const [exitDate, setExitDate] = useState('');

  const hydrateProfile = (e: Employee) => {
    setFirstName(e.first_name ?? '');
    setLastName(e.last_name ?? '');
    setEmail(e.email ?? '');
    setPhone(e.phone ?? '');
    setEmploymentType(e.employment_type ?? '');
    setEmploymentStatus(e.employment_status ?? '');
    setJoiningDate(e.joining_date ?? '');
    setExitDate(e.exit_date ?? '');
  };

  // Hydrate once when loaded
  useEffect(() => {
    if (employee) hydrateProfile(employee);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [employee?.id]);

  const updateMut = useMutation<Employee, ApiError, void>({
    mutationFn: () =>
      updateEmployee(employeeIdNum, {
        first_name: firstName || undefined,
        last_name: lastName || null,
        email: email || null,
        phone: phone || null,
        employment_type: employmentType || undefined,
        employment_status: employmentStatus || undefined,
        joining_date: joiningDate || undefined,
        exit_date: exitDate || null,
      }),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['hr', 'employees', employeeIdNum] });
      await qc.invalidateQueries({ queryKey: ['hr', 'employees'] });
    },
  });

  const deleteMut = useMutation<{ status: string }, ApiError, void>({
    mutationFn: () => deleteEmployee(employeeIdNum),
    onSuccess: async () => {
      await qc.invalidateQueries({ queryKey: ['hr', 'employees'] });
      navigate('/hr/employees');
    },
  });

  // Documents form state
  const [docType, setDocType] = useState('');
  const [docTitle, setDocTitle] = useState('');
  const [docFileRef, setDocFileRef] = useState('');

  const createDocMut = useMutation<EmployeeDocument, ApiError, void>({
    mutationFn: () =>
      createEmployeeDocument(employeeIdNum, {
        document_type: docType,
        title: docTitle || null,
        file_ref: docFileRef,
      }),
    onSuccess: async () => {
      setDocType('');
      setDocTitle('');
      setDocFileRef('');
      await qc.invalidateQueries({
        queryKey: ['hr', 'employees', employeeIdNum, 'documents'],
      });
    },
  });

  const deleteDocMut = useMutation<{ status: string }, ApiError, { documentId: number }>({
    mutationFn: ({ documentId }: { documentId: number }) =>
      deleteEmployeeDocument(employeeIdNum, documentId),
    onSuccess: async () => {
      await qc.invalidateQueries({
        queryKey: ['hr', 'employees', employeeIdNum, 'documents'],
      });
    },
  });

  // Assets form state
  const [assetCategory, setAssetCategory] = useState('ppe');
  const [assetName, setAssetName] = useState('');
  const [assetTag, setAssetTag] = useState('');
  const [assetIssuedOn, setAssetIssuedOn] = useState('');

  const assignAssetMut = useMutation<EmployeeAsset, ApiError, void>({
    mutationFn: () =>
      assignEmployeeAsset(employeeIdNum, {
        asset_category: assetCategory,
        asset_name: assetName,
        asset_tag: assetTag || null,
        issued_on: assetIssuedOn,
      }),
    onSuccess: async () => {
      setAssetName('');
      setAssetTag('');
      setAssetIssuedOn('');
      await qc.invalidateQueries({
        queryKey: ['hr', 'employees', employeeIdNum, 'assets'],
      });
    },
  });

  const markReturnedTodayMut = useMutation<EmployeeAsset, ApiError, { assetId: number }>({
    mutationFn: ({ assetId }: { assetId: number }) => {
      const today = new Date().toISOString().slice(0, 10);
      return updateEmployeeAsset(employeeIdNum, assetId, { returned_on: today });
    },
    onSuccess: async () => {
      await qc.invalidateQueries({
        queryKey: ['hr', 'employees', employeeIdNum, 'assets'],
      });
    },
  });

  const deleteAssetMut = useMutation<{ status: string }, ApiError, { assetId: number }>({
    mutationFn: ({ assetId }: { assetId: number }) => deleteEmployeeAsset(employeeIdNum, assetId),
    onSuccess: async () => {
      await qc.invalidateQueries({
        queryKey: ['hr', 'employees', employeeIdNum, 'assets'],
      });
    },
  });

  const errorText = updateMut.error?.message;

  if (!Number.isFinite(employeeIdNum)) {
    return <Typography>Invalid employee id.</Typography>;
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2} alignItems="center">
        <Button variant="outlined" onClick={() => navigate('/hr/employees')}>
          Back
        </Button>
        <Typography variant="h5">HR • Employee</Typography>
        <Box sx={{ flex: 1 }} />
        <Button
          variant="outlined"
          color="error"
          onClick={() => deleteMut.mutate()}
          disabled={deleteMut.isPending}
        >
          Delete
        </Button>
      </Stack>

      <Paper sx={{ p: 2 }}>
        <Tabs value={tab} onChange={(_event: unknown, v: TabKey) => setTab(v)}>
          <Tab value="profile" label="Profile" />
          <Tab value="documents" label="Documents" />
          <Tab value="assets" label="Assets" />
        </Tabs>
      </Paper>

      {tab === 'profile' ? (
        <Paper sx={{ p: 2 }}>
          <Stack spacing={2}>
            <Typography variant="subtitle1">
              {employee ? `${employee.first_name} ${employee.last_name ?? ''}` : 'Loading…'}
            </Typography>

            <Stack spacing={2} direction={{ xs: 'column', md: 'row' }}>
              <TextField
                label="First Name"
                value={firstName}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setFirstName(e.target.value)}
                size="small"
                sx={{ width: 240 }}
              />
              <TextField
                label="Last Name"
                value={lastName}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setLastName(e.target.value)}
                size="small"
                sx={{ width: 240 }}
              />
              <TextField
                label="Email"
                value={email}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
                size="small"
                sx={{ width: 280 }}
              />
              <TextField
                label="Phone"
                value={phone}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setPhone(e.target.value)}
                size="small"
                sx={{ width: 200 }}
              />
            </Stack>

            <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
              <TextField
                label="Employment Type"
                value={employmentType}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setEmploymentType(e.target.value)}
                size="small"
                sx={{ width: 200 }}
              />
              <TextField
                label="Status"
                value={employmentStatus}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setEmploymentStatus(e.target.value)}
                size="small"
                sx={{ width: 180 }}
              />
              <TextField
                label="Joining Date"
                value={joiningDate}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setJoiningDate(e.target.value)}
                type="date"
                size="small"
                InputLabelProps={{ shrink: true }}
                sx={{ width: 180 }}
              />
              <TextField
                label="Exit Date"
                value={exitDate}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setExitDate(e.target.value)}
                type="date"
                size="small"
                InputLabelProps={{ shrink: true }}
                sx={{ width: 180 }}
              />
              <Button
                variant="contained"
                onClick={() => updateMut.mutate()}
                disabled={updateMut.isPending}
              >
                Save
              </Button>
            </Stack>

            {errorText ? (
              <Typography variant="body2" color="error">
                {errorText}
              </Typography>
            ) : null}
          </Stack>
        </Paper>
      ) : null}

      {tab === 'documents' ? (
        <Stack spacing={2}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Add Document
            </Typography>
            <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
              <TextField
                label="Type"
                value={docType}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setDocType(e.target.value)}
                size="small"
                sx={{ width: 200 }}
              />
              <TextField
                label="Title"
                value={docTitle}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setDocTitle(e.target.value)}
                size="small"
                sx={{ width: 280 }}
              />
              <TextField
                label="File Ref"
                value={docFileRef}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setDocFileRef(e.target.value)}
                size="small"
                sx={{ flex: 1, minWidth: 260 }}
              />
              <Button
                variant="contained"
                disabled={!docType || !docFileRef || createDocMut.isPending}
                onClick={() => createDocMut.mutate()}
              >
                Add
              </Button>
            </Stack>
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Documents
            </Typography>
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Type</TableCell>
                    <TableCell>Title</TableCell>
                    <TableCell>File Ref</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(docsQuery.data ?? []).map((d: EmployeeDocument) => (
                    <TableRow key={d.id} hover>
                      <TableCell>{d.id}</TableCell>
                      <TableCell>{d.document_type}</TableCell>
                      <TableCell>{d.title ?? '—'}</TableCell>
                      <TableCell>{d.file_ref}</TableCell>
                      <TableCell align="right">
                        <Button
                          color="error"
                          size="small"
                          onClick={() => deleteDocMut.mutate({ documentId: d.id })}
                          disabled={deleteDocMut.isPending}
                        >
                          Delete
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {docsQuery.isLoading ? (
                    <TableRow>
                      <TableCell colSpan={5}>Loading…</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </Box>
          </Paper>
        </Stack>
      ) : null}

      {tab === 'assets' ? (
        <Stack spacing={2}>
          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Assign Asset
            </Typography>
            <Stack spacing={2} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'end' }}>
              <TextField
                label="Category"
                value={assetCategory}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setAssetCategory(e.target.value)}
                size="small"
                sx={{ width: 200 }}
              />
              <TextField
                label="Name"
                value={assetName}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setAssetName(e.target.value)}
                size="small"
                sx={{ width: 260 }}
              />
              <TextField
                label="Tag"
                value={assetTag}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setAssetTag(e.target.value)}
                size="small"
                sx={{ width: 220 }}
              />
              <TextField
                label="Issued On"
                value={assetIssuedOn}
                onChange={(e: ChangeEvent<HTMLInputElement>) => setAssetIssuedOn(e.target.value)}
                type="date"
                size="small"
                InputLabelProps={{ shrink: true }}
                sx={{ width: 180 }}
              />
              <Button
                variant="contained"
                disabled={
                  !assetCategory || !assetName || !assetIssuedOn || assignAssetMut.isPending
                }
                onClick={() => assignAssetMut.mutate()}
              >
                Assign
              </Button>
            </Stack>
          </Paper>

          <Paper sx={{ p: 2 }}>
            <Typography variant="h6" sx={{ mb: 1 }}>
              Assets
            </Typography>
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>ID</TableCell>
                    <TableCell>Category</TableCell>
                    <TableCell>Name</TableCell>
                    <TableCell>Tag</TableCell>
                    <TableCell>Issued</TableCell>
                    <TableCell>Returned</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {(assetsQuery.data ?? []).map((a: EmployeeAsset) => (
                    <TableRow key={a.id} hover>
                      <TableCell>{a.id}</TableCell>
                      <TableCell>{a.asset_category}</TableCell>
                      <TableCell>{a.asset_name}</TableCell>
                      <TableCell>{a.asset_tag ?? '—'}</TableCell>
                      <TableCell>{a.issued_on}</TableCell>
                      <TableCell>{a.returned_on ?? '—'}</TableCell>
                      <TableCell align="right">
                        {a.returned_on ? null : (
                          <Button
                            size="small"
                            onClick={() => markReturnedTodayMut.mutate({ assetId: a.id })}
                            disabled={markReturnedTodayMut.isPending}
                          >
                            Mark Returned
                          </Button>
                        )}
                        <Button
                          color="error"
                          size="small"
                          onClick={() => deleteAssetMut.mutate({ assetId: a.id })}
                          disabled={deleteAssetMut.isPending}
                        >
                          Delete
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                  {assetsQuery.isLoading ? (
                    <TableRow>
                      <TableCell colSpan={7}>Loading…</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </Box>
          </Paper>
        </Stack>
      ) : null}
    </Stack>
  );
}
