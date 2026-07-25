# EmoTend Light Beverage UI Design

## Scope

This redesign changes only the browser interface and its local flavor-preview data. It keeps the current alcohol menu, backend API, LLM configuration, prompts, dialogue routing, profiles, Android bridge, and report flow unchanged.

The dark Windows preview remains recoverable from local commit `58a8927`.

## Flavor Model

The read-only radar chart uses these axes in this exact order:

1. 甜度
2. 茶感
3. 奶香
4. 果香
5. 清爽度
6. 口感层次

The six existing emotion drinks receive explicit preview values instead of relabeling the old alcohol-oriented values:

| Emotion | 甜度 | 茶感 | 奶香 | 果香 | 清爽度 | 口感层次 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 清醒 | 20 | 35 | 5 | 70 | 90 | 65 |
| 兴奋 | 55 | 25 | 0 | 80 | 85 | 70 |
| 难过 | 70 | 20 | 75 | 25 | 35 | 65 |
| 疲惫 | 30 | 60 | 20 | 15 | 40 | 70 |
| 焦虑 | 25 | 45 | 10 | 55 | 75 | 75 |
| 犹豫 | 40 | 50 | 20 | 60 | 65 | 80 |

Specification adjustments remain local UI previews:

- 低甜 caps 甜度 at 25.
- 标准甜 raises 甜度 to at least 58.
- 清爽 raises 清爽度, lowers 奶香, and slightly lowers 甜度.
- 醇厚 raises 奶香 and 口感层次, and slightly raises 甜度.

## Visual Direction

The interface uses a cool, light beverage-lab visual system:

- Page canvas: cool off-white.
- Surfaces: white with fine neutral borders.
- Primary text: charcoal.
- Primary action: coral orange.
- Supporting accents: teal and mint.
- Radar chart: fine cool-gray grid, translucent coral fill, teal data stroke.
- Face stage: light neutral display surface while preserving all existing expression animation.
- Final report: white editorial report with pale section bands.
- Receipt: restrained pale paper treatment integrated with the report background.

The layout, navigation, and visibility rules remain unchanged.

## Compatibility

- The Android `EmoTenderAndroid.startSpeech()` bridge is unchanged.
- Windows recording remains out of scope.
- No backend field names or API paths change.
- Existing local drink customization does not claim to modify backend recipes.

