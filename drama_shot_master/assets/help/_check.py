"""校验 help/ 下所有页面：标签闭合、内部链接存在、引用了 style.css。"""
import sys
from pathlib import Path
from html.parser import HTMLParser

HELP = Path(__file__).resolve().parent
VOID = {"meta", "br", "img", "link", "input", "hr", "area", "base", "col", "source"}


class Bal(HTMLParser):
    def __init__(self):
        super().__init__()
        self.stack = []
        self.hrefs = []
        self.has_css = False

    def handle_starttag(self, t, attrs):
        d = dict(attrs)
        if t == "a" and d.get("href"):
            self.hrefs.append(d["href"])
        if t == "link" and d.get("href", "").endswith("style.css"):
            self.has_css = True
        if t not in VOID:
            self.stack.append(t)

    def handle_endtag(self, t):
        if self.stack and self.stack[-1] == t:
            self.stack.pop()
        elif t in self.stack:
            while self.stack and self.stack.pop() != t:
                pass


def main():
    pages = sorted(HELP.glob("*.html"))
    bad = []
    for p in pages:
        b = Bal()
        b.feed(p.read_text(encoding="utf-8"))
        if b.stack:
            bad.append(f"{p.name}: 标签未闭合 {b.stack[-5:]}")
        if not b.has_css:
            bad.append(f"{p.name}: 未引用 style.css")
        for h in b.hrefs:
            if h.startswith(("http", "#", "mailto:")):
                continue
            target = (HELP / h).resolve()
            if not target.exists():
                bad.append(f"{p.name}: 死链 -> {h}")
    if not (HELP / "assets" / "style.css").exists():
        bad.append("assets/style.css 缺失")
    if bad:
        print("FAIL:")
        for x in bad:
            print("  ", x)
        sys.exit(1)
    print(f"OK: {len(pages)} 页全部通过（标签闭合 / 引 CSS / 内链有效）")


if __name__ == "__main__":
    main()
