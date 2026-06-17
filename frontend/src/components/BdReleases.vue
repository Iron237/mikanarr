<script setup>
// BD 发行展示(grill 第七轮三件套 + 按发行懒加载):
//  列表只拿概要(计数),展开某套才拉它的完整特典(GET /api/bd/releases/{id})——避免一口气全加载卡顿。
//  图片→文件夹折叠成「册」+漫画翻页阅读器;音频→「专辑」CD 播放器歌单;视频→复用正片 FileTags 全规格。
import { onMounted, onUnmounted, reactive, ref } from 'vue'
import Icon from './Icon.vue'
import FileTags from './FileTags.vue'
import { api, fmtSize } from '../api'
import { requestNative } from '../native'

const props = defineProps({
  releases: { type: Array, default: () => [] },   // 概要数组(含计数)
  showHeader: { type: Boolean, default: true },    // 是否渲染发行标题行(BD 库页自带管理行则关)
})

const SRC_BADGE = { bdrip: ['BDRip', 'accent'], raw_disc: ['自购原盘', 'green'] }
function open(url) { if (url) requestNative(url) }
function fmtDur(s) {
  if (!s && s !== 0) return ''
  const m = Math.floor(s / 60), sec = Math.round(s % 60)
  return `${m}:${String(sec).padStart(2, '0')}`
}

// ---- 按发行懒加载 -----------------------------------------------------------
const expanded = reactive({})   // id → bool
const details = reactive({})    // id → 完整特典 detail
const loading = reactive({})    // id → bool
async function toggle(r) {
  if (expanded[r.id]) { expanded[r.id] = false; return }
  expanded[r.id] = true
  if (!details[r.id] && !loading[r.id]) {
    loading[r.id] = true
    try { details[r.id] = await api.get(`/api/bd/releases/${r.id}`) }
    catch (e) { details[r.id] = { error: e.message } }
    finally { loading[r.id] = false }
  }
}

// ---- 漫画翻页阅读器 ----------------------------------------------------------
const reader = ref(null)   // { title, pages, idx, double, rtl }
function openBook(bk) { reader.value = { title: bk.folder, pages: bk.pages, idx: 0, double: false, rtl: false } }
function closeReader() { reader.value = null }
function step(forward) {
  const r = reader.value
  if (!r) return
  const n = r.double ? 2 : 1
  r.idx = Math.max(0, Math.min(r.pages.length - 1, r.idx + (forward ? n : -n)))
}
const spread = () => {
  const r = reader.value
  if (!r) return []
  if (!r.double) return [r.pages[r.idx]].filter(Boolean)
  const a = r.pages[r.idx], b = r.pages[r.idx + 1]
  return (r.rtl ? [b, a] : [a, b]).filter(Boolean)
}
function onKey(e) {
  if (!reader.value) return
  if (e.key === 'Escape') closeReader()
  else if (e.key === 'ArrowRight') step(!reader.value.rtl)
  else if (e.key === 'ArrowLeft') step(reader.value.rtl)
}
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))

// ---- CD 播放器歌单 -----------------------------------------------------------
const curList = ref([])
const curIdx = ref(-1)
const curTrack = () => curList.value[curIdx.value] || null
function playList(tracks, i) { curList.value = tracks; curIdx.value = i }
function isCur(t) { const c = curTrack(); return c && c.id === t.id }
function audioPrev() { if (curIdx.value > 0) curIdx.value-- }
function audioNext() { if (curIdx.value < curList.value.length - 1) curIdx.value++ }
function onEnded() { curIdx.value < curList.value.length - 1 ? curIdx.value++ : stopAudio() }
function stopAudio() { curList.value = []; curIdx.value = -1 }

// ---- 视频特典浏览器串流 ------------------------------------------------------
const videoSrc = ref(null)
function playVideo(v) { videoSrc.value = v.url }
</script>

<template>
  <div v-for="r in releases" :key="r.id" class="bd-rel card">
    <div v-if="showHeader" class="row" style="flex-wrap: wrap; gap: 8px;">
      <Icon name="disc" :size="16" class="muted" />
      <strong class="bd-title" :title="r.title">{{ r.title }}</strong>
      <span class="tag" :class="SRC_BADGE[r.source_kind]?.[1]">{{ SRC_BADGE[r.source_kind]?.[0] || r.source_kind }}</span>
      <span class="tag" :class="r.owned ? 'green' : 'red'">{{ r.owned ? '已购买' : '未购买' }}</span>
      <span v-if="r.total_size" class="tag">{{ fmtSize(r.total_size) }}</span>
    </div>

    <!-- 概要计数 + 展开 -->
    <div class="row bd-counts">
      <span v-if="r.image_book_count" class="muted">图集 {{ r.image_book_count }} 本 / {{ r.image_count }} 张</span>
      <span v-if="r.audio_album_count" class="muted">音频 {{ r.audio_album_count }} 专辑 / {{ r.audio_count }} 曲</span>
      <span v-if="r.video_count" class="muted">视频特典 {{ r.video_count }}</span>
      <span v-if="r.has_discs" class="muted">自购原盘(逐碟 PowerDVD)</span>
      <span v-if="!r.extra_count && !r.has_discs" class="muted">无特典</span>
      <div class="spacer" />
      <button v-if="r.extra_count || r.has_discs" class="btn xs" @click="toggle(r)">
        <Icon :name="expanded[r.id] ? 'chevron-down' : 'chevron-right'" :size="13" />
        {{ expanded[r.id] ? '收起' : '展开特典' }}
      </button>
    </div>

    <!-- 懒加载内容 -->
    <div v-if="expanded[r.id]" class="bd-body">
      <div v-if="loading[r.id]" class="muted bd-load">加载特典中…</div>
      <div v-else-if="details[r.id]?.error" class="bd-load" style="color: var(--red);">加载失败:{{ details[r.id].error }}</div>
      <template v-else-if="details[r.id]">
        <!-- 自购原盘:逐碟 PowerDVD -->
        <div v-if="details[r.id].source_kind === 'raw_disc'" class="bd-discs">
          <template v-if="details[r.id].discs?.length">
            <div v-for="d in details[r.id].discs" :key="d.name" class="bd-disc">
              <Icon name="disc" :size="14" class="muted" />
              <span class="bd-fname" :title="d.name">{{ d.name }}</span>
              <div class="spacer" />
              <button class="btn xs" :disabled="!d.bd_url" title="用 PowerDVD 蓝光播放(带菜单)" @click="open(d.bd_url)">
                <Icon name="play" :size="12" /> PowerDVD
              </button>
              <button class="btn xs" :disabled="!d.reveal_url" title="在资源管理器中打开" @click="open(d.reveal_url)">
                <Icon name="folder-open" :size="12" /> 打开目录
              </button>
            </div>
            <div v-if="!details[r.id].discs[0].bd_url" class="muted bd-raw">
              未配置「已购原盘宿主机根」— 在 设置 → 播放 填写并安装协议处理器后可一键播放
            </div>
          </template>
          <div v-else class="muted bd-raw">自购原盘(BDMV)· 未发现可播放的碟结构(或目录未挂载)</div>
        </div>

        <!-- 图片:文件夹折叠成「册」→ 漫画翻页阅读器 -->
        <section v-if="details[r.id].image_books?.length" class="bd-sec">
          <div class="bd-sec-h">图集 / 书子 <span class="muted">{{ details[r.id].image_books.length }} 本</span></div>
          <div class="book-grid">
            <button v-for="(bk, bi) in details[r.id].image_books" :key="bi" class="book" @click="openBook(bk)">
              <img :src="bk.cover" loading="lazy" />
              <div class="book-cap">
                <span class="bk-name" :title="bk.folder">{{ bk.folder }}</span>
                <span class="muted">{{ bk.count }}P</span>
              </div>
            </button>
          </div>
        </section>

        <!-- 音频:文件夹折叠成「专辑」→ CD 播放器歌单 -->
        <section v-if="details[r.id].audio_albums?.length" class="bd-sec">
          <div class="bd-sec-h">音频 <span class="muted">{{ details[r.id].audio_albums.length }} 张专辑</span></div>
          <div v-for="(al, ai) in details[r.id].audio_albums" :key="ai" class="album">
            <div class="album-h">
              <img v-if="al.cover" :src="al.cover" class="album-cov" loading="lazy" />
              <Icon v-else name="disc" :size="16" class="muted" />
              <strong>{{ al.folder }}</strong>
              <span class="muted">{{ al.count }} 曲</span>
            </div>
            <ol class="tracklist">
              <li v-for="(t, ti) in al.tracks" :key="t.id" :class="{ cur: isCur(t) }" @click="playList(al.tracks, ti)">
                <span class="tno">{{ t.track_no ?? ti + 1 }}</span>
                <span class="ttitle" :title="t.name">{{ t.title }}</span>
                <Icon v-if="isCur(t)" name="volume" :size="13" class="playing" />
                <span class="muted tdur">{{ fmtDur(t.duration) }}</span>
              </li>
            </ol>
          </div>
        </section>

        <!-- 视频特典:独立列表 + 完整规格(复用正片 FileTags)-->
        <section v-if="details[r.id].videos?.length" class="bd-sec">
          <div class="bd-sec-h">特典视频 <span class="muted">{{ details[r.id].videos.length }}</span></div>
          <div v-for="v in details[r.id].videos" :key="v.id" class="vid-item">
            <div class="vid-top">
              <span class="tag accent">{{ v.label }}</span>
              <span class="vid-name" :title="v.name">{{ v.name }}</span>
              <div class="spacer" />
              <button class="btn xs" title="浏览器内播放" @click="playVideo(v)"><Icon name="play" :size="12" /> 播放</button>
              <button class="btn xs" :disabled="!v.play_url" title="本机默认播放器" @click="open(v.play_url)">本机</button>
              <button class="btn xs" :disabled="!v.reveal_url" title="在资源管理器中打开" @click="open(v.reveal_url)">
                <Icon name="folder-open" :size="12" />
              </button>
            </div>
            <FileTags :file="v" />
          </div>
        </section>
      </template>
    </div>
  </div>

  <!-- 漫画翻页阅读器 -->
  <div v-if="reader" class="reader-mask" @click.self="closeReader">
    <div class="reader-bar">
      <strong class="r-title" :title="reader.title">{{ reader.title }}</strong>
      <span class="muted">{{ reader.idx + 1 }} / {{ reader.pages.length }}</span>
      <div class="spacer" />
      <button class="btn xs" :class="{ primary: reader.double }" @click="reader.double = !reader.double">
        {{ reader.double ? '跨页' : '单页' }}
      </button>
      <button class="btn xs" :class="{ primary: reader.rtl }" @click="reader.rtl = !reader.rtl">
        {{ reader.rtl ? '右开←' : '左开→' }}
      </button>
      <button class="btn xs" @click="closeReader"><Icon name="close" :size="13" /></button>
    </div>
    <div class="reader-stage">
      <button class="nav-btn left" :disabled="reader.idx <= 0" @click="step(reader.rtl)">‹</button>
      <div class="pages">
        <img v-for="p in spread()" :key="p.id" :src="p.url" :title="p.name" />
      </div>
      <button class="nav-btn right" :disabled="reader.idx >= reader.pages.length - 1" @click="step(!reader.rtl)">›</button>
    </div>
    <div class="thumbs">
      <img v-for="(p, pi) in reader.pages" :key="p.id" :src="p.url" loading="lazy"
           :class="{ on: pi === reader.idx }" @click="reader.idx = pi" />
    </div>
  </div>

  <!-- 视频浏览器串流灯箱 -->
  <div v-if="videoSrc" class="lb-mask" @click.self="videoSrc = null">
    <video :src="videoSrc" controls autoplay />
    <button class="btn sm vid-close" @click="videoSrc = null"><Icon name="close" :size="14" /></button>
  </div>

  <!-- CD 播放器底栏(连播)-->
  <div v-if="curTrack()" class="player-bar">
    <button class="btn xs" :disabled="curIdx <= 0" @click="audioPrev"><Icon name="chevron-left" :size="14" /></button>
    <button class="btn xs" :disabled="curIdx >= curList.length - 1" @click="audioNext"><Icon name="chevron-right" :size="14" /></button>
    <div class="pb-info">
      <span class="pb-title" :title="curTrack().name">{{ curTrack().title }}</span>
      <span class="muted">{{ curIdx + 1 }} / {{ curList.length }}</span>
    </div>
    <audio :key="curTrack().id" :src="curTrack().url" controls autoplay @ended="onEnded" />
    <button class="btn xs" title="关闭" @click="stopAudio"><Icon name="close" :size="14" /></button>
  </div>
</template>

<style scoped>
.bd-rel { margin-bottom: 12px; padding: 13px 16px; }
.bd-title { word-break: break-all; }
.bd-counts { gap: 12px; flex-wrap: wrap; font-size: 12.5px; margin-top: 6px; }
.bd-body { margin-top: 6px; }
.bd-load { padding: 10px 2px; font-size: 12.5px; }
.bd-raw { font-size: 12.5px; margin-top: 8px; }
.bd-discs { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.bd-disc { display: flex; align-items: center; gap: 8px; font-size: 12.5px; }
.bd-fname { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 420px; }

.bd-sec { margin-top: 14px; }
.bd-sec-h { font-size: 13px; color: var(--accent); font-weight: 600; margin-bottom: 8px; }
.bd-sec-h .muted { font-weight: 400; font-size: 12px; }

.book-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 10px; }
.book { padding: 0; border: 1px solid var(--border); border-radius: 8px; overflow: hidden;
  background: #0b0e14; cursor: pointer; text-align: left; }
.book:hover { border-color: var(--accent); }
.book img { width: 100%; aspect-ratio: 3/4; object-fit: cover; display: block; }
.book-cap { display: flex; justify-content: space-between; gap: 6px; padding: 5px 7px; font-size: 11.5px; }
.bk-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

.album { margin-bottom: 12px; }
.album-h { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 13px; }
.album-cov { width: 34px; height: 34px; object-fit: cover; border-radius: 4px; border: 1px solid var(--border); }
.tracklist { list-style: none; margin: 0; padding: 0; }
.tracklist li { display: flex; align-items: center; gap: 10px; padding: 5px 8px; border-radius: 6px;
  cursor: pointer; font-size: 12.5px; }
.tracklist li:hover { background: var(--bg-soft, rgba(255,255,255,.04)); }
.tracklist li.cur { background: var(--accent-dim, rgba(80,140,255,.15)); color: var(--accent); }
.tno { width: 22px; text-align: right; color: var(--text-dim); font-variant-numeric: tabular-nums; }
.ttitle { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tdur { flex-shrink: 0; font-variant-numeric: tabular-nums; }
.playing { color: var(--accent); }

.vid-item { padding: 8px 0; border-top: 1px solid var(--border); }
.vid-item:first-of-type { border-top: none; }
.vid-top { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; font-size: 12.5px; }
.vid-name { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 380px; }

.reader-mask { position: fixed; inset: 0; background: rgba(0,0,0,.92); z-index: 120;
  display: flex; flex-direction: column; }
.reader-bar { display: flex; align-items: center; gap: 10px; padding: 10px 16px; color: #ddd; }
.r-title { max-width: 40vw; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.reader-stage { flex: 1; display: flex; align-items: center; justify-content: center; min-height: 0; gap: 6px; }
.pages { display: flex; gap: 4px; height: 100%; align-items: center; justify-content: center; }
.pages img { max-height: 78vh; max-width: 46vw; object-fit: contain; border-radius: 4px; }
.nav-btn { width: 48px; height: 90px; font-size: 32px; line-height: 1; color: #fff;
  background: rgba(255,255,255,.06); border: none; border-radius: 8px; cursor: pointer; }
.nav-btn:hover:not(:disabled) { background: rgba(255,255,255,.18); }
.nav-btn:disabled { opacity: .25; cursor: default; }
.thumbs { display: flex; gap: 5px; overflow-x: auto; padding: 8px 16px; background: rgba(0,0,0,.4); }
.thumbs img { height: 56px; border-radius: 3px; cursor: pointer; opacity: .55; border: 2px solid transparent; }
.thumbs img.on { opacity: 1; border-color: var(--accent); }

.lb-mask { position: fixed; inset: 0; background: rgba(0,0,0,.9); z-index: 120;
  display: flex; align-items: center; justify-content: center; padding: 24px; }
.lb-mask video { max-width: 100%; max-height: 100%; border-radius: 8px; outline: none; }
.vid-close { position: fixed; top: 16px; right: 16px; }

.player-bar { position: fixed; left: 0; right: 0; bottom: 0; z-index: 110;
  display: flex; align-items: center; gap: 10px; padding: 8px 16px;
  background: var(--bg-elev, #11151d); border-top: 1px solid var(--border); }
.pb-info { display: flex; flex-direction: column; min-width: 0; max-width: 240px; }
.pb-title { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 12.5px; }
.player-bar audio { height: 34px; flex: 1; max-width: 520px; margin-left: auto; }
</style>
