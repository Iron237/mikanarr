"""BD 发行管理(ADR-0004):收藏总览 / 购买状态 / 绑番剧 / 扫描 / 特典文件串流。"""
import re
from pathlib import Path, PurePosixPath

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Bangumi, BdExtra, BdRelease

router = APIRouter(prefix="/api/bd", tags=["bd"])

# 类别展示名(前端分组标题)
CATEGORY_LABELS = {
    "sp_anime": "特别动画", "short_drama": "短剧", "credits": "映像特典(NC)",
    "menu": "菜单", "pv": "PV / 预告", "music_video": "音乐视频", "audio": "音频",
    "gallery": "图集", "scans": "扫描 / 书子", "other": "其他",
}
_CATEGORY_ORDER = ["sp_anime", "short_drama", "credits", "pv", "music_video", "menu",
                   "audio", "gallery", "scans", "other"]


def _owned_discs(r: BdRelease) -> list[dict]:
    """自购原盘:枚举含 BDMV 的碟子目录 → PowerDVD 蓝光播放 / 资源管理器定位目标(按碟)。"""
    from pathlib import Path

    from app.services import launch
    if r.source_kind != "raw_disc" or not (r.root_path or "").startswith("@owned/"):
        return []
    folder = r.root_path[len("@owned/"):]
    mount = Path(settings.bd_owned_mount) / folder
    out: list[dict] = []
    try:    # NAS/CIFS 挂载抖动会抛 OSError;序列化时不可拖垮 /api/bd/releases 与详情页
        if not mount.is_dir():
            return []
        for d in sorted([x for x in mount.iterdir() if x.is_dir()], key=lambda x: x.name):
            if (d / "BDMV").is_dir():
                host = launch.owned_host_path(f"{folder}/{d.name}")
                out.append({"name": d.name, "bd_url": launch.launch_url("bd", host),
                            "reveal_url": launch.launch_url("reveal", host)})
        if not out and (mount / "BDMV").is_dir():   # 单碟直接在发行根
            host = launch.owned_host_path(folder)
            out.append({"name": r.title, "bd_url": launch.launch_url("bd", host),
                        "reveal_url": launch.launch_url("reveal", host)})
    except OSError:
        return []
    return out


_COVER_RE = re.compile(r"cover|folder|front|jacket|booklet|封面", re.I)


def _natkey(s: str) -> list:
    """自然排序键:数字段按数值比(2 在 10 前),其余按小写。"""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s or "")]


def _folder_of(rel: str) -> str:
    return str(PurePosixPath(rel).parent)


def _extra_url(extra_id: int) -> str:
    return f"/api/bd/extra/{extra_id}/raw"


def bd_release_summary(r: BdRelease) -> dict:
    """一套 BD 发行 → 轻量概要(列表/详情用,不含特典数组,按发行懒加载):各类计数 + 绑定 + 类型。"""
    n_img = n_aud = n_vid = 0
    img_folders: set[str] = set()
    aud_folders: set[str] = set()
    for e in r.extras:
        if e.media_kind == "image":
            n_img += 1
            img_folders.add(_folder_of(e.relative_path))
        elif e.media_kind == "audio":
            n_aud += 1
            aud_folders.add(_folder_of(e.relative_path))
        elif e.media_kind == "video":
            n_vid += 1
    return {
        "id": r.id, "title": r.title, "source_kind": r.source_kind, "owned": r.owned,
        "disc_count": r.disc_count, "total_size": r.total_size,
        "bangumi_id": r.bangumi_id, "extra_count": len(r.extras),
        "image_book_count": len(img_folders), "image_count": n_img,
        "audio_album_count": len(aud_folders), "audio_count": n_aud,
        "video_count": n_vid, "has_discs": r.source_kind == "raw_disc",
    }


def bd_release_detail(r: BdRelease) -> dict:
    """一套 BD 发行 → 完整展示结构(grill 第七轮三件套,按发行懒加载时才返):
    - image_books:图片按所在文件夹折叠成「册」(一个文件夹一本,前端漫画翻页阅读器)。
    - audio_albums:音频按文件夹折叠成「专辑」,曲目按 track_no/文件名排序(CD 播放器歌单)。
    - videos:视频特典扁平列表 + 完整规格(前端复用正片 FileTags 展示)。
    - discs:自购原盘逐碟 PowerDVD 启动。"""
    from app.services import launch

    img_by_folder: dict[str, list] = {}
    aud_by_folder: dict[str, list] = {}
    videos: list[dict] = []
    for e in r.extras:
        if e.media_kind == "image":
            img_by_folder.setdefault(_folder_of(e.relative_path), []).append(e)
        elif e.media_kind == "audio":
            aud_by_folder.setdefault(_folder_of(e.relative_path), []).append(e)
        elif e.media_kind == "video":
            videos.append({
                "id": e.id, "path": e.relative_path, "name": e.name,
                "category": e.category, "label": CATEGORY_LABELS.get(e.category, e.category),
                "size": e.size, "resolution": e.resolution, "subgroup": None, "source": "BD",
                "codec": e.video_codec, "color_depth": e.color_depth, "hdr": e.hdr,
                "bitrate": e.bitrate, "duration": e.duration,
                "audio_tracks": e.audio_tracks or [], "subtitle_tracks": e.subtitle_tracks or [],
                "url": _extra_url(e.id),
                "play_url": launch.media_launch("play", e.relative_path),
                "reveal_url": launch.media_launch("reveal", e.relative_path),
            })

    # 每个文件夹的封面图(供同文件夹音频专辑复用):优先名字含 cover/folder/front,否则首图
    folder_cover: dict[str, str] = {}
    for folder, imgs in img_by_folder.items():
        imgs.sort(key=lambda e: _natkey(e.name))
        cov = next((e for e in imgs if _COVER_RE.search(e.name)), imgs[0])
        folder_cover[folder] = _extra_url(cov.id)

    image_books = []
    for folder, imgs in img_by_folder.items():
        pages = [{"id": e.id, "name": e.name, "url": _extra_url(e.id)} for e in imgs]
        image_books.append({"folder": PurePosixPath(folder).name or r.title,
                            "count": len(pages), "cover": pages[0]["url"], "pages": pages})
    image_books.sort(key=lambda b: _natkey(b["folder"]))

    audio_albums = []
    for folder, auds in aud_by_folder.items():
        auds.sort(key=lambda e: (e.track_no if e.track_no is not None else 9999, _natkey(e.name)))
        tracks = [{"id": e.id, "url": _extra_url(e.id), "track_no": e.track_no,
                   "title": e.track_title or PurePosixPath(e.name).stem, "name": e.name,
                   "duration": e.duration, "size": e.size} for e in auds]
        audio_albums.append({"folder": PurePosixPath(folder).name or r.title,
                            "count": len(tracks), "cover": folder_cover.get(folder),
                            "tracks": tracks})
    audio_albums.sort(key=lambda a: _natkey(a["folder"]))

    _cat_idx = {c: i for i, c in enumerate(_CATEGORY_ORDER)}
    videos.sort(key=lambda v: (_cat_idx.get(v["category"], 99), _natkey(v["name"])))

    return {
        "id": r.id, "title": r.title, "source_kind": r.source_kind, "owned": r.owned,
        "disc_count": r.disc_count, "total_size": r.total_size,
        "bangumi_id": r.bangumi_id, "extra_count": len(r.extras),
        "image_books": image_books, "audio_albums": audio_albums, "videos": videos,
        "discs": _owned_discs(r),
    }


@router.get("/releases")
def list_releases(db: Session = Depends(get_db)):
    """发行列表:只返概要(计数),特典按发行懒加载(GET /releases/{id})。"""
    rows = db.execute(select(BdRelease)).scalars().all()
    out = []
    for r in rows:
        d = bd_release_summary(r)
        b = db.get(Bangumi, r.bangumi_id) if r.bangumi_id else None
        d["bangumi_title"] = b.title if b else None
        d["poster"] = f"/data/{b.poster_path}" if b and b.poster_path else None
        out.append(d)
    out.sort(key=lambda x: (x["bangumi_title"] is None, x["bangumi_title"] or x["title"]))
    return out


@router.get("/releases/{release_id}")
def release_detail(release_id: int, db: Session = Depends(get_db)):
    """单套发行的完整特典(image_books/audio_albums/videos/discs);前端展开某套时才拉。"""
    r = db.get(BdRelease, release_id)
    if not r:
        raise HTTPException(404)
    return bd_release_detail(r)


@router.post("/scan")
def scan():
    from app.services import bd_scan
    if not bd_scan.start():
        raise HTTPException(409, "已有 BD 扫描在进行中")
    return {"started": True}


@router.get("/scan/status")
def scan_status():
    from app.services import bd_scan
    return bd_scan.state


@router.patch("/releases/{release_id}")
def update_release(release_id: int, payload: dict, db: Session = Depends(get_db)):
    """改购买状态 / 绑定番剧。owned + 已绑番剧 时,顺带把番剧设为 bd_owned(排除自动下载)。"""
    r = db.get(BdRelease, release_id)
    if not r:
        raise HTTPException(404)
    old_bid = r.bangumi_id
    if "bangumi_id" in payload:
        bid = payload["bangumi_id"]
        if bid is not None and not db.get(Bangumi, int(bid)):
            raise HTTPException(400, "番剧不存在")
        r.bangumi_id = int(bid) if bid is not None else None
    if "owned" in payload:
        r.owned = bool(payload["owned"])
    db.flush()
    # 重算受影响番剧的 bd_owned(新绑 + 旧绑/解绑都要):有 owned 发行 → 排除自动下载,否则解除
    for bid in {old_bid, r.bangumi_id} - {None}:
        b = db.get(Bangumi, bid)
        if b:
            b.bd_owned = any(x.owned for x in db.execute(select(BdRelease).where(
                BdRelease.bangumi_id == bid)).scalars())
    db.commit()
    return {"ok": True, "owned": r.owned, "bangumi_id": r.bangumi_id}


@router.delete("/releases/{release_id}", status_code=204)
def delete_release(release_id: int, db: Session = Depends(get_db)):
    """从库里移除该 BD 发行记录(不动磁盘文件)。"""
    r = db.get(BdRelease, release_id)
    if not r:
        raise HTTPException(404)
    db.delete(r)
    db.commit()


@router.get("/extra/{extra_id}/raw")
def extra_raw(extra_id: int, db: Session = Depends(get_db)):
    """串流/下载一个特典文件(图片预览、音频播放、视频)。文件不动(ADR-0001)。"""
    e = db.get(BdExtra, extra_id)
    if not e:
        raise HTTPException(404)
    base = Path(settings.download_root_local).resolve()
    try:
        fp = (base / e.relative_path).resolve()
    except (OSError, ValueError):
        raise HTTPException(404) from None
    if base not in fp.parents or not fp.is_file():   # 防目录穿越 + 存在性
        raise HTTPException(404)
    return FileResponse(str(fp), filename=e.name)
