import type { PropsWithChildren, ReactElement } from "react";
import {
  View,
  type ViewProps,
  type ViewStyle,
} from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";
import { cardStyle, subtleShadowStyle, theme } from "../theme";

type SurfaceTone = "card" | "danger" | "navy" | "recessed" | "teal";

interface SurfaceCardProps extends PropsWithChildren<ViewProps> {
  elevated?: boolean;
  tone?: SurfaceTone;
}

interface DecorativeMarkProps {
  pattern?: "bridge" | "center" | "pair" | "shield" | "tiles" | "wave";
  size?: number;
  tone?: "danger" | "navy" | "teal";
}

const toneColors: Record<SurfaceTone, string> = {
  card: theme.colors.card,
  danger: theme.colors.dangerSoft,
  navy: theme.colors.navySurface,
  recessed: theme.colors.surfaceLow,
  teal: theme.colors.tealSurface,
};

export function SafeScreen({ children }: PropsWithChildren): ReactElement {
  return (
    <SafeAreaView
      style={{ flex: 1, backgroundColor: theme.colors.canvas }}
      edges={["top", "bottom"]}
    >
      {children}
    </SafeAreaView>
  );
}

export function SurfaceCard({
  children,
  elevated = false,
  style,
  tone = "card",
  ...props
}: SurfaceCardProps): ReactElement {
  return (
    <View
      {...props}
      style={[
        cardStyle,
        { backgroundColor: toneColors[tone] },
        elevated ? subtleShadowStyle : null,
        style,
      ]}
    >
      {children}
    </View>
  );
}

export function PersistentFooter({ children }: PropsWithChildren): ReactElement {
  return (
    <View
      style={{
        backgroundColor: theme.colors.canvas,
        borderTopColor: theme.colors.border,
        borderTopWidth: 1,
        paddingTop: theme.space.md,
      }}
    >
      {children}
    </View>
  );
}

export function DecorativeMark({
  pattern = "center",
  size = theme.size.icon,
  tone = "navy",
}: DecorativeMarkProps): ReactElement {
  const main =
    tone === "danger"
      ? theme.colors.danger
      : tone === "teal"
        ? theme.colors.teal
        : theme.colors.navy;
  const soft =
    tone === "danger"
      ? theme.colors.dangerSoft
      : tone === "teal"
        ? theme.colors.tealSoft
        : theme.colors.navySoft;
  const unit = size / 12;

  let content: ReactElement;
  if (pattern === "wave") {
    const bars = [4, 7, 10, 6, 9, 5, 3];
    content = (
      <View style={{ flexDirection: "row", alignItems: "center", gap: unit }}>
        {bars.map((height, index) => (
          <View
            key={`${height}-${index}`}
            style={{
              backgroundColor: index % 2 === 0 ? main : soft,
              borderRadius: unit,
              height: height * unit,
              width: Math.max(2, unit * 1.2),
            }}
          />
        ))}
      </View>
    );
  } else if (pattern === "pair") {
    content = (
      <View style={{ flexDirection: "row", alignItems: "flex-end", gap: unit }}>
        <View style={{ width: unit * 4, height: unit * 7, borderRadius: unit * 2, backgroundColor: soft }} />
        <View style={{ width: unit * 4, height: unit * 10, borderRadius: unit * 2, backgroundColor: main }} />
      </View>
    );
  } else if (pattern === "tiles") {
    content = (
      <View style={{ width: unit * 9, height: unit * 9, flexDirection: "row", flexWrap: "wrap", gap: unit }}>
        {[0, 1, 2, 3].map((tile) => (
          <View
            key={tile}
            style={{ width: unit * 4, height: unit * 4, borderRadius: unit, backgroundColor: tile === 3 ? main : soft }}
          />
        ))}
      </View>
    );
  } else if (pattern === "bridge") {
    content = (
      <View style={{ width: unit * 10, height: unit * 8, justifyContent: "space-between" }}>
        <View style={{ height: unit * 2, borderRadius: unit, backgroundColor: main }} />
        <View style={{ height: unit * 2, width: "72%", alignSelf: "center", borderRadius: unit, backgroundColor: soft }} />
        <View style={{ height: unit * 2, width: "42%", alignSelf: "center", borderRadius: unit, backgroundColor: main }} />
      </View>
    );
  } else if (pattern === "shield") {
    content = (
      <View
        style={{
          width: unit * 8,
          height: unit * 9,
          borderColor: main,
          borderWidth: Math.max(2, unit),
          borderRadius: unit * 3,
          alignItems: "center",
          justifyContent: "center",
          transform: [{ rotate: "45deg" }],
        }}
      >
        <View style={{ width: unit * 2, height: unit * 2, borderRadius: unit, backgroundColor: main }} />
      </View>
    );
  } else {
    content = (
      <View style={{ width: unit * 8, height: unit * 8, borderRadius: unit * 4, backgroundColor: soft, alignItems: "center", justifyContent: "center" }}>
        <View style={{ width: unit * 3, height: unit * 3, borderRadius: unit * 1.5, backgroundColor: main }} />
      </View>
    );
  }

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      style={{ width: size, height: size, alignItems: "center", justifyContent: "center" } as ViewStyle}
    >
      {content}
    </View>
  );
}
