// Custom entry: headless tasks (notification actions, shift location) must be defined at JS startup, before expo-router mounts anything.
import './src/features/push/backgroundTask';
import './src/features/tracking/task';
import 'expo-router/entry';
