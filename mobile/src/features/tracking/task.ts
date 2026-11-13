import * as TaskManager from 'expo-task-manager';
import { handleLocations, LOCATION_TASK } from './tracking';

// Must run at JS startup (imported from index.js), never inside a component: the OS can start the app headless to
// deliver locations and the task must already be defined by then.
TaskManager.defineTask(LOCATION_TASK, async ({ data, error }) => {
  if (error) return;
  try {
    await handleLocations(data);
  } catch (e) {
    console.warn('[tracking] location task failed', e instanceof Error ? e.message : e);
  }
});
