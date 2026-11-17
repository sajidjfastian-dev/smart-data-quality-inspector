---
name: Demo login
description: The pretend "Sajid" login that gates data intake; what it must and must not do.
---
Login is a demonstration session only: a single SSO-styled button signs in directly as Sajid/Submitter, without a preliminary dialog. Hide role choices and role explanations. Log out clears the session (except interface language).

**Why:** the user requested seamless SSO-style demo sign-in, confirmed “Hide role details”, and requested confirmation on approval.

**How to apply:** never collect or store credentials, never tie it to inspection history, and keep the UI honest that it is a demo session. Login/Logout and the Settings icon share one row at the bottom-left of the sidebar; the header language switch is an EN/AR segmented control (radio group); the app has no footer. Render anything conditional (e.g. toasts) after the account panel, never before it — shifting its position makes Streamlit briefly show duplicate panels. AppTest-based tests must start sessions signed in (tests/demo_login.py helper).
