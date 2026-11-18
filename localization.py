"""Session-scoped translations for app-owned Streamlit interface text.

Dataset values and widget option values remain unchanged. Only text originating
from static application UI expressions is translated.
"""

import ast
import functools
import html
import inspect
import json
import re
from pathlib import Path

import streamlit as native
from streamlit.delta_generator import DeltaGenerator
from review_translations import REVIEW_ARABIC
from insights_translations import INSIGHTS_ARABIC
from ticket_translations import TICKET_ARABIC
from request_translations import REQUEST_ARABIC
from request_dashboard_translations import REQUEST_DASHBOARD_ARABIC
from change_preview import PREVIEW_ARABIC
from demo_sidebar_translations import DEMO_SIDEBAR_ARABIC
from persistent_demo_translations import PERSISTENT_DEMO_ARABIC
from quality_overview_translations import QUALITY_OVERVIEW_ARABIC
from issue_workspace_translations import ISSUE_WORKSPACE_ARABIC
from request_approval_translations import REQUEST_APPROVAL_ARABIC


_ROOT = Path(__file__).resolve().parent
_ARABIC = json.loads((_ROOT / "assets" / "translations" / "ar.json").read_text(encoding="utf-8"))
_ARABIC.update({
    "Share of findings": "نسبة النتائج",
    "All categories are listed below, including small slices.": "جميع الفئات مدرجة أدناه، بما فيها الشرائح الصغيرة.",
    "Column-level findings and duplicate rows, ranked by count.": "النتائج على مستوى الأعمدة والصفوف المكررة، مرتبة حسب العدد.",
    "Each share is measured against all detected findings.": "تُحسب كل نسبة من إجمالي النتائج المكتشفة.",
    "Missing rows (%)": "الصفوف ذات القيم المفقودة (%)",
    "Exact counts and share of rows; all columns are listed.": "الأعداد الدقيقة ونسبة الصفوف؛ جميع الأعمدة مدرجة.",
    "Review missing values in {0} ({1} missing).": "راجع القيم المفقودة في {0} (النسبة المفقودة {1}).",
    "Findings are review candidates, not confirmed errors.": "النتائج مرشحة للمراجعة وليست أخطاء مؤكدة.",
})
_ARABIC.update(REVIEW_ARABIC)
_ARABIC.update(INSIGHTS_ARABIC)
_ARABIC.update(TICKET_ARABIC)
_ARABIC.update(REQUEST_ARABIC)
_ARABIC.update(REQUEST_DASHBOARD_ARABIC)
_ARABIC.update(PREVIEW_ARABIC)
_ARABIC.update(DEMO_SIDEBAR_ARABIC)
_ARABIC.update(PERSISTENT_DEMO_ARABIC)
_ARABIC.update(QUALITY_OVERVIEW_ARABIC)
_ARABIC.update(ISSUE_WORKSPACE_ARABIC)
_ARABIC.update(REQUEST_APPROVAL_ARABIC)
_REVERSE = {value: key for key, value in _ARABIC.items() if "{" not in key}
_PATTERNS = []
for _source, _translation in _ARABIC.items():
    if not re.search(r"\{\d+\}", _source):
        continue
    _parts = re.split(r"(\{\d+\})", _source)
    _indices = [int(part[1:-1]) for part in _parts if re.fullmatch(r"\{\d+\}", part)]
    _pattern = "".join("(.*?)" if re.fullmatch(r"\{\d+\}", part) else re.escape(part) for part in _parts)
    _PATTERNS.append((len(_source), re.compile("^" + _pattern + "$", re.DOTALL), _indices, _translation))
_PATTERNS.sort(key=lambda item: item[0], reverse=True)
_MARKUP_CLASSES = (
    'class="welcome-panel"', 'class="brand-header"', 'class="sidebar-brand"',
    'class="sidebar-source-heading"', 'class="sidebar-helper"', 'class="sidebar-divider"',
    'class="sidebar-session-note"', 'class="dashboard-intro"', 'class="settings-hero"',
    'class="workflow-panel"',
)
_MARKUP_TEXT = {" ".join(key.split()): value for key, value in _ARABIC.items() if "<" not in key}


def language():
    return native.session_state.get("interface_language", "English")


def translate(value, locale=None):
    if (locale if locale is not None else language()) != "العربية" or not isinstance(value, str):
        return value
    if value in _ARABIC:
        return _ARABIC[value]
    for _, pattern, indices, translated in _PATTERNS:
        match = pattern.fullmatch(value)
        if match:
            captures = dict(zip(indices, match.groups()))
            return re.sub(r"\{(\d+)\}", lambda found: captures[int(found.group(1))], translated)
    return value


def translate_issue_type(value, locale=None):
    """Translate generated issue labels without altering a custom rule's value."""
    if isinstance(value, str) and value.startswith("Custom: "):
        return translate("Custom: {0}", locale).format(translate(value[len("Custom: "):], locale))
    return translate(value, locale)


def translate_progress(message):
    """Translate generated progress wording while keeping column names intact."""
    if language() != "العربية":
        return message
    parts = message.split(" · ", 2)
    parts[0] = translate(parts[0])
    if len(parts) == 3:
        parts[2] = translate(parts[2])
    return " · ".join(parts)


def display_profile(profile):
    """Localize only app-owned profile labels, never dataset column names."""
    if language() != "العربية":
        return profile
    result = profile.copy()
    result["Detected type"] = result["Detected type"].map(
        lambda text: " · ".join(translate(part) for part in text.split(" · "))
    )
    return result.rename(columns=translate)


def display_findings(issues):
    """Localize generated findings for display; leave exported findings untouched."""
    if language() != "العربية":
        return issues
    result = issues.copy()
    duplicate_rows = result["Issue Type"] == "Duplicate Row"
    result.loc[duplicate_rows, "Column Name"] = translate("Entire row")
    result.loc[duplicate_rows, "Current Value"] = translate("Exact match to an earlier row")
    result["Issue Type"] = result["Issue Type"].map(translate_issue_type)
    result["Suggested Fix"] = result["Suggested Fix"].map(translate)
    return result.rename(columns=translate)


def translate_markup(value):
    if language() != "العربية" or not any(marker in value for marker in _MARKUP_CLASSES):
        return value

    def replace(match):
        text = match.group(1)
        normalized = " ".join(html.unescape(text).split())
        translated = _MARKUP_TEXT.get(normalized)
        if not translated:
            return match.group(0)
        leading = text[:len(text) - len(text.lstrip())]
        trailing = text[len(text.rstrip()):]
        return ">" + leading + html.escape(translated, quote=False) + trailing + "<"

    value = re.sub(r">([^<>]+)<", replace, value)
    def replace_label(match):
        original = html.unescape(match.group(1))
        translated = _ARABIC.get(original)
        return 'aria-label="' + html.escape(translated, quote=True) + '"' if translated else match.group(0)
    return re.sub(r'aria-label="([^"]+)"', replace_label, value)


@functools.lru_cache(maxsize=8)
def _ui_sites(filename):
    """Identify application-owned literal UI expressions, excluding user data."""
    path = Path(filename)
    if path.parent != _ROOT or path.name not in {"app.py", "api_settings.py", "data_insights.py"}:
        return {}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    sites = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        first = node.args[0] if node.args else None
        owned = isinstance(first, (ast.Constant, ast.JoinedStr))
        option_arg = node.args[1] if len(node.args) > 1 else None
        static_options = isinstance(option_arg, (ast.List, ast.Tuple))
        for line in range(node.lineno, node.end_lineno + 1):
            sites.setdefault((line, node.func.attr), []).append((owned, static_options))
    return sites


_LABEL_METHODS = {
    "button", "download_button", "checkbox", "toggle", "radio", "selectbox", "multiselect",
    "text_input", "text_area", "number_input", "slider", "select_slider", "file_uploader",
    "expander", "status", "spinner", "popover", "dialog", "chat_input", "metric", "subheader",
    "header", "title", "caption", "info", "warning", "error", "success", "write", "markdown",
    "form_submit_button", "progress", "update",
}
_OPTION_METHODS = {"selectbox", "multiselect", "radio", "select_slider"}


def _wrap(value):
    if isinstance(value, DeltaGenerator):
        return _Proxy(value)
    if isinstance(value, list) and value and all(isinstance(item, DeltaGenerator) for item in value):
        return [_Proxy(item) for item in value]
    return value


class _Proxy:
    def __init__(self, target):
        self._target = target

    def __enter__(self):
        return _wrap(self._target.__enter__())

    def __exit__(self, *args):
        return self._target.__exit__(*args)

    def __getattr__(self, name):
        target = getattr(self._target, name)
        if not callable(target):
            return _wrap(target)

        def invoke(*args, **kwargs):
            frame = inspect.currentframe().f_back
            sites = _ui_sites(frame.f_code.co_filename).get((frame.f_lineno, name), [])
            owned = any(site[0] for site in sites)
            static_options = any(site[1] for site in sites)
            args = list(args)
            locale = language()
            if name == "tabs" and args and isinstance(args[0], (list, tuple)):
                original = args[0]
                translated = [translate(item, locale) for item in original]
                key = kwargs.get("key")
                if key and key in native.session_state:
                    current = native.session_state[key]
                    canonical = _REVERSE.get(current, current)
                    if canonical in original and current != translate(canonical, locale):
                        native.session_state[key] = translate(canonical, locale)
                args[0] = translated
            elif locale == "العربية":
                if name in _LABEL_METHODS:
                    if args and owned and isinstance(args[0], str):
                        args[0] = translate_markup(translate(args[0]))
                    for key in ("help", "label", "placeholder", "text"):
                        if key in kwargs and isinstance(kwargs[key], str):
                            kwargs[key] = translate(kwargs[key])
                    if name in _OPTION_METHODS and static_options:
                        original_format = kwargs.get("format_func", str)
                        kwargs["format_func"] = lambda option: translate(original_format(option), locale)
            return _wrap(target(*args, **kwargs))

        return invoke


st = _Proxy(native)
