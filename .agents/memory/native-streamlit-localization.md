---
name: Native Streamlit localization
description: Constraints on translating built-in Streamlit controls without changing user data.
---

The current Streamlit version does not expose translations for native controls. The Arabic interface adapts specific control chrome in the browser while leaving filenames, dataset values, options and exports untouched.

**Why:** CSS-only replacement would not give screen readers translated labels, and translating arbitrary page text can alter user-provided data.

**How to apply:** Scope any additions to identifiable native control elements and known interface strings; exercise upload, language switching and user-data preservation in browser tests after Streamlit upgrades.

Capture the current locale in option-formatting callbacks rather than looking up session language when the callback is later invoked.

**Why:** Streamlit/AppTest can serialize a previous render's widget after a language switch; live language lookup then produces labels absent from that widget's original options.

**How to apply:** Bind the render-time locale in native selectbox, radio and multiselect formatters while keeping underlying option values unchanged.

Check the visible selected state after switching languages, not only the stored selection.

**Why:** Native controls can retain an old display label or lose their visible checked indicator even when canonical session values remain correct.

**How to apply:** Preserve canonical choices independently of locale-specific presentation widgets when needed, and verify both language directions in a real browser.
