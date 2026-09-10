---
name: Civic Operations
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#45464d'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#76777d'
  outline-variant: '#c6c6cd'
  surface-tint: '#565e74'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#131b2e'
  on-primary-container: '#7c839b'
  inverse-primary: '#bec6e0'
  secondary: '#006a61'
  on-secondary: '#ffffff'
  secondary-container: '#86f2e4'
  on-secondary-container: '#006f66'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#2f1500'
  on-tertiary-container: '#c76c00'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2fd'
  primary-fixed-dim: '#bec6e0'
  on-primary-fixed: '#131b2e'
  on-primary-fixed-variant: '#3f465c'
  secondary-fixed: '#89f5e7'
  secondary-fixed-dim: '#6bd8cb'
  on-secondary-fixed: '#00201d'
  on-secondary-fixed-variant: '#005049'
  tertiary-fixed: '#ffdcc3'
  tertiary-fixed-dim: '#ffb77d'
  on-tertiary-fixed: '#2f1500'
  on-tertiary-fixed-variant: '#6e3900'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Inter
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Inter
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Inter
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.005em
  body-lg:
    fontFamily: Noto Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
  body-md:
    fontFamily: Noto Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
  body-sm:
    fontFamily: Noto Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  label-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.01em
  label-sm:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.03em
  code-sm:
    fontFamily: Noto Sans
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  space-1: 0.25rem
  space-2: 0.5rem
  space-3: 0.75rem
  space-4: 1rem
  space-5: 1.25rem
  space-6: 1.5rem
  space-8: 2rem
  space-10: 2.5rem
  space-12: 3rem
  gutter-compact: 0.5rem
  gutter-default: 1rem
  margin-screen: 1.5rem
---

## Brand & Style

This design system establishes an institutional, high-consequence command interface for public-sector emergency response and civic atrocity monitoring. The design rejects decorative visual tropes, ambient gradients, and speculative artificial intelligence aesthetics in favor of unyielding clarity, rapid cognitive triage, and total auditability.

The visual style is **Institutional Modern**: clean, dense, structured, and anchored in bureaucratic rigor. It treats interface space as a high-density information terminal where operators, state magistrates, and enforcement liaisons must comprehend incident escalations, dispatch critical resources, and verify algorithmic classifications under extreme temporal stress.

### Design Principles
- **Clarity Over Novelty:** Visual signals strictly denote state or hazard. Red is rationed solely for immediate, unacknowledged physical danger.
- **Bilingual Parity:** English and Devanagari typographic scripts maintain matched vertical metrics, line rhythm, and stroke presence across data density tiers.
- **Dual-Control Assurance:** Algorithmic inferences remain visually subordinate to human validation. Unconfirmed model assessments appear with provisional borders and confidence ratings, while human-confirmed statuses adopt definitive teal stamps.
- **Mechanical Restraint:** Flat surfaces, precise 1px administrative dividers, and strict 4px grid increments eliminate all atmospheric ambiguity.

## Colors

The color architecture is built around operational utility, extreme legibility, and standardized triage semantics. The base theme is light, built to maintain legibility in well-lit operational control rooms and government field offices.

### Palette Architecture
- **Primary (`#0F172A` / `#1E293B`):** Deep Navy/Slate. Used for persistent command navigation, global mastheads, critical data tables, and high-emphasis structural containers. Communicates institutional authority.
- **Secondary (`#0D9488`):** Muted Deep Teal. Dedicated entirely to human-verified operational steps, signed-off dispatches, and confirmed field events.
- **Tertiary (`#D97706`):** Amber / Ochre. Indicates heuristic uncertainty, algorithmic divergence, pending clearances, and time-critical operational escalations.
- **Immediate Hazard Crimson (`#DC2626` / `#EF4444`):** Strictly restricted. Never used for general errors, validation warnings, or secondary deletions. It is activated solely when an unacknowledged immediate threat to life or field safety is logged.
- **Neutral Surface & Boundaries (`#F8FAFC`, `#F1F5F9`, `#E2E8F0`):** Cool, clinical background planes. High-contrast border definitions (`#E2E8F0` on panels, `#CBD5E1` on interactive boundaries) provide distinct tabular visual containment without heavy shadows.
- **Text & Data Tokens:** Primary content rests at `#0F172A` (meeting WCAG AAA contrast against `#F8FAFC`), supporting audit metadata at `#475569`, and disabled system rules at `#94A3B8`.

## Typography

The typographical engine supports fluid bilingual parity between English and Devanagari. Inter handles structural labels, coordinates, identification codes, and metric dashboards, while Noto Sans provides universal glyph integrity for vernacular incident narratives, field witness notes, and official communications.

### Implementation Guidelines
- **Cross-Script Metric Baseline:** When Devanagari and Latin scripts appear inline, align both to the text baseline. Maintain identical optical height using Noto Sans across Hindi, Marathi, and Sanskritized dispatch descriptors.
- **Numeric Discipline:** Tabular figures (`tnum`) and slashed zeros (`zero`) are globally enforced for all incident tracking IDs, Indian Standard Time (IST) timestamps, police station zone codes, and section classifications.
- **Vertical Rhythm:** Paragraphs are optimized for quick reading with a 1.4 to 1.5 line-height ratio, avoiding loose leading that could compromise data density.

## Layout & Spacing

The layout model utilizes a structured, high-density 12-column grid system tuned for situational dashboards and complex incident records. Information density is prioritized over wide aesthetic padding.

### Grid & Density Hierarchy
- **Desktop (1440px+):** Fixed 260px primary navigation sidebar (navy), a collapsible 380px triage/audit panel on the right, and a responsive 12-column data workspace in the center with 16px gutters and 24px outer margins.
- **Tablet / Operational Field Terminals (1024px - 1439px):** 64px compact icon-rail navigation sidebar, 16px margins, and dynamic 8-column center workspace. The inspection pane converts to an off-canvas drawer.
- **Mobile Handheld (Field Operatives):** Single-column stacked triage list. Pinned emergency dispatch bar at the viewport base.

### Layout Principles
- **Predictable Coordinates:** Data panels, status counters, and real-time incident queues sit within defined bounding boxes to prevent cumulative layout shift during live WebSocket updates.
- **Compact Verticality:** Padding inside data rows is locked to `space-2` (8px) top and bottom, ensuring at least 18 actionable cases remain visible above the fold on standard enterprise displays.

## Elevation & Depth

This system avoids ambient blur and decorative multi-stop drop shadows. Visual depth is established through **tonal layering and crisp structural borders**, reflecting the clarity of printed legal and governmental registries.

### Surface Hierarchy
- **Canvas Base (`#F8FAFC`):** The foundational viewport floor.
- **Level 1 Panels (`#FFFFFF`):** High-contrast, clean white data cards, triage tables, and record sheets bordered by a 1px solid `#E2E8F0` stroke.
- **Level 2 Inset / Scaffolding (`#F1F5F9`):** Audit detail headers, code containers, and system metadata boxes. Embedded using an interior `#E2E8F0` border with zero drop shadow.
- **Level 3 Persistent Navigation (`#0F172A`):** Deepest visual plane, acting as a permanent visual anchor on the left and top framing.
- **Level 4 Overlays & Verification Modals (`#FFFFFF` with `#0F172A` wash):** Modal screens sit above a semi-opaque `#0F172A` backdrop (opacity 65%). Modals use a crisp border (`#CBD5E1`) and a functional structural shadow: `0 4px 6px -1px rgba(15, 23, 42, 0.08), 0 10px 15px -3px rgba(15, 23, 42, 0.12)`.

## Shapes

The shape system applies a controlled radius of 0.25rem (`4px`), providing a structured, utilitarian appearance suited to official records. Circular pills and sweeping border radiuses are eliminated to maximize screen real estate and align cleanly with data tables.

### Corner Rules
- **Base Components (`rounded` / 4px):** Applied to form inputs, buttons, status indicators, table cells, and panel borders.
- **Structural Containers (`rounded-lg` / 8px):** Reserved exclusively for major application surfaces, such as detached modal dialogs, flyout notifications, and root system cards.
- **Indicators and Badges:** Sharp rectangular badges with uniform 2px or 4px radii. Circular radiuses (9999px) are permitted only for single-digit unread count indicators.

## Components

### Buttons
- **Primary Operational:** Background `#0F172A`, text `#FFFFFF`, 4px radius, 36px height for default density, 32px for compact tables. Padding: 0 14px. Focus state: 2px offset ring in `#0D9488`.
- **Human Confirmation Action:** Background `#0D9488`, text `#FFFFFF`. Hover `#0F766E`. Active `#115E59`. Used for manual dispatch, identity verification, and sign-offs.
- **Hazard Escalation (Restricted):** Background `#DC2626`, text `#FFFFFF`. Requires double-interaction or click-hold confirmation to prevent accidental triggering.
- **Secondary / Administrative:** Background `#FFFFFF`, border 1px solid `#CBD5E1`, text `#1E293B`. Hover `#F8FAFC`.

### Chips & Audit Badges
- **Verified Status:** Background `#F0FDFA`, border 1px solid `#5EEAD4`, text `#0F766E`.
- **Model Confidence Score:** Mono-spaced numeric display. Border 1px solid `#E2E8F0`, background `#F8FAFC`. Color-coded trailing confidence dot: Teal (90%+), Amber (70-89%), Red (<70% or flagged conflict).
- **Hazard Warning:** Background `#FEF2F2`, border 1px solid `#FCA5A5`, text `#991B1B`.

### Confidence Bars
- **Anatomy:** 4px tall flat-fill track with a `#E2E8F0` background. Fill color matches confidence states (Teal/Amber/Crimson). Placed directly adjacent to system-generated classifications to show operational reliability.

### Data Lists & Tabular Registers
- **Row Architecture:** Alternate row fills disabled. Rows rely on 1px bottom borders (`#F1F5F9`). Active row hover is `#F8FAFC`.
- **Selected Incident Row:** 3px vertical line indicator at the far-left border in `#0F172A` or `#DC2626` (if critical), with a `#F1F5F9` background.

### Input Fields & Controls
- **Inputs:** Height 36px, background `#FFFFFF`, border 1px solid `#CBD5E1`, text `#0F172A`, font-size 14px. Focus state: border `#0F172A` with a 1px solid outline.
- **Checkboxes & Radios:** Sharp square checkboxes (2px radius). Checked state `#0F172A` with high-contrast white check. Error state outlines strictly `#DC2626`.

### Cards & Case Folders
- Flat white containers (`#FFFFFF`) with 1px borders (`#E2E8F0`). Card headers feature a light grey accent background (`#F8FAFC`) with an integrated case identifier, section tags (e.g., IPC / SC-ST Prevention of Atrocities Act references), and an audit timestamp in Indian Standard Time (IST).