---
name: Browser navigation checks
description: Non-obvious differences between Streamlit state tests and browser navigation.
---

Verify sidebar shortcuts in a real browser, not only through AppTest session state.

**Why:** Programmatic state can appear correct in AppTest while a browser still shows the first settings tab or a panel anchored outside the visible area. CSS-generated decorative symbols also contribute to accessible tab names, so an exact label locator can falsely suggest a visible tab is missing.

**How to apply:** Check the selected tab and visible panel after clicking a shortcut. Inspect accessible names when a locator fails, and distinguish that test issue from a real navigation failure.
