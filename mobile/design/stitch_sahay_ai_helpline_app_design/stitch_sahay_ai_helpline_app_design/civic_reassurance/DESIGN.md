---
name: Civic Reassurance
colors:
  surface: '#faf8ff'
  surface-dim: '#d2d9f4'
  surface-bright: '#faf8ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f2f3ff'
  surface-container: '#eaedff'
  surface-container-high: '#e2e7ff'
  surface-container-highest: '#dae2fd'
  on-surface: '#131b2e'
  on-surface-variant: '#444651'
  inverse-surface: '#283044'
  inverse-on-surface: '#eef0ff'
  outline: '#757682'
  outline-variant: '#c5c5d3'
  surface-tint: '#4059aa'
  primary: '#00236f'
  on-primary: '#ffffff'
  primary-container: '#1e3a8a'
  on-primary-container: '#90a8ff'
  inverse-primary: '#b6c4ff'
  secondary: '#006a61'
  on-secondary: '#ffffff'
  secondary-container: '#86f2e4'
  on-secondary-container: '#006f66'
  tertiary: '#442100'
  on-tertiary: '#ffffff'
  tertiary-container: '#653400'
  on-tertiary-container: '#fc922b'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dce1ff'
  primary-fixed-dim: '#b6c4ff'
  on-primary-fixed: '#00164e'
  on-primary-fixed-variant: '#264191'
  secondary-fixed: '#89f5e7'
  secondary-fixed-dim: '#6bd8cb'
  on-secondary-fixed: '#00201d'
  on-secondary-fixed-variant: '#005049'
  tertiary-fixed: '#ffdcc3'
  tertiary-fixed-dim: '#ffb77d'
  on-tertiary-fixed: '#2f1500'
  on-tertiary-fixed-variant: '#6e3900'
  background: '#faf8ff'
  on-background: '#131b2e'
  surface-variant: '#dae2fd'
typography:
  display-lg:
    fontFamily: Public Sans
    fontSize: 36px
    fontWeight: '700'
    lineHeight: 44px
    letterSpacing: -0.02em
  display-lg-mobile:
    fontFamily: Public Sans
    fontSize: 28px
    fontWeight: '700'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Public Sans
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Public Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  headline-sm:
    fontFamily: Public Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
  body-lg:
    fontFamily: Noto Sans
    fontSize: 17px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Noto Sans
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
  body-sm:
    fontFamily: Noto Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  label-lg:
    fontFamily: Noto Sans
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  label-md:
    fontFamily: Noto Sans
    fontSize: 14px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Noto Sans
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  touch-min: 48px
  pad-xs: 4px
  pad-sm: 8px
  pad-md: 12px
  pad-lg: 16px
  pad-xl: 24px
  pad-2xl: 32px
  gutter-mobile: 16px
  margin-mobile: 16px
  gutter-desktop: 24px
  margin-desktop: 32px
---

## Brand & Style

This design system establishes an authoritative, trauma-informed, and civic-minded digital environment for citizens seeking safety, legal aid, and institutional assistance. The target demographic spans vulnerable citizens, community advocates, field officers, and distress callers across diverse linguistic and technological proficiencies.

The emotional objective is absolute reassurance, institutional dignity, discretion, and friction-free clarity. When a user opens an interface governed by this system, they must immediately sense stability, confidentiality, and dependable state-level efficacy without bureaucratic intimidation.

The aesthetic philosophy fuses **Corporate / Modern** civic precision with strict accessibility principles:
- **No superficial ornamentation**: Frosted glass, decorative gradients, skeuomorphic extrusions, and aggressive micro-animations are prohibited to prevent cognitive strain and latency in low-bandwidth distress environments.
- **Uncompromised legibility**: Generous touch regions, high optical separation, structured layouts, and persistent bilingual parity ensure that every critical decision is legible within seconds.
- **Dignified containment**: Interfaces rely on solid structural containers, subtle boundaries, and stable grounding colors to project safety and permanence.

## Colors

The color palette anchors its visual trust in an authoritative deep navy, reinforced by balanced civic functional accents that indicate stability, safety, system readiness, and immediate distress support.

### Hierarchy & Token Application
- **Primary (`#1E3A8A`)**: Deep Navy. Serves as the principal brand marker, driving key navigation bars, critical affirmative buttons, focus states, and primary informational milestones. It projects sovereign credibility and legal permanence.
- **Secondary (`#0D9488`)**: Muted Teal. Used for safe confirmation banners, verified grievance markers, protected connectivity statuses, and affirmative resolution tags. It offers visual calm without the harshness of hyper-saturated neon greens.
- **Tertiary (`#D97706`)**: Warm Amber. Denotes warning alerts, offline synchronization states, network dropouts, or pending administrative verifications without inducing panic.
- **Neutral (`#0F172A`)**: Slate Black / Deep Midnight. Anchors dominant typography and dense icon states. Supporting neutrals include `#F8FAFC` (Calm Canvas Tint), `#F1F5F9` (Recessed Surface Tier), `#E2E8F0` (Structural Border Stroke), and `#64748B` (Secondary Contextual Meta).
- **Critical / Emergency (`#DC2626` / `#991B1B`)**: Muted Brick Red. Reserved exclusively for direct panic triggers, immediate distress hotlines, emergency disconnects, and unrecoverable failure signals. Never used decoratively.

All contrast relationships strictly satisfy WCAG 2.1 Level AAA requirements for institutional readability across high-glare ambient conditions on budget mobile screens.

## Typography

The typographic engine balances institutional authority with global multi-script harmony. **Public Sans** provides clear, geometric, and official presence for headings, while **Noto Sans** delivers effortless parity across Latin and Devanagari scripts for structural UI copy and running body text.

### Implementation Guidelines
- **Bilingual Stacking**: When Hindi and English are paired (e.g., Primary Label in Hindi, secondary transcript in English), maintain a consistent typographic ratio: Hindi takes precedence at `body-md` (Medium/Semibold) with the secondary English translation placed directly beneath in `label-sm` (Regular) using `#475569`.
- **Minimum Body Threshold**: Running body copy must never drop below `15px` (`body-md`) on primary mobile viewports to ensure total legibility for stressed or elderly individuals.
- **Line Heights**: Generous vertical metrics (minimum 1.5x on running paragraphs) prevent glyph collisions in multi-script Devanagari matras and vowel signs.

## Layout & Spacing

This design system uses an 8px base rhythmic grid paired with a 4px sub-grid for tight inline badges and compact inputs. The architectural layout strategy follows a responsive fluid grid bounded by safe margins.

### Breakpoints & Fluid Form Factors
- **Mobile (0 – 599px)**: 4-column fluid grid. Screen margin: `16px`. Column gutter: `16px`. Elements strictly honor dynamic safe-area insets at the top status bar and bottom gesture bar.
- **Tablet (600 – 1023px)**: 8-column fluid grid. Screen margin: `24px`. Column gutter: `20px`. Single-column flows convert into dual-pane master-detail containers for rapid triage workflows.
- **Desktop (1024px+)**: 12-column grid. Maximum container width capped at `1120px` to maintain optimal ergonomic scanning lengths during administrative dispatch operations.

### Defensive Touch Real Estate
Every interactive control (button, chip selector, toggle, text link, accordion trigger) must maintain a bounding collision envelope of at least `48px x 48px`, regardless of visual icon size.

## Elevation & Depth

Visual hierarchy is constructed through **tonal surface layering combined with low-contrast structural outlines**, rather than high-contrast dramatic drop shadows. This preserves visual cleanliness and provides an unencumbered spatial hierarchy.

### The Tiered Elevation System
- **Level 0 (Canvas Base)**: `#F8FAFC`. The foundational backdrop upon which all layout sequences rest.
- **Level 1 (Structural Cards & Surfaces)**: `#FFFFFF`. Pure white planar elements bordered by a crisp `1px` border stroke (`#E2E8F0`). Flat elevation with no ambient shadow when static.
- **Level 2 (Active Sheets & Focus Cards)**: `#FFFFFF` paired with an ultra-diffused, ambient downward blur: `box-shadow: 0 4px 12px -2px rgba(15, 23, 42, 0.06), 0 2px 6px -1px rgba(15, 23, 42, 0.04)`. Used for active triage panels and focused complaint inputs.
- **Level 3 (Modals, Safety Drawers & Floating Assistance Overlays)**: `#FFFFFF` accompanied by `box-shadow: 0 12px 24px -4px rgba(15, 23, 42, 0.12), 0 4px 8px -2px rgba(15, 23, 42, 0.06)`. Backdrops use an authoritative deep scrim: `rgba(15, 23, 42, 0.6)`.

Gradients and semi-transparent blur backdrops are strictly disallowed for functional surfaces; content containers must remain fully opaque to preserve maximum contrast.

## Shapes

The design system enforces a roundedness token value of `2` (Moderate Rounded), yielding elements with an organic yet structural curvature that feels human and welcoming without appearing trivial or playful.

### Corner Radius Scale
- **Base Components (`rounded-md` / 8px)**: Used for standard text entry fields, status indicators, and notification callouts.
- **Card Containers & Modules (`rounded-lg` / 16px)**: Standard for all complaint review cards, verified officer information blocks, and legal guidance panels.
- **Major Surfaces & Sheets (`rounded-xl` / 24px)**: Applied to top-sheet alerts, bottom modal panels, and persistent container surfaces.
- **Pills / Full Round (`rounded-full` / 9999px)**: Reserved strictly for standalone status chips, secondary quick-filter tags, and primary audio call/dispatch buttons.

## Components

### Buttons & Quick Dispatch Triggers
- **Primary Action**: Solid Deep Navy (`#1E3A8A`) with high-contrast white typography (`#FFFFFF`). Minimum height: `52px`. Roundedness: `rounded-lg` (16px). Focus ring: `3px` solid `#0D9488` with a 2px offset.
- **Emergency Panic / Instant Distress**: Urgent Brick Red (`#DC2626`) surface, bold centered bilingual label ("SOS / आपातकालीन सहायता"), reinforced with an unmistakable telephone receiver or shield glyph. Always fixed or easily accessible on screen.
- **Persistent 'Talk to a Person' Button**: Positioned persistently at the bottom navigation or sticky sheet tier. Styled as a full-width pill (`rounded-full`) or elevated card with an icon, bilingual title ("Talk to Officer / अधिकारी से बात करें"), and active response badge ("24x7 Available").

### Input Fields & Verification Controls
- **Text Inputs**: Height `52px`, `#FFFFFF` background, solid 1.5px border (`#CBD5E1`). Corner radius `8px`. Active focus state shifts the border to 2px `#1E3A8A`. Error states introduce a 2px `#DC2626` outline and render error text immediately below the field with an accompanying alert icon.
- **Bilingual Labels**: Floating or statically stacked labels explicitly display both English and Hindi text strings (e.g., "Full Name / पूरा नाम").

### Cards & Grievance Panels
- **Anatomy**: Constructed on `#FFFFFF`, bounded by `1px` border (`#E2E8F0`), interior padding of `20px`, and `16px` corner curvature (`rounded-lg`).
- **Header**: Includes an institutional category badge on the left, accompanied by date/case status indicators on the right.
- **Divider**: Subtle structural horizontal rule (`#F1F5F9`) separating metadata from actionable contact details.

### Selection Controls (Checkboxes, Radio Buttons, Toggles)
- **Geometry**: Radio controls use concentric circles (22px diameter). Checkboxes are square with 4px corner radii (22px width/height).
- **Target Size**: Surrounding tap envelope is padded to `48px x 48px`.
- **Active State**: Primary Deep Navy (`#1E3A8A`) fill with pure white tick or pip.

### Chips & Filter Tags
- **Filter Chips**: Height `36px`, pill-shaped (`rounded-full`), padded `12px` horizontally.
- **Inactive**: Solid `#F1F5F9` background with `#334155` text.
- **Active**: Deep Navy (`#1E3A8A`) background with `#FFFFFF` text and a visible checkmark icon.

### Offline & Status Banners
- Non-intrusive strip spanning the full width of the mobile viewport.
- **Coloring**: Warm Amber `#FEF3C7` background with `#B45309` bold text, alerting users when grievance drafts are stored locally during network loss.