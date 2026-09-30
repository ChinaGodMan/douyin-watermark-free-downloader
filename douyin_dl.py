#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Douyin Watermark-free Downloader · 抖音无水印视频/图文下载器
=============================================================
仅依赖 requests 的轻量下载工具：解析分享链接 / 分享文本，下载无水印视频与原图。

原理（无需登录、无需签名）：
  1. 解析分享短链 v.douyin.com/xxxx  →  跟随重定向拿到真实链接与 aweme_id
  2. 用移动端 UA 请求 https://www.iesdouyin.com/share/video/<id>
  3. 从页面内嵌的 _ROUTER_DATA JSON 中提取 play_addr.url_list[0]
  4. 把地址里的 playwm 替换为 play 得到无水印版本，再跟随重定向下载

⚠️ 本工具仅用于学习研究与个人合理使用，请遵守法律法规及平台条款，尊重创作者版权。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:  # pragma: no cover
    sys.exit("缺少依赖 requests，请先执行:  pip install requests")

__version__ = "1.0.0"

UA_MOBILE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
)
UA_DESKTOP = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)

# 分享链接 / 各形态链接的正则
URL_RE = re.compile(
    r"https?://(?:v\.douyin\.com/\S+|(?:www\.)?iesdouyin\.com/share/(?:video|slides|note)/\d+"
    r"|(?:www\.|m\.)?douyin\.com/(?:video|note|slides)/\d+|www\.douyin\.com/\d+)"
)
ID_RE = re.compile(r"/(?:video|slides|note)/(\d+)")
SHARE_HTTP_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_HTML_ESCAPE = {"&quot;": '"', "&amp;": "&", "&lt;": "<", "&gt;": ">", "&#39;": "'", "&nbsp;": " "}


def sanitize_name(name: str, max_len: int = 80) -> str:
    """去掉 Windows/各平台非法字符，控制长度。"""
    name = re.sub(r'[\\/:*?"<>|\r\n\t#]', "_", name).strip().strip(".")
    name = re.sub(r"\s+", " ", name)
    if not name:
        name = "douyin"
    return name[:max_len]


def extract_url(text: str) -> Optional[str]:
    """从任意文本中提取抖音链接。"""
    m = URL_RE.search(text)
    if m:
        return m.group(0).rstrip("/")
    # 兜底：取文本中第一个 http(s) 链接
    m = SHARE_HTTP_RE.search(text)
    return m.group(0).rstrip(")").rstrip("，。；）") if m else None


def resolve_aweme_id(url: str, session: requests.Session) -> Optional[str]:
    """解析链接 -> aweme_id。支持短链/长链/图文。"""
    url = url.rstrip("/")
    m = ID_RE.search(url)
    if m:
        return m.group(1)
    # 短链：跟随重定向
    try:
        r = session.get(url, headers={"User-Agent": UA_MOBILE},
                        allow_redirects=True, timeout=15)
        final = r.url or url
        m = ID_RE.search(final)
        if m:
            return m.group(1)
    except requests.RequestException as e:
        print(f"  [!] 短链解析失败: {e}")
    return None


def _extract_json(text: str):
    """从分享页 HTML 中提取内嵌 JSON 数据。"""
    # 形态1: window._ROUTER_DATA = {...};
    m = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*?\});?\s*</script>", text, re.S)
    if m:
        return json.loads(m.group(1))
    # 形态2: <script id="RENDER_DATA" type="application/json">URL编码JSON</script>
    m = re.search(r'<script\s+id="RENDER_DATA"\s+type="application/json"[^>]*>(.*?)</script>', text, re.S)
    if m:
        import urllib.parse
        return json.loads(urllib.parse.unquote(m.group(1)))
    # 形态3: window._ROUTER_DATA = {...}; 没有紧随的 </script>（宽松匹配）
    m = re.search(r"window\._ROUTER_DATA\s*=\s*(\{.*\})\s*;\s*$", text, re.S)
    if m:
        return json.loads(m.group(1))
    return None


def _walk_json(obj, target: str):
    """在嵌套 dict 中按 key 名搜索（返回第一个命中）。"""
    if isinstance(obj, dict):
        if target in obj:
            return obj[target]
        for v in obj.values():
            r = _walk_json(v, target)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _walk_json(v, target)
            if r is not None:
                return r
    return None


def _find_aweme(data):
    """定位真正的 aweme 数据对象（_ROUTER_DATA 深层嵌套）。"""
    if not isinstance(data, dict):
        return None
    # 1) 显式 aweme 字段
    r = _walk_json(data, "aweme")
    if isinstance(r, dict):
        return r
    # 2) item_list[0]（分享页主要形态）
    r = _walk_json(data, "item_list")
    if isinstance(r, list) and r and isinstance(r[0], dict):
        return r[0]
    # 3) 数据本身就带作品字段
    if any(k in data for k in ("desc", "video", "images", "aweme_id")):
        return data
    # 4) 递归找第一个含作品字段的 dict
    def rec(o):
        if isinstance(o, dict):
            if any(k in o for k in ("desc", "video", "images", "aweme_id")):
                return o
            for v in o.values():
                r = rec(v)
                if r is not None:
                    return r
        elif isinstance(o, list):
            for v in o:
                r = rec(v)
                if r is not None:
                    return r
        return None
    return rec(data)


def parse_aweme(data: dict) -> dict:
    """从 _ROUTER_DATA 提取视频/图文信息。"""
    info = {"type": "unknown", "title": "", "author": "", "video_url": None,
            "images": [], "music": None}
    detail = _find_aweme(data)
    if not isinstance(detail, dict):
        return info
    # 标题
    info["title"] = (detail.get("desc") or detail.get("share_info", {}).get("share_title") or "").strip()
    # 作者
    author = detail.get("author") or {}
    if isinstance(author, dict):
        info["author"] = (author.get("nickname") or author.get("unique_id") or "").strip()
    # 视频播放地址
    video = detail.get("video") or {}
    play = video.get("play_addr") or video.get("playAddr") if isinstance(video, dict) else None
    if isinstance(play, dict):
        url_list = play.get("url_list") or play.get("urlList") or []
        if url_list:
            info["video_url"] = url_list[0]
            info["type"] = "video"
    # 图集
    images = detail.get("images")
    if isinstance(images, list):
        urls = []
        for im in images:
            if not isinstance(im, dict):
                continue
            ul = im.get("url_list") or im.get("urlList") or []
            # 图集里的 url 一般是 [高清, 带水印] 两个，取第一个
            if ul:
                urls.append(ul[0])
        if urls:
            info["images"] = urls
            info["type"] = "images"
    # 音乐（可选信息）
    music = detail.get("music", {})
    if isinstance(music, dict):
        mu = music.get("play_url", {}).get("url_list") or []
        info["music"] = mu[0] if mu else None
    return info


def no_watermark(url: str) -> str:
    """playwm -> play，得到无水印地址。"""
    return url.replace("/playwm/", "/play/").replace("playwm", "play")


def format_size(size):
    """格式化文件大小"""
    if size < 1024:
        return f"{size}B"
    elif size < 1024 * 1024:
        return f"{size / 1024:.1f}KB"
    elif size < 1024 * 1024 * 1024:
        return f"{size / 1024 / 1024:.1f}MB"
    else:
        return f"{size / 1024 / 1024 / 1024:.1f}GB"

def download(url: str, dest: Path, session: requests.Session, headers: dict, label: str = ""):
    """下载到 dest，带进度条与重试。"""
    for attempt in range(3):
        try:
            with session.get(url, headers=headers, stream=True, timeout=(10, 60)) as r:
                r.raise_for_status()
                total = int(r.headers.get("Content-Length") or 0)
                done = 0
                with open(dest, "wb") as f:
                    for chunk in r.iter_content(chunk_size=1 << 16):
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)
                        if total:
                            pct = done * 100 // total
                            downloaded_str = format_size(done)
                            total_str = format_size(total)
                            sys.stdout.write(f"\r  {label} {pct}% ({downloaded_str}/{total_str})")
                            sys.stdout.flush()
                sys.stdout.write("\033[2K\r")
                if os.path.getsize(dest) == 0:
                    raise ValueError("空文件（可能 UA 不对或被限流）")
                return True
        except (requests.RequestException, ValueError) as e:
            print(f"  [!] 第 {attempt + 1} 次下载失败: {e}")
            time.sleep(2 * (attempt + 1))
    return False


def download_one(link_or_text: str, out_dir: Path, session: requests.Session) -> Optional[dict]:
    """处理单个分享链接，返回解析信息。"""
    url = extract_url(link_or_text)
    if not url:
        print(f"  [!] 未在输入中找到抖音链接: {link_or_text[:60]}")
        return None
    print(f"  [*] 解析链接: {url}")
    aweme_id = resolve_aweme_id(url, session)
    if not aweme_id:
        print("  [!] 无法解析 aweme_id，链接可能已失效或被删")
        return None

    page = f"https://www.iesdouyin.com/share/video/{aweme_id}/"
    for attempt in range(3):
        try:
            r = session.get(page, headers={"User-Agent": UA_MOBILE}, timeout=20)
            if r.status_code != 200:
                raise requests.RequestException(f"HTTP {r.status_code}")
            data = _extract_json(r.text)
            if not data:
                raise ValueError("页面未包含数据，可能被 WAF 拦截")
            break
        except (requests.RequestException, ValueError, json.JSONDecodeError) as e:
            if attempt == 2:
                print(f"  [!] 解析失败: {e}（可稍后重试）")
                return None
            time.sleep(2 * (attempt + 1))

    info = parse_aweme(data)
    if info["type"] == "video" and info["video_url"]:
        print(f"  [*] 视频: {info['title'][:40] or '(无标题)'} by {info['author'] or '未知'}")
        video_url = no_watermark(info["video_url"])
        fname = sanitize_name(f"{info['author']}_{info['title']}") or aweme_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = out_dir / f"{fname}_{timestamp}.mp4"
        if download(video_url, dest, session, {"User-Agent": UA_MOBILE}, label="视频"):
            print(f"  [✓] 已保存: {dest}")
        info["file"] = str(dest)
    elif info["type"] == "images" and info["images"]:
        print(f"  [*] 图文作品: {len(info['images'])} 张 by {info['author'] or '未知'}")
        base = sanitize_name(f"{info['author']}_{info['title']}") or aweme_id
        sub = out_dir
        if len(info["images"]) > 10 :
          sub = out_dir / base
          sub.mkdir(parents=True, exist_ok=True)
        ok = 0
        for i, img_url in enumerate(info["images"], 1):
            ext = Path(img_url.split("?")[0]).suffix or ".jpg"
            if len(ext) > 5:
                ext = ".jpg"
            dest = sub / f"{base}{i:02d}{ext}"
            if download(img_url, dest, session, {"User-Agent": UA_MOBILE}, label=f"图片{i}"):
                ok += 1
        bgm_sub =out_dir / "bgm_musics"
        img_music = info["video_url"].split('video_id=')[1].split('&')[0]
        bgm_sub.mkdir(parents=True, exist_ok=True)
        print(f"  [✓] 已保存 {ok}/{len(info['images'])} 张到: {sub}")
        info["dir"] = str(sub)
        if img_music:
          alert = input("是否需要下载图集背景音乐？(Y/y 下载): ")
          if alert.lower() == 'y' :
            download(img_music, f"{bgm_sub}/{base}.mp3", session, {"User-Agent": UA_MOBILE}, label=f"下载背景音乐")
    else:
        print("  [!] 未能识别作品类型（视频或图文）")
        return None
    return info


def main():
    ap = argparse.ArgumentParser(description="抖音无水印视频/图文下载器 (仅供学习研究使用)")
    ap.add_argument("input", help="分享链接 / 分享文本 / 含链接的txt文件")
    ap.add_argument("-o", "--output", default="/storage/emulated/0/Pictures/douyin", help="保存目录 (默认 downloads)")
    ap.add_argument("-b", "--batch", action="store_true", help="输入是 txt 文件，每行一个链接")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON 摘要")
    args = ap.parse_args()

    out_dir = Path(args.output)
    out_dir.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({"Accept-Language": "zh-CN,zh;q=0.9"})
    # Windows 下清理可能干扰的代理环境变量
    for k in ("ALL_PROXY", "all_proxy"):
        if os.environ.get(k):
            print(f"  [i] 提示：检测到代理环境变量 {k}，如解析失败请尝试清除后重试")

    if args.batch:
        links = [l.strip() for l in Path(args.input).read_text(encoding="utf-8").splitlines() if l.strip()]
        print(f"[*] 批量模式: {len(links)} 条链接")
        results = []
        for i, link in enumerate(links, 1):
            print(f"[{i}/{len(links)}]")
            r = download_one(link, out_dir, session)
            if r:
                results.append(r)
            time.sleep(1.5)  # 限速避免被 WAF
        if args.json:
            print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        r = download_one(args.input, out_dir, session)
        if args.json and r:
            print(json.dumps(r, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(130)
