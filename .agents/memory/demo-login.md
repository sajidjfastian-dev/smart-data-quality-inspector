---
name: Demo login
description: The pretend "Sajid" login that gates data intake; what it must and must not do.
---
Login is a demonstration session only: "Continue without signing in" marks the session as logged in as Sajid; Log out clears the session (except interface language). Uploads, the sample workspace and reading from an API are only available while logged in.

**Why:** the user asked for a pretend login flow ("pretend like I logged in/out") until organisation SSO exists.

**How to apply:** never collect or store credentials, never tie it to inspection history, and keep the UI honest that it is a demo session. Login/Logout and the Settings icon share one row at the bottom-left of the sidebar; the header language switch is an EN/AR segmented control (radio group); the app has no footer. Render anything conditional (e.g. toasts) after the account panel, never before it — shifting its position makes Streamlit briefly show duplicate panels. AppTest-based tests must start sessions signed in (tests/demo_login.py helper).
