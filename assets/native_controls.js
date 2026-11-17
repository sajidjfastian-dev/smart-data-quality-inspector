// Streamlit 1.67 does not expose locale strings for its built-in widgets.
// Limit changes to control chrome, never filenames, uploaded values or options.
(() => {
  const arabic = __ARABIC__;
  const previous = window.__inspectorLocale;
  if (previous) previous.observer.disconnect();
  const originals = previous ? previous.originals : new Map();
  const strings = {
    "Upload": "رفع الملفات",
    "Upload directories": "رفع المجلدات",
    "Add files": "إضافة ملفات",
    "Remove file": "إزالة الملف",
    "Delete file": "حذف الملف",
    "Drag and drop files here": "اسحب الملفات وأفلتها هنا",
    "Drag and drop a file here": "اسحب الملف وأفلته هنا",
    "Choose an option": "اختر خياراً",
    "Choose options": "اختر الخيارات",
    "Choose or add an option": "اختر خياراً أو أضفه",
    "Choose or add options": "اختر خيارات أو أضفها",
    "No options to select": "لا توجد خيارات للاختيار",
    "Open": "فتح",
    "Close": "إغلاق",
    "Clear": "مسح",
    "Clear all": "مسح الكل",
    "file upload": "رفع ملف",
    "Collapse sidebar": "طي الشريط الجانبي",
    "Expand sidebar": "توسيع الشريط الجانبي",
    "Main menu": "القائمة الرئيسية",
    "Link to heading": "رابط إلى العنوان",
    "Show/hide columns": "إظهار الأعمدة أو إخفاؤها",
    "Download as CSV": "تنزيل بصيغة CSV",
    "Search": "بحث",
    "Fullscreen": "ملء الشاشة",
    "Exit fullscreen": "الخروج من ملء الشاشة",
    "Send message": "إرسال الرسالة",
    "Chat message from assistant": "رسالة محادثة من المساعد",
    "Chat message from user": "رسالة محادثة من المستخدم",
    "Skip to main content": "الانتقال إلى المحتوى الرئيسي",
    "Stop": "إيقاف",
  };
  function localized(value) {
    if (strings[value]) return strings[value];
    const limit = value.match(/^(.+?) per file$/);
    if (limit) return `${limit[1]} لكل ملف`;
    const remove = value.match(/^Remove (.+)$/);
    if (remove) return `إزالة ${remove[1]}`;
    const help = value.match(/^Help for (.+)$/);
    if (help) return `مساعدة بشأن ${help[1]}`;
    const options = value.match(/^(\d+) options? available\.$/);
    return options ? `${options[1]} خيارات متاحة.` : value;
  }
  function text(node) {
    if (!originals.has(node)) originals.set(node, node.nodeValue);
    const original = originals.get(node);
    const value = arabic ? localized(original) : original;
    if (node.nodeValue !== value) node.nodeValue = value;
  }
  function attribute(element, name) {
    const value = element.getAttribute(name);
    if (!value) return;
    let saved = originals.get(element);
    if (!saved || typeof saved !== "object") originals.set(element, saved = {});
    if (saved[name] && value !== saved[name] && value !== localized(saved[name]) &&
        name === "aria-label" && (/^Remove .+/.test(value) || /^Help for .+/.test(value))) {
      saved[name] = value;
    }
    // React can replace an attribute after a rerun; only recognize known chrome.
    if (!saved[name] && (strings[value] || Object.values(strings).includes(value) ||
        ((name === "aria-label") && (/^Remove .+/.test(value) || /^Help for .+/.test(value))))) {
      saved[name] = Object.keys(strings).find(key => strings[key] === value) || value;
    }
    if (!saved[name]) return;
    const desired = arabic ? localized(saved[name]) : saved[name];
    if (value !== desired) element.setAttribute(name, desired);
  }
  function update() {
    document.documentElement.lang = arabic ? "ar" : "en";
    document.documentElement.dir = arabic ? "rtl" : "ltr";
    document.querySelectorAll(
      '[data-testid="stFileUploaderDropzoneInstructions"], ' +
      '[data-testid="stFileUploaderDropzone"] button, ' +
      '[data-testid="stFileUploaderDropzone"] [data-testid="stFileUploaderDropzoneInstructions"]'
    ).forEach(element => {
      const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
      while (walker.nextNode()) text(walker.currentNode);
    });
    document.querySelectorAll('[data-testid="stFileUploader"] [aria-label], [data-testid="stFileUploader"] [title], button[aria-label], a[aria-label], input[placeholder], [data-testid="stChatMessageContent"]')
      .forEach(element => ["aria-label", "title", "placeholder"].forEach(name => attribute(element, name)));
    document.querySelectorAll('[data-testid="stSkipToContent"], [data-testid="stStatusWidget"] button')
      .forEach(element => {
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) if (strings[walker.currentNode.nodeValue] || originals.has(walker.currentNode)) text(walker.currentNode);
      });
    document.querySelectorAll('[role="log"][aria-live="assertive"][aria-relevant="additions"]')
      .forEach(element => {
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) if (/^\d+ options? available\.$/.test(walker.currentNode.nodeValue) || originals.has(walker.currentNode)) text(walker.currentNode);
      });
    // Drop prompts are present only during an active drag, not in uploaded filenames.
    document.querySelectorAll('[data-testid="stFileUploaderDropzone"]')
      .forEach(element => {
        const walker = document.createTreeWalker(element, NodeFilter.SHOW_TEXT);
        while (walker.nextNode()) {
          if (strings[walker.currentNode.nodeValue] && walker.currentNode.nodeValue.startsWith("Drag and drop")) text(walker.currentNode);
        }
      });
    for (const node of originals.keys()) if (!node.isConnected) originals.delete(node);
  }
  const observer = new MutationObserver(update);
  window.__inspectorLocale = {observer, originals};
  update();
  observer.observe(document.body, {childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ["placeholder", "aria-label", "title"]});
})();
