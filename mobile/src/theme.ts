import type { TextStyle, ViewStyle } from "react-native";

export const theme = {
  colors: {
    canvas: "#FAF8FF",
    surfaceLow: "#F2F3FF",
    surface: "#EAEDFF",
    surfaceHigh: "#E2E7FF",
    card: "#FFFFFF",
    ink: "#131B2E",
    muted: "#444651",
    navy: "#00236F",
    navySecondary: "#1E3A8A",
    navySoft: "#DCE1FF",
    navySurface: "#EAEDFF",
    focus: "#4059AA",
    outline: "#C5C5D3",
    border: "#E2E8F0",
    teal: "#006A61",
    tealStrong: "#0D9488",
    tealSoft: "#89F5E7",
    tealSurface: "#86F2E4",
    danger: "#BA1A1A",
    dangerSoft: "#FFDAD6",
    disabled: "#E2E7FF",
  },
  radius: {
    small: 8,
    medium: 12,
    large: 16,
    xlarge: 24,
    pill: 999,
  },
  size: {
    touch: 48,
    button: 52,
    header: 80,
    icon: 48,
  },
  space: {
    xs: 4,
    sm: 8,
    md: 12,
    lg: 16,
    xl: 24,
    xxl: 32,
  },
} as const;

export const typeStyles = {
  display: {
    color: theme.colors.navy,
    fontSize: 28,
    fontWeight: "700",
    lineHeight: 36,
  } satisfies TextStyle,
  title: {
    color: theme.colors.navy,
    fontSize: 28,
    fontWeight: "700",
    lineHeight: 36,
  } satisfies TextStyle,
  headline: {
    color: theme.colors.navy,
    fontSize: 24,
    fontWeight: "700",
    lineHeight: 32,
  } satisfies TextStyle,
  heading: {
    color: theme.colors.navy,
    fontSize: 20,
    fontWeight: "600",
    lineHeight: 28,
  } satisfies TextStyle,
  subheading: {
    color: theme.colors.ink,
    fontSize: 18,
    fontWeight: "600",
    lineHeight: 26,
  } satisfies TextStyle,
  body: {
    color: theme.colors.ink,
    fontSize: 17,
    fontWeight: "400",
    lineHeight: 26,
  } satisfies TextStyle,
  bodyMedium: {
    color: theme.colors.ink,
    fontSize: 15,
    fontWeight: "400",
    lineHeight: 24,
  } satisfies TextStyle,
  detail: {
    color: theme.colors.muted,
    fontSize: 14,
    fontWeight: "400",
    lineHeight: 20,
  } satisfies TextStyle,
  caption: {
    color: theme.colors.muted,
    fontSize: 12,
    fontWeight: "600",
    letterSpacing: 0.24,
    lineHeight: 16,
  } satisfies TextStyle,
  label: {
    fontSize: 16,
    fontWeight: "600",
    lineHeight: 24,
  } satisfies TextStyle,
} as const;

export const subtleShadowStyle = {
  elevation: 2,
  shadowColor: theme.colors.ink,
  shadowOffset: { height: 2, width: 0 },
  shadowOpacity: 0.06,
  shadowRadius: 6,
} satisfies ViewStyle;

export const cardStyle = {
  backgroundColor: theme.colors.card,
  borderColor: theme.colors.border,
  borderRadius: theme.radius.large,
  borderWidth: 1,
  padding: 20,
} satisfies ViewStyle;

export const pressFeedbackStyle = {
  transform: [{ scale: 0.98 }],
} satisfies ViewStyle;
