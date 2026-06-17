"""BD 发行管理(ADR-0004):收藏总览 / 购买状态 / 绑番剧 / 扫描 / 打开目录。

去特典分支:特典不在网页展示。正片(纯集号)替换 web 正片走剧集网格;特典(带描述标签的
视频 / 音频 / 图集)留在发行目录里,经「打开目录」(mikanarr://reveal)用资源管理器 / 本机应用浏览。
自购原盘(raw_disc)仍可逐碟 PowerDVD 蓝光播放。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Bangumi, BdRelease

router = APIRouter(prefix="/api/bd", tags=["bd"])


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


def _open_url(r: BdRelease) -> str | None:
    """该发行目录的「打开目录」URL(mikanarr://reveal):在资源管理器里定位发行 / 原盘文件夹,
    特典就在其中,用本机应用浏览。未配置宿主机根 → None(前端按钮置灰提示)。"""
    from app.services import launch
    if r.source_kind == "raw_disc" and (r.root_path or "").startswith("@owned/"):
        return launch.launch_url("reveal", launch.owned_host_path(r.root_path[len("@owned/"):]))
    return launch.media_launch("reveal", r.root_path)


def bd_release_out(r: BdRelease) -> dict:
    """一套 BD 发行 → 展示结构(无特典编目):绑定 / 类型 / 购买 / 大小 + 打开目录 URL。

    自购原盘逐碟 PowerDVD 列表按发行懒加载(GET /releases/{id},含 FS 枚举),不在此返。"""
    return {
        "id": r.id, "title": r.title, "source_kind": r.source_kind, "owned": r.owned,
        "disc_count": r.disc_count, "total_size": r.total_size, "bangumi_id": r.bangumi_id,
        "has_discs": r.source_kind == "raw_disc", "open_url": _open_url(r),
    }


@router.get("/releases")
def list_releases(db: Session = Depends(get_db)):
    """发行列表:发行实体 + 打开目录 URL(特典不编目、不在网页展示)。"""
    rows = db.execute(select(BdRelease)).scalars().all()
    out = []
    for r in rows:
        d = bd_release_out(r)
        b = db.get(Bangumi, r.bangumi_id) if r.bangumi_id else None
        d["bangumi_title"] = b.title if b else None
        d["poster"] = f"/data/{b.poster_path}" if b and b.poster_path else None
        out.append(d)
    out.sort(key=lambda x: (x["bangumi_title"] is None, x["bangumi_title"] or x["title"]))
    return out


@router.get("/releases/{release_id}")
def release_detail(release_id: int, db: Session = Depends(get_db)):
    """自购原盘逐碟 PowerDVD 列表(FS 枚举);前端展开某套原盘发行时才拉。"""
    r = db.get(BdRelease, release_id)
    if not r:
        raise HTTPException(404)
    return {"id": r.id, "discs": _owned_discs(r)}


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
