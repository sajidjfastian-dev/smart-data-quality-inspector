# Accessibility and language readiness

The application keeps its own product branding. English and Arabic can be
selected in the header; Arabic is displayed right-to-left. Uploaded data,
column names, endpoint addresses and exported data are not translated.

The [UAE Design System accessibility guidance](https://designsystem.gov.ae/guidelines/accessibility)
targets WCAG 2.2 AA. The
[national digital accessibility policy](https://uaelegislation.gov.ae/en/policy/details/the-national-digital-accessibility-policy)
also describes organisational responsibilities, including accessibility
statements, support channels and testing with people of determination and
senior citizens. Applicability and any CBUAE-specific requirements need to be
confirmed by the organisation responsible for deployment.

This app has not been independently audited or certified. In particular:

- Some Streamlit-provided controls and dynamic content are still in English,
  and the local Arabic assistant supports common questions rather than every
  possible request. Exports retain their original data and report language.
- Keyboard, screen-reader, contrast, responsive and right-to-left behavior
  must be tested across the complete application, including tables and charts,
  with assistive-technology users.
- An accurate public accessibility statement and organisational arrangements
  required by the applicable policy must be supplied and maintained by the
  deployment owner. Do not claim conformance until those steps and an audit
  have been completed.
