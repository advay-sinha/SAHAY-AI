/** Presentation contracts for the Civic Reassurance mobile redesign. */

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const MOBILE = path.join(__dirname, "..");
const read = (...parts) => fs.readFileSync(path.join(MOBILE, ...parts), "utf8");

test("the shared theme carries the approved civic palette and type scale", () => {
  const source = read("src", "theme.ts");
  for (const token of ["#FAF8FF", "#00236F", "#006A61", "#DCE1FF", "#BA1A1A"]) {
    assert.ok(source.includes(token), `${token} is missing from the mobile theme`);
  }
  assert.match(source, /fontSize:\s*28/);
  assert.match(source, /lineHeight:\s*36/);
  assert.match(source, /borderRadius:\s*theme\.radius\.large/);
});

test("shared presentation surfaces hide decorative marks from screen readers", () => {
  const source = read("src", "components", "Presentation.tsx");
  assert.match(source, /export function SurfaceCard/);
  assert.match(source, /export function DecorativeMark/);
  assert.match(source, /export function SafeScreen/);
  assert.match(source, /edges=\{\["top", "bottom"\]\}/);
  assert.match(source, /accessibilityElementsHidden/);
  assert.match(source, /importantForAccessibility="no-hide-descendants"/);
  assert.match(source, /size = theme\.size\.icon/);
  assert.match(source, /export function PersistentFooter/);
});

test("every redesigned screen consumes the shared presentation system", () => {
  for (const name of [
    "LanguageScreen.tsx",
    "ConsentScreen.tsx",
    "HomeScreen.tsx",
    "TalkScreen.tsx",
    "ChatScreen.tsx",
    "HandoffScreen.tsx",
    "MyRequestsScreen.tsx",
    "ErrorScreen.tsx",
  ]) {
    const source = read("src", "screens", name);
    assert.match(source, /from "\.\.\/theme";/, `${name} does not use the shared theme`);
    assert.match(source, /<SafeScreen>/, `${name} does not render the safe-area shell`);
  }
});

test("chat avoids the Android keyboard without changing its send controller", () => {
  const source = read("src", "screens", "ChatScreen.tsx");
  assert.match(source, /behavior=\{Platform\.OS === "ios" \? "padding" : "height"\}/);
  assert.match(source, /createChatSendController/);
  assert.match(source, /keyboardDismissMode="none"/);
  assert.match(source, /keyboardShouldPersistTaps="handled"/);
  assert.match(source, /maxHeight:\s*96/);
  assert.match(source, /minHeight:\s*theme\.size\.button/);
  assert.match(source, /\bscrollEnabled\b/);
});

test("the persistent human control retains its larger target and localized label", () => {
  const source = read("src", "components", "TalkToPersonButton.tsx");
  assert.match(source, /label = t\("human\.button"\)/);
  assert.match(source, /minHeight:\s*56/);
  assert.match(source, /backgroundColor:\s*disabled \? theme\.colors\.disabled : theme\.colors\.navySecondary/);
  assert.match(source, /accessibilityState=\{\{ busy, disabled \}\}/);
});

test("chat keeps messages and every composer action in one reachable scroll region", () => {
  const source = read("src", "screens", "ChatScreen.tsx");
  const scrollStart = source.indexOf("<ScrollView");
  const scrollEnd = source.indexOf("</ScrollView>");
  const messages = source.indexOf("displayMessages.map");
  const input = source.indexOf("<TextInput");
  const send = source.indexOf('accessibilityLabel={t("chat.send")}');
  const human = source.indexOf("<TalkToPersonButton onPress={onRequestHuman} />");

  assert.ok(scrollStart >= 0 && scrollEnd > scrollStart, "chat scroll region is missing");
  for (const [name, position] of Object.entries({ human, input, messages, send })) {
    assert.ok(position > scrollStart && position < scrollEnd, `${name} is not keyboard-reachable`);
  }
  assert.equal((source.match(/<ScrollView\b/g) ?? []).length, 1);
  const composer = source.indexOf("<SurfaceCard elevated", human);
  assert.ok(composer > human && composer < scrollEnd, "composer card is not grouped in the scroll region");
  assert.match(source.slice(composer, scrollEnd), /flexDirection: "row"[\s\S]*<TextInput[\s\S]*accessibilityLabel=\{t\("chat\.send"\)\}/);
});

test("language options start neutral and expose no false selected state", () => {
  const source = read("src", "screens", "LanguageScreen.tsx");
  assert.equal(
    (source.match(/accessibilityState=\{\{ disabled: false, selected: false \}\}/g) ?? []).length,
    2,
  );
  assert.doesNotMatch(source, /selected:\s*true|backgroundColor:\s*theme\.colors\.navySoft/);
  assert.equal((source.match(/style=\{\(\{ pressed \}\) =>/g) ?? []).length, 2);
  assert.match(source, /pressed \? pressedButtonStyle : null/);
  assert.match(source, /pressed \? pressFeedbackStyle : null/);
});

test("handoff keeps its actionable human control after the scrolling content", () => {
  const source = read("src", "screens", "HandoffScreen.tsx");
  const scrollStart = source.indexOf("<ScrollView");
  const scrollEnd = source.indexOf("</ScrollView>");
  const disclosure = source.indexOf("<AiDisclosure />");
  const human = source.indexOf("<TalkToPersonButton");

  assert.ok(disclosure >= 0 && disclosure < scrollStart, "handoff disclosure is not persistent");
  assert.ok(scrollStart >= 0 && scrollEnd > scrollStart, "handoff scroll region is missing");
  assert.ok(human > scrollEnd, "handoff control can scroll out of reach");
  assert.match(source, /state !== "requested"/);
  assert.match(source, /busy=\{isRequesting\}/);
  assert.match(source, /disabled=\{isRequesting\}/);
});

test("home hero uses a wrapping vertical composition", () => {
  const source = read("src", "screens", "HomeScreen.tsx");
  assert.match(source, /flexDirection: "column"/);
  assert.match(source, /minHeight: 168/);
  assert.match(source, /alignSelf: "stretch", flex: 1, justifyContent: "flex-end"/);
  assert.match(source, /color: theme\.colors\.card, flexShrink: 1/);
});

test("every interactive Pressable supplies contrast-preserving pressed feedback", () => {
  const targets = [
    ["components", "TalkToPersonButton.tsx"],
    ["screens", "LanguageScreen.tsx"],
    ["screens", "ConsentScreen.tsx"],
    ["screens", "HomeScreen.tsx"],
    ["screens", "TalkScreen.tsx"],
    ["screens", "ChatScreen.tsx"],
    ["screens", "MyRequestsScreen.tsx"],
    ["screens", "ErrorScreen.tsx"],
  ];

  for (const parts of targets) {
    const source = read("src", ...parts);
    const controls = (source.match(/<Pressable\b/g) ?? []).length;
    const stateStyles = (source.match(/style=\{\(\{ pressed \}\) =>/g) ?? []).length;
    assert.ok(controls > 0, `${parts.at(-1)} has no Pressable control`);
    assert.equal(stateStyles, controls, `${parts.at(-1)} lacks pressed-state styling`);
    assert.match(source, /pressFeedbackStyle/);
  }

  const themeSource = read("src", "theme.ts");
  assert.match(themeSource, /pressFeedbackStyle/);
  assert.match(themeSource, /transform:\s*\[\{ scale: 0\.98 \}\]/);
  assert.doesNotMatch(themeSource.match(/export const pressFeedbackStyle[\s\S]*$/)?.[0] ?? "", /opacity|color/);
});

test("decorative presentation uses React Native geometry rather than text glyphs", () => {
  const source = read("src", "components", "Presentation.tsx");
  assert.doesNotMatch(source, /\bText\b|symbol:/);
  assert.match(source, /pattern\?: "bridge" \| "center" \| "pair" \| "shield" \| "tiles" \| "wave"/);
  assert.match(source, /accessibilityElementsHidden/);
  assert.match(source, /importantForAccessibility="no-hide-descendants"/);
});

test("fixed safety controls remain outside scrolling content on composed screens", () => {
  for (const name of ["HomeScreen.tsx", "TalkScreen.tsx", "HandoffScreen.tsx", "MyRequestsScreen.tsx", "ErrorScreen.tsx"]) {
    const source = read("src", "screens", name);
    const scrollEnd = source.indexOf("</ScrollView>");
    const footer = source.indexOf("<PersistentFooter>");
    assert.ok(scrollEnd >= 0 && footer > scrollEnd, `${name} footer is not persistent`);
  }
});

test("talk presents a large hidden voice motif without rendering a microphone control", () => {
  const source = read("src", "screens", "TalkScreen.tsx");
  assert.match(source, /pattern="wave" size=\{88\} tone="teal"/);
  assert.match(source, /height:\s*144/);
  assert.match(source, /width:\s*144/);
  assert.doesNotMatch(source, /microphone|tap_to|listening|speaking|record|timer/i);
});
