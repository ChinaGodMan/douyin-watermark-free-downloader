# -*- coding: utf-8 -*-
"""douyin_dl 核心逻辑单元测试（无需真实网络）"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import douyin_dl as D

fails = 0
def check(name, cond, detail=""):
    global fails
    print(("PASS " if cond else "FAIL ") + name + (f"  | {detail}" if detail and not cond else ""))
    if not cond: fails += 1

# 1. extract_url：各种分享文本
for txt, expect in [
    ("7.43 复制打开抖音，看看视频 https://v.douyin.com/abc123/ 哈", "https://v.douyin.com/abc123"),
    ("https://www.iesdouyin.com/share/video/7412345678901234567/", "https://www.iesdouyin.com/share/video/7412345678901234567"),
    ("https://www.douyin.com/video/7412345678901234567 复制此链接", "https://www.douyin.com/video/7412345678901234567"),
    ("随便一段没有链接的文字", None),
]:
    got = D.extract_url(txt)
    check(f"extract_url: {txt[:40]}", got == expect, f"got={got}")

# 2. resolve_aweme_id：长链直接提取
check("resolve long video url", D.resolve_aweme_id("https://www.douyin.com/video/7412345678901234567", None) == "7412345678901234567")
check("resolve iesdouyin url", D.resolve_aweme_id("https://www.iesdouyin.com/share/video/9998887776665554443/", None) == "9998887776665554443")

# 3. _extract_json：_ROUTER_DATA 形态
html1 = '<html><script>window._ROUTER_DATA = {"loaderData": {"x": 1}};</script></html>'
d1 = D._extract_json(html1)
check("extract _ROUTER_DATA", isinstance(d1, dict) and d1.get("loaderData",{}).get("x")==1, f"got={d1}")

# 4. _extract_json：RENDER_DATA URL编码形态
import urllib.parse
payload = json.dumps({"a": {"b": 2}})
html2 = f'<script id="RENDER_DATA" type="application/json">{urllib.parse.quote(payload)}</script>'
d2 = D._extract_json(html2)
check("extract RENDER_DATA", isinstance(d2, dict) and d2.get("a",{}).get("b")==2, f"got={d2}")

# 5. parse_aweme：视频
video_data = {"loaderData": {"video_(id)": {"videoInfoRes": {"item_list": [{
    "desc": "测试视频标题",
    "author": {"nickname": "测试作者"},
    "video": {"play_addr": {"url_list": ["https://aweme.snssdk.com/aweme/v1/playwm/?video_id=ABC", "https://x2"]}},
    "music": {"play_url": {"url_list": ["https://m"]}}
}]}}}}
v = D.parse_aweme(video_data)
check("parse video type", v["type"]=="video", f"got={v['type']}")
check("parse video title", v["title"]=="测试视频标题")
check("parse video author", v["author"]=="测试作者")
check("parse video url", v["video_url"] and v["video_url"].startswith("https://aweme.snssdk.com/aweme/v1/playwm"), f"got={v['video_url']}")
check("no_watermark replace", D.no_watermark("https://aweme.snssdk.com/aweme/v1/playwm/?a=1") == "https://aweme.snssdk.com/aweme/v1/play/?a=1")

# 6. parse_aweme：图文
img_data = {"loaderData": {"x": {"item_list": [{
    "desc": "测试图文", "author": {"nickname": "图作者"},
    "images": [{"url_list": ["https://p1.douyinpic.com/aa.jpeg?high", "https://p1.douyinpic.com/aa.jpeg"]},
               {"url_list": ["https://p2.douyinpic.com/bb.jpeg"]}]
}]}}}
im = D.parse_aweme(img_data)
check("parse images type", im["type"]=="images", f"got={im['type']}")
check("parse images count", len(im["images"])==2, f"got={len(im['images'])}")

# 7. sanitize_name（8 个非法字符全部替换为 _）
_bad = 'a/b:c*d?"<>|'
check("sanitize illegal chars", D.sanitize_name(_bad) == "a_b_c_d_____", f"got={D.sanitize_name(_bad)}")

# 8. CLI --help 可运行
import subprocess
r = subprocess.run([sys.executable, "douyin_dl.py", "--help"], capture_output=True, text=True)
check("cli --help exit0", r.returncode == 0, r.stderr[:200])

print(f"\n{'ALL PASS' if fails==0 else str(fails)+' FAILED'}")
sys.exit(1 if fails else 0)
