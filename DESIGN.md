# frankHUB — Design System

Extracted from `autosolutionsai-didac/FrankBody-HUB` (the internal mock for Frank Body). This is the recipe book for building **more apps in the same look + voice** without going back to the source repo every time.

The stack assumed here is the same one the mock uses:

- **React 19 + Vite + TypeScript**
- **Tailwind via CDN** (`<script src="https://cdn.tailwindcss.com"></script>`)
- **lucide-react** for icons
- **recharts** for data viz
- Google Fonts: **Montserrat**, **Inter**, **Courier Prime**

Drop the snippets below into a new app and you get the same product family identity for free.

---

## 1. Brand DNA

Three things define the surface:

1. **Soft pink page + off-black ink.** Cosmetics-counter calm broken up by editorial typography.
2. **MONTSERRAT BLACK ALL-CAPS** for everything that wants to shout. Inter handles the rest.
3. **Cheeky, second-person voice.** "Hey babe." / "Where's the goods?" / "Make it pop." Module names get nicknames, never department labels.

If a screen ever feels generic, those three knobs are usually the fix.

---

## 2. Color tokens

Custom palette is declared inside the Tailwind CDN config in `index.html`. Use these exact tokens — everything in the system keys off them.

```js
tailwind.config = {
  theme: {
    extend: {
      colors: {
        frank: {
          pink:   '#F8E6E6', // signature soft pink — page background
          dark:   '#2A2A2A', // off-black — primary ink, primary button
          coffee: '#6F4E37', // scrub-brown accent — sparingly
          accent: '#E8B4B4'  // dusty pink — accent / hover borders
        }
      }
    }
  }
}
```

| Token | Hex | Role |
|---|---|---|
| `frank-pink` | `#F8E6E6` | Page bg, soft chip backgrounds, scrollbar track |
| `frank-dark` | `#2A2A2A` | Primary text, primary button fill, logo border, sticky nav fill |
| `frank-accent` | `#E8B4B4` | Hover borders, accent rules, chart highlights |
| `frank-coffee` | `#6F4E37` | Decorative accent for "scrub" / texture moments |
| `#D1A3A3` | `—` | Scrollbar thumb (literal hex, not a token) |
| white | `#FFFFFF` | Cards, sidebar, modal surfaces |

### Per-module accent palette

Each app in the hub owns one accent color from Tailwind defaults. Cards on the dashboard, headers inside the module, and any module-specific CTA all use the same hue. Keep this mapping so the hub stays color-coded.

| Module | Accent | Tailwind class |
|---|---|---|
| CRM | Pink | `bg-pink-500` |
| Forecasting | Blue | `bg-blue-500` |
| 3PL / Logistics | Teal | `bg-teal-500` |
| Designer | Indigo | `bg-indigo-500` |
| Legal Agent | Slate | `bg-slate-800` |
| Copywriter Agent | Orange | `bg-orange-500` |
| Expenses | Purple | `bg-purple-500` |

### Status palette

Always rendered as **pill chips**: `rounded-full px-2.5 py-0.5 text-xs font-bold uppercase tracking-wide`.

| State | Background → Text |
|---|---|
| VIP | `bg-purple-100 text-purple-700` (+ filled `Star` 10px) |
| Active / Healthy / Approved | `bg-green-100 text-green-700` |
| Pending | `bg-yellow-100 text-yellow-700` |
| Warning | `bg-orange-100 text-orange-600` |
| Critical / Churned | `bg-red-100 text-red-600` (or `text-red-700`) |
| Overstock / Info | `bg-blue-100 text-blue-600` |

---

## 3. Typography

Loaded once in `index.html`:

```html
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;800&family=Inter:wght@400;500;600&family=Courier+Prime:wght@400;700&display=swap" rel="stylesheet">
```

Wired into Tailwind:

```js
fontFamily: {
  sans:  ['Inter', 'sans-serif'],          // default body / UI
  brand: ['Montserrat', 'sans-serif'],     // headlines, labels, capsulated chrome
  mono:  ['Courier Prime', 'monospace'],   // logo wordmark, numbers, IDs, "technical" labels
}
```

### Type scale (recipes, not just sizes)

| Role | Class string |
|---|---|
| Page hero ("HEY BABE.") | `font-brand text-4xl md:text-5xl font-black text-frank-dark uppercase` |
| Page H2 ("THE CRM") | `font-brand text-3xl font-black text-frank-dark uppercase` |
| Card title | `font-brand font-black text-2xl text-frank-dark uppercase` |
| Sub-header H3 | `font-brand font-bold text-lg text-frank-dark` |
| Nav item | `text-sm font-bold uppercase tracking-wider` |
| Eyebrow / micro-label | `text-xs font-black uppercase tracking-widest text-gray-400` (or `text-frank-dark/40`) |
| Body | `text-sm font-medium` |
| Helper / sub-text | `text-xs text-gray-500 font-medium` |
| Monetary / numeric | `font-mono font-bold` |
| Mono chat (Legal Eagle replies) | `font-mono text-sm leading-relaxed` |

**Rules of thumb**

- Headlines are **Montserrat 800 (`font-black`), uppercase**. Don't reach for `font-bold` — go all the way.
- Labels (eyebrows, table headers, status pills) are **`uppercase tracking-widest`** and one of `text-xs` / `text-[10px]` / `text-[9px]`. The wider the tracking the smaller the type — they're inseparable.
- Numbers, IDs (`TRK-9921`, `$120,000`), and the logo are **always mono**. This is how the system signals "data" vs "voice".

---

## 4. The wordmark

Built in code, not an SVG. Two side-by-side capsules with a 2px black border, lowercase mono inside:

```tsx
const FrankLogo = ({ className = "text-2xl" }: { className?: string }) => (
  <div className={`flex items-stretch select-none ${className}`}>
    <div className="border-2 border-frank-dark rounded-l-md px-3 py-1 flex items-center justify-center bg-transparent">
      <span className="font-mono font-normal text-frank-dark tracking-tight leading-none pt-1">frank</span>
    </div>
    <div className="border-2 border-l-0 border-frank-dark rounded-r-md px-3 py-1 flex items-center justify-center bg-transparent">
      <span className="font-mono font-normal text-frank-dark tracking-tight leading-none pt-1">body</span>
    </div>
  </div>
);
```

Anytime you need a sub-brand mark for a new module, follow the same two-capsule pattern: `mono lowercase + 2px frank-dark border + transparent fill`.

---

## 5. Layout system

```
┌──────────────────────────────────────────────────────────┐
│  Sidebar 256px (white)  │   Main (bg-frank-pink)         │
│  ─ logo                 │   max-w-7xl mx-auto            │
│  ─ nav (sectioned)      │   p-4 md:p-8                   │
│  ─ "Logged in as" card  │   pt-24 md:pt-12               │
└──────────────────────────────────────────────────────────┘
```

- **Page background is `bg-frank-pink`.** Cards, sidebar, and inputs are white. This contrast is the foundation of the whole look — never put white-on-white.
- **Sidebar** is `w-64`, `border-r-2 border-frank-dark/10`, `shadow-xl`. Logo block has `border-b-2 border-frank-dark/10`. Nav is grouped into labelled sections (`Business`, `Creative`, `Agents`) with `font-black uppercase tracking-widest text-xs text-frank-dark/40` headers.
- **Mobile** uses a fixed `h-16` white top bar with `Menu` / `X` toggle (lucide). The mobile menu is a full-screen white panel.

### Active nav item

```tsx
isActive
  ? 'bg-frank-dark text-white shadow-lg'
  : 'text-frank-dark hover:bg-frank-accent/20'
```

Big, blocky, no rounded indicator — the entire row inverts to black.

---

## 6. Components

### 6.1 Card (default surface)

```html
<div class="bg-white p-6 rounded-xl border border-gray-100 shadow-sm">…</div>
```

Hoverable variant (used on dashboard tiles and kanban cards):

```html
<div class="group bg-white p-6 rounded-xl border-2 border-transparent
            hover:border-frank-dark hover:shadow-xl transition-all duration-300
            cursor-pointer">
```

### 6.2 Dashboard module tile

Anatomy:

1. **Soft glow** — large blurred circle of the module's accent color, top-right, `opacity-10`.
2. **Icon disc** — `w-12 h-12 rounded-full ${accent} text-white` with a lucide icon at 24px / `strokeWidth={2.5}`.
3. **Title** — `font-brand font-black text-2xl uppercase`.
4. **Description** — `text-sm text-gray-500 font-medium leading-relaxed`.
5. **Footer CTA** — `text-xs font-bold uppercase tracking-widest` + lucide `ArrowRight` that does `group-hover:translate-x-1`.

This is the canonical pattern for "entry point to an app".

### 6.3 Buttons

```html
<!-- Primary -->
<button class="bg-frank-dark text-white px-4 py-2 rounded-lg
               font-bold text-sm uppercase tracking-wide
               hover:bg-black transition-colors flex items-center gap-2">
  <Plus size="16" /> Add Babe
</button>

<!-- Secondary / outline -->
<button class="px-4 py-2 border border-gray-200 rounded-lg
               text-sm font-bold text-gray-600 hover:bg-gray-50">

<!-- Ghost icon -->
<button class="p-3 text-slate-400 hover:text-slate-600 hover:bg-slate-100
               rounded-lg border border-transparent hover:border-slate-200">

<!-- Module-themed CTA (e.g. Expenses) -->
<button class="bg-purple-600 text-white px-6 py-3 rounded-lg
               font-bold text-sm uppercase tracking-wide hover:bg-purple-700">

<!-- Hero "Make Magic" button (Designer) -->
<button class="w-full lg:w-64 h-32 rounded-xl font-black uppercase tracking-wide
               bg-frank-dark text-white border-2 border-frank-dark shadow-lg
               hover:bg-black hover:shadow-xl hover:-translate-y-1 transition-all">
```

### 6.4 Segmented tab control

Used for "The Babes / The Big Fish":

```html
<div class="flex bg-white p-1 rounded-lg border border-gray-200 shadow-sm">
  <button class="px-6 py-2 rounded-md text-sm font-bold uppercase tracking-wide
                 bg-frank-dark text-white shadow-md">Active</button>
  <button class="px-6 py-2 rounded-md text-sm font-bold uppercase tracking-wide
                 text-gray-500 hover:text-frank-dark hover:bg-gray-50">Inactive</button>
</div>
```

### 6.5 Pill chips

Tag chip (small, pink):
```html
<span class="text-[9px] font-bold uppercase tracking-wider
             bg-frank-pink text-frank-dark px-1.5 py-0.5 rounded">Retail</span>
```

Status pill:
```html
<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full
             text-xs font-bold uppercase tracking-wide
             bg-purple-100 text-purple-700">
  <Star size="10" fill="currentColor" /> VIP
</span>
```

### 6.6 Inputs

```html
<!-- Search -->
<div class="relative">
  <Search class="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size="18" />
  <input class="w-full pl-10 pr-4 py-2 bg-gray-50 rounded-lg text-sm font-medium
                focus:outline-none focus:ring-2 focus:ring-pink-300" />
</div>

<!-- Textarea (brief) -->
<textarea class="w-full bg-gray-50 border-2 border-gray-100 rounded-lg p-3
                 text-sm font-medium resize-none h-32
                 focus:outline-none focus:border-orange-400 focus:ring-0" />
```

Focus ring color **matches the module's accent** (`focus:ring-pink-300` in CRM, `focus:border-orange-400` in Copywriter, `focus:ring-frank-accent` in Designer).

### 6.7 Data table

- Header row: `bg-gray-50 border-b border-gray-100 sticky top-0 z-10`
- Header cells: `px-6 py-4 text-xs font-black text-gray-400 uppercase tracking-widest`
- Row hover: `hover:bg-pink-50/30 transition-colors group`
- Body cells: `px-6 py-4`
- Avatar (initial circle): `w-8 h-8 rounded-full bg-frank-pink flex items-center justify-center font-bold text-xs text-frank-dark`
- Money cells: right-aligned, `font-mono font-bold`

### 6.8 Kanban column

```html
<div class="flex-1 flex flex-col h-full bg-gray-50/50 rounded-xl
            border border-gray-200/60 max-w-[320px]">
  <!-- Header: top border accents in the stage's color -->
  <div class="p-4 border-t-4 border-blue-200 bg-blue-50/30 rounded-t-xl sticky top-0">
    <h3 class="font-brand font-black text-sm uppercase tracking-wide">Flirting</h3>
    <p class="text-xs font-medium text-gray-500">
      <span class="font-mono text-frank-dark">$85k</span> potential
    </p>
  </div>
  <div class="p-3 space-y-3 overflow-y-auto flex-1">
    <!-- cards -->
  </div>
</div>
```

Card hover: `hover:shadow-md hover:border-frank-accent transition-all cursor-grab`.

Kanban stage names follow the brand: **Fresh Meat → Flirting → The Date → Going Steady → Locked Down**. When you build a new pipeline, name the stages in voice, never "Lead / Qualified / Proposal".

### 6.9 AI Insight card (the "hero" black card)

Used by Oracle / Forecast. This pattern is reusable for any "the AI noticed something" moment:

```html
<div class="bg-frank-dark text-white p-6 rounded-xl shadow-xl
            relative overflow-hidden border-l-8 border-frank-accent">
  <div class="flex gap-6 items-start">
    <div class="w-12 h-12 rounded-full bg-white/10 flex items-center justify-center
                flex-shrink-0 animate-pulse">
      <BrainCircuit size="24" class="text-frank-accent" />
    </div>
    <div>
      <h3 class="font-brand font-bold text-lg mb-2
                 text-frank-accent uppercase tracking-wide">Strategic Insight</h3>
      <p class="font-medium text-lg leading-relaxed">
        <span class="font-bold text-frank-accent">Action Required:</span> …
      </p>
    </div>
  </div>
</div>
```

Key moves: **black bg + frank-accent left border + pink-accent label color + pulsing icon disc**.

### 6.10 Glow decoration

The decorative blurred blob in the top-right corner of input cards & result panels:

```html
<div class="absolute top-0 right-0 p-32 -mr-10 -mt-10
            bg-frank-pink rounded-full opacity-50 blur-3xl pointer-events-none">
</div>
```

Swap `bg-frank-pink` for `bg-orange-100`, `bg-purple-100`, etc. to theme the glow to the module.

### 6.11 Dot-grid background

For chat surfaces (Legal Eagle):

```html
<div class="absolute inset-0 opacity-[0.03] pointer-events-none"
     style="background-image: radial-gradient(#000 1px, transparent 1px);
            background-size: 20px 20px;">
</div>
```

### 6.12 Progress bar

Always 2.5px tall, rounded-full, accent-colored:

```html
<div class="w-full bg-gray-100 rounded-full h-2.5">
  <div class="bg-teal-500 h-2.5 rounded-full transition-all duration-1000"
       style="width: 60%"></div>
</div>
```

Color the fill with the module accent. Pair with 4 evenly-spaced uppercase milestone labels (`Ordered • Port • Customs • Delivered`).

### 6.13 Custom scrollbar

Lives in the `<style>` block of `index.html`:

```css
::-webkit-scrollbar           { width: 8px; }
::-webkit-scrollbar-track     { background: #F8E6E6; }
::-webkit-scrollbar-thumb     { background: #D1A3A3; border-radius: 4px; }
::-webkit-scrollbar-thumb:hover { background: #2A2A2A; }
```

---

## 7. Iconography

- **Library**: [`lucide-react`](https://lucide.dev). No emoji in UI.
- **Sizes**: 14 / 16 / 18 / 20 / 24 — pick to match the surrounding type.
- **Stroke**: default (2). Dashboard tile icons override to `strokeWidth={2.5}` because they sit inside a colored disc.
- **Placement on tiles**: always inside a `w-12 h-12 rounded-full` disc filled with the module accent.

Recurring picks for module identity: `Users` (CRM), `TrendingUp` (Forecast), `Ship` (3PL), `Palette` (Designer), `Scale` (Legal), `PenTool` (Copy), `Receipt` (Expenses), `BrainCircuit` (any "AI is thinking").

---

## 8. Motion

Subtle, fast, never showy. The full inventory:

| Where | What |
|---|---|
| View enter | `animate-fade-in` (define in CSS, opacity 0→1 over 300ms) |
| Hover arrow | `group-hover:translate-x-1 transition-transform` |
| Hover lift on hero CTA | `hover:-translate-y-1 hover:shadow-xl transition-all` |
| Active button press | `active:scale-95` |
| Loading icon | `animate-spin` on lucide `RefreshCw` / `Layers` |
| AI thinking | `animate-pulse` on the avatar disc + skeleton bars (`h-4 bg-white/20 rounded`) |
| Image zoom on hover | `group-hover:scale-110 transition-transform duration-700` inside `overflow-hidden` |
| Progress bar fill | `transition-all duration-1000` |

Add this to your global CSS so `animate-fade-in` works:

```css
@keyframes fade-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
.animate-fade-in { animation: fade-in .35s ease-out both; }
```

---

## 9. Charts (recharts)

- Grid: `<CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#f0f0f0" />`
- Axes: `axisLine={false} tickLine={false}` with `tick={{ fontSize: 10, fontWeight: 600 }}`
- Primary series: `stroke="#2A2A2A" strokeWidth={3}` (frank-dark)
- Forecast / predicted: `strokeDasharray="5 5" strokeWidth={2}`
- Filled area: `fill="#F8E6E6" stroke="#E8B4B4"` (pink / accent)
- Tooltip: `contentStyle={{ borderRadius: '8px', border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}`

Legend lives **outside** the chart, top-right, as `<span class="w-3 h-3 rounded-full bg-frank-dark"></span> Sales`.

---

## 10. Voice & copy

Module names, screen titles, and CTAs follow a strict pattern: **never the boring noun**. The brand voice is direct, second-person, slightly flirty, never corporate.

| Don't say | Say |
|---|---|
| "Welcome" | **HEY BABE.** |
| "Dashboard" | **Hub Home** |
| "Customers" | **The Babes** |
| "Pipeline" | **The Big Fish** |
| "Legal Assistant" | **Legal Babe** / **Legal Eagle** |
| "Copy Generator" | **The Copy Desk** |
| "Designer / Image gen" | **The Art Dept.** |
| "Forecast" | **Oracle AI** |
| "Logistics" | **Where's the goods?** |
| "Expenses" | **Spend it.** |
| "Generate" | **Make Magic** |
| "Submit" | **Approve Draft** |
| "Add lead" | **Add Deal** / **Add Babe** |
| "Add row" | **+ Add Babe** |
| "Loading..." | **Writing Magic…** / **Reviewing clauses…** / **Running Models…** |
| Pipeline stages | **Fresh Meat → Flirting → The Date → Going Steady → Locked Down** |
| Tone presets | **Cheeky / Extra Dirty / Sincere / Hype** |

Subtitles do the work of explaining what the module actually is, in a normal sentence:
> "Manage the babes (B2C) and the big fish (B2B)."
> "Demand Sensing & Inventory Optimization."
> "Brief the robots. Get 5 options. Pick the hottest one."

Empty states & error states keep the voice:
> "Waiting for the brief…" / "Writer's block. Try again, babe." / "System overload. Try again."

---

## 11. Page recipe (build a new module in 5 minutes)

```tsx
export const NewView: React.FC = () => (
  <div className="space-y-6 animate-fade-in flex flex-col min-h-full">

    {/* 1. Header — always font-brand black uppercase + sub */}
    <div className="flex flex-col md:flex-row justify-between items-end gap-4">
      <div>
        <h2 className="font-brand text-3xl font-black text-frank-dark uppercase">
          Module name in voice
        </h2>
        <p className="text-gray-600 font-medium text-sm">
          One-line explanation of what this actually does.
        </p>
      </div>
      {/* primary CTA or segmented control here */}
    </div>

    {/* 2. Optional: AI insight card (black, accent-bordered) */}

    {/* 3. Content grid — usually 1 / 2 / 3 col responsive */}
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 flex-1 min-h-0">
      {/* white rounded-xl shadow-sm cards */}
    </div>

  </div>
);
```

Then wire it into `App.tsx` + `AppView` + `Layout` nav with a lucide icon and a section header (Business / Creative / Agents / **YourSection**).

---

## 12. File-level starter

### `index.html`
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>frankHUB</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;800&family=Inter:wght@400;500;600&family=Courier+Prime:wght@400;700&display=swap" rel="stylesheet">
  <script>
    tailwind.config = {
      theme: {
        extend: {
          colors: {
            frank: {
              pink:   '#F8E6E6',
              dark:   '#2A2A2A',
              coffee: '#6F4E37',
              accent: '#E8B4B4'
            }
          },
          fontFamily: {
            sans:  ['Inter', 'sans-serif'],
            brand: ['Montserrat', 'sans-serif'],
            mono:  ['Courier Prime', 'monospace'],
          }
        }
      }
    }
  </script>
  <style>
    html, body, #root { height: 100%; margin: 0; padding: 0; }
    body { background-color: #F8E6E6; color: #2A2A2A; }
    ::-webkit-scrollbar { width: 8px; }
    ::-webkit-scrollbar-track { background: #F8E6E6; }
    ::-webkit-scrollbar-thumb { background: #D1A3A3; border-radius: 4px; }
    ::-webkit-scrollbar-thumb:hover { background: #2A2A2A; }
    @keyframes fade-in { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }
    .animate-fade-in { animation: fade-in .35s ease-out both; }
  </style>
</head>
<body>
  <div id="root"></div>
  <script type="module" src="/index.tsx"></script>
</body>
</html>
```

### `package.json` deps
```
react ^19   react-dom ^19   lucide-react   recharts   @google/genai
```

---

## 13. Quick "don'ts"

- ❌ Don't use Tailwind's `bg-pink-100` for the page background — it's not the same hue as `frank-pink`.
- ❌ Don't use `font-bold` where the spec says `font-black`. The whole brand voice depends on Montserrat 800.
- ❌ Don't emoji a label. Use a lucide icon at 12–14px instead.
- ❌ Don't combine two module accents on one screen. Pick the module's color and stick to it; pink (the brand) is always allowed.
- ❌ Don't write neutral copy. If a label could appear in any SaaS app, it's wrong here.
- ❌ Don't put white surfaces directly on white. Cards always sit on `frank-pink`, never on white.

---

See `frankhub-design-system.html` in this project for a live, visual rendering of every token & component listed above.
