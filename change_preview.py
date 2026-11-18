"""Masked, paginated fixed-copy preview with cell-specific fix descriptions."""
from html import escape
from math import ceil

PREVIEW_ARABIC = {
    "Preview version": "نسخة المعاينة",
    "Preview page": "صفحة المعاينة",
    "Highlighted cells were corrected. Hover over a cell to see the applied fix.": "تم تصحيح الخلايا المميزة. مرّر المؤشر فوق الخلية لمعرفة التصحيح المطبق.",
    "Apply fixes in Review & fix to see corrected cells here.": "طبّق التصحيحات في المراجعة والتصحيح لرؤية الخلايا المصححة هنا.",
    "Removed duplicate rows: {0}. Removed rows are not present in the corrected preview.": "الصفوف المكررة المحذوفة: {0}. لا تظهر الصفوف المحذوفة في المعاينة المصححة.",
    "Rows {0}–{1} of {2}. Downloads include all rows.": "الصفوف {0}–{1} من {2}. تتضمن التنزيلات جميع الصفوف.",
    "The download uses this fixed copy without applying additional fixes.": "يستخدم التنزيل هذه النسخة المصححة دون تطبيق تصحيحات إضافية.",
    "Reapply fixes to refresh the corrected preview.": "أعد تطبيق التصحيحات لتحديث المعاينة المصححة.",
    "Corrected data preview": "معاينة البيانات المصححة",
    "No rows to preview.": "لا توجد صفوف للمعاينة.",
}


def preview_html(safe_frame, changes, start, translate):
    """Accept ONLY already masked data; tooltip contents are fix types, not values."""
    reasons = {}
    for _, change in changes.iterrows():
        if change["Change reason"] == "Removed duplicate row":
            continue
        row, column = change["Corrected row"], change["Column position"]
        if row is None or column is None:
            continue
        try:
            position = (int(row) - 1, int(column))
        except (ValueError, TypeError):
            continue
        reasons.setdefault(position, []).append(translate(str(change["Change reason"])))
    header = "<th>" + escape(translate("Row Number")) + "</th>"
    header += "".join("<th>" + escape(str(column)) + "</th>" for column in safe_frame.columns)
    body = []
    for offset, values in enumerate(safe_frame.itertuples(index=False, name=None)):
        cells = [f'<th scope="row">{start + offset + 1}</th>']
        for column, value in enumerate(values):
            reason = "; ".join(dict.fromkeys(reasons.get((start + offset, column), [])))
            attrs = (f' class="fixed-preview-cell" tabindex="0" title="{escape(reason, quote=True)}"'
                     f' aria-label="{escape(str(value) + ". " + reason, quote=True)}"') if reason else ""
            cells.append(f"<td{attrs}>{escape(str(value))}</td>")
        body.append("<tr>" + "".join(cells) + "</tr>")
    return (
        '<style>.fixed-preview-wrap{overflow:auto;max-height:620px;border:1px solid #d4e2dc;border-radius:10px}'
        '.fixed-preview-table{border-collapse:separate;border-spacing:0;min-width:100%;font-size:1rem}'
        '.fixed-preview-table th,.fixed-preview-table td{padding:12px 16px;border-bottom:1px solid #e1e9e5;text-align:start;white-space:pre-wrap;min-width:100px}'
        '.fixed-preview-table thead th{position:sticky;top:0;background:#edf4f0;z-index:1;color:#244b42}'
        '.fixed-preview-table td.fixed-preview-cell{background:#d9f0e4!important;color:#174c3b;box-shadow:inset 3px 0 #268368;cursor:help}'
        '.fixed-preview-cell:focus{outline:2px solid #176653;outline-offset:-2px}'
        '</style><div class="fixed-preview-wrap" tabindex="0" role="region" aria-label="'
        + escape(translate("Corrected data preview"), quote=True)
        + '"><table class="fixed-preview-table"><thead><tr>' + header
        + "</tr></thead><tbody>" + "".join(body) + "</tbody></table></div>"
    )


def render_change_preview(frame, changes, protected, key):
    from localization import native as st, translate as t
    from security_guardrails import mask_dataframe
    if frame.empty:
        st.info(t("No rows to preview."))
        return
    pages = max(1, ceil(len(frame) / 100))
    page_key = "fixed_preview_page_" + key
    if st.session_state.get(page_key, 1) > pages:
        st.session_state[page_key] = 1
    page = st.number_input(t("Preview page"), min_value=1, max_value=pages,
                           key=page_key) if pages > 1 else 1
    start = (page - 1) * 100
    safe = mask_dataframe(frame.iloc[start:start + 100], protected)
    st.caption(t("Highlighted cells were corrected. Hover over a cell to see the applied fix."))
    st.markdown(preview_html(safe, changes, start, t), unsafe_allow_html=True)
    st.caption(t("Rows {0}–{1} of {2}. Downloads include all rows.").format(start + 1, start + len(safe), len(frame)))
    removed = int((changes["Change reason"] == "Removed duplicate row").sum())
    if removed:
        st.caption(t("Removed duplicate rows: {0}. Removed rows are not present in the corrected preview.").format(removed))
