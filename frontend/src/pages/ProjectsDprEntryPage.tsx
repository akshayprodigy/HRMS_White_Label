import type { ChangeEvent } from 'react';
import { useEffect, useMemo, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Chip,
  Divider,
  MenuItem,
  Paper,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';

import type { Project } from '../api/core/projects';
import { listProjects } from '../api/core/projects';
import type { DprActivityLineCreate, DprCreate, DprDrillingLineCreate } from '../api/projects/dprs';
import {
  deleteDprQueueItem,
  enqueueDpr,
  getDprQueueCounts,
  listDprQueue,
  syncDprQueue,
  type DprQueueItem,
} from '../offline/dprQueue';

type DrillingLineDraft = {
  location: string;
  meters_drilled: string;
  recovered_meters: string;
};

type ActivityLineDraft = {
  activity: string;
  hours: string;
  remarks: string;
};

function statusChip(item: DprQueueItem) {
  const common = { size: 'small' as const, variant: 'outlined' as const };
  if (item.status === 'pending') return <Chip {...common} label="Pending" color="warning" />;
  if (item.status === 'syncing') return <Chip {...common} label="Syncing" color="info" />;
  if (item.status === 'synced') return <Chip {...common} label="Synced" color="success" />;
  return <Chip {...common} label="Failed" color="error" />;
}

export function ProjectsDprEntryPage() {
  const projectsQuery = useQuery({ queryKey: ['core', 'projects'], queryFn: listProjects });

  const [online, setOnline] = useState<boolean>(navigator.onLine);
  const [queueItems, setQueueItems] = useState<DprQueueItem[]>([]);
  const [counts, setCounts] = useState({ pending: 0, syncing: 0, failed: 0, synced: 0 });
  const [syncing, setSyncing] = useState(false);

  const [projectId, setProjectId] = useState<number | ''>('');
  const [dprDate, setDprDate] = useState<string>(() => new Date().toISOString().slice(0, 10));
  const [shift, setShift] = useState('');
  const [remarks, setRemarks] = useState('');

  const [drillingLines, setDrillingLines] = useState<DrillingLineDraft[]>([
    { location: '', meters_drilled: '', recovered_meters: '' },
  ]);

  const [activityLines, setActivityLines] = useState<ActivityLineDraft[]>([]);

  const [localError, setLocalError] = useState<string | null>(null);

  const canSubmit = useMemo(() => {
    if (!projectId) return false;
    if (!dprDate) return false;

    const validDrill = drillingLines.some((l) => Number.isFinite(parseFloat(l.meters_drilled)));
    return validDrill;
  }, [projectId, dprDate, drillingLines]);

  const reloadQueue = async () => {
    const [items, c] = await Promise.all([listDprQueue(), getDprQueueCounts()]);
    setQueueItems(items);
    setCounts(c);
  };

  const doSync = async () => {
    setSyncing(true);
    setLocalError(null);
    try {
      await syncDprQueue({ includeFailed: true });
    } catch {
      setLocalError('Sync failed. Please try again.');
    } finally {
      setSyncing(false);
      await reloadQueue();
    }
  };

  useEffect(() => {
    let cancelled = false;

    (async () => {
      if (cancelled) return;
      await reloadQueue();
      if (navigator.onLine) {
        await doSync();
      }
    })();

    const onOnline = async () => {
      setOnline(true);
      await doSync();
    };
    const onOffline = () => setOnline(false);

    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);

    return () => {
      cancelled = true;
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onAddDrillingLine = () => {
    setDrillingLines((prev) => [
      ...prev,
      { location: '', meters_drilled: '', recovered_meters: '' },
    ]);
  };

  const onRemoveDrillingLine = (idx: number) => {
    setDrillingLines((prev) => prev.filter((_, i) => i !== idx));
  };

  const onAddActivityLine = () => {
    setActivityLines((prev) => [...prev, { activity: '', hours: '', remarks: '' }]);
  };

  const onRemoveActivityLine = (idx: number) => {
    setActivityLines((prev) => prev.filter((_, i) => i !== idx));
  };

  const onSubmit = async () => {
    setLocalError(null);
    if (!projectId) return;

    const drillingPayload: DprDrillingLineCreate[] = drillingLines
      .map((l, idx) => {
        const meters = parseFloat(l.meters_drilled);
        const recovered = l.recovered_meters.trim() ? parseFloat(l.recovered_meters) : null;
        return {
          line_no: idx + 1,
          location: l.location.trim() ? l.location.trim() : null,
          meters_drilled: meters,
          recovered_meters: recovered,
        } satisfies DprDrillingLineCreate;
      })
      .filter((l) => Number.isFinite(l.meters_drilled) && l.meters_drilled > 0);

    if (drillingPayload.length === 0) {
      setLocalError('Add at least one drilling line with meters drilled > 0.');
      return;
    }

    const activityPayload: DprActivityLineCreate[] = activityLines
      .map((l, idx) => {
        const hours = l.hours.trim() ? parseFloat(l.hours) : null;
        return {
          line_no: idx + 1,
          activity: l.activity.trim(),
          hours,
          remarks: l.remarks.trim() ? l.remarks.trim() : null,
        } satisfies DprActivityLineCreate;
      })
      .filter((l) => l.activity.length > 0);

    const payload: DprCreate = {
      project_id: projectId,
      dpr_date: dprDate,
      shift: shift.trim() ? shift.trim() : null,
      remarks: remarks.trim() ? remarks.trim() : null,
      drilling_lines: drillingPayload,
      activity_lines: activityPayload,
      consumption_lines: [],
    };

    await enqueueDpr(payload);
    await reloadQueue();

    if (navigator.onLine) {
      await doSync();
    }

    setRemarks('');
  };

  const projects = projectsQuery.data ?? [];

  return (
    <Stack spacing={2}>
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={1} alignItems={{ md: 'center' }}>
        <Typography variant="h5" sx={{ flexGrow: 1 }}>
          Projects • DPR • Entry (Offline)
        </Typography>
        <Chip
          size="small"
          label={online ? 'Online' : 'Offline'}
          color={online ? 'success' : 'default'}
          variant="outlined"
        />
      </Stack>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={1} direction={{ xs: 'column', md: 'row' }} alignItems={{ md: 'center' }}>
          <Typography variant="body2" sx={{ flexGrow: 1 }}>
            Queue: {counts.pending} pending • {counts.syncing} syncing • {counts.failed} failed •{' '}
            {counts.synced} synced
          </Typography>
          <Button variant="outlined" onClick={reloadQueue} disabled={syncing}>
            Refresh
          </Button>
          <Button variant="contained" onClick={doSync} disabled={syncing || !online}>
            Sync now
          </Button>
        </Stack>
        {localError ? (
          <Alert severity="error" sx={{ mt: 2 }}>
            {localError}
          </Alert>
        ) : null}
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Stack spacing={2}>
          <Typography variant="h6">New DPR</Typography>

          <Stack spacing={2} direction={{ xs: 'column', md: 'row' }}>
            <TextField
              select
              label="Project"
              value={projectId}
              onChange={(e: ChangeEvent<HTMLInputElement>) =>
                setProjectId(e.target.value ? Number(e.target.value) : '')
              }
              size="small"
              sx={{ minWidth: 280 }}
            >
              {projects.map((p: Project) => (
                <MenuItem key={p.id} value={p.id}>
                  {p.code} — {p.name}
                </MenuItem>
              ))}
            </TextField>

            <TextField
              label="Date"
              type="date"
              value={dprDate}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setDprDate(e.target.value)}
              size="small"
              sx={{ width: 200 }}
              InputLabelProps={{ shrink: true }}
            />

            <TextField
              label="Shift (optional)"
              value={shift}
              onChange={(e: ChangeEvent<HTMLInputElement>) => setShift(e.target.value)}
              size="small"
              sx={{ width: 220 }}
            />
          </Stack>

          <TextField
            label="Remarks (optional)"
            value={remarks}
            onChange={(e: ChangeEvent<HTMLInputElement>) => setRemarks(e.target.value)}
            size="small"
            multiline
            minRows={2}
          />

          <Divider />

          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
              Drilling lines
            </Typography>
            <Button variant="outlined" onClick={onAddDrillingLine}>
              Add line
            </Button>
          </Stack>

          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell>
                  <TableCell>Location</TableCell>
                  <TableCell>Meters drilled</TableCell>
                  <TableCell>Recovered (optional)</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {drillingLines.map((l, idx) => (
                  <TableRow key={idx} hover>
                    <TableCell>{idx + 1}</TableCell>
                    <TableCell>
                      <TextField
                        value={l.location}
                        onChange={(e: ChangeEvent<HTMLInputElement>) =>
                          setDrillingLines((prev) =>
                            prev.map((row, i) =>
                              i === idx ? { ...row, location: e.target.value } : row,
                            ),
                          )
                        }
                        size="small"
                        placeholder="BH-1"
                        fullWidth
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        value={l.meters_drilled}
                        onChange={(e: ChangeEvent<HTMLInputElement>) =>
                          setDrillingLines((prev) =>
                            prev.map((row, i) =>
                              i === idx ? { ...row, meters_drilled: e.target.value } : row,
                            ),
                          )
                        }
                        size="small"
                        placeholder="0"
                        fullWidth
                      />
                    </TableCell>
                    <TableCell>
                      <TextField
                        value={l.recovered_meters}
                        onChange={(e: ChangeEvent<HTMLInputElement>) =>
                          setDrillingLines((prev) =>
                            prev.map((row, i) =>
                              i === idx ? { ...row, recovered_meters: e.target.value } : row,
                            ),
                          )
                        }
                        size="small"
                        placeholder="0"
                        fullWidth
                      />
                    </TableCell>
                    <TableCell sx={{ whiteSpace: 'nowrap' }}>
                      <Button
                        color="error"
                        onClick={() => onRemoveDrillingLine(idx)}
                        disabled={drillingLines.length <= 1}
                      >
                        Remove
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>

          <Divider />

          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="subtitle1" sx={{ flexGrow: 1 }}>
              Activity lines (optional)
            </Typography>
            <Button variant="outlined" onClick={onAddActivityLine}>
              Add line
            </Button>
          </Stack>

          {activityLines.length ? (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>#</TableCell>
                    <TableCell>Activity</TableCell>
                    <TableCell>Hours</TableCell>
                    <TableCell>Remarks</TableCell>
                    <TableCell />
                  </TableRow>
                </TableHead>
                <TableBody>
                  {activityLines.map((l, idx) => (
                    <TableRow key={idx} hover>
                      <TableCell>{idx + 1}</TableCell>
                      <TableCell>
                        <TextField
                          value={l.activity}
                          onChange={(e: ChangeEvent<HTMLInputElement>) =>
                            setActivityLines((prev) =>
                              prev.map((row, i) =>
                                i === idx ? { ...row, activity: e.target.value } : row,
                              ),
                            )
                          }
                          size="small"
                          fullWidth
                        />
                      </TableCell>
                      <TableCell>
                        <TextField
                          value={l.hours}
                          onChange={(e: ChangeEvent<HTMLInputElement>) =>
                            setActivityLines((prev) =>
                              prev.map((row, i) =>
                                i === idx ? { ...row, hours: e.target.value } : row,
                              ),
                            )
                          }
                          size="small"
                          fullWidth
                        />
                      </TableCell>
                      <TableCell>
                        <TextField
                          value={l.remarks}
                          onChange={(e: ChangeEvent<HTMLInputElement>) =>
                            setActivityLines((prev) =>
                              prev.map((row, i) =>
                                i === idx ? { ...row, remarks: e.target.value } : row,
                              ),
                            )
                          }
                          size="small"
                          fullWidth
                        />
                      </TableCell>
                      <TableCell sx={{ whiteSpace: 'nowrap' }}>
                        <Button color="error" onClick={() => onRemoveActivityLine(idx)}>
                          Remove
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          ) : (
            <Typography variant="body2" sx={{ opacity: 0.8 }}>
              No activity lines.
            </Typography>
          )}

          <Button variant="contained" disabled={!canSubmit} onClick={onSubmit}>
            Save (queues if offline)
          </Button>
        </Stack>
      </Paper>

      <Paper sx={{ p: 2 }}>
        <Typography variant="h6" sx={{ mb: 1 }}>
          Offline queue
        </Typography>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Status</TableCell>
                <TableCell>Created</TableCell>
                <TableCell>Project</TableCell>
                <TableCell>Date</TableCell>
                <TableCell>Shift</TableCell>
                <TableCell>Attempts</TableCell>
                <TableCell>Server DPR</TableCell>
                <TableCell>Error</TableCell>
                <TableCell />
              </TableRow>
            </TableHead>
            <TableBody>
              {queueItems.map((item: DprQueueItem) => (
                <TableRow key={item.id} hover>
                  <TableCell>{statusChip(item)}</TableCell>
                  <TableCell>{new Date(item.createdAt).toLocaleString()}</TableCell>
                  <TableCell>{item.payload.project_id}</TableCell>
                  <TableCell>{item.payload.dpr_date}</TableCell>
                  <TableCell>{item.payload.shift ?? '-'}</TableCell>
                  <TableCell>{item.attemptCount}</TableCell>
                  <TableCell>{item.serverDprId ?? '-'}</TableCell>
                  <TableCell sx={{ maxWidth: 420, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {item.errorMessage ?? '-'}
                  </TableCell>
                  <TableCell sx={{ whiteSpace: 'nowrap' }}>
                    <Button
                      color="error"
                      onClick={async () => {
                        await deleteDprQueueItem(item.id);
                        await reloadQueue();
                      }}
                      disabled={item.status === 'syncing'}
                    >
                      Delete
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {!queueItems.length ? (
                <TableRow>
                  <TableCell colSpan={9}>No queued DPRs.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </Box>
      </Paper>
    </Stack>
  );
}
