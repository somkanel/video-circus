# 浏览器发现（动态网页才读取）

平台提取器和静态 HTML 都失败后，由 Agent 使用宿主已有的浏览器工具。Codex 桌面使用 cua_repl；不要启动另一套浏览器绕过宿主要求。

1. 打开用户给的页面，检查可见标题和播放器。确认正文视频与广告、推荐视频不同。
2. 查看主页面和 iframe；frame 内播放器可能跨域。主文档 `querySelector('video')` 不会进入 iframe，需用宿主 frame 工具逐层查看。
3. 优先取得平台 embed URL 或 video.currentSrc/source 的真实 HTTP(S) 地址。读属性是发现，不等于证明视频可播放。
4. 需要播放才能暴露资源时，按页面可见播放控件操作并检查结果。若 src 为 `blob:`，不要交给 FFmpeg；使用宿主 pageAssets 或明确可用的网络观察工具找 MP4、m3u8、mpd。没有该能力时，说明具体限制，不假造网络嗅探能力。
5. 如果浏览器或当前宿主可用的专用只读工具允许下载媒体，取得本地文件再用 fetch.py 验证；否则将真实候选保存为私有 JSON。多个候选先通过可见播放器和标题辨认，仍不明确再请用户选择。用专用工具时按其接口解析页面身份，不猜测私有接口或资源ID。

专用工具的转写/纪要导出和媒体下载要分别判断：页面未生成转写、转写导出失败时继续已有的媒体下载路线，不能把空稿当成功，也不要自动触发远端转写。签名地址失效或会话不足时只沿有依据的已有访问路线恢复；没有可用下载能力则明确缺失能力。

## 已下载文件的来源记录

从网页经宿主下载到本地时，用权限0600的来源JSON记录本次实际观察。字段恰为以下六项；不接受Cookie、请求头或签名媒体URL。media_sha256是所下载文件的真实SHA256，不是页面URL的哈希。

```json
{
  "page_url": "https://example.com/lesson",
  "title": "页面中确认的正文课程",
  "duration": 120.5,
  "acquisition_method": "host_download",
  "observed_by": "宿主浏览器与只读下载工具",
  "media_sha256": "填写真实文件的64位SHA256"
}
```

`acquisition_method` 可为 browser_download、host_download、external_download。时长为播放器实际观察的正数秒，不能填文件自己的探测时长冒充独立来源。没有观察到标题/时长时省略整个origin-file并明确缺失，不猜测值。

```bash
python3 scripts/fetch.py '/path/downloaded.mp4' \
  --origin-file '/path/origin.private.json' --output '/path/verified-media'
```

脚本校验文件哈希，保留脱敏原网页和host_observation标记，并将来源时长用于现有完整解码/时长匹配验证；不修改已封存旧清单。来源声明与脚本的媒体验证是不同证据：哈希绑定不能证明人或Agent观察的标题正确。页面URL输出去掉userinfo、query、fragment，路径含敏感令牌时仍只保留私有任务包，不公开记录。

候选文件格式（权限 0600，不提交到公开仓库）：

```json
[
  {
    "url": "https://media.example/video.m3u8",
    "kind": "media",
    "page": "https://example.com/lesson",
    "label": "正文课程"
  }
]
```

`kind` 为 `media` 表示真实媒体或清单，`embed` 表示交给 yt-dlp 的平台页面。只放本次观察到的地址，不猜 URL。浏览器脚本抓到的其他网站 iframe 不自动等同于视频。

```bash
python3 scripts/fetch.py '<原网页>' --candidates-file '<私有 JSON>' --output '<任务目录>'
```

多候选用 `--candidate 0`（零起始）。必要请求头独立保存在私有 JSON，通过 `--headers-file` 传入；只包含此媒体所需的头，不导出整份浏览器 Cookie。签名地址过期时重新在浏览器获取。浏览器登录态不自动同步到独立下载器。

如果媒体地址可下载但页面存在试看/分段/多集，记录实际范围，并检查所有必要片段；成功下载一个 MP4 不证明整个课程已获取。当前脚本不会录制无界直播，也不会解密 DRM。
