"""Anonymous public descriptions only; no player extraction, sessions or video claims."""
import hashlib
import http.client
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .core import ModelError

LIMIT = 4_000_000


def canonical(url):
    try:
        p = urlsplit(url)
        if p.scheme != 'https' or p.username or p.password or p.port not in (None, 443):
            raise ValueError()
        if p.hostname == 'youtu.be':
            identifier = p.path.removeprefix('/')
        elif p.hostname in ('youtube.com', 'www.youtube.com', 'm.youtube.com'):
            if p.path == '/watch':
                values = parse_qs(p.query).get('v', [])
                identifier = values[0] if len(values) == 1 else ''
            else:
                match = re.fullmatch(r'/(?:shorts|embed)/([A-Za-z0-9_-]{11})/?', p.path)
                identifier = match.group(1) if match else ''
        else:
            raise ValueError()
        if not re.fullmatch(r'[A-Za-z0-9_-]{11}', identifier):raise ValueError()
    except (ValueError, TypeError):
        raise ValueError('仅接受 YouTube 公开视频的 watch、shorts 或 youtu.be HTTPS 地址。') from None
    return 'https://www.youtube.com/watch?v=' + identifier


def description(body, url):
    """Discard player URLs/captions and retain bounded, attributed public text."""
    match = re.search(r'(?:var\s+)?ytInitialPlayerResponse\s*=\s*', body)
    try:
        if not match:raise ValueError()
        value, _ = json.JSONDecoder().raw_decode(body[match.end():])
        if value.get('playabilityStatus', {}).get('status') != 'OK':
            raise ModelError('YouTube 要求登录、验证或限制访问；已停止，不绕过验证。')
        details = value['videoDetails']
        if details['videoId'] != url.rsplit('=', 1)[-1]:raise ValueError()
        title, text, author = (details.get(key, '') for key in ('title', 'shortDescription', 'author'))
        if not all(isinstance(item, str) for item in (title, text, author)) or not title.strip():raise ValueError()
    except (ValueError, KeyError, TypeError, AttributeError):
        raise ModelError('YouTube 未提供可验证的公开简介，未读取视频内容。') from None
    return {'url': url, 'title': title[:300], 'text': ('作者：' + author[:300] + '\n公开简介：' + text[:6000]),
            'method': 'public_metadata_only', 'retrieved_at': datetime.now(timezone.utc).isoformat(),
            'sha256': hashlib.sha256(body.encode()).hexdigest(), 'complete_video_view': False}


def _read(url):
    from .research import target, PinnedHTTPS
    url = canonical(url)
    parsed, address = target(url)
    connection = PinnedHTTPS(parsed.hostname, address)
    response = None
    try:
        connection.request('GET', parsed.path + '?' + parsed.query,
                           headers={'User-Agent': 'Dafeiyu public video reader', 'Accept-Encoding': 'identity'})
        response = connection.getresponse()
        # Do not follow redirects into consent/login pages or fetch player/media endpoints.
        if response.status != 200 or 'text/html' not in response.getheader('Content-Type', ''):
            raise ModelError('YouTube 公开页面不可读；未进入登录或验证流程。')
        if response.getheader('Content-Encoding', 'identity') not in ('identity', ''):raise ModelError('YouTube 页面压缩格式不支持。')
        body = response.read(LIMIT + 1)
        if len(body) > LIMIT:raise ModelError('YouTube 页面超过 4MB 上限。')
        return description(body.decode('utf-8', errors='replace'), url)
    except (OSError, http.client.HTTPException):
        raise ModelError('YouTube 公开页面连接失败。') from None
    finally:
        if response is not None:response.close()
        connection.close()


def page_source(url, cancelled=lambda: False):
    url = canonical(url)
    if cancelled():raise ModelError('YouTube 阅读已取消。')
    try:
        child = subprocess.run([sys.executable, '-m', 'dafeiyu.youtube'], input=json.dumps({'url': url}),
                               cwd=str(Path(__file__).resolve().parent.parent), capture_output=True, text=True, timeout=15)
        result = json.loads(child.stdout)
        if child.returncode or not isinstance(result, dict) or result.get('error'):raise ValueError()
        if cancelled():raise ModelError('YouTube 阅读已取消。')
        return result
    except (subprocess.TimeoutExpired, OSError, ValueError):
        raise ModelError('YouTube 公开简介暂不可读或要求验证；未获取字幕、声音或画面。') from None


if __name__ == '__main__':
    try:print(json.dumps(_read(json.loads(sys.stdin.read(4096))['url'])))
    except Exception:
        print(json.dumps({'error': 'public_page_unavailable'}))
        sys.exit(1)
