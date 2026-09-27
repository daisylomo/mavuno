import '@/global.css';
import { Platform } from 'react-native';

export const Colors = {
  // Primary brand color for all public users (Farmers & Customers)
  brandGreen: '#2D6A4F',
  
  // Internal system color
  adminSlate: '#264653',
  
  // Shared universal colors
  background: '#F8F9FA',
  surface: '#FFFFFF',
  text: '#212529',
  textMuted: '#6C757D',

  // Light / dark themes for expo template compatibility
  light: {
    text: '#212529',
    background: '#F8F9FA',
    backgroundElement: '#E9ECEF',
    backgroundSelected: '#DEE2E6',
    textSecondary: '#6C757D',
    tint: '#2D6A4F',
  },
  dark: {
    text: '#FFFFFF',
    background: '#121212',
    backgroundElement: '#1E1E1E',
    backgroundSelected: '#2C2C2C',
    textSecondary: '#A0A0A0',
    tint: '#52B788',
  },
} as const;

export type ThemeColor = keyof typeof Colors.light & keyof typeof Colors.dark;

export const Fonts = Platform.select({
  ios: {
    sans: 'system-ui',
    serif: 'ui-serif',
    rounded: 'ui-rounded',
    mono: 'ui-monospace',
  },
  default: {
    sans: 'normal',
    serif: 'serif',
    rounded: 'normal',
    mono: 'monospace',
  },
  web: {
    sans: 'var(--font-display)',
    serif: 'var(--font-serif)',
    rounded: 'var(--font-rounded)',
    mono: 'var(--font-mono)',
  },
});

export const Spacing = {
  half: 2,
  one: 4,
  two: 8,
  three: 16,
  four: 24,
  five: 32,
  six: 40,
  seven: 48,
  eight: 64,
} as const;

export const MaxContentWidth = 800;
export const BottomTabInset = 60;