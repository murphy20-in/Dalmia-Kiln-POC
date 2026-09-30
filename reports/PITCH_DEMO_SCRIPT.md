# Pitch demo script: Kiln Intelligence for Dalmia Cement, Ariyalur

**Length:** 10 minutes, plus Q&A. **Screen:** 1280×720 projector, browser zoom 100%.

## Before the meeting (5 minutes)

1. `cd dashboard && npm run dev`, or open the GitHub Pages link. Check that it loads with no network (the app has no backend).
2. Open these tabs in order:
   - Tab 1: `http://localhost:5173/?present=1#/` (presentation mode: no sidebar, 1.15× type).
   - Tab 2: `http://localhost:5173/?present=1#/console?t=2025-06-14T11:10` (the Normal → Warning climb).
3. In presentation mode, **←/→** move between pages in pitch order and **Esc** exits. **P** toggles the mode.
4. Have the plant's numbers ready if you can: clinker TPD, unplanned stoppage hours per year, fuel ₹/Mkcal.

## Click-by-click

### 1. Executive Summary (2 min), Tab 1
- **Say:** "We took six months of your SCADA exports, 2.58 million rows and 203 tags, and built the first stage of the kiln intelligence system on your own data."
- **Point at the journey stepper:** "You asked to move from reactive to planned intervention. Early detection is delivered on your data. Prediction is the next stage, and it needs your event logs."
- **Point at the 4 tiles, then the 3 finding cards:**
  - "Time in Warning went from a quarter of running time in June to over half in August."
  - "Eleven of the twelve abnormal periods involved several systems at once."
  - "When alternative fuel stops, PC coal rises about 6 TPH within the hour."
- **Point at the scorecard:** five objectives delivered, early signals on leading indicators, early warning needs event logs.
- Press **→**.

### 2. Kiln Health Console (3 min)
- It opens where Period 9, the highest-severity period, began drifting (15 Jul, 21:00). The period itself was flagged from 16 Jul, 03:00. The jump chips and "Replay" links always land on the drift onset, so you can watch it build. **Say:** "This is what a shift engineer would see: one health number, the state in words, what's driving it, and the last 24 hours."
- **Switch to Tab 2** (14 Jun, 11:10). The gauge is **Normal**.
- **Press Play (1×).** Narrate as it climbs. In about 8 seconds it reaches **Watch** and the drivers change. In about 18 seconds it reaches **Warning**, with combustion and stability bars growing and the reasons list updating.
- **Point at the grey arc:** "Critical is locked on purpose. It switches on only after we calibrate against your coating and stoppage logs."
- **Point at Decision support:** "Stage 3 links states to decisions: optimise, plan cleaning, plan a shutdown. It's illustrative today."
- **Optional:** type `2025-06-17 12:00` in the time box to show "Kiln stopped / no data": "We draw gaps as gaps; we never guess."
- Press **→**.

### 3. Efficiency Story (1.5 min)
- **Say:** "Is the kiln getting less efficient? Time in Warning went from 25% in June to 53% in August."
- **Point at the monthly columns, then the drivers chart:** combustion and draft carry most of it.
- **Tick "Sensitivity check: O₂ analyser excluded":** "Part of the August rise traces to the kiln-inlet O₂ analyser. Your calibration schedule will tell us how much is process and how much is instrument."
- Press **→**.

### 4. Abnormal Periods (1 min)
- **Say:** "Twelve abnormal operating periods, found automatically from process data. Three are high severity."
- **Click Period 3 (15 Jun)** in the timeline. The drawer shows times, systems, load context and the ±24 h chart. Click **Replay in Console** if time allows.
- **Say:** "The next step is matching these to your plant logs. That is task one of Stage 2."
- Press **→** twice (skip Alternative Fuel if short of time).

### 5. Alternative Fuel (1 min, optional)
- **Say:** "When AFR stops, PC coal steps in within the hour and preheater temperatures dip. 27 of the 43 links we found held up again on August data."
- **Point at "To go deeper":** "Your data tells us how much alternative fuel was fired, not what it was. Calorific value, moisture and the RDF/plastic split unlock fuel-quality → deposit-risk modelling."

### 6. Roadmap & Value (1.5 min)
- **Walk the four stages:** Stage 1 delivered; Stage 2 in 8–12 weeks; Stage 3 is the live console; Stage 4 is intervention recommendations.
- **Value calculator:** "These are placeholders. Let's put your numbers in." Type their clinker TPD, stoppage hours and fuel cost. The efficiency gain starts at **0%** on purpose: Stage 1 measured process drift, not a fuel-efficiency loss. Only enter a gain if they propose one. **Say the label out loud:** "Illustrative: your inputs, not a measured result."

### 7. The ask (30 s)
- **Point at the navy band:** "To start Stage 2 we need four things: event logs for April–September, the O₂ analyser calibration schedule, fuel-quality logs, and a process-engineering contact."
- **Click "Download summary (PDF)"** only if they want a leave-behind. It prints the current page.

## Objection handling

| They ask | Answer |
|---|---|
| "Does it predict?" | "Not yet. We had no event logs to learn from. That's Stage 2. The *How we validated* page shows the test we ran and why it didn't pass yet." |
| "Are these real deposits?" | "They're abnormal operating periods found from process data. Matching them to your logs is Stage 2 task one." |
| "Why is August so high?" | "Partly real drift, partly the O₂ analyser. Its calibration schedule separates the two." |
| "Can it run on our infra?" | "Today it's a static export: no server, no data leaves your network. Stage 3 connects read-only to your historian." |
| "How do we know the numbers are right?" | "Every number on screen traces to a versioned output, and each stage reruns to identical results. See *Data Readiness* and *How we validated*." |
| "What happened in September?" | "The main kiln workbook for September was truncated. We left it out rather than guess, and it's on the data-ask list." |

## Riskiest moments

1. **Play at 4×** moves fast and skips kiln-stopped spans. Stay on 1× for the narrated climb.
2. **Someone reads "Warning" as an alarm.** Say: "Warning means clearly away from your April–May normal. It's not a trip limit."
3. **Pushback on the value calculator.** Never defend the placeholder numbers; ask for theirs.
4. **"Why is Period 12 High but pale on the heatmap?"** Severity measures how high and how long the index stayed. The heatmap measures how far each individual system moved. Period 12 was long and broad rather than extreme in one system.
