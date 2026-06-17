"""BD 三件套展示结构 + 番剧生命周期(完结转补全 / 全 BD 收尾)单元测试(内存 SQLite)。"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (AiringStatus, Bangumi, BdExtra, BdRelease, Episode, EpisodeType,
                        Subscription, Torrent, TorrentEpisode, TorrentStatus, VideoFile)
from app.services import lifecycle


@pytest.fixture()
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    s = sessionmaker(bind=engine)()
    yield s
    s.close()


# ---- BD 发行展示结构(bd_release_out)----------------------------------------
def _bdrip(db):
    b = Bangumi(mikan_bangumi_id=1, title="孤独摇滚")
    db.add(b)
    db.flush()
    r = BdRelease(bangumi_id=b.id, title="[VCB] Bocchi", source_kind="bdrip",
                  root_path="BD/[VCB] Bocchi", owned=False)
    db.add(r)
    db.flush()
    return b, r


def _extra(db, r, **kw):
    db.add(BdExtra(bd_release_id=r.id, **kw))
    db.flush()


def test_image_books_grouped_natsorted_with_cover(db):
    _, r = _bdrip(db)
    for name in ("002.jpg", "010.jpg", "001.jpg", "cover.jpg"):
        _extra(db, r, category="scans", media_kind="image", name=name,
               relative_path=f"BD/[VCB] Bocchi/Scans/Vol.1/{name}")
    _extra(db, r, category="scans", media_kind="image", name="001.jpg",
           relative_path="BD/[VCB] Bocchi/Scans/Vol.2/001.jpg")
    from app.api.bd import bd_release_detail as bd_release_out
    books = bd_release_out(r)["image_books"]
    assert len(books) == 2
    v1 = next(bk for bk in books if bk["folder"] == "Vol.1")
    assert v1["count"] == 4
    # 自然排序:001 < 002 < 010 < cover(字母排数字后)
    assert [p["name"] for p in v1["pages"]] == ["001.jpg", "002.jpg", "010.jpg", "cover.jpg"]
    # 册封面 = 首页(第 1 页,自然排序后的 001.jpg)
    assert v1["cover"] == v1["pages"][0]["url"]


def test_audio_album_sorted_by_track_no(db):
    _, r = _bdrip(db)
    for name, tno, title in (("03.flac", 3, "曲三"), ("01.flac", 1, "曲一"), ("02.flac", 2, None)):
        _extra(db, r, category="audio", media_kind="audio", name=name,
               relative_path=f"BD/[VCB] Bocchi/CDs/Album/{name}",
               track_no=tno, track_title=title, duration=200.0)
    from app.api.bd import bd_release_detail as bd_release_out
    albums = bd_release_out(r)["audio_albums"]
    assert len(albums) == 1 and albums[0]["folder"] == "Album"
    assert [t["track_no"] for t in albums[0]["tracks"]] == [1, 2, 3]
    assert albums[0]["tracks"][1]["title"] == "02"   # 无标签标题 → 回退文件名 stem


def test_videos_carry_full_spec(db):
    _, r = _bdrip(db)
    _extra(db, r, category="sp_anime", media_kind="video", name="SP01.mkv",
           relative_path="BD/[VCB] Bocchi/SPs/SP01.mkv", resolution="1920x1080",
           video_codec="hevc", color_depth="10bit", hdr=None, bitrate=12_000_000,
           audio_tracks=[{"codec": "flac", "lang": "jpn"}],
           subtitle_tracks=[{"codec": "ass", "lang": "chs"}])
    from app.api.bd import bd_release_detail as bd_release_out
    v = bd_release_out(r)["videos"][0]
    assert v["source"] == "BD" and v["codec"] == "hevc" and v["color_depth"] == "10bit"
    assert v["resolution"] == "1920x1080" and v["label"] == "特别动画"
    assert v["audio_tracks"] and v["subtitle_tracks"]


# ---- 生命周期 ----------------------------------------------------------------
def _ep(db, b, n, typ=EpisodeType.REGULAR):
    e = Episode(bangumi_id=b.id, number=float(n), type=typ)
    db.add(e)
    db.flush()
    return e


def _torrent(db, sub, info_hash, ep, source, is_active, rel):
    t = Torrent(subscription_id=sub.id, guid=f"g-{info_hash}", info_hash=info_hash,
                title_raw="x", torrent_url="", status=TorrentStatus.ARCHIVED)
    db.add(t)
    db.flush()
    db.add(VideoFile(torrent_id=t.id, episode_id=ep.id, relative_path=rel,
                     source=source, is_active=is_active))
    db.add(TorrentEpisode(torrent_id=t.id, episode_id=ep.id))
    db.flush()
    return t


def test_full_bd_finalize_deletes_web_keeps_bd(db, monkeypatch):
    deleted = []
    monkeypatch.setattr(lifecycle.downloader, "delete",
                        lambda h, delete_files: deleted.append((h, delete_files)))
    monkeypatch.setattr(lifecycle, "_notify", lambda *a, **k: None)
    b = Bangumi(mikan_bangumi_id=1, title="番", eps_total=2, auto_best=True,
                airing_status=AiringStatus.FINISHED)
    db.add(b)
    db.flush()
    rss = Subscription(bangumi_id=b.id, mikan_subgroup_id="123", subgroup_name="组",
                       enabled=True, save_path="/d")
    auto = Subscription(bangumi_id=b.id, mikan_subgroup_id="auto", enabled=False, save_path="/d")
    db.add_all([rss, auto])
    db.flush()
    e1, e2 = _ep(db, b, 1), _ep(db, b, 2)
    wt1 = _torrent(db, rss, "webhash1", e1, "Web", False, "web/01.mkv")
    wt2 = _torrent(db, rss, "webhash2", e2, "Web", False, "web/02.mkv")
    bd1 = _torrent(db, auto, "bdhash1", e1, "BD", True, "bd/01.mkv")
    _torrent(db, auto, "bdhash2", e2, "BD", True, "bd/02.mkv")

    assert lifecycle.bd_complete(db, b) is True
    assert lifecycle.finalize_complete(db, b) is True
    assert b.auto_best is False                  # 停定期扫
    db.refresh(rss)
    assert rss.enabled is False                  # 停真订阅
    assert {h for h, _ in deleted} == {"webhash1", "webhash2"}   # 删 web,且带删文件
    assert all(df for _, df in deleted)
    assert db.get(Torrent, wt1.id) is None and db.get(Torrent, wt2.id) is None
    assert db.get(Torrent, bd1.id) is not None   # BD 种子保留
    # 幂等:再调一次无动作
    assert lifecycle.finalize_complete(db, b) is False


def test_finalize_noop_when_not_all_bd(db, monkeypatch):
    monkeypatch.setattr(lifecycle, "_notify", lambda *a, **k: None)
    b = Bangumi(mikan_bangumi_id=1, title="番", eps_total=2, auto_best=True)
    db.add(b)
    db.flush()
    rss = Subscription(bangumi_id=b.id, mikan_subgroup_id="1", enabled=True, save_path="/d")
    db.add(rss)
    db.flush()
    e1, e2 = _ep(db, b, 1), _ep(db, b, 2)
    _torrent(db, rss, "bd1", e1, "BD", True, "bd/01.mkv")   # 只有第 1 集是 BD
    _torrent(db, rss, "web2", e2, "Web", True, "web/02.mkv")
    assert lifecycle.bd_complete(db, b) is False
    assert lifecycle.finalize_complete(db, b) is False
    assert b.auto_best is True                   # 未完成 → 不动


def test_evaluate_airing_flips_on_eps_downloaded(db, monkeypatch):
    monkeypatch.setattr(lifecycle, "_notify", lambda *a, **k: None)
    b = Bangumi(mikan_bangumi_id=2, title="新番", eps_total=2,
                airing_status=AiringStatus.AIRING, auto_best=False)
    db.add(b)
    db.flush()
    rss = Subscription(bangumi_id=b.id, mikan_subgroup_id="9", enabled=True,
                       exclude_batch=True, save_path="/d")
    db.add(rss)
    db.flush()
    e1, e2 = _ep(db, b, 1), _ep(db, b, 2)
    _torrent(db, rss, "w1", e1, "Web", True, "w/01.mkv")
    _torrent(db, rss, "w2", e2, "Web", True, "w/02.mkv")
    assert lifecycle.evaluate_airing(db, b) is True
    assert b.airing_status == AiringStatus.FINISHED and b.auto_best is True
    db.refresh(rss)
    assert rss.exclude_batch is False            # 完结后放开合集


def test_evaluate_airing_skips_without_mikan_id(db, monkeypatch):
    monkeypatch.setattr(lifecycle, "_notify", lambda *a, **k: None)
    b = Bangumi(title="本地导入无蜜柑", eps_total=2, airing_status=AiringStatus.AIRING)
    db.add(b)
    db.flush()
    assert lifecycle.evaluate_airing(db, b) is False   # 无蜜柑 ID 不转补全


# ---- BD 正片/特典判别(纯集号 vs 描述标签;不靠 web 集号匹配)--------------------
@pytest.mark.parametrize("name,is_extra", [
    # 正片:中间方括号是纯集号
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [01][Ma10p_1080p][x265_aac].mkv", False),
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [12][Ma10p_1080p][x265_aac].mkv", False),
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [12.5][Ma10p_1080p][x265_aac].mkv", False),
    # 特典:中间方括号带描述标签(截图实例)——绝不能当正片
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [BOCCHI THE TALK! 01][Ma10p_1080p][x265_flac].mkv", True),
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [Lyric Video 02][Ma10p_1080p][x265_flac].mkv", True),
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [Menu01][Ma10p_1080p][x265_flac].mkv", True),
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [NCED01][Ma10p_1080p][x265_flac].mkv", True),
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [Character PV 02][Ma10p_1080p][x265_flac].mkv", True),
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [IV][Ma10p_1080p][x265_flac].mkv", True),
    ("[DMG&VCB-Studio] BOCCHI THE ROCK! [Road to Guitar Hero 01][Ma10p_1080p][x265_flac].mkv", True),
    # DBD-Raws 式:作品名在方括号内,标题方括号不得误当特典(否则正片被剔)
    ("[DBD-Raws][深夜重拳][01][1080P][BDRip][HEVC-10bit][FLAC].mkv", False),
    ("[DBD-Raws][深夜重拳][12][1080P][BDRip][HEVC-10bit][FLAC].mkv", False),
    ("[DBD-Raws][Mayonaka Punch][After Broadcasting Short Drama][01][1080P][BDRip][HEVC-10bit][FLAC].mkv", True),
    ("[DBD-Raws][深夜重拳][NCOP][1080P][BDRip][HEVC-10bit][FLAC].mkv", True),
])
def test_bd_video_discriminator(name, is_extra):
    from app.services.bd_scan import bd_is_extra_video
    assert bd_is_extra_video(name) is is_extra


def test_release_summary_counts(db):
    _, r = _bdrip(db)
    _extra(db, r, category="scans", media_kind="image", name="001.jpg",
           relative_path="BD/x/Scans/Vol.1/001.jpg")
    _extra(db, r, category="scans", media_kind="image", name="002.jpg",
           relative_path="BD/x/Scans/Vol.1/002.jpg")
    _extra(db, r, category="audio", media_kind="audio", name="01.flac",
           relative_path="BD/x/CDs/A/01.flac", track_no=1)
    _extra(db, r, category="other", media_kind="video", name="SP.mkv",
           relative_path="BD/x/SP.mkv")
    from app.api.bd import bd_release_summary
    s = bd_release_summary(r)
    assert s["image_count"] == 2 and s["image_book_count"] == 1
    assert s["audio_count"] == 1 and s["audio_album_count"] == 1
    assert s["video_count"] == 1 and s["extra_count"] == 4


def test_heal_bd_extras_removes_mismapped_keeps_main(db):
    """全局自愈:BD 番剧里被误登记成正片的特典(任意来源/嵌套)移出,正片保留。锁 深夜重拳 回归。"""
    from app.services.library_scan import _heal_bd_extras
    b = Bangumi(mikan_bangumi_id=9, title="深夜重拳", eps_total=12)
    db.add(b)
    db.flush()
    db.add(BdRelease(bangumi_id=b.id, title="rel", source_kind="bdrip",
                     root_path="深夜重拳/rel", owned=False))      # 该番有 BD 发行 → BD 上下文
    sub = Subscription(bangumi_id=b.id, mikan_subgroup_id="local", enabled=False, save_path="/d")
    db.add(sub)
    db.flush()
    t = Torrent(subscription_id=sub.id, guid="library:9", title_raw="x", torrent_url="",
                status=TorrentStatus.ARCHIVED)
    db.add(t)
    db.flush()
    e1 = Episode(bangumi_id=b.id, number=1.0, type=EpisodeType.REGULAR)
    db.add(e1)
    db.flush()
    main = VideoFile(torrent_id=t.id, episode_id=e1.id, source="BD", is_active=True,
                     relative_path="深夜重拳/rel/[DBD-Raws][深夜重拳][01][1080P][BDRip].mkv")
    extra = VideoFile(torrent_id=t.id, episode_id=e1.id, source="BD", is_active=True,
                      relative_path="深夜重拳/rel/短剧/[DBD-Raws][Mayonaka Punch]"
                                    "[After Broadcasting Short Drama][01][1080P][BDRip].mkv")
    db.add_all([main, extra])
    db.flush()
    assert _heal_bd_extras(db) == 1
    assert db.get(VideoFile, extra.id) is None     # 短剧特典移出剧集
    assert db.get(VideoFile, main.id) is not None  # 纯集号正片保留
