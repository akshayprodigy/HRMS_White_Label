// Custom entry: the headless notification task must be defined at JS startup, before expo-router mounts anything.
import './src/features/push/backgroundTask';
import 'expo-router/entry';
