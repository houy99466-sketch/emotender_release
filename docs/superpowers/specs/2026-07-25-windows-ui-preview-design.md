# EmoTend Windows UI Preview Design

## Scope

This preview keeps the existing alcohol menu, LLM provider, ASR implementation, backend API, dialogue modes, profiles, and report flow unchanged. It changes only the recommendation-preview interface in `static/index.html`.

## Interaction

- The existing six-axis flavor chart remains visually unchanged and keeps the current dimensions: 甜、鲜、酸、咸、涩、苦.
- The chart is read-only. Pointer and touch interaction cannot change data points.
- A `调整规格` button appears below the chart.
- The button opens a modal modeled after the supplied ordering screenshot: grouped option sections, clear selected states, a selection summary, cancel, and confirmation actions.
- Option values are explicitly marked as UI preview data and do not modify backend recipes.
- Confirming options updates the local preview summary and flavor chart only. It does not claim that the backend recipe changed.

## Visual Replacement

The six random drink photos and random-selection behavior are removed from the recommendation flow. A deterministic drink-composition illustration replaces them. The illustration uses the current drink color, temperature selection, and option summary, and is labeled `饮品构成示意` so it cannot be mistaken for a real product photograph.

## Compatibility

The existing Windows webpage and Android WebView continue to consume the same HTML. No MiMo integration, milk-tea data, mobile-native rewrite, or backend endpoint change is included.
