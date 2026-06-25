(() => {
        // Language switching is handled by the shared portal script in _language_switcher.html.

        const root = document.querySelector("[data-video-editor]");
        if (!root) return;
        const api = root.dataset.projectsApiUrl || "/api/video-projects/";
        const csrf = (document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || "";
        const csrfToken = () => decodeURIComponent((document.cookie.match(/(?:^|; )csrftoken=([^;]+)/) || [])[1] || csrf || "");
        const currentProject = JSON.parse(document.getElementById("video-project-data").textContent || "null");
        const appMessages = (() => {
          try {
            return JSON.parse(document.getElementById("app-messages")?.textContent || "{}");
          } catch {
            return {};
          }
        })();
        const t = (key, fallback = "") => appMessages[key] || fallback || key;
        const readOnly = Boolean(currentProject && currentProject.can_edit === false);
        const video = root.querySelector("[data-editor-video]");
        const fileInput = root.querySelector("[data-editor-file]");
        const videoPanelInput = root.querySelector("[data-video-file-panel]");
        const videoPanelName = root.querySelector("[data-video-panel-name]");
        const audioInput = root.querySelector("[data-audio-file-panel]");
        const audioPanelName = root.querySelector("[data-audio-panel-name]");
        const imageInput = document.querySelector("[data-image-file]");
        const dropzone = root.querySelector("[data-editor-dropzone]");
        const frame = root.querySelector("[data-preview-frame]");
        const overlayRoot = root.querySelector("[data-preview-overlays]");
        const trackList = root.querySelector("[data-track-list]");
        const timeline = root.querySelector("[data-editor-timeline]");
        const timelineScroll = timeline.closest(".editor-timeline-scroll");
        const timeRuler = root.querySelector("[data-time-ruler]");
        const playhead = root.querySelector("[data-editor-playhead]");
        const playheadLabel = root.querySelector("[data-playhead-label]");
        const snapLine = root.querySelector("[data-snap-line]");
        const mediaBin = root.querySelector("[data-media-bin]");
        const mediaFilters = root.querySelector("[data-media-filters]");
        const assetPreview = document.querySelector("[data-asset-preview]");
        const clipMenu = document.querySelector("[data-clip-menu]");
        const play = root.querySelector("[data-editor-play]");
        const seek = root.querySelector("[data-editor-seek]");
        const time = root.querySelector("[data-editor-time]");
        const durationNode = root.querySelector("[data-editor-duration]");
        const title = root.querySelector("[data-editor-title]");
        const saveStatus = root.querySelector("[data-save-status]");
        const saveRetry = root.querySelector("[data-save-retry]");
        const aspectMenu = root.querySelector("[data-aspect-menu]");
        const aspectToggle = root.querySelector("[data-aspect-toggle]");
        const aspectOptions = root.querySelector("[data-aspect-options]");
        const aspectCurrent = root.querySelector("[data-aspect-current]");
        const aspectSize = root.querySelector("[data-aspect-size]");
        const toolTitle = root.querySelector("[data-tool-title]");
        const exportShortcut = document.querySelector("[data-editor-export-shortcut]");
        const renderExport = root.querySelector("[data-render-export]");
        const exportProgress = root.querySelector("[data-export-progress]");
        const exportProgressBar = root.querySelector("[data-export-progress-bar]");
        const exportStatus = root.querySelector("[data-export-status]");
        const exportDownload = root.querySelector("[data-export-download]");
        const exportQueue = root.querySelector("[data-export-queue]");
        const exportCover = root.querySelector("[data-export-cover]");
        const subtitleInput = root.querySelector("[data-subtitle-file]");
        const autoSubtitleButton = root.querySelector("[data-auto-subtitles]");
        const autoSubtitleLanguage = root.querySelector("[data-auto-subtitles-language]");
        const autoSubtitleStatus = root.querySelector("[data-auto-subtitles-status]");
        const confirmModal = document.querySelector("[data-editor-confirm]");
        const confirmTitle = confirmModal?.querySelector("[data-confirm-title]");
        const confirmCopy = confirmModal?.querySelector("[data-confirm-copy]");
        const confirmAction = confirmModal?.querySelector("[data-confirm-action]");
        const confirmCancel = confirmModal?.querySelectorAll("[data-confirm-cancel]") || [];

        const defaults = {
          tracks: [
            {id: "video-main", type: "video", name: t("video", "Video"), order: 0},
            {id: "text-1", type: "text", name: t("text", "Text"), order: 1},
            {id: "image-1", type: "image", name: t("image", "Image"), order: 2},
            {id: "audio-1", type: "audio", name: t("audio", "Audio"), order: 3},
          ],
          clips: [],
          aspect: "9 / 16",
          background: "",
          title: t("new_project", "New project"),
        };
        let projectId = currentProject && currentProject.id ? String(currentProject.id) : "";
        let assets = currentProject && currentProject.assets ? currentProject.assets : [];
        let state = normalizeState(currentProject && currentProject.state ? currentProject.state : {});
        let selectedClipId = state.clips[0] ? state.clips[0].id : "";
        let selectedClipIds = new Set(selectedClipId ? [selectedClipId] : []);
        let saveTimer = 0;
        let recorder = null;
        let recordChunks = [];
        let draggingClip = null;
        let draggingOverlay = null;
        let projectTime = 0;
        let playing = false;
        let rafId = 0;
        let lastTick = 0;
        let activeVideoClipId = "";
        let timelineScale = Number(localStorage.getItem("videoEditorTimelineScale") || 76);
        const timelineScaleMin = 8;
        const timelineScaleMax = 520;
        const audioPool = new Map();
        let internalVideoPause = false;
        let historyPast = [];
        let historyFuture = [];
        const historyLimit = 5;
        let snapEnabled = true;
        let timelineDensity = localStorage.getItem("videoEditorDensity") || "normal";
        let copiedClip = null;
        let copiedClips = [];
        let selectedAssetId = "";
        let mediaFilter = "all";
        let marquee = null;
        let dirty = false;
        let saving = false;
        let saveFailed = false;
        let exportQuality = "720p";
        let exportPreset = "shorts";
        let textEditSnapshot = "";
        let lastPlayheadPersist = 0;
        let exportQueueTimer = 0;
        const EXPORT_PRESETS = {
          shorts: {aspect: "9 / 16", quality: "1080p"},
          reels: {aspect: "9 / 16", quality: "1080p"},
          tiktok: {aspect: "9 / 16", quality: "1080p"},
          youtube: {aspect: "16 / 9", quality: "1080p"},
          square: {aspect: "1 / 1", quality: "1080p"},
          feed: {aspect: "4 / 5", quality: "1080p"},
          pinterest: {aspect: "3 / 4", quality: "1080p"},
          cinema: {aspect: "21 / 9", quality: "1080p"},
        };
        let cropMode = false;
        let videoReframeDrag = null;
        let videoWheelHistory = false;
        let videoWheelTimer = 0;
        let pendingConfirm = null;
        const timelineScrollbar = createTimelineScrollbar();
        installInspectorResetButtons();

        function normalizeState(raw) {
          const value = {...defaults, ...raw};
          value.tracks = Array.isArray(raw.tracks) && raw.tracks.length ? raw.tracks : defaults.tracks;
          value.clips = Array.isArray(raw.clips) ? raw.clips.map(normalizeClip) : [];
          value.backgroundMode = raw.backgroundMode || "solid";
          value.backgroundValue = raw.backgroundValue || raw.background || "#020617";
          return value;
        }
        function normalizeClip(clip) {
          const duration = Math.max(0.25, Number(clip.duration || clip.sourceEnd || 4));
          const normalized = {
            ...clip,
            start: Math.max(0, Number(clip.start || 0)),
            duration,
            x: Number.isFinite(Number(clip.x)) ? Number(clip.x) : 50,
            y: Number.isFinite(Number(clip.y)) ? Number(clip.y) : 50,
            scale: Number.isFinite(Number(clip.scale)) ? Number(clip.scale) : (clip.type === "image" ? 42 : 100),
            boxWidth: Number.isFinite(Number(clip.boxWidth)) ? Math.max(18, Math.min(86, Number(clip.boxWidth))) : (["text", "caption"].includes(clip.type) ? (clip.type === "caption" ? 42 : 36) : undefined),
            rotation: Number.isFinite(Number(clip.rotation)) ? Number(clip.rotation) : 0,
            style: {speed: 1, fit: "contain", opacity: 100, transition: "none", fadeIn: 0, fadeOut: 0, ...(clip.style || {})},
          };
          if (normalized.type === "caption") normalized.type = "caption";
          if (["video", "audio"].includes(normalized.type)) {
            normalized.sourceStart = Math.max(0, Number(clip.sourceStart || 0));
            normalized.sourceEnd = Math.max(normalized.sourceStart + 0.25, Number(clip.sourceEnd || normalized.sourceStart + duration));
            normalized.duration = Math.max(0.25, normalized.sourceEnd - normalized.sourceStart);
          }
          return normalized;
        }
        const fmt = (value) => {
          const safe = Number.isFinite(value) ? Math.max(0, value) : 0;
          return `${Math.floor(safe / 60)}:${String(Math.floor(safe % 60)).padStart(2, "0")}`;
        };
        const uid = (prefix) => `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
        const assetById = (id) => assets.find((asset) => String(asset.id) === String(id));
        const clipById = (id) => state.clips.find((clip) => clip.id === id);
        const selectedClip = () => clipById(selectedClipId);
        const selectedClips = () => state.clips.filter((clip) => selectedClipIds.has(clip.id));
        const selectedClipIdList = () => Array.from(selectedClipIds).filter((id) => clipById(id));
        const timelineDuration = () => Math.max(12, ...state.clips.map((clip) => Number(clip.start || 0) + Number(clip.duration || 4)));
        const secondsToPx = (seconds) => Math.max(0, Number(seconds || 0) * timelineScale);
        const pxToSeconds = (px) => Math.max(0, Number(px || 0) / timelineScale);
        const pxDeltaToSeconds = (px) => Number(px || 0) / timelineScale;
        function snapshotState() {
          return JSON.stringify({state, selectedClipId, selectedClipIds: selectedClipIdList(), projectTime});
        }
        function restoreSnapshot(snapshot) {
          const value = JSON.parse(snapshot);
          state = normalizeState(value.state || {});
          selectedClipId = value.selectedClipId || (state.clips[0] ? state.clips[0].id : "");
          selectedClipIds = new Set((value.selectedClipIds || [selectedClipId]).filter((id) => clipById(id)));
          if (!selectedClipIds.size && selectedClipId) selectedClipIds.add(selectedClipId);
          projectTime = Number(value.projectTime || 0);
          render();
          scheduleSave();
        }
        function setSelection(ids, primary = "") {
          selectedClipIds = new Set(ids.filter((id) => clipById(id)));
          selectedClipId = primary && selectedClipIds.has(primary) ? primary : (selectedClipIdList()[0] || "");
        }
        function selectOnly(id) {
          setSelection(id ? [id] : [], id);
        }
        function toggleClipSelection(id) {
          if (!id) return;
          if (selectedClipIds.has(id)) selectedClipIds.delete(id);
          else selectedClipIds.add(id);
          selectedClipId = id;
          if (!selectedClipIds.size) selectedClipId = "";
        }
        function ensureClipSelected(id) {
          if (!selectedClipIds.has(id)) selectOnly(id);
          else selectedClipId = id;
        }
        function normalizeSelection() {
          setSelection(selectedClipIdList(), selectedClipId);
        }
        function activateInspectorPanel(tool, options = {}) {
          if (!tool) return;
          root.querySelectorAll("[data-tool-panel]").forEach((panel) => panel.classList.toggle("is-active", panel.dataset.toolPanel === tool));
          root.querySelectorAll("[data-panel-tab]").forEach((item) => item.classList.toggle("is-active", item.dataset.panelTab === tool));
          root.querySelectorAll("[data-editor-tool]").forEach((item) => item.classList.toggle("is-active", item.dataset.editorTool === tool));
          root.querySelector(`[data-panel-tab="${CSS.escape(tool)}"]`)?.scrollIntoView({behavior: "smooth", inline: "center", block: "nearest"});
          const panel = root.querySelector(`[data-tool-panel="${CSS.escape(tool)}"]`);
          if (options.scroll !== false && panel && window.matchMedia("(max-width: 760px)").matches) {
            panel.scrollIntoView({block: "nearest"});
          }
        }
        function inspectorPanelForClip(clip) {
          if (!clip) return "";
          if (["text", "caption"].includes(clip.type)) return "text";
          if (clip.type === "audio") return "audio";
          return "trim";
        }
        function focusInspectorForClip(clip, options = {}) {
          const panel = inspectorPanelForClip(clip);
          if (panel) activateInspectorPanel(panel, options);
        }
        function overlayPositionBounds(clip, loose = false) {
          if (isTextOverlayClip(clip)) return loose ? {min: -140, max: 240} : {min: -55, max: 155};
          return {min: 0, max: 100};
        }
        function clampOverlayPositionValue(value, clip, loose = false) {
          const bounds = overlayPositionBounds(clip, loose);
          const number = Number.isFinite(Number(value)) ? Number(value) : 50;
          return Math.max(bounds.min, Math.min(bounds.max, number));
        }
        function updateClipPatch(ids, patch, options = {}) {
          const clips = ids.map((id) => clipById(id)).filter(Boolean);
          if (!clips.length) return;
          if (options.history !== false) pushHistory();
          clips.forEach((clip) => {
            if (patch.start !== undefined) clip.start = Math.max(0, Number(patch.start) || 0);
            if (patch.duration !== undefined) clip.duration = Math.max(0.25, Number(patch.duration) || 0.25);
            if (patch.end !== undefined) clip.duration = Math.max(0.25, Number(patch.end) - clip.start);
            if (patch.x !== undefined) clip.x = clampOverlayPositionValue(patch.x, clip, true);
            if (patch.y !== undefined) clip.y = clampOverlayPositionValue(patch.y, clip, true);
            if (patch.scale !== undefined) {
              const bounds = clip.type === "video" ? videoScaleBounds(clip) : {min: 8, max: 160};
              const maxScale = bounds.max;
              const minScale = bounds.min;
              clip.scale = Math.max(minScale, Math.min(maxScale, Number(patch.scale) || 100));
            }
            if (patch.rotation !== undefined) clip.rotation = Number(patch.rotation) || 0;
            if (patch.style) clip.style = {...(clip.style || {}), ...patch.style};
            if (["video", "audio"].includes(clip.type)) {
              clip.sourceStart = Math.max(0, Number(clip.sourceStart || 0));
              clip.sourceEnd = Math.max(clip.sourceStart + 0.25, clip.sourceStart + clip.duration);
            }
          });
          if (options.render !== false) render();
          scheduleSave();
        }
        function resetInspectorField(name) {
          const ids = selectedClipIdList();
          if (!ids.length) return;
          const defaultsByName = {
            start: {start: 0},
            duration: {duration: 4},
            end: {duration: 4},
            x: {x: 50},
            y: {y: 50},
            scale: {scale: selectedClip()?.type === "image" ? 42 : 100},
            rotation: {rotation: 0},
            fit: {style: {fit: "contain"}},
            speed: {style: {speed: 1}},
            opacity: {style: {opacity: 100}},
            volume: {style: {volume: 1}},
            fadeIn: {style: {fadeIn: 0}},
            fadeOut: {style: {fadeOut: 0}},
          };
          const patch = defaultsByName[name];
          if (patch) updateClipPatch(ids, patch);
        }
        function installInspectorResetButtons() {
          const fields = [
            ["[data-clip-start]", "start"], ["[data-clip-duration]", "duration"], ["[data-clip-end]", "end"],
            ["[data-clip-x]", "x"], ["[data-clip-y]", "y"], ["[data-clip-scale]", "scale"], ["[data-clip-rotation]", "rotation"],
            ["[data-clip-fit]", "fit"], ["[data-clip-speed]", "speed"], ["[data-filter-opacity]", "opacity"],
            ["[data-volume]", "volume"], ["[data-fade-in]", "fadeIn"], ["[data-fade-out]", "fadeOut"],
          ];
          fields.forEach(([selector, name]) => {
            const input = root.querySelector(selector);
            const label = input?.closest("label");
            if (!input || !label || label.querySelector(`[data-reset-field="${name}"]`)) return;
            label.classList.add("editor-reset-field");
            const button = document.createElement("button");
            button.type = "button";
            button.className = "editor-reset-button";
            button.dataset.resetField = name;
            button.dataset.icon = "rotate-ccw";
            button.title = "Reset";
            button.setAttribute("aria-label", "Reset");
            button.addEventListener("click", () => resetInspectorField(name));
            label.append(button);
          });
        }
        function pushHistorySnapshot(snapshot) {
          if (!snapshot) return;
          if (historyPast[historyPast.length - 1] === snapshot) return;
          historyPast.push(snapshot);
          if (historyPast.length > historyLimit) historyPast.shift();
          historyFuture = [];
        }
        function pushHistory() {
          pushHistorySnapshot(snapshotState());
        }
        function undo() {
          if (!historyPast.length) return;
          historyFuture.push(snapshotState());
          if (historyFuture.length > historyLimit) historyFuture.shift();
          restoreSnapshot(historyPast.pop());
        }
        function redo() {
          if (!historyFuture.length) return;
          historyPast.push(snapshotState());
          if (historyPast.length > historyLimit) historyPast.shift();
          restoreSnapshot(historyFuture.pop());
        }
        function isUndoShortcut(event) {
          const key = event.key.toLowerCase();
          return (event.ctrlKey || event.metaKey) && !event.shiftKey && (key === "z" || event.code === "KeyZ");
        }
        function isRedoShortcut(event) {
          const key = event.key.toLowerCase();
          return ((event.ctrlKey || event.metaKey) && event.shiftKey && (key === "z" || event.code === "KeyZ")) || (event.ctrlKey && key === "y");
        }
        function playheadStorageKey() {
          return `videoEditorPlayhead:${projectId || currentProject?.id || window.location.pathname}`;
        }
        function persistProjectTime(force = false) {
          const now = Date.now();
          if (!force && now - lastPlayheadPersist < 500) return;
          lastPlayheadPersist = now;
          try {
            localStorage.setItem(playheadStorageKey(), String(Math.max(0, Number(projectTime) || 0)));
          } catch {}
        }
        function restoreProjectTime() {
          try {
            const saved = Number(localStorage.getItem(playheadStorageKey()));
            if (Number.isFinite(saved)) projectTime = Math.max(0, Math.min(timelineDuration(), saved));
          } catch {}
        }
        function snapTime(value, excludeId = "") {
          if (!snapEnabled) return {value: Math.max(0, value), snapped: false};
          const threshold = pxToSeconds(10);
          const duration = timelineDuration();
          const points = [0, projectTime];
          for (let second = 0; second <= Math.ceil(duration); second += 1) points.push(second);
          state.clips.forEach((clip) => {
            if (clip.id === excludeId) return;
            points.push(clip.start, clip.start + clip.duration);
          });
          const target = points.find((point) => Math.abs(point - value) <= threshold);
          return {value: Math.max(0, Number.isFinite(target) ? target : value), snapped: Number.isFinite(target)};
        }
        function showSnapLine(seconds, visible) {
          if (!snapLine) return;
          snapLine.hidden = !visible;
          if (visible) snapLine.style.left = `${secondsToPx(seconds)}px`;
        }
        const jsonFetch = async (url, options = {}) => {
          const response = await fetch(url, {
            ...options,
            headers: {"Accept": "application/json", ...(options.headers || {}), ...(options.body && !(options.body instanceof FormData) ? {"Content-Type": "application/json"} : {}), "X-CSRFToken": csrfToken()},
          });
          if (!response.ok) {
            const payload = await response.json().catch(() => ({}));
            throw new Error(payload.error || `HTTP ${response.status}`);
          }
          return response.json();
        };
        const setStatus = (value, failed = false) => {
          saveStatus.textContent = value;
          saveStatus.classList.toggle("is-error", failed);
          if (saveRetry) saveRetry.hidden = !failed;
        };
        const savedTime = () => new Date().toLocaleTimeString([], {hour: "2-digit", minute: "2-digit"});
        async function ensureProject() {
          if (projectId) return projectId;
          const data = await jsonFetch(`${api}create/`, {method: "POST", body: JSON.stringify({title: state.title, state})});
          projectId = String(data.project.id);
          window.history.replaceState({}, "", `${window.location.pathname}?project=${projectId}`);
          persistProjectTime(true);
          return projectId;
        }
        function collectState() {
          state.title = title.textContent.trim() || t("new_project", "New project");
          state.aspect = frame.style.getPropertyValue("--editor-aspect").trim() || "9 / 16";
          state.background = frame.style.background || "";
          state.backgroundMode = state.backgroundMode || "solid";
          state.backgroundValue = state.backgroundValue || state.background || "#020617";
          return state;
        }
        function scheduleSave() {
          if (readOnly) return;
          dirty = true;
          saveFailed = false;
          setStatus(t("saving", "Saving..."));
          clearTimeout(saveTimer);
          saveTimer = setTimeout(saveProject, 500);
        }
        async function saveProject() {
          if (readOnly) return;
          try {
            saving = true;
            await ensureProject();
            const body = {title: state.title || t("new_project", "New project"), state: collectState()};
            const data = await jsonFetch(`${api}${projectId}/save/`, {method: "POST", body: JSON.stringify(body)});
            assets = data.project.assets || assets;
            dirty = false;
            saveFailed = false;
            setStatus(`${t("saved", "Saved")} ${savedTime()}`);
          } catch (error) {
            saveFailed = true;
            setStatus(t("save_failed", "Save failed"), true);
          } finally {
            saving = false;
          }
        }
        async function uploadAsset(file, kind, thumbnail = "", duration = 0) {
          if (readOnly) throw new Error(t("view_only", "View only"));
          if (!file) return null;
          await ensureProject();
          const form = new FormData();
          form.append("file", file);
          form.append("kind", kind);
          if (thumbnail) form.append("thumbnail", thumbnail);
          if (duration) form.append("duration", String(duration));
          try {
            const data = await jsonFetch(`${api}${projectId}/assets/`, {method: "POST", body: form});
            assets = data.project.assets || [...assets, data.asset];
            return data.asset;
          } catch (error) {
            setStatus(`${t("unsupported_or_too_large", "Unsupported or too large")}: ${file.name}`, true);
            return null;
          }
        }
        async function thumbnailFromVideo(file) {
          const url = URL.createObjectURL(file);
          const source = document.createElement("video");
          source.muted = true;
          source.src = url;
          const wait = (event) => new Promise((resolve, reject) => {
            source.addEventListener(event, resolve, {once: true});
            source.addEventListener("error", reject, {once: true});
          });
          try {
            await wait("loadedmetadata");
            const duration = Number.isFinite(source.duration) ? source.duration : 1;
            source.currentTime = Math.max(0, Math.min(duration - 0.05, duration * (0.18 + Math.random() * 0.64)));
            await wait("seeked");
            const canvas = document.createElement("canvas");
            canvas.width = 640;
            canvas.height = 360;
            const ctx = canvas.getContext("2d");
            const ratio = Math.max(canvas.width / (source.videoWidth || 640), canvas.height / (source.videoHeight || 360));
            const w = (source.videoWidth || 640) * ratio;
            const h = (source.videoHeight || 360) * ratio;
            ctx.drawImage(source, (canvas.width - w) / 2, (canvas.height - h) / 2, w, h);
            return canvas.toDataURL("image/jpeg", 0.78);
          } catch (error) {
            return "";
          } finally {
            URL.revokeObjectURL(url);
          }
        }
        async function mediaDuration(file, kind) {
          if (!["video", "audio"].includes(kind)) return 0;
          const url = URL.createObjectURL(file);
          const media = document.createElement(kind === "video" ? "video" : "audio");
          media.preload = "metadata";
          media.src = url;
          try {
            await new Promise((resolve, reject) => {
              media.addEventListener("loadedmetadata", resolve, {once: true});
              media.addEventListener("error", reject, {once: true});
            });
            return Number.isFinite(media.duration) ? media.duration : 0;
          } catch (error) {
            return 0;
          } finally {
            URL.revokeObjectURL(url);
          }
        }
        function addClip(clip) {
          pushHistory();
          const normalized = normalizeClip(clip);
          state.clips.push(normalized);
          selectOnly(normalized.id);
          focusInspectorForClip(normalized);
          render();
          scheduleSave();
        }
        function defaultStartForKind(kind) {
          if (kind === "video" && projectTime <= 0.05) {
            const end = Math.max(0, ...state.clips.filter((clip) => clip.type === "video").map((clip) => clip.start + clip.duration));
            return end;
          }
          return currentTime();
        }
        async function handleFile(file, kind = "") {
          if (!file) return;
          const fileInfo = classifyFile(file);
          kind = kind || fileInfo.kind || "image";
          if (["video", "image"].includes(kind) && videoPanelName) videoPanelName.textContent = file.name;
          if (kind === "audio" && audioPanelName) audioPanelName.textContent = file.name;
          setStatus(`${t("uploading", "Uploading")} ${file.name}`);
          const thumbnail = kind === "video" ? await thumbnailFromVideo(file) : "";
          const mediaSeconds = await mediaDuration(file, kind);
          const asset = await uploadAsset(file, kind, thumbnail, mediaSeconds);
          if (!asset) return;
          const track = state.tracks.find((item) => item.type === kind) || state.tracks[state.tracks.length - 1];
          const duration = asset.duration || (kind === "video" ? 12 : kind === "audio" ? 10 : 5);
          const clipDuration = kind === "image" ? 5 : duration;
          addClip({
            id: uid(kind),
            type: kind,
            trackId: track.id,
            assetId: asset.id,
            start: defaultStartForKind(kind),
            duration: clipDuration,
            sourceStart: 0,
            sourceEnd: clipDuration,
            x: 50,
            y: 50,
            scale: kind === "image" ? 42 : 100,
            style: {},
            text: "",
          });
        }
        function addTextClip() {
          const track = state.tracks.find((item) => item.type === "text") || state.tracks[1];
          addClip({
            id: uid("text"),
            type: "text",
            trackId: track.id,
            start: currentTime(),
            duration: 4,
            x: 50,
            y: 78,
            scale: 100,
            boxWidth: 38,
            text: t("your_headline", "Your headline"),
            style: {font: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif", size: 22, color: "#ffffff", stroke: "#000000", strokeWidth: 1, bg: "#000000", bgAlpha: 48},
          });
        }
        function addCaptionClip(text = t("caption", "Caption"), start = currentTime(), duration = 3, options = {}) {
          const track = state.tracks.find((item) => item.type === "text") || state.tracks[1];
          const style = {
            font: "system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
            size: 24,
            color: "#ffffff",
            stroke: "#000000",
            strokeWidth: 1,
            bg: "#000000",
            bgAlpha: 42,
            ...(options.style && typeof options.style === "object" ? options.style : {}),
          };
          const clip = {
            id: uid("caption"),
            type: "caption",
            trackId: track.id,
            start,
            duration,
            x: Number.isFinite(Number(options.x)) ? Number(options.x) : 50,
            y: Number.isFinite(Number(options.y)) ? Number(options.y) : 84,
            scale: Number.isFinite(Number(options.scale)) ? Number(options.scale) : 100,
            boxWidth: Number.isFinite(Number(options.boxWidth)) ? Math.max(18, Math.min(86, Number(options.boxWidth))) : 42,
            rotation: Number.isFinite(Number(options.rotation)) ? Number(options.rotation) : 0,
            text,
            style,
          };
          if (options.source && typeof options.source === "object") clip.subtitleSource = {...options.source};
          if (options.history === false) {
            state.clips.push(normalizeClip(clip));
            setSelection([clip.id], clip.id);
          } else {
            addClip(clip);
          }
        }
        function parseSubtitleTime(value) {
          const parts = String(value || "").replace(",", ".").split(":").map(Number);
          if (parts.length === 3) return parts[0] * 3600 + parts[1] * 60 + parts[2];
          if (parts.length === 2) return parts[0] * 60 + parts[1];
          return Number(parts[0] || 0);
        }
        function parseSubtitleText(text) {
          return String(text || "").replace(/\r/g, "").split(/\n\s*\n/).map((block) => {
            const lines = block.split("\n").filter(Boolean);
            const timeLine = lines.find((line) => line.includes("-->"));
            if (!timeLine) return null;
            const [startRaw, endRaw] = timeLine.split("-->").map((item) => item.trim().split(/\s+/)[0]);
            const textLines = lines.slice(lines.indexOf(timeLine) + 1).join(" ").trim();
            return {start: parseSubtitleTime(startRaw), end: parseSubtitleTime(endRaw), text: textLines || t("caption", "Caption")};
          }).filter(Boolean);
        }
        function addTrack(type) {
          pushHistory();
          const order = Math.max(0, ...state.tracks.map((track) => Number(track.order || 0))) + 1;
          state.tracks.push({id: uid(type), type, name: typeName(type), order});
          render();
          scheduleSave();
        }
        function deleteTrack(id) {
          const track = state.tracks.find((item) => item.id === id);
          if (!track || track.id === "video-main") return;
          pushHistory();
          state.tracks = state.tracks.filter((item) => item.id !== id);
          state.clips = state.clips.filter((clip) => clip.trackId !== id);
          normalizeSelection();
          render();
          scheduleSave();
        }
        function currentTime() {
          return projectTime;
        }
        function isClipActive(clip, at = projectTime) {
          return at >= Number(clip.start || 0) && at <= Number(clip.start || 0) + Number(clip.duration || 0);
        }
        function activeVideoClip() {
          return state.clips
            .filter((clip) => clip.type === "video" && isClipActive(clip))
            .sort((a, b) => (state.tracks.find((track) => track.id === b.trackId)?.order || 0) - (state.tracks.find((track) => track.id === a.trackId)?.order || 0))[0] || null;
        }
        function activeAudioClips() {
          return state.clips.filter((clip) => clip.type === "audio" && isClipActive(clip));
        }
        function isSubtitleSourceClip(clip) {
          return Boolean(clip && ["video", "audio"].includes(clip.type) && clip.assetId && assetById(clip.assetId));
        }
        function autoSubtitleSourceClip() {
          const selectedSource = [selectedClip(), ...selectedClips()].find(isSubtitleSourceClip);
          if (selectedSource) return selectedSource;
          const activeSource = [activeVideoClip(), ...activeAudioClips()].find(isSubtitleSourceClip);
          if (activeSource) return activeSource;
          return state.clips
            .filter(isSubtitleSourceClip)
            .sort((a, b) => Number(a.start || 0) - Number(b.start || 0))[0] || null;
        }
        function setAutoSubtitleStatus(message, stateName = "") {
          if (!autoSubtitleStatus) return;
          autoSubtitleStatus.textContent = message || "";
          autoSubtitleStatus.dataset.state = stateName;
        }
        function autoSubtitleErrorMessage(error) {
          const message = String(error?.message || "");
          if (error instanceof TypeError || /failed to fetch|networkerror|connection/i.test(message)) {
            return t("server_unavailable", "Server is unavailable. Start Django and try again.");
          }
          return message || t("auto_subtitles_failed", "Auto subtitles failed");
        }
        function closeAutoSubtitleLanguageChoice() {
          const choice = root.querySelector("[data-auto-subtitle-language-choice]");
          if (!choice) return;
          choice.classList.remove("is-open");
          choice.querySelector("[data-language-current]")?.setAttribute("aria-expanded", "false");
        }
        function setupAutoSubtitleLanguageChoice() {
          const choice = root.querySelector("[data-auto-subtitle-language-choice]");
          if (!choice || !autoSubtitleLanguage) return;
          const current = choice.querySelector("[data-language-current]");
          const currentLabel = current?.querySelector("b");
          const optionButtons = Array.from(choice.querySelectorAll("[data-language-value]"));
          const setLanguage = (button) => {
            if (!button) return;
            autoSubtitleLanguage.value = button.dataset.languageValue || "";
            if (currentLabel) currentLabel.textContent = button.textContent.trim();
            optionButtons.forEach((item) => {
              const selected = item === button;
              item.classList.toggle("is-selected", selected);
              item.setAttribute("aria-selected", selected ? "true" : "false");
            });
          };
          setLanguage(optionButtons.find((button) => button.classList.contains("is-selected")) || optionButtons[0]);
          current?.addEventListener("click", (event) => {
            event.stopPropagation();
            const open = !choice.classList.contains("is-open");
            root.querySelectorAll(".editor-language-choice.is-open").forEach((item) => {
              if (item !== choice) item.classList.remove("is-open");
            });
            choice.classList.toggle("is-open", open);
            current.setAttribute("aria-expanded", open ? "true" : "false");
          });
          optionButtons.forEach((button) => button.addEventListener("click", (event) => {
            event.stopPropagation();
            setLanguage(button);
            closeAutoSubtitleLanguageChoice();
          }));
          choice.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
              closeAutoSubtitleLanguageChoice();
              current?.focus();
            }
          });
        }
        function closeTextFontChoice() {
          const choice = root.querySelector("[data-text-font-choice]");
          if (!choice) return;
          clearTextFontPreview();
          choice.classList.remove("is-open");
          choice.querySelector("[data-font-current]")?.setAttribute("aria-expanded", "false");
        }
        function selectedTextOverlayContent() {
          if (!selectedClipId) return null;
          return overlayRoot.querySelector(`.editor-overlay-item[data-clip-id="${CSS.escape(selectedClipId)}"] .editor-overlay-text-content`);
        }
        function setTextFontCurrentPreview(value, label = "") {
          const choice = root.querySelector("[data-text-font-choice]");
          const current = choice?.querySelector("[data-font-current]");
          const currentLabel = current?.querySelector("b");
          if (current) current.style.fontFamily = value || "";
          if (currentLabel && label) currentLabel.textContent = label;
        }
        function previewTextFontValue(value, label = "") {
          const clip = selectedClip();
          if (!clip || !["text", "caption"].includes(clip.type)) return;
          const textNode = selectedTextOverlayContent();
          if (!textNode) return;
          textNode.dataset.fontPreview = "true";
          textNode.style.fontFamily = value;
          setTextFontCurrentPreview(value, label);
          root.querySelectorAll("[data-font-value]").forEach((button) => {
            button.classList.toggle("is-previewing", button.dataset.fontValue === value);
          });
        }
        function clearTextFontPreview() {
          const clip = selectedClip();
          const textNode = selectedTextOverlayContent();
          if (clip && textNode?.dataset.fontPreview === "true") {
            delete textNode.dataset.fontPreview;
            textNode.style.fontFamily = clip.style?.font || root.querySelector("[data-text-font]")?.value || "system-ui";
          }
          root.querySelectorAll("[data-font-value].is-previewing").forEach((button) => button.classList.remove("is-previewing"));
          const selected = root.querySelector("[data-text-font-choice] [data-font-value].is-selected");
          setTextFontCurrentPreview(selected?.dataset.fontValue || "", selected?.dataset.fontLabel || selected?.textContent?.trim() || "");
        }
        function setTextFontChoiceValue(value, options = {}) {
          const input = root.querySelector("[data-text-font]");
          const choice = root.querySelector("[data-text-font-choice]");
          if (!input || !choice) return;
          const buttons = Array.from(choice.querySelectorAll("[data-font-value]"));
          const selected = buttons.find((button) => button.dataset.fontValue === value) || buttons[0];
          if (!selected) return;
          input.value = selected.dataset.fontValue || "";
          const label = selected.dataset.fontLabel || selected.textContent.trim();
          setTextFontCurrentPreview(input.value, label);
          buttons.forEach((button) => {
            const active = button === selected;
            button.classList.toggle("is-selected", active);
            button.setAttribute("aria-selected", active ? "true" : "false");
          });
          if (options.emit) {
            input.dispatchEvent(new Event("input", {bubbles: true}));
            input.dispatchEvent(new Event("change", {bubbles: true}));
          }
        }
        function setupTextFontChoice() {
          const choice = root.querySelector("[data-text-font-choice]");
          const input = root.querySelector("[data-text-font]");
          if (!choice || !input) return;
          const current = choice.querySelector("[data-font-current]");
          const search = choice.querySelector("[data-font-search]");
          const buttons = Array.from(choice.querySelectorAll("[data-font-value]"));
          const filterFonts = () => {
            const query = String(search?.value || "").trim().toLowerCase();
            buttons.forEach((button) => {
              const label = `${button.dataset.fontLabel || ""} ${button.textContent || ""}`.toLowerCase();
              button.hidden = Boolean(query && !label.includes(query));
            });
          };
          setTextFontChoiceValue(input.value);
          choice.addEventListener("click", (event) => event.stopPropagation());
          current?.addEventListener("click", (event) => {
            event.stopPropagation();
            const open = !choice.classList.contains("is-open");
            choice.classList.toggle("is-open", open);
            current.setAttribute("aria-expanded", open ? "true" : "false");
            if (open) {
              if (search) {
                search.value = "";
                filterFonts();
                window.setTimeout(() => search.focus(), 0);
              }
            }
          });
          search?.addEventListener("input", filterFonts);
          buttons.forEach((button) => {
            const preview = () => previewTextFontValue(button.dataset.fontValue || "", button.dataset.fontLabel || button.textContent.trim());
            button.addEventListener("pointerenter", preview);
            button.addEventListener("focus", preview);
          });
          choice.querySelector("[data-font-options]")?.addEventListener("pointerleave", clearTextFontPreview);
          buttons.forEach((button) => button.addEventListener("click", (event) => {
            event.stopPropagation();
            setTextFontChoiceValue(button.dataset.fontValue || "", {emit: true});
            closeTextFontChoice();
          }));
          choice.addEventListener("keydown", (event) => {
            if (event.key === "Escape") {
              closeTextFontChoice();
              current?.focus();
            }
          });
        }
        function setupPropertyTabScroller() {
          const tabs = root.querySelector("[data-property-tabs]");
          const buttons = Array.from(root.querySelectorAll("[data-tab-scroll]"));
          if (!tabs || !buttons.length) return;
          const syncButtons = () => {
            const max = Math.max(0, tabs.scrollWidth - tabs.clientWidth - 1);
            buttons.forEach((button) => {
              const direction = Number(button.dataset.tabScroll || 0);
              button.disabled = direction < 0 ? tabs.scrollLeft <= 1 : tabs.scrollLeft >= max;
            });
          };
          buttons.forEach((button) => button.addEventListener("click", () => {
            const direction = Number(button.dataset.tabScroll || 0);
            tabs.scrollBy({left: direction * Math.max(96, Math.round(tabs.clientWidth * 0.72)), behavior: "smooth"});
            window.setTimeout(syncButtons, 220);
          }));
          tabs.addEventListener("scroll", syncButtons, {passive: true});
          window.addEventListener("resize", syncButtons);
          syncButtons();
        }
        async function generateAutoSubtitles() {
          if (readOnly || !autoSubtitleButton) return;
          const sourceClip = autoSubtitleSourceClip();
          if (!sourceClip) {
            setAutoSubtitleStatus(t("auto_subtitles_no_source", "Add or select a video/audio clip first."), "error");
            return;
          }
          autoSubtitleButton.disabled = true;
          autoSubtitleButton.classList.add("is-working");
          autoSubtitleButton.dataset.icon = "loader-circle";
          setAutoSubtitleStatus(t("auto_subtitles_running", "Transcribing audio..."), "busy");
          try {
            await ensureProject();
            if (dirty) await saveProject();
            const payload = {
              asset_id: sourceClip.assetId,
              language: autoSubtitleLanguage?.value || "auto",
              timeline_start: Number(sourceClip.start || 0),
              source_start: Number(sourceClip.sourceStart || 0),
              source_end: Number(sourceClip.sourceEnd || 0),
              clip_duration: Number(sourceClip.duration || 0),
            };
            const data = await jsonFetch(`${api}${projectId}/subtitles/auto/`, {method: "POST", body: JSON.stringify(payload)});
            if (data.job) {
              await pollAutoSubtitleJob(data.job);
              return;
            }
            const cues = Array.isArray(data.cues) ? data.cues : [];
            if (!cues.length) {
              setAutoSubtitleStatus(t("auto_subtitles_no_speech", "No speech detected in this clip."), "error");
              return;
            }
            pushHistory();
            cues.forEach((cue) => addCaptionClip(cue.text, cue.start, Math.max(0.2, cue.end - cue.start), {...cue, history: false}));
            render();
            scheduleSave();
            setAutoSubtitleStatus(`${t("auto_subtitles_done", "Subtitles added")}: ${cues.length}`, "ok");
          } catch (error) {
            setAutoSubtitleStatus(`${t("auto_subtitles_failed", "Auto subtitles failed")}: ${autoSubtitleErrorMessage(error)}`, "error");
          } finally {
            autoSubtitleButton.disabled = false;
            autoSubtitleButton.classList.remove("is-working");
            autoSubtitleButton.dataset.icon = "captions";
          }
        }
        async function pollAutoSubtitleJob(job) {
          if (!job?.id) return;
          setAutoSubtitleStatus(job.message || t("auto_subtitles_running", "Transcribing audio..."), "busy");
          if (job.status === "done") {
            applyAutoSubtitleJobResult(job);
            return;
          }
          if (job.status === "failed" || job.status === "cancelled") {
            throw new Error(job.error || job.message || t("auto_subtitles_failed", "Auto subtitles failed"));
          }
          await new Promise((resolve) => window.setTimeout(resolve, 1400));
          const data = await jsonFetch(`${api}${projectId}/export/${job.id}/`);
          await pollAutoSubtitleJob(data.job);
        }
        function applyAutoSubtitleJobResult(job) {
          const count = Number(job.cue_count || (Array.isArray(job.cues) ? job.cues.length : 0));
          if (job.project) {
            assets = job.project.assets || assets;
            state = normalizeState(job.project.state || state);
            normalizeSelection();
            render();
          } else if (Array.isArray(job.cues) && job.cues.length) {
            pushHistory();
            job.cues.forEach((cue) => addCaptionClip(cue.text, cue.start, Math.max(0.2, cue.end - cue.start), {...cue, history: false}));
            render();
            scheduleSave();
          }
          if (!count) {
            setAutoSubtitleStatus(t("auto_subtitles_no_speech", "No speech detected in this clip."), "error");
            return;
          }
          setAutoSubtitleStatus(`${t("auto_subtitles_done", "Subtitles added")}: ${count}`, "ok");
        }
        function clipFilterValue(clip) {
          const style = clip && clip.style ? clip.style : {};
          const preset = style.filter && style.filter !== "none" ? style.filter : "";
          const brightness = Number(style.brightness || 100);
          const contrast = Number(style.contrast || 100);
          const saturate = Number(style.saturate || 100);
          const custom = `brightness(${brightness / 100}) contrast(${contrast / 100}) saturate(${saturate / 100})`;
          return [preset, custom].filter(Boolean).join(" ");
        }
        function clipOpacityValue(clip) {
          return Math.max(0, Math.min(1, Number(clip?.style?.opacity ?? 100) / 100));
        }
        function clipVolumeValue(clip) {
          return Math.max(0, Math.min(1.5, Number(clip?.style?.volume ?? 1)));
        }
        function clipSpeedValue(clip) {
          return Math.max(0.25, Math.min(2, Number(clip?.style?.speed ?? 1)));
        }
        function videoFrameFit(clip) {
          const fit = clip?.style?.fit || "contain";
          return fit === "crop" ? "cover" : fit;
        }
        function videoScaleBounds(clip) {
          const fit = clip?.style?.fit || "contain";
          return fit === "cover" || fit === "crop" ? {min: 100, max: 300} : {min: 8, max: 300};
        }
        function videoFrameScale(clip) {
          const bounds = videoScaleBounds(clip);
          return Math.max(bounds.min, Math.min(bounds.max, Number(clip?.scale || 100)));
        }
        function ensureVideoReframeMode(clip) {
          if (!clip || clip.type !== "video") return;
          clip.style = clip.style || {};
          clip.x = Math.max(0, Math.min(100, Number.isFinite(Number(clip.x)) ? Number(clip.x) : 50));
          clip.y = Math.max(0, Math.min(100, Number.isFinite(Number(clip.y)) ? Number(clip.y) : 50));
          clip.scale = videoFrameScale(clip);
        }
        function applyVideoFrameStyle(clip) {
          if (!clip) {
            video.style.objectFit = "contain";
            video.style.objectPosition = "50% 50%";
            video.style.transform = "";
            video.style.transformOrigin = "50% 50%";
            frame.classList.remove("is-reframing-video");
            return;
          }
          const x = Math.max(0, Math.min(100, Number(clip.x ?? 50)));
          const y = Math.max(0, Math.min(100, Number(clip.y ?? 50)));
          const scale = videoFrameScale(clip) / 100;
          video.style.objectFit = videoFrameFit(clip);
          video.style.objectPosition = `${x}% ${y}%`;
          video.style.transform = scale > 1.001 ? `scale(${scale})` : "";
          video.style.transformOrigin = `${x}% ${y}%`;
          frame.classList.toggle("is-reframing-video", cropMode && clip.type === "video");
        }
        function selectedActiveVideoClip() {
          const clip = selectedClip();
          if (clip && clip.type === "video" && isClipActive(clip)) return clip;
          return null;
        }
        function fadeOpacity(clip, base = 1) {
          const offset = Math.max(0, projectTime - clip.start);
          const remaining = Math.max(0, clip.start + clip.duration - projectTime);
          const fadeIn = Number(clip.style?.fadeIn || 0);
          const fadeOut = Number(clip.style?.fadeOut || 0);
          let value = base;
          if (fadeIn > 0) value = Math.min(value, offset / fadeIn);
          if (fadeOut > 0) value = Math.min(value, remaining / fadeOut);
          return Math.max(0, Math.min(1, value));
        }
        function audioForAsset(asset) {
          if (!asset) return null;
          if (!audioPool.has(String(asset.id))) {
            const item = new Audio(asset.preview_url);
            item.preload = "metadata";
            audioPool.set(String(asset.id), item);
          }
          return audioPool.get(String(asset.id));
        }
        function syncMediaForProjectTime(shouldPlay = playing) {
          const clip = activeVideoClip();
          const asset = clip && assetById(clip.assetId);
          if (asset && clip) {
            if (!video.src.endsWith(asset.preview_url)) {
              video.src = asset.preview_url;
              video.load();
            }
            video.hidden = false;
            dropzone.hidden = true;
            video.style.filter = clipFilterValue(clip);
            video.style.opacity = String(fadeOpacity(clip, clipOpacityValue(clip)));
            applyVideoFrameStyle(clip);
            video.volume = clipVolumeValue(clip);
            video.playbackRate = clipSpeedValue(clip);
            const local = Math.max(clip.sourceStart || 0, Math.min(clip.sourceEnd || clip.duration, (clip.sourceStart || 0) + ((projectTime - clip.start) * clipSpeedValue(clip))));
            if (Math.abs((video.currentTime || 0) - local) > 0.18) video.currentTime = local;
            if (shouldPlay && video.paused) video.play().catch(() => {});
            activeVideoClipId = clip.id;
          } else {
            internalVideoPause = true;
            video.pause();
            internalVideoPause = false;
            activeVideoClipId = "";
            applyVideoFrameStyle(null);
            if (state.clips.some((item) => item.type === "video")) {
              video.hidden = true;
              dropzone.hidden = playing;
            } else {
              video.removeAttribute("src");
              video.hidden = true;
              dropzone.hidden = false;
            }
          }
          const activeAudioIds = new Set();
          activeAudioClips().forEach((audioClip) => {
            const audioAsset = assetById(audioClip.assetId);
            const media = audioForAsset(audioAsset);
            if (!media) return;
            activeAudioIds.add(String(audioAsset.id));
            const local = Math.max(audioClip.sourceStart || 0, Math.min(audioClip.sourceEnd || audioClip.duration, (audioClip.sourceStart || 0) + ((projectTime - audioClip.start) * clipSpeedValue(audioClip))));
            if (Math.abs((media.currentTime || 0) - local) > 0.18) media.currentTime = local;
            media.volume = clipVolumeValue(audioClip) * fadeOpacity(audioClip, 1);
            media.playbackRate = clipSpeedValue(audioClip);
            media.muted = video.muted;
            if (shouldPlay && media.paused) media.play().catch(() => {});
            if (!shouldPlay && !media.paused) media.pause();
          });
          audioPool.forEach((media, id) => {
            if (!activeAudioIds.has(id) && !media.paused) media.pause();
          });
        }
        function updateOverlayVisibility() {
          const now = currentTime();
          overlayRoot.querySelectorAll("[data-clip-id]").forEach((node) => {
            const clip = clipById(node.dataset.clipId);
            node.hidden = !clip || now < clip.start || now > clip.start + clip.duration;
          });
        }
        function applyBackgroundMode() {
          root.classList.toggle("has-blur-background", state.backgroundMode === "blur");
          root.classList.toggle("has-gradient-background", state.backgroundMode === "gradient");
          frame.style.background = state.backgroundMode === "gradient" ? "linear-gradient(135deg,#2563eb,#ec4899)" : (state.backgroundValue || state.background || "#020617");
        }
        function selectClip(id) {
          selectOnly(id);
          focusInspectorForClip(clipById(id));
          render();
        }
        function deleteSelectedClip() {
          deleteClipsByIds(selectedClipIdList());
        }
        async function confirmDeleteSelectedClip() {
          const count = selectedClipIds.size;
          if (!count) return;
          const ok = await askConfirm({
            title: count > 1 ? t("delete_selected_clips_question", "Delete selected clips?") : t("delete_clip_question", "Delete clip?"),
            copy: t("delete_selected_clips_copy", "This removes selected clips from the timeline."),
          });
          if (ok) deleteSelectedClip();
        }
        function deleteClipById(id) {
          deleteClipsByIds([id]);
        }
        function deleteClipsByIds(ids) {
          const targets = new Set(ids.filter(Boolean));
          if (!targets.size) return;
          pushHistory();
          state.clips = state.clips.filter((clip) => !targets.has(String(clip.id)));
          normalizeSelection();
          render();
          scheduleSave();
        }
        function render() {
          normalizeSelection();
          title.textContent = state.title || t("new_project", "New project");
          frame.style.setProperty("--editor-aspect", state.aspect || "9 / 16");
          syncAspectMenu();
          applyBackgroundMode();
          root.classList.toggle("is-compact-timeline", timelineDensity === "compact");
          renderTracks();
          renderPreview();
          renderProperties();
          renderMediaBin();
          sync();
        }
        function syncAspectMenu() {
          const compact = String(state.aspect || "9 / 16").replace(/\s+/g, "");
          const buttons = [...root.querySelectorAll("[data-aspect]")];
          const active = buttons.find((button) => button.dataset.aspect === compact) || buttons[0];
          buttons.forEach((button) => button.classList.toggle("is-active", button === active));
          if (!active) return;
          const label = active.querySelector("b")?.textContent || active.dataset.aspect || "9:16";
          const size = [active.dataset.label, active.dataset.size].filter(Boolean).join(" ");
          if (aspectCurrent) aspectCurrent.textContent = label;
          if (aspectSize) aspectSize.textContent = size || active.querySelector("small")?.textContent || "";
        }
        function closeAspectMenu() {
          if (!aspectOptions) return;
          aspectOptions.hidden = true;
          aspectMenu?.classList.remove("is-open");
          aspectToggle?.setAttribute("aria-expanded", "false");
        }
        function setAspectFromButton(button) {
          if (!button) return;
          state.aspect = button.dataset.aspect.replace("/", " / ");
          frame.style.setProperty("--editor-aspect", state.aspect);
          syncAspectMenu();
          closeAspectMenu();
          render();
          scheduleSave();
        }
        function renderTracks() {
          const duration = timelineDuration();
          const width = Math.max(720, secondsToPx(duration));
          timeline.style.setProperty("--timeline-width", `${width}px`);
          renderRuler(duration);
          const ordered = [...state.tracks].sort((a, b) => (a.order || 0) - (b.order || 0));
          trackList.replaceChildren(...ordered.map((track) => {
            const row = document.createElement("div");
            row.className = `editor-track is-${track.type}`;
            row.dataset.trackId = track.id;
            const label = document.createElement("div");
            label.className = "editor-track-label";
            label.title = track.name;
            const labelIcon = document.createElement("span");
            labelIcon.className = "editor-track-icon";
            labelIcon.dataset.icon = trackIcon(track.type);
            const removeTrack = document.createElement("button");
            removeTrack.className = "editor-icon-button";
            removeTrack.type = "button";
            removeTrack.title = t("delete", "Delete");
            removeTrack.dataset.icon = "trash-2";
            removeTrack.hidden = track.id === "video-main";
            removeTrack.addEventListener("click", () => deleteTrack(track.id));
            label.append(labelIcon, removeTrack);
            const lane = document.createElement("div");
            lane.className = "editor-track-lane";
            lane.dataset.trackId = track.id;
            lane.dataset.trackType = track.type;
            if (!state.clips.some((clip) => clip.trackId === track.id)) {
              const empty = document.createElement("span");
              empty.className = "editor-track-empty";
              empty.textContent = track.type === "video"
                ? t("empty_track_video", "Drop video or image here")
                : track.type === "text"
                  ? t("empty_track_text", "Double-click to add text")
                  : track.type === "audio"
                    ? t("empty_track_audio", "Drop audio here")
                    : t("empty_track_image", "Drop image here");
              lane.append(empty);
            }
            lane.addEventListener("dblclick", (event) => {
              if (track.type === "text") {
                seekFromClient(event.clientX);
                addTextClip();
              }
            });
            lane.addEventListener("dragover", (event) => {
              if (!hasDraggedFiles(event) && !hasDraggedAsset(event)) return;
              event.preventDefault();
              event.dataTransfer.dropEffect = "copy";
              lane.classList.add("is-drop-target");
              showSnapLine(pxToSeconds(event.clientX - timeRuler.getBoundingClientRect().left), true);
            });
            lane.addEventListener("dragleave", () => {
              lane.classList.remove("is-drop-target");
              showSnapLine(0, false);
            });
            lane.addEventListener("drop", async (event) => {
              const assetId = event.dataTransfer?.getData("application/x-cherryx-asset");
              if (assetId) {
                event.preventDefault();
                lane.classList.remove("is-drop-target");
                showSnapLine(0, false);
                const rect = timeRuler.getBoundingClientRect();
                addAssetToTimeline(assetById(assetId), {lane, start: pxToSeconds(event.clientX - rect.left)});
                return;
              }
              const files = droppedFiles(event);
              if (!files.length) return;
              event.preventDefault();
              lane.classList.remove("is-drop-target");
              showSnapLine(0, false);
              for (const [index, file] of files.entries()) {
                await handleTimelineDrop(file, lane, event.clientX, index * 0.35);
              }
            });
            state.clips.filter((clip) => clip.trackId === track.id).forEach((clip) => lane.append(renderClip(clip, duration)));
            row.append(label, lane);
            return row;
          }));
          requestAnimationFrame(updateTimelineScrollbar);
        }
        function renderRuler(duration) {
          const ticks = [];
          const max = Math.ceil(duration);
          for (let second = 0; second <= max; second += 1) {
            const tick = document.createElement("span");
            tick.className = `editor-ruler-tick${second % 5 === 0 ? " is-major" : ""}`;
            tick.style.left = `${secondsToPx(second)}px`;
            if (second % 5 === 0) tick.textContent = fmt(second);
            ticks.push(tick);
          }
          timeRuler.replaceChildren(...ticks);
        }
        function laneFromPoint(x, y, type) {
          const lanes = document.elementsFromPoint(x, y)
            .map((item) => item.closest ? item.closest(".editor-track-lane") : null)
            .filter(Boolean);
          return lanes.find((lane, index, list) => {
            if (list.indexOf(lane) !== index) return false;
            return lane.dataset.trackType === type || (type === "image" && lane.dataset.trackType === "video");
          }) || null;
        }
        function renderClip(clip, total) {
          const node = document.createElement("div");
          node.className = `editor-layer-clip is-${clip.type}${selectedClipIds.has(clip.id) ? " is-selected" : ""}${clip.id === selectedClipId ? " is-primary-selected" : ""}`;
          positionClipNode(node, clip);
          node.dataset.clipId = clip.id;
          node.innerHTML = `<span class="editor-trim-handle is-left" data-trim="left"></span><span class="editor-clip-kind" data-icon="${trackIcon(clip.type)}"></span><b></b><small></small><span class="editor-trim-handle is-right" data-trim="right"></span>`;
          const asset = assetById(clip.assetId);
          const clipTitle = clip.type === "text" ? clip.text : (asset && asset.name) || clip.type;
          node.querySelector("b").textContent = shortClipName(clipTitle);
          node.title = clipTitle;
          node.querySelector("small").textContent = `${fmt(clip.start)} - ${fmt(clip.start + clip.duration)}`;
          if (clip.type === "video" && asset && asset.thumbnail_url) node.style.setProperty("--clip-thumb", `url("${asset.thumbnail_url}")`);
          if (clip.type === "image" && asset && isImageAsset(asset) && asset.preview_url) node.style.setProperty("--clip-thumb", `url("${asset.preview_url}")`);
          if (["audio", "video"].includes(clip.type) && asset?.waveform_url) loadWaveform(asset, node);
          if (clip.type === "image" && asset && !isImageAsset(asset)) node.classList.add("is-document");
          if (clip.style?.transition && clip.style.transition !== "none") node.dataset.transition = clip.style.transition;
          node.addEventListener("pointerdown", (event) => {
            if (event.target.closest("button")) return;
            if (event.shiftKey) {
              toggleClipSelection(clip.id);
              render();
              node.dataset.skipClick = "true";
              event.preventDefault();
              return;
            }
            ensureClipSelected(clip.id);
            root.querySelectorAll(".editor-layer-clip").forEach((item) => item.classList.toggle("is-selected", item === node));
            node.classList.add("is-dragging");
            renderProperties();
            focusInspectorForClip(clip, {scroll: false});
            const mode = event.target.dataset.trim || "move";
            const lane = node.closest(".editor-track-lane");
            const groupClips = mode === "move" ? selectedClips().map((item) => ({id: item.id, start: item.start, trackId: item.trackId})) : [];
            draggingClip = {
              id: clip.id,
              mode,
              startX: event.clientX,
              startY: event.clientY,
              start: clip.start,
              duration: clip.duration,
              sourceStart: clip.sourceStart || 0,
              sourceEnd: clip.sourceEnd || clip.duration,
              laneRect: lane ? lane.getBoundingClientRect() : timeline.getBoundingClientRect(),
              groupClips,
            };
            pushHistory();
            if (node.isConnected) node.setPointerCapture(event.pointerId);
            event.preventDefault();
          });
          node.addEventListener("pointermove", (event) => {
            if (!draggingClip || draggingClip.id !== clip.id) return;
            const delta = pxDeltaToSeconds(event.clientX - draggingClip.startX);
            if (draggingClip.mode === "left") {
              const nextStart = Math.max(0, Math.min(draggingClip.start + draggingClip.duration - 0.25, draggingClip.start + delta));
              const sourceDelta = nextStart - draggingClip.start;
              clip.start = nextStart;
              clip.sourceStart = Math.max(0, draggingClip.sourceStart + sourceDelta);
              clip.duration = Math.max(0.25, draggingClip.duration - sourceDelta);
            } else if (draggingClip.mode === "right") {
              clip.duration = Math.max(0.25, draggingClip.duration + delta);
              clip.sourceEnd = Math.max((clip.sourceStart || 0) + 0.25, draggingClip.sourceStart + clip.duration);
            } else {
              const snapped = snapTime(draggingClip.start + delta, clip.id);
              const nextStart = snapped.value;
              const groupDelta = Math.max(-Math.min(...draggingClip.groupClips.map((item) => item.start)), nextStart - draggingClip.start);
              draggingClip.groupClips.forEach((item) => {
                const groupClip = clipById(item.id);
                if (!groupClip) return;
                groupClip.start = Math.max(0, item.start + groupDelta);
                const groupNode = root.querySelector(`.editor-layer-clip[data-clip-id="${CSS.escape(item.id)}"]`);
                if (groupNode) positionClipNode(groupNode, groupClip);
              });
              showSnapLine(nextStart, snapped.snapped);
              const lane = laneFromPoint(event.clientX, event.clientY, clip.type);
              if (lane && lane.dataset.trackId !== clip.trackId) {
                clip.trackId = lane.dataset.trackId;
                lane.append(node);
              }
            }
            positionClipNode(node, clip);
            node.querySelector("small").textContent = `${fmt(clip.start)} - ${fmt(clip.start + clip.duration)}`;
            sync();
          });
          const finishDrag = (event) => {
            if (event && node.hasPointerCapture(event.pointerId)) node.releasePointerCapture(event.pointerId);
            draggingClip = null;
            node.classList.remove("is-dragging");
            showSnapLine(0, false);
            renderTracks();
            renderProperties();
            scheduleSave();
          };
          node.addEventListener("pointerup", finishDrag);
          node.addEventListener("pointercancel", finishDrag);
          node.addEventListener("click", (event) => {
            if (node.dataset.skipClick) {
              delete node.dataset.skipClick;
              return;
            }
            if (event.shiftKey) toggleClipSelection(clip.id);
            else if (!selectedClipIds.has(clip.id) || selectedClipIds.size <= 1) selectOnly(clip.id);
            focusInspectorForClip(clip);
            render();
          });
          node.addEventListener("contextmenu", (event) => {
            event.preventDefault();
            ensureClipSelected(clip.id);
            root.querySelectorAll(".editor-layer-clip").forEach((item) => item.classList.toggle("is-selected", item === node));
            showClipMenu(event.clientX, event.clientY, node);
            renderProperties();
            focusInspectorForClip(clip, {scroll: false});
          });
          return node;
        }
        function positionClipNode(node, clip) {
          node.style.left = `${secondsToPx(clip.start)}px`;
          node.style.width = `${Math.max(36, secondsToPx(clip.duration))}px`;
        }
        function shortClipName(value) {
          const raw = String(value || "").trim();
          if (raw.length <= 18) return raw;
          const dot = raw.lastIndexOf(".");
          const ext = dot > 0 ? raw.slice(dot) : "";
          return `${raw.slice(0, 13)}вЂ¦${ext.slice(0, 5)}`;
        }
        async function loadWaveform(asset, node) {
          if (node.dataset.waveformLoaded || !asset.waveform_url) return;
          node.dataset.waveformLoaded = "true";
          try {
            let response = await fetch(asset.waveform_url, {headers: {"Accept": "application/json"}});
            if (!response.ok) response = await fetch(asset.waveform_url, {method: "POST", headers: {"Accept": "application/json", "X-CSRFToken": decodeURIComponent(csrf)}});
            const data = await response.json();
            const samples = (data.samples || []).slice(0, 64);
            if (!samples.length) return;
            const wave = document.createElement("span");
            wave.className = "editor-clip-waveform";
            wave.replaceChildren(...samples.map((sample) => {
              const bar = document.createElement("i");
              bar.style.height = `${Math.max(3, Math.round(Number(sample) * 18))}px`;
              return bar;
            }));
            node.append(wave);
          } catch (error) {
            node.dataset.waveformLoaded = "";
          }
        }
        function renderVideoReframeOverlay(clip) {
          const guide = document.createElement("div");
          guide.className = `editor-video-reframe${cropMode ? " is-active" : ""}`;
          guide.dataset.clipId = clip.id;
          guide.title = t("drag_to_reframe", "Drag to reframe");
          guide.innerHTML = "<span></span><i></i>";
          guide.addEventListener("pointerdown", startVideoReframeDrag);
          guide.addEventListener("pointermove", moveVideoReframe);
          guide.addEventListener("pointerup", finishVideoReframe);
          guide.addEventListener("pointercancel", finishVideoReframe);
          guide.addEventListener("wheel", handleVideoReframeWheel, {passive: false});
          return guide;
        }
        function startVideoReframeDrag(event) {
          if (readOnly || event.button !== 0) return;
          if (event.target.closest?.(".editor-overlay-item")) return;
          if (event.currentTarget === overlayRoot && event.target !== overlayRoot) return;
          const clip = selectedActiveVideoClip() || activeVideoClip();
          if (!clip || clip.type !== "video") return;
          if (event.currentTarget === video && !cropMode && selectedClip()?.id !== clip.id) {
            selectOnly(clip.id);
            render();
            return;
          }
          event.preventDefault();
          event.stopPropagation();
          selectOnly(clip.id);
          ensureVideoReframeMode(clip);
          pushHistory();
          const target = event.currentTarget;
          videoReframeDrag = {
            id: clip.id,
            startX: event.clientX,
            startY: event.clientY,
            x: clip.x ?? 50,
            y: clip.y ?? 50,
          };
          if (target.setPointerCapture) target.setPointerCapture(event.pointerId);
          target.classList?.add("is-dragging");
        }
        function moveVideoReframe(event) {
          if (!videoReframeDrag) return;
          const clip = clipById(videoReframeDrag.id);
          if (!clip) return;
          const rect = frame.getBoundingClientRect();
          const dx = ((event.clientX - videoReframeDrag.startX) / Math.max(1, rect.width)) * 100;
          const dy = ((event.clientY - videoReframeDrag.startY) / Math.max(1, rect.height)) * 100;
          clip.x = Math.max(0, Math.min(100, videoReframeDrag.x + dx));
          clip.y = Math.max(0, Math.min(100, videoReframeDrag.y + dy));
          applyVideoFrameStyle(clip);
          updateClipControls(clip);
        }
        function finishVideoReframe(event) {
          if (!videoReframeDrag) return;
          const target = event.currentTarget;
          if (target?.hasPointerCapture?.(event.pointerId)) target.releasePointerCapture(event.pointerId);
          target?.classList?.remove("is-dragging");
          videoReframeDrag = null;
          renderPreview();
          renderProperties();
          scheduleSave();
        }
        function handleVideoReframeWheel(event) {
          if (event.target.closest?.(".editor-overlay-item")) return;
          if (event.currentTarget === overlayRoot && event.target !== overlayRoot) return;
          const clip = selectedActiveVideoClip() || activeVideoClip();
          if (!clip || clip.type !== "video") return;
          event.preventDefault();
          event.stopPropagation();
          ensureVideoReframeMode(clip);
          selectOnly(clip.id);
          if (!videoWheelHistory) {
            pushHistory();
            videoWheelHistory = true;
          }
          clearTimeout(videoWheelTimer);
          videoWheelTimer = setTimeout(() => {
            videoWheelHistory = false;
          }, 450);
          const delta = event.deltaY > 0 ? -6 : 6;
          const bounds = videoScaleBounds(clip);
          clip.scale = Math.max(bounds.min, Math.min(bounds.max, videoFrameScale(clip) + delta));
          applyVideoFrameStyle(clip);
          updateClipControls(clip);
          scheduleSave();
        }
        function isTextOverlayClip(clip) {
          return clip && ["text", "caption"].includes(clip.type);
        }
        function textOverlayBoxWidth(clip) {
          return Math.max(18, Math.min(86, Number(clip?.boxWidth || (clip?.type === "caption" ? 42 : 36))));
        }
        function setTextOverlayBoxWidth(clip, width) {
          if (!isTextOverlayClip(clip)) return;
          clip.boxWidth = Math.max(18, Math.min(86, Number(width) || textOverlayBoxWidth(clip)));
        }
        function textOverlayFallback(clip) {
          return clip?.type === "caption" ? t("caption", "Caption") : t("text", "Text");
        }
        function normalizedOverlayText(node, fallback) {
          const raw = (node.innerText || node.textContent || "").replace(/\u00a0/g, " ").replace(/\r/g, "");
          return raw.split("\n").map((line) => line.replace(/[ \t]+$/g, "")).join("\n").trim() || fallback;
        }
        function setOverlayTextEditing(node, textLayer, clip, editing) {
          if (editing) {
            textEditSnapshot = snapshotState();
            node.dataset.editing = "true";
            textLayer.contentEditable = "true";
            textLayer.focus();
            const range = document.createRange();
            range.selectNodeContents(textLayer);
            range.collapse(false);
            const selection = window.getSelection();
            selection.removeAllRanges();
            selection.addRange(range);
            return;
          }
          delete node.dataset.editing;
          textLayer.contentEditable = "false";
          clip.text = normalizedOverlayText(textLayer, textOverlayFallback(clip));
          textLayer.textContent = clip.text;
          if (textEditSnapshot && snapshotState() !== textEditSnapshot) pushHistorySnapshot(textEditSnapshot);
          textEditSnapshot = "";
          updateTextControls(clip);
          renderTracks();
          scheduleSave();
        }
        function applyTextPreset(clip, preset) {
          if (!isTextOverlayClip(clip)) return;
          clip.style = {...(clip.style || {})};
          if (preset === "clean") {
            Object.assign(clip.style, {fontWeight: 760, strokeWidth: 0, bgAlpha: 28, textShadow: "0 8px 22px rgba(0,0,0,.34)", animation: "none"});
          } else if (preset === "caption") {
            Object.assign(clip.style, {fontWeight: 850, strokeWidth: 1, bgAlpha: 42, textShadow: "0 3px 0 rgba(0,0,0,.55), 0 10px 26px rgba(0,0,0,.28)", animation: "none"});
          } else if (preset === "headline") {
            Object.assign(clip.style, {fontWeight: 930, strokeWidth: 2, bgAlpha: 0, textShadow: "0 3px 0 rgba(0,0,0,.72), 0 12px 30px rgba(0,0,0,.34)", animation: "headline"});
          }
        }
        function createTextOverlayToolbar(clip, textLayer) {
          const toolbar = document.createElement("div");
          toolbar.className = "editor-overlay-text-toolbar";
          toolbar.contentEditable = "false";
          toolbar.setAttribute("aria-label", t("text", "Text"));
          const buttons = [
            {icon: "bold", title: t("bold", "Bold"), action: "bold"},
            {icon: "case-upper", title: t("uppercase", "Uppercase"), action: "uppercase"},
            {icon: "align-left", title: t("align_left", "Left"), action: "left"},
            {icon: "align-center", title: t("align_center", "Center"), action: "center"},
            {icon: "align-right", title: t("align_right", "Right"), action: "right"},
            {icon: "sparkles", title: "Clean", action: "preset-clean"},
            {icon: "captions", title: t("caption", "Caption"), action: "preset-caption"},
          ];
          buttons.forEach((item) => {
            const button = document.createElement("button");
            button.type = "button";
            button.title = item.title;
            button.setAttribute("aria-label", item.title);
            button.dataset.icon = item.icon;
            button.dataset.textOverlayAction = item.action;
            if (item.action === "bold" && Number(clip.style?.fontWeight || 850) >= 850) button.classList.add("is-active");
            if (item.action === "uppercase" && clip.style?.textTransform === "uppercase") button.classList.add("is-active");
            if (item.action === (clip.style?.textAlign || "center")) button.classList.add("is-active");
            toolbar.append(button);
          });
          toolbar.addEventListener("pointerdown", (event) => {
            event.stopPropagation();
          });
          toolbar.addEventListener("click", (event) => {
            const button = event.target.closest("[data-text-overlay-action]");
            if (!button) return;
            event.preventDefault();
            event.stopPropagation();
            pushHistory();
            clip.style = {...(clip.style || {})};
            const action = button.dataset.textOverlayAction;
            if (action === "bold") clip.style.fontWeight = Number(clip.style.fontWeight || 850) >= 850 ? 700 : 900;
            if (action === "uppercase") clip.style.textTransform = clip.style.textTransform === "uppercase" ? "none" : "uppercase";
            if (["left", "center", "right"].includes(action)) clip.style.textAlign = action;
            if (action === "preset-clean") applyTextPreset(clip, "clean");
            if (action === "preset-caption") applyTextPreset(clip, "caption");
            applyTextStyle(textLayer, clip.style);
            updateTextControls(clip);
            renderPreview();
            scheduleSave();
          });
          return toolbar;
        }
        function clampOverlayClipToFrame(clip, node, rect = frame.getBoundingClientRect()) {
          if (!clip || !node || !rect.width || !rect.height) return;
          if (isTextOverlayClip(clip)) {
            const loose = Boolean(draggingOverlay?.free);
            clip.x = clampOverlayPositionValue(clip.x ?? 50, clip, loose);
            clip.y = clampOverlayPositionValue(clip.y ?? 50, clip, loose);
            node.style.left = `${clip.x}%`;
            node.style.top = `${clip.y}%`;
            return;
          }
          const marginPx = 8;
          const halfWidthPct = Math.min(48, ((node.offsetWidth / 2 + marginPx) / rect.width) * 100);
          const halfHeightPct = Math.min(48, ((node.offsetHeight / 2 + marginPx) / rect.height) * 100);
          clip.x = Math.max(halfWidthPct, Math.min(100 - halfWidthPct, Number(clip.x ?? 50)));
          clip.y = Math.max(halfHeightPct, Math.min(100 - halfHeightPct, Number(clip.y ?? 50)));
          node.style.left = `${clip.x}%`;
          node.style.top = `${clip.y}%`;
        }
        function commitOverlayDragHistory() {
          if (!draggingOverlay?.beforeSnapshot || draggingOverlay.historyCommitted) return;
          if (snapshotState() === draggingOverlay.beforeSnapshot) return;
          pushHistorySnapshot(draggingOverlay.beforeSnapshot);
          draggingOverlay.historyCommitted = true;
        }
        function finishActiveOverlayDrag() {
          if (!draggingOverlay) return;
          if (draggingOverlay.beforeSnapshot && !draggingOverlay.historyCommitted && snapshotState() !== draggingOverlay.beforeSnapshot) {
            pushHistorySnapshot(draggingOverlay.beforeSnapshot);
          }
          draggingOverlay = null;
          scheduleSave();
        }
        function renderPreview() {
          const hasVideo = state.clips.some((clip) => clip.type === "video");
          const hasActiveVisual = state.clips.some((clip) => ["video", "image"].includes(clip.type) && isClipActive(clip));
          if (!hasVideo) {
            video.removeAttribute("src");
            video.hidden = true;
            dropzone.hidden = false;
          } else {
            dropzone.hidden = playing || hasActiveVisual;
          }
          overlayRoot.replaceChildren();
          const reframeClip = selectedActiveVideoClip();
          if (reframeClip) overlayRoot.append(renderVideoReframeOverlay(reframeClip));
          state.clips.filter((clip) => ["text", "caption", "image"].includes(clip.type)).forEach((clip) => {
            const node = document.createElement("div");
            node.className = `editor-overlay-item is-${clip.type}${clip.id === selectedClipId ? " is-selected" : ""}`;
            node.dataset.clipId = clip.id;
            node.style.left = `${clip.x ?? 50}%`;
            node.style.top = `${clip.y ?? 50}%`;
            node.style.transform = `translate(-50%, -50%) rotate(${clip.rotation || 0}deg)`;
            node.style.width = clip.type === "image" ? `${clip.scale || 42}%` : `${textOverlayBoxWidth(clip)}%`;
            node.style.zIndex = String(clip.style?.zIndex || 2);
            if (clip.type === "image") {
              const asset = assetById(clip.assetId);
              if (asset && isImageAsset(asset)) {
                const img = document.createElement("img");
                img.src = asset.preview_url;
                img.alt = "";
                img.style.filter = clipFilterValue(clip);
                img.style.opacity = String(fadeOpacity(clip, clipOpacityValue(clip)));
                img.style.objectFit = clip.style?.fit === "cover" || clip.style?.fit === "crop" ? "cover" : "contain";
                if (clip.style?.crop) {
                  const crop = clip.style.crop;
                  img.style.clipPath = `inset(${crop.y}% ${Math.max(0, 100 - crop.x - crop.width)}% ${Math.max(0, 100 - crop.y - crop.height)}% ${crop.x}%)`;
                }
                node.append(img);
              } else {
                const fileCard = document.createElement("div");
                fileCard.className = "editor-file-overlay";
                fileCard.innerHTML = `<i data-icon="file-text"></i><b></b><small></small>`;
                fileCard.querySelector("b").textContent = asset?.name || "File";
                fileCard.querySelector("small").textContent = asset?.media_type || "document";
                fileCard.style.opacity = String(fadeOpacity(clip, clipOpacityValue(clip)));
                node.append(fileCard);
              }
              if (cropMode && clip.id === selectedClipId && clip.style?.crop) {
                const crop = clip.style.crop;
                const cropBox = document.createElement("span");
                cropBox.className = "editor-crop-box";
                cropBox.style.left = `${crop.x}%`;
                cropBox.style.top = `${crop.y}%`;
                cropBox.style.width = `${crop.width}%`;
                cropBox.style.height = `${crop.height}%`;
                ["nw", "ne", "sw", "se"].forEach((corner) => {
                  const handle = document.createElement("i");
                  handle.dataset.cropHandle = corner;
                  cropBox.append(handle);
                });
                node.append(cropBox);
              }
              const resize = document.createElement("span");
              resize.className = "editor-overlay-handle is-resize";
              resize.dataset.overlayHandle = "resize";
              resize.title = t("size", "Size");
              const rotate = document.createElement("span");
              rotate.className = "editor-overlay-handle is-rotate";
              rotate.dataset.overlayHandle = "rotate";
              rotate.title = t("rotation", "Rotation");
              const remove = document.createElement("button");
              remove.type = "button";
              remove.className = "editor-overlay-delete";
              remove.dataset.overlayDelete = "true";
              remove.dataset.icon = "trash-2";
              remove.title = t("delete", "Delete");
              remove.setAttribute("aria-label", t("delete", "Delete"));
              node.append(resize, rotate, remove);
            } else {
              node.contentEditable = "false";
              node.spellcheck = false;
              const textLayer = document.createElement("span");
              textLayer.className = "editor-overlay-text-content";
              textLayer.contentEditable = "false";
              textLayer.spellcheck = false;
              textLayer.textContent = clip.text || textOverlayFallback(clip);
              applyTextStyle(textLayer, clip.style || {});
              node.style.opacity = String(fadeOpacity(clip, clipOpacityValue(clip)));
              const guide = document.createElement("span");
              guide.className = "editor-overlay-text-guide";
              guide.textContent = `${Math.round(textOverlayBoxWidth(clip))}%`;
              guide.contentEditable = "false";
              const resizeLeft = document.createElement("span");
              resizeLeft.contentEditable = "false";
              resizeLeft.className = "editor-overlay-handle is-resize is-left";
              resizeLeft.dataset.overlayHandle = "resize-left";
              resizeLeft.title = t("width", "Width");
              const resizeRight = document.createElement("span");
              resizeRight.contentEditable = "false";
              resizeRight.className = "editor-overlay-handle is-resize is-right";
              resizeRight.dataset.overlayHandle = "resize-right";
              resizeRight.title = t("width", "Width");
              const rotate = document.createElement("span");
              rotate.contentEditable = "false";
              rotate.className = "editor-overlay-handle is-rotate";
              rotate.dataset.overlayHandle = "rotate";
              rotate.title = t("rotation", "Rotation");
              node.append(textLayer, guide, resizeLeft, resizeRight, rotate);
              if (clip.id === selectedClipId) node.append(createTextOverlayToolbar(clip, textLayer));
              textLayer.addEventListener("input", () => {
                clip.text = normalizedOverlayText(textLayer, textOverlayFallback(clip));
                updateTextControls(clip);
                renderTracks();
                scheduleSave();
              });
              textLayer.addEventListener("dblclick", (event) => {
                event.stopPropagation();
                event.preventDefault();
                selectOnly(clip.id);
                focusInspectorForClip(clip, {scroll: false});
                setOverlayTextEditing(node, textLayer, clip, true);
              });
              textLayer.addEventListener("keydown", (event) => {
                if (node.dataset.editing !== "true") return;
                if (event.key === "Enter" && !event.shiftKey) {
                  event.preventDefault();
                  textLayer.blur();
                }
                if (event.key === "Escape") {
                  event.preventDefault();
                  textLayer.textContent = clip.text || textOverlayFallback(clip);
                  textLayer.blur();
                }
              });
              textLayer.addEventListener("blur", () => {
                if (node.dataset.editing !== "true") return;
                setOverlayTextEditing(node, textLayer, clip, false);
              });
            }
            node.addEventListener("contextmenu", (event) => {
              event.preventDefault();
              event.stopPropagation();
              selectOnly(clip.id);
              renderProperties();
              focusInspectorForClip(clip, {scroll: false});
              overlayRoot.querySelectorAll(".editor-overlay-item").forEach((item) => item.classList.toggle("is-selected", item === node));
              showClipMenu(event.clientX, event.clientY, node);
            });
            node.addEventListener("pointerdown", (event) => {
              if (node.dataset.editing === "true") return;
              if (event.target.closest("[data-text-overlay-action]")) return;
              if (event.target.closest("[data-overlay-delete]")) {
                event.stopPropagation();
                event.preventDefault();
                deleteClipById(clip.id);
                return;
              }
              selectOnly(clip.id);
              renderProperties();
              focusInspectorForClip(clip, {scroll: false});
              overlayRoot.querySelectorAll(".editor-overlay-item").forEach((item) => item.classList.toggle("is-selected", item === node));
              const rect = frame.getBoundingClientRect();
              const handle = event.target.dataset.cropHandle ? `crop-${event.target.dataset.cropHandle}` : (event.target.dataset.overlayHandle || "move");
              const beforeOverlayDrag = snapshotState();
              draggingOverlay = {
                id: clip.id,
                mode: handle,
                beforeSnapshot: beforeOverlayDrag,
                startX: event.clientX,
                startY: event.clientY,
                x: clip.x ?? 50,
                y: clip.y ?? 50,
                scale: clip.scale || 42,
                boxWidth: textOverlayBoxWidth(clip),
                rotation: clip.rotation || 0,
                crop: {...(clip.style?.crop || {x: 10, y: 10, width: 80, height: 80})},
                free: event.altKey,
                centerX: rect.left + ((clip.x ?? 50) / 100) * rect.width,
                centerY: rect.top + ((clip.y ?? 50) / 100) * rect.height,
                frameWidth: rect.width,
              };
              if (node.isConnected) node.setPointerCapture(event.pointerId);
              event.preventDefault();
            });
            node.addEventListener("pointermove", (event) => {
              if (!draggingOverlay || draggingOverlay.id !== clip.id) return;
              const rect = frame.getBoundingClientRect();
              draggingOverlay.free = Boolean(event.altKey);
              if (String(draggingOverlay.mode).startsWith("crop-")) {
                clip.style = clip.style || {};
                const dx = ((event.clientX - draggingOverlay.startX) / rect.width) * 100;
                const dy = ((event.clientY - draggingOverlay.startY) / rect.height) * 100;
                const crop = {...draggingOverlay.crop};
                if (draggingOverlay.mode.includes("e")) crop.width = Math.max(10, Math.min(100 - crop.x, draggingOverlay.crop.width + dx));
                if (draggingOverlay.mode.includes("s")) crop.height = Math.max(10, Math.min(100 - crop.y, draggingOverlay.crop.height + dy));
                if (draggingOverlay.mode.includes("w")) {
                  crop.x = Math.max(0, Math.min(draggingOverlay.crop.x + dx, draggingOverlay.crop.x + draggingOverlay.crop.width - 10));
                  crop.width = draggingOverlay.crop.width + (draggingOverlay.crop.x - crop.x);
                }
                if (draggingOverlay.mode.includes("n")) {
                  crop.y = Math.max(0, Math.min(draggingOverlay.crop.y + dy, draggingOverlay.crop.y + draggingOverlay.crop.height - 10));
                  crop.height = draggingOverlay.crop.height + (draggingOverlay.crop.y - crop.y);
                }
                clip.style.crop = crop;
                renderPreview();
              } else if (String(draggingOverlay.mode).startsWith("resize")) {
                if (isTextOverlayClip(clip)) {
                  const dx = ((event.clientX - draggingOverlay.startX) / rect.width) * 100;
                  const nextWidth = draggingOverlay.mode === "resize-left" ? draggingOverlay.boxWidth - dx * 2 : draggingOverlay.boxWidth + dx * 2;
                  setTextOverlayBoxWidth(clip, nextWidth);
                  node.style.width = `${textOverlayBoxWidth(clip)}%`;
                  const guide = node.querySelector(".editor-overlay-text-guide");
                  if (guide) guide.textContent = `${Math.round(textOverlayBoxWidth(clip))}%`;
                  clampOverlayClipToFrame(clip, node, rect);
                } else {
                  const distance = Math.hypot(event.clientX - draggingOverlay.centerX, event.clientY - draggingOverlay.centerY);
                  clip.scale = Math.max(8, Math.min(120, (distance * 2 / draggingOverlay.frameWidth) * 100));
                  node.style.width = `${clip.scale}%`;
                }
              } else if (draggingOverlay.mode === "rotate") {
                const radians = Math.atan2(event.clientY - draggingOverlay.centerY, event.clientX - draggingOverlay.centerX);
                clip.rotation = Math.round((radians * 180 / Math.PI) + 90);
                node.style.transform = `translate(-50%, -50%) rotate(${clip.rotation}deg)`;
              } else {
                clip.x = clampOverlayPositionValue(((event.clientX - rect.left) / rect.width) * 100, clip, event.altKey);
                clip.y = clampOverlayPositionValue(((event.clientY - rect.top) / rect.height) * 100, clip, event.altKey);
                clampOverlayClipToFrame(clip, node, rect);
              }
              commitOverlayDragHistory();
            });
            const finishOverlayDrag = (event) => {
              if (node.hasPointerCapture(event.pointerId)) node.releasePointerCapture(event.pointerId);
              finishActiveOverlayDrag();
            };
            node.addEventListener("pointerup", finishOverlayDrag);
            node.addEventListener("pointercancel", finishOverlayDrag);
            node.addEventListener("wheel", (event) => {
              if (!["image", "text", "caption"].includes(clip.type)) return;
              event.preventDefault();
              if (isTextOverlayClip(clip)) {
                setTextOverlayBoxWidth(clip, textOverlayBoxWidth(clip) + (event.deltaY > 0 ? -2 : 2));
                node.style.width = `${textOverlayBoxWidth(clip)}%`;
                clampOverlayClipToFrame(clip, node);
              } else {
                clip.scale = Math.max(10, Math.min(96, (clip.scale || 42) + (event.deltaY > 0 ? -3 : 3)));
                node.style.width = `${clip.scale}%`;
              }
              scheduleSave();
            }, {passive: false});
            overlayRoot.append(node);
            if (isTextOverlayClip(clip)) clampOverlayClipToFrame(clip, node);
          });
          updateOverlayVisibility();
          syncMediaForProjectTime(false);
        }
        function renderProperties() {
          const clip = selectedClip();
          toolTitle.textContent = selectedClipIds.size > 1 ? `${selectedClipIds.size} clips selected` : (clip ? `${typeName(clip.type)} - ${fmt(clip.start)} - ${fmt(clip.start + clip.duration)}` : "Project");
          if (clip && ["text", "caption"].includes(clip.type)) updateTextControls(clip);
          updateClipControls(clip);
          updateEffectControls(clip);
        }
        function updateClipControls(clip) {
          const set = (selector, value, disabled = !clip) => {
            const input = root.querySelector(selector);
            if (!input) return;
            input.value = value;
            input.disabled = disabled;
          };
          const style = clip?.style || {};
          const canPosition = Boolean(clip && ["text", "caption", "image", "video"].includes(clip.type));
          const canZoom = Boolean(clip && ["image", "video"].includes(clip.type));
          set("[data-clip-start]", clip ? clip.start.toFixed(2) : "");
          set("[data-clip-duration]", clip ? clip.duration.toFixed(2) : "");
          set("[data-clip-end]", clip ? (clip.start + clip.duration).toFixed(2) : "");
          set("[data-clip-x]", clip ? Math.round(clip.x ?? 50) : "", !canPosition);
          set("[data-clip-y]", clip ? Math.round(clip.y ?? 50) : "", !canPosition);
          set("[data-clip-scale]", clip ? Math.round(clip.scale ?? (clip.type === "image" ? 42 : 100)) : "", !canZoom);
          set("[data-clip-rotation]", clip ? Math.round(clip.rotation ?? 0) : "", !clip || !["text", "caption", "image"].includes(clip.type));
          set("[data-clip-fit]", style.fit || "contain", !clip || !["video", "image"].includes(clip.type));
          set("[data-clip-speed]", String(style.speed || 1), !clip || !["video", "audio"].includes(clip.type));
          updateChoice("clip-fit", style.fit || "contain", !clip || !["video", "image"].includes(clip.type));
          updateChoice("clip-speed", String(style.speed || 1), !clip || !["video", "audio"].includes(clip.type));
          const fadeIn = root.querySelector("[data-fade-in]");
          const fadeOut = root.querySelector("[data-fade-out]");
          const transition = root.querySelector("[data-transition]");
          if (fadeIn) { fadeIn.value = style.fadeIn || 0; fadeIn.disabled = !clip; }
          if (fadeOut) { fadeOut.value = style.fadeOut || 0; fadeOut.disabled = !clip; }
          if (transition) { transition.value = style.transition || "none"; transition.disabled = !clip || clip.type !== "video"; }
          root.querySelector("[data-fade-in-label]").textContent = `${Number(fadeIn?.value || 0).toFixed(1)}s`;
          root.querySelector("[data-fade-out-label]").textContent = `${Number(fadeOut?.value || 0).toFixed(1)}s`;
        }
        function updateChoice(name, value, disabled = false) {
          const choice = root.querySelector(`[data-choice="${name}"]`);
          if (!choice) return;
          const current = choice.querySelector("[data-choice-current]");
          const selected = choice.querySelector(`[data-choice-value="${CSS.escape(String(value))}"]`);
          if (current) {
            current.textContent = selected ? selected.textContent : value;
            current.disabled = disabled;
          }
          choice.querySelectorAll("[data-choice-value]").forEach((button) => {
            button.classList.toggle("is-selected", button.dataset.choiceValue === String(value));
            button.disabled = disabled;
          });
        }
        function applyTextStyle(node, style) {
          const bg = hexToRgb(style.bg || "#000000");
          const alpha = Math.max(0, Math.min(100, Number(style.bgAlpha ?? 48))) / 100;
          node.style.fontFamily = style.font || "system-ui";
          node.style.fontSize = `${style.size || 22}px`;
          node.style.fontWeight = String(style.fontWeight || 850);
          node.style.color = style.color || "#ffffff";
          node.style.background = `rgba(${bg.r}, ${bg.g}, ${bg.b}, ${alpha})`;
          node.style.webkitTextStroke = `${style.strokeWidth || 0}px ${style.stroke || "#000000"}`;
          node.style.textShadow = style.textShadow || "0 3px 0 rgba(0,0,0,.55)";
          node.style.textAlign = style.textAlign || "center";
          node.style.lineHeight = String(style.lineHeight || 1.12);
          node.style.letterSpacing = `${Number(style.letterSpacing || 0)}px`;
          node.style.textTransform = style.textTransform || "none";
          node.dataset.subtitleAnimation = style.animation || "none";
          if (node.parentElement?.classList.contains("editor-overlay-item")) {
            node.parentElement.dataset.subtitleAnimation = style.animation || "none";
          }
        }
        function updateTextControls(clip) {
          clip.style = clip.style || {};
          root.querySelector("[data-text-value]").value = clip.text || "";
          setTextFontChoiceValue(clip.style.font || root.querySelector("[data-text-font]").value);
          root.querySelector("[data-text-size]").value = clip.style.size || 22;
          root.querySelector("[data-text-color]").value = clip.style.color || "#ffffff";
          root.querySelector("[data-text-stroke]").value = clip.style.stroke || "#000000";
          root.querySelector("[data-text-stroke-width]").value = clip.style.strokeWidth || 0;
          root.querySelector("[data-text-bg]").value = clip.style.bg || "#000000";
          root.querySelector("[data-text-bg-alpha]").value = clip.style.bgAlpha ?? 48;
          root.querySelector("[data-text-size-label]").textContent = root.querySelector("[data-text-size]").value;
          root.querySelector("[data-text-stroke-width-label]").textContent = root.querySelector("[data-text-stroke-width]").value;
          root.querySelector("[data-text-bg-alpha-label]").textContent = `${root.querySelector("[data-text-bg-alpha]").value}%`;
        }
        function updateEffectControls(clip) {
          const style = clip && clip.style ? clip.style : {};
          const volume = root.querySelector("[data-volume]");
          const volumeLabel = root.querySelector("[data-volume-label]");
          if (volume) {
            volume.value = String(style.volume ?? 1);
            volume.disabled = !clip || !["video", "audio"].includes(clip.type);
          }
          if (volumeLabel) volumeLabel.textContent = `${Math.round(Number(volume?.value || 1) * 100)}%`;
          ["brightness", "contrast", "saturate", "opacity"].forEach((name) => {
            const input = root.querySelector(`[data-filter-${name}]`);
            const label = root.querySelector(`[data-filter-${name}-label]`);
            const fallback = name === "opacity" ? 100 : 100;
            if (input) {
              input.value = String(style[name] ?? fallback);
              input.disabled = !clip || !["video", "image"].includes(clip.type);
            }
            if (label) label.textContent = `${input ? input.value : fallback}%`;
          });
          root.querySelectorAll("[data-filter]").forEach((button) => {
            button.classList.toggle("is-selected", (style.filter || "none") === button.dataset.filter);
          });
        }
        function applyClipEffects() {
          const clip = selectedClip();
          if (!clip) return;
          clip.style = clip.style || {};
          renderPreview();
          syncMediaForProjectTime(playing);
          updateClipControls(clip);
          updateEffectControls(clip);
          scheduleSave();
        }
        function duplicateSelectedClip() {
          const clips = selectedClips();
          if (!clips.length) return;
          pushHistory();
          const copies = clips.map((clip) => normalizeClip({...clip, id: uid(`${clip.type}-copy`), start: clip.start + Math.min(1, Math.max(0.25, clip.duration * 0.15))}));
          state.clips.push(...copies);
          setSelection(copies.map((clip) => clip.id), copies[0].id);
          render();
          scheduleSave();
        }
        function assetTimelineKind(asset) {
          return asset.kind === "image" ? "image" : asset.kind;
        }
        function assetMatchesFilter(asset) {
          if (mediaFilter === "all") return true;
          if (mediaFilter === "docs") return asset.kind === "image" && asset.visual_kind && asset.visual_kind !== "image";
          if (mediaFilter === "image") return asset.kind === "image" && (!asset.visual_kind || asset.visual_kind === "image");
          return asset.kind === mediaFilter;
        }
        function textClipMatchesFilter() {
          return mediaFilter === "all" || mediaFilter === "text";
        }
        function preferredTrackForAsset(asset, lane = null) {
          const kind = assetTimelineKind(asset);
          const laneType = lane?.dataset?.trackType || "";
          if (kind === "audio" && laneType === "audio") return lane.dataset.trackId;
          if (kind !== "audio" && ["video", "image"].includes(laneType)) return lane.dataset.trackId;
          return (state.tracks.find((item) => item.type === kind)?.id || state.tracks.find((item) => item.type === "video")?.id || state.tracks[0]?.id);
        }
        function addAssetToTimeline(asset, options = {}) {
          if (!asset) return;
          const kind = assetTimelineKind(asset);
          const trackId = options.trackId || preferredTrackForAsset(asset, options.lane);
          const duration = kind === "image" ? 5 : Math.max(1, Number(asset.duration || 5));
          addClip({
            id: uid(kind),
            type: kind,
            trackId,
            assetId: asset.id,
            start: Number.isFinite(options.start) ? Math.max(0, options.start) : defaultStartForKind(kind),
            duration,
            sourceStart: 0,
            sourceEnd: duration,
            x: 50,
            y: 50,
            scale: kind === "image" ? 42 : 100,
            style: {},
            text: "",
          });
        }
        async function renameAsset(asset, name) {
          const next = String(name || "").trim();
          if (!asset || !asset.rename_url || !next || next === asset.name) return;
          const data = await jsonFetch(asset.rename_url, {method: "POST", body: JSON.stringify({name: next})});
          assets = data.project.assets || assets.map((item) => item.id === asset.id ? data.asset : item);
          render();
        }
        function showAssetPreview(asset, event) {
          if (!assetPreview || !asset) return;
          assetPreview.hidden = false;
          assetPreview.className = `editor-asset-preview is-${asset.kind}`;
          if ((asset.thumbnail_url || isImageAsset(asset)) && asset.preview_url) {
            assetPreview.innerHTML = `<div></div><b></b><small></small>`;
            assetPreview.querySelector("div").style.backgroundImage = `url("${asset.thumbnail_url || asset.preview_url}")`;
          } else {
            assetPreview.innerHTML = `<i data-icon="file-text"></i><b></b><small></small>`;
          }
          assetPreview.querySelector("b").textContent = asset.name || "Asset";
          assetPreview.querySelector("small").textContent = `${asset.visual_kind || asset.kind} - ${asset.size_text || ""}`;
          const left = Math.min(window.innerWidth - 238, event.clientX + 16);
          const top = Math.min(window.innerHeight - 190, event.clientY + 16);
          assetPreview.style.left = `${Math.max(8, left)}px`;
          assetPreview.style.top = `${Math.max(8, top)}px`;
        }
        function hideAssetPreview() {
          if (assetPreview) assetPreview.hidden = true;
        }
        async function deleteAsset(asset) {
          if (!asset || !asset.delete_url) return;
          pushHistory();
          const data = await jsonFetch(asset.delete_url, {method: "POST"});
          assets = data.project.assets || assets.filter((item) => item.id !== asset.id);
          state = normalizeState(data.project.state || state);
          normalizeSelection();
          render();
        }
        function renderMediaBin() {
          if (!mediaBin) return;
          const visibleAssets = assets.filter(assetMatchesFilter);
          const visibleTextClips = textClipMatchesFilter() ? state.clips.filter((clip) => ["text", "caption"].includes(clip.type)) : [];
          if (!visibleAssets.length && !visibleTextClips.length) {
            mediaBin.innerHTML = "";
            const empty = document.createElement("div");
            empty.className = "editor-media-empty";
            empty.textContent = t("no_media_or_text_yet", "No media or text yet");
            mediaBin.append(empty);
            return;
          }
          const textItems = visibleTextClips.map((clip) => {
            const item = document.createElement("article");
            item.className = `editor-media-item is-text${selectedClipIds.has(clip.id) ? " is-selected" : ""}`;
            const preview = document.createElement("button");
            preview.type = "button";
            preview.className = "editor-media-preview";
            preview.dataset.icon = clip.type === "caption" ? "file-text" : "type";
            preview.addEventListener("click", () => selectClip(clip.id));
            const meta = document.createElement("div");
            meta.innerHTML = `<b></b><small></small>`;
            meta.querySelector("b").textContent = clip.text || (clip.type === "caption" ? t("caption", "Caption") : t("text", "Text"));
            meta.querySelector("small").textContent = `${typeName(clip.type)} - ${fmt(clip.start)} - ${fmt(clip.start + clip.duration)}`;
            const actions = document.createElement("div");
            actions.className = "editor-media-actions";
            const select = document.createElement("button");
            select.type = "button";
            select.textContent = t("select", "Select");
            select.addEventListener("click", () => selectClip(clip.id));
            const duplicate = document.createElement("button");
            duplicate.type = "button";
            duplicate.textContent = t("duplicate", "Duplicate");
            duplicate.addEventListener("click", () => {
              selectOnly(clip.id);
              duplicateSelectedClip();
            });
            actions.append(select, duplicate);
            item.append(preview, meta, actions);
            return item;
          });
          const assetItems = visibleAssets.map((asset) => {
            const item = document.createElement("article");
            item.className = `editor-media-item is-${asset.kind}${String(asset.id) === String(selectedAssetId) ? " is-selected" : ""}`;
            item.draggable = true;
            item.dataset.assetId = asset.id;
            const preview = document.createElement("button");
            preview.type = "button";
            preview.className = "editor-media-preview";
            preview.style.backgroundImage = (asset.thumbnail_url || isImageAsset(asset)) ? `url("${asset.thumbnail_url || asset.preview_url}")` : "";
            preview.dataset.icon = asset.kind === "video" ? "film" : asset.kind === "audio" ? "music" : isImageAsset(asset) ? "image" : "file-text";
            preview.addEventListener("click", () => { selectedAssetId = asset.id; addAssetToTimeline(asset); });
            const meta = document.createElement("div");
            meta.innerHTML = `<b></b><small></small>`;
            meta.querySelector("b").textContent = asset.name || asset.kind;
            meta.querySelector("b").title = t("double_click_rename", "Double-click to rename");
            meta.querySelector("b").addEventListener("dblclick", () => {
              const input = document.createElement("input");
              input.value = asset.name || "";
              input.className = "editor-asset-rename";
              meta.querySelector("b").replaceWith(input);
              input.focus();
              input.select();
              let finished = false;
              const finish = async (save) => {
                if (finished) return;
                finished = true;
                if (save) await renameAsset(asset, input.value);
                else renderMediaBin();
              };
              input.addEventListener("keydown", (event) => {
                if (event.key === "Enter") finish(true);
                if (event.key === "Escape") finish(false);
              });
              input.addEventListener("blur", () => finish(true), {once: true});
            });
            const visualLabel = asset.kind === "image" && asset.visual_kind && asset.visual_kind !== "image" ? asset.visual_kind.toUpperCase() : typeName(asset.kind);
            meta.querySelector("small").textContent = `${visualLabel} - ${asset.size_text || ""}`;
            const actions = document.createElement("div");
            actions.className = "editor-media-actions";
            const add = document.createElement("button");
            add.type = "button";
            add.textContent = t("add", "Add");
            add.addEventListener("click", () => addAssetToTimeline(asset));
            const remove = document.createElement("button");
            remove.type = "button";
            remove.textContent = t("delete", "Delete");
            remove.addEventListener("click", async () => {
              const ok = await askConfirm({
                title: t("delete_media_asset_question", "Delete media asset?"),
                copy: t("delete_media_asset_copy", "This removes the file from the project and deletes clips that use it."),
              });
              if (ok) deleteAsset(asset);
            });
            actions.append(add, remove);
            item.append(preview, meta, actions);
            item.addEventListener("dragstart", (event) => {
              selectedAssetId = asset.id;
              event.dataTransfer.effectAllowed = "copy";
              event.dataTransfer.setData("application/x-cherryx-asset", String(asset.id));
              event.dataTransfer.setData("text/plain", String(asset.id));
            });
            item.addEventListener("pointerenter", (event) => showAssetPreview(asset, event));
            item.addEventListener("pointermove", (event) => showAssetPreview(asset, event));
            item.addEventListener("pointerleave", hideAssetPreview);
            return item;
          });
          mediaBin.replaceChildren(...textItems, ...assetItems);
        }
        function showClipMenu(x, y, anchor = null) {
          if (!clipMenu) return;
          const clip = selectedClip();
          const textClip = isTextOverlayClip(clip);
          clipMenu.dataset.menuKind = textClip ? "text" : "clip";
          clipMenu.querySelectorAll("[data-text-menu-only]").forEach((item) => { item.hidden = !textClip; });
          clipMenu.querySelectorAll("[data-non-text-menu-only]").forEach((item) => { item.hidden = textClip; });
          clipMenu.hidden = false;
          const menuRect = clipMenu.getBoundingClientRect();
          const anchorRect = anchor?.getBoundingClientRect ? anchor.getBoundingClientRect() : null;
          const preferredTop = anchorRect ? anchorRect.top - menuRect.height - 10 : y - menuRect.height - 10;
          const fallbackTop = anchorRect ? anchorRect.bottom + 10 : y + 10;
          const top = preferredTop > 8 ? preferredTop : Math.min(window.innerHeight - menuRect.height - 8, fallbackTop);
          const left = Math.min(window.innerWidth - menuRect.width - 8, Math.max(8, x - menuRect.width / 2));
          clipMenu.style.left = `${left}px`;
          clipMenu.style.top = `${Math.max(8, top)}px`;
        }
        function hideClipMenu() {
          if (clipMenu) clipMenu.hidden = true;
        }
        function editSelectedTextOverlay() {
          const clip = selectedClip();
          if (!isTextOverlayClip(clip)) return;
          renderPreview();
          const node = overlayRoot.querySelector(`.editor-overlay-item[data-clip-id="${CSS.escape(clip.id)}"]`);
          const textLayer = node?.querySelector(".editor-overlay-text-content");
          if (node && textLayer) setOverlayTextEditing(node, textLayer, clip, true);
        }
        function applySelectedTextPreset(preset) {
          const clip = selectedClip();
          if (!isTextOverlayClip(clip)) return;
          pushHistory();
          applyTextPreset(clip, preset);
          updateTextControls(clip);
          renderPreview();
          scheduleSave();
        }
        function changeSelectedZ(delta) {
          const clip = selectedClip();
          if (!clip) return;
          pushHistory();
          clip.style = clip.style || {};
          clip.style.zIndex = Number(clip.style.zIndex || 2) + delta;
          renderPreview();
          scheduleSave();
        }
        function hexToRgb(hex) {
          const raw = String(hex || "#000").replace("#", "").padEnd(6, "0");
          return {r: parseInt(raw.slice(0, 2), 16) || 0, g: parseInt(raw.slice(2, 4), 16) || 0, b: parseInt(raw.slice(4, 6), 16) || 0};
        }
        function trackIcon(type) {
          return {video: "film", text: "type", image: "image", audio: "music"}[type] || "circle";
        }
        function typeName(type) {
          return {
            video: t("video", "Video"),
            text: t("text", "Text"),
            caption: t("caption", "Caption"),
            image: t("image", "Image"),
            audio: t("audio", "Audio"),
          }[type] || t("layer", "Layer");
        }
        function sync() {
          const duration = timelineDuration();
          projectTime = Math.max(0, Math.min(projectTime, duration));
          const current = projectTime;
          const ratio = duration ? current / duration : 0;
          seek.value = String(Math.round(ratio * 1000));
          seek.style.setProperty("--seek", `${ratio * 100}%`);
          playhead.style.left = `${secondsToPx(current)}px`;
          playhead.dataset.time = fmt(current);
          if (playheadLabel) playheadLabel.textContent = fmt(current);
          time.textContent = `${fmt(current)} / ${fmt(duration)}`;
          durationNode.textContent = fmt(duration);
          play.dataset.icon = playing ? "pause" : "play";
          updateOverlayVisibility();
        }
        async function refreshExportQueue() {
          if (!projectId || !exportQueue) return;
          clearTimeout(exportQueueTimer);
          try {
            const data = await jsonFetch(`${api}${projectId}/exports/`);
            renderExportQueue(data.jobs || []);
          } catch (error) {
            exportQueue.innerHTML = `<small>Export queue unavailable</small>`;
          }
        }
        function renderExportQueue(jobs) {
          if (!exportQueue) return;
          if (!jobs.length) {
            exportQueue.innerHTML = `<small>No exports yet</small>`;
            return;
          }
          exportQueue.replaceChildren(...jobs.map((job) => {
            const item = document.createElement("article");
            item.className = `editor-export-job is-${job.status}`;
            item.innerHTML = `<b></b><small></small><i><span></span></i><div></div>`;
            item.querySelector("b").textContent = job.kind === "video_cover" ? "Cover frame" : `MP4 ${job.quality || ""}`;
            item.querySelector("small").textContent = job.error || job.message || job.status;
            item.querySelector("span").style.width = `${Math.max(3, Number(job.progress || 0))}%`;
            const actions = item.querySelector("div");
            if (job.download_url) {
              const link = document.createElement("a");
              link.href = job.download_url;
              link.textContent = job.kind === "video_cover" ? "Download cover" : "Download";
              link.download = "";
              actions.append(link);
            }
            if (["queued", "running"].includes(job.status)) {
              const cancel = document.createElement("button");
              cancel.type = "button";
              cancel.textContent = "Cancel";
              cancel.addEventListener("click", async () => {
                await jsonFetch(`${api}${projectId}/export/${job.id}/cancel/`, {method: "POST"});
                refreshExportQueue();
              });
              actions.append(cancel);
            }
            return item;
          }));
          if (jobs.some((job) => ["queued", "running"].includes(job.status))) {
            exportQueueTimer = window.setTimeout(refreshExportQueue, 1600);
          }
        }
        function seekTo(seconds) {
          projectTime = Math.max(0, Math.min(timelineDuration(), Number(seconds) || 0));
          syncMediaForProjectTime(playing);
          sync();
          persistProjectTime(true);
        }
        function seekFromClient(clientX) {
          const rect = timeRuler.getBoundingClientRect();
          seekTo(pxToSeconds(clientX - rect.left));
        }
        function startPlayheadDrag(event) {
          event.preventDefault();
          event.stopPropagation();
          playhead.classList.add("is-dragging");
          seekFromClient(event.clientX);
          const move = (moveEvent) => seekFromClient(moveEvent.clientX);
          const finish = (upEvent) => {
            playhead.classList.remove("is-dragging");
            if (playhead.hasPointerCapture(upEvent.pointerId)) playhead.releasePointerCapture(upEvent.pointerId);
            playhead.removeEventListener("pointermove", move);
            playhead.removeEventListener("pointerup", finish);
            playhead.removeEventListener("pointercancel", finish);
          };
          playhead.setPointerCapture(event.pointerId);
          playhead.addEventListener("pointermove", move);
          playhead.addEventListener("pointerup", finish);
          playhead.addEventListener("pointercancel", finish);
        }
        function startPlayback() {
          playing = true;
          lastTick = performance.now();
          syncMediaForProjectTime(true);
          tickPlayback(lastTick);
          sync();
        }
        function pausePlayback() {
          playing = false;
          cancelAnimationFrame(rafId);
          video.pause();
          audioPool.forEach((media) => media.pause());
          sync();
          persistProjectTime(true);
        }
        function tickPlayback(now) {
          if (!playing) return;
          const delta = Math.max(0, (now - lastTick) / 1000);
          lastTick = now;
          projectTime = Math.min(timelineDuration(), projectTime + delta);
          if (projectTime >= timelineDuration()) {
            pausePlayback();
            return;
          }
          syncMediaForProjectTime(true);
          sync();
          persistProjectTime(false);
          rafId = requestAnimationFrame(tickPlayback);
        }
        function splitSelectedClip() {
          const clip = selectedClip();
          if (!clip || projectTime <= clip.start + 0.08 || projectTime >= clip.start + clip.duration - 0.08) return;
          const offset = projectTime - clip.start;
          const right = normalizeClip({
            ...clip,
            id: uid(`${clip.type}-split`),
            start: projectTime,
            duration: clip.duration - offset,
            sourceStart: (clip.sourceStart || 0) + offset,
            sourceEnd: clip.sourceEnd || (clip.sourceStart || 0) + clip.duration,
          });
          clip.duration = offset;
          if (["video", "audio"].includes(clip.type)) clip.sourceEnd = (clip.sourceStart || 0) + offset;
          state.clips.push(right);
          selectOnly(right.id);
          render();
          scheduleSave();
        }
        function trimSelectedClipToPlayhead(edge) {
          const clip = selectedClip();
          if (!clip || projectTime <= clip.start + 0.02 || projectTime >= clip.start + clip.duration - 0.02) return;
          pushHistory();
          const offset = projectTime - clip.start;
          if (edge === "start") {
            clip.start = projectTime;
            clip.duration = Math.max(0.25, clip.duration - offset);
            if (["video", "audio"].includes(clip.type)) {
              clip.sourceStart = Math.max(0, Number(clip.sourceStart || 0) + offset);
              clip.sourceEnd = Math.max(clip.sourceStart + 0.25, clip.sourceStart + clip.duration);
            }
          } else {
            clip.duration = Math.max(0.25, offset);
            if (["video", "audio"].includes(clip.type)) {
              clip.sourceEnd = Math.max(Number(clip.sourceStart || 0) + 0.25, Number(clip.sourceStart || 0) + clip.duration);
            }
          }
          render();
          syncMediaForProjectTime(playing);
          scheduleSave();
        }
        function setTimelineScale(value) {
          timelineScale = Math.max(timelineScaleMin, Math.min(timelineScaleMax, value));
          localStorage.setItem("videoEditorTimelineScale", String(timelineScale));
          renderTracks();
          sync();
        }
        function zoomTimeline(direction) {
          const multiplier = direction > 0 ? 1.32 : 1 / 1.5;
          setTimelineScale(timelineScale * multiplier);
        }
        function askConfirm({title: modalTitle, copy, action = t("delete", "Delete")}) {
          return new Promise((resolve) => {
            if (!confirmModal) {
              resolve(window.confirm(modalTitle || t("continue_action", "Continue?")));
              return;
            }
            pendingConfirm = resolve;
            if (confirmTitle) confirmTitle.textContent = modalTitle || t("confirm_action", "Confirm action");
            if (confirmCopy) confirmCopy.textContent = copy || t("action_cannot_be_undone", "This action cannot be undone.");
            if (confirmAction) confirmAction.textContent = action;
            confirmModal.hidden = false;
            confirmAction?.focus();
          });
        }
        function createTimelineScrollbar() {
          if (!timelineScroll) return null;
          timelineScroll.classList.add("has-custom-scrollbar");
          const xRail = document.createElement("div");
          const yRail = document.createElement("div");
          const xThumb = document.createElement("button");
          const yThumb = document.createElement("button");
          xRail.className = "editor-custom-scrollbar is-horizontal";
          yRail.className = "editor-custom-scrollbar is-vertical";
          xThumb.className = "editor-custom-scrollbar-thumb";
          yThumb.className = "editor-custom-scrollbar-thumb";
          xThumb.type = "button";
          yThumb.type = "button";
          xThumb.setAttribute("aria-label", "Scroll timeline horizontally");
          yThumb.setAttribute("aria-label", "Scroll timeline vertically");
          xRail.append(xThumb);
          yRail.append(yThumb);
          timelineScroll.after(xRail, yRail);
          const bindDrag = (thumb, axis) => {
            thumb.addEventListener("pointerdown", (event) => {
              event.preventDefault();
              thumb.setPointerCapture(event.pointerId);
              thumb.classList.add("is-dragging");
              const startPointer = axis === "x" ? event.clientX : event.clientY;
              const startScroll = axis === "x" ? timelineScroll.scrollLeft : timelineScroll.scrollTop;
              const onMove = (moveEvent) => {
                const rail = axis === "x" ? xRail : yRail;
                const railSize = axis === "x" ? rail.clientWidth : rail.clientHeight;
                const thumbSize = axis === "x" ? thumb.offsetWidth : thumb.offsetHeight;
                const scrollSize = axis === "x" ? timelineScroll.scrollWidth - timelineScroll.clientWidth : timelineScroll.scrollHeight - timelineScroll.clientHeight;
                const dragSpace = Math.max(1, railSize - thumbSize);
                const delta = (axis === "x" ? moveEvent.clientX : moveEvent.clientY) - startPointer;
                const next = startScroll + (delta / dragSpace) * scrollSize;
                if (axis === "x") timelineScroll.scrollLeft = next;
                else timelineScroll.scrollTop = next;
              };
              const onEnd = (upEvent) => {
                thumb.classList.remove("is-dragging");
                thumb.releasePointerCapture(upEvent.pointerId);
                thumb.removeEventListener("pointermove", onMove);
                thumb.removeEventListener("pointerup", onEnd);
                thumb.removeEventListener("pointercancel", onEnd);
              };
              thumb.addEventListener("pointermove", onMove);
              thumb.addEventListener("pointerup", onEnd);
              thumb.addEventListener("pointercancel", onEnd);
            });
          };
          const bindRail = (rail, thumb, axis) => {
            rail.addEventListener("pointerdown", (event) => {
              if (event.target === thumb) return;
              const rect = rail.getBoundingClientRect();
              const railSize = axis === "x" ? rect.width : rect.height;
              const thumbSize = axis === "x" ? thumb.offsetWidth : thumb.offsetHeight;
              const scrollSize = axis === "x" ? timelineScroll.scrollWidth - timelineScroll.clientWidth : timelineScroll.scrollHeight - timelineScroll.clientHeight;
              const position = (axis === "x" ? event.clientX - rect.left : event.clientY - rect.top) - thumbSize / 2;
              const next = (position / Math.max(1, railSize - thumbSize)) * scrollSize;
              if (axis === "x") timelineScroll.scrollLeft = next;
              else timelineScroll.scrollTop = next;
            });
          };
          bindDrag(xThumb, "x");
          bindDrag(yThumb, "y");
          bindRail(xRail, xThumb, "x");
          bindRail(yRail, yThumb, "y");
          timelineScroll.addEventListener("scroll", updateTimelineScrollbar, {passive: true});
          window.addEventListener("resize", updateTimelineScrollbar);
          if ("ResizeObserver" in window) {
            const resizeObserver = new ResizeObserver(() => updateTimelineScrollbar());
            resizeObserver.observe(timelineScroll);
            resizeObserver.observe(timeline);
            resizeObserver.observe(timelineScroll.closest(".editor-timeline-panel") || timelineScroll);
          }
          return {xRail, yRail, xThumb, yThumb};
        }
        function updateTimelineScrollbar() {
          if (!timelineScrollbar || !timelineScroll) return;
          const {xRail, yRail, xThumb, yThumb} = timelineScrollbar;
          const maxX = Math.max(0, timelineScroll.scrollWidth - timelineScroll.clientWidth);
          const maxY = Math.max(0, timelineScroll.scrollHeight - timelineScroll.clientHeight);
          xRail.hidden = maxX <= 1;
          yRail.hidden = maxY <= 1;
          if (maxX > 1) {
            const railWidth = Math.max(1, xRail.clientWidth);
            const thumbWidth = Math.max(48, Math.round((timelineScroll.clientWidth / timelineScroll.scrollWidth) * railWidth));
            const safeThumbWidth = Math.min(railWidth, thumbWidth);
            const left = Math.round((timelineScroll.scrollLeft / maxX) * Math.max(1, railWidth - safeThumbWidth));
            xThumb.style.width = `${safeThumbWidth}px`;
            xThumb.style.transform = `translateX(${left}px)`;
          }
          if (maxY > 1) {
            const railHeight = Math.max(1, yRail.clientHeight);
            const thumbHeight = Math.max(42, Math.round((timelineScroll.clientHeight / timelineScroll.scrollHeight) * railHeight));
            const safeThumbHeight = Math.min(railHeight, thumbHeight);
            const top = Math.round((timelineScroll.scrollTop / maxY) * Math.max(1, railHeight - safeThumbHeight));
            yThumb.style.height = `${safeThumbHeight}px`;
            yThumb.style.transform = `translateY(${top}px)`;
          }
        }
        function startMarqueeSelection(event) {
          const startX = event.clientX;
          const startY = event.clientY;
          const additive = event.shiftKey;
          const initial = new Set(selectedClipIds);
          const box = document.createElement("div");
          box.className = "editor-marquee";
          timeline.append(box);
          marquee = {box, startX, startY, additive, initial};
          const update = (moveEvent) => {
            const left = Math.min(startX, moveEvent.clientX);
            const top = Math.min(startY, moveEvent.clientY);
            const width = Math.abs(moveEvent.clientX - startX);
            const height = Math.abs(moveEvent.clientY - startY);
            const timelineRect = timeline.getBoundingClientRect();
            box.style.left = `${left - timelineRect.left}px`;
            box.style.top = `${top - timelineRect.top}px`;
            box.style.width = `${width}px`;
            box.style.height = `${height}px`;
            const rect = {left, top, right: left + width, bottom: top + height};
            const ids = new Set(additive ? initial : []);
            root.querySelectorAll(".editor-layer-clip").forEach((node) => {
              const item = node.getBoundingClientRect();
              const intersects = item.left <= rect.right && item.right >= rect.left && item.top <= rect.bottom && item.bottom >= rect.top;
              if (intersects) ids.add(node.dataset.clipId);
            });
            setSelection(Array.from(ids), selectedClipId);
            root.querySelectorAll(".editor-layer-clip").forEach((node) => node.classList.toggle("is-selected", selectedClipIds.has(node.dataset.clipId)));
            renderProperties();
          };
          const finish = (upEvent) => {
            timeline.releasePointerCapture(upEvent.pointerId);
            box.remove();
            marquee = null;
            timeline.removeEventListener("pointermove", update);
            timeline.removeEventListener("pointerup", finish);
            timeline.removeEventListener("pointercancel", finish);
            if (Math.abs(upEvent.clientX - startX) < 4 && Math.abs(upEvent.clientY - startY) < 4 && !additive) {
              selectOnly("");
              seekFromClient(upEvent.clientX);
            }
            render();
          };
          timeline.setPointerCapture(event.pointerId);
          timeline.addEventListener("pointermove", update);
          timeline.addEventListener("pointerup", finish);
          timeline.addEventListener("pointercancel", finish);
        }
        function closeConfirm(result = false) {
          if (confirmModal) confirmModal.hidden = true;
          if (pendingConfirm) pendingConfirm(result);
          pendingConfirm = null;
        }
        async function renameProjectTitle(nextTitle) {
          await ensureProject();
          const data = await jsonFetch(`${api}${projectId}/rename/`, {method: "POST", body: JSON.stringify({title: nextTitle})});
          const savedTitle = data.project?.title || nextTitle;
          title.textContent = savedTitle;
          state.title = savedTitle;
          return savedTitle;
        }
        function startTitleEdit() {
          if (title.querySelector("input")) return;
          const original = title.textContent.trim() || t("new_project", "New project");
          const input = document.createElement("input");
          input.className = "editor-title-input";
          input.value = original;
          input.maxLength = 180;
          title.textContent = "";
          title.append(input);
          input.focus();
          input.select();
          let done = false;
          const finish = async (save) => {
            if (done) return;
            done = true;
            const next = input.value.trim() || original;
            title.textContent = original;
            if (!save || next === original) return;
            setStatus(t("saving", "Saving..."));
            try {
              await renameProjectTitle(next);
              setStatus(`${t("saved", "Saved")} ${savedTime()}`);
            } catch (error) {
              setStatus(t("rename_failed", "Rename failed"), true);
            }
          };
          input.addEventListener("keydown", (event) => {
            if (event.key === "Enter") finish(true);
            if (event.key === "Escape") finish(false);
          });
          input.addEventListener("blur", () => finish(true));
        }
        async function startExport() {
          if (!renderExport) return;
          clearTimeout(saveTimer);
          await saveProject();
          renderExport.disabled = true;
          if (exportDownload) exportDownload.hidden = true;
          if (exportProgress) exportProgress.hidden = false;
          if (exportProgressBar) exportProgressBar.style.width = "4%";
          if (exportStatus) exportStatus.textContent = t("starting_export", "Starting export...");
          try {
            const data = await jsonFetch(`${api}${projectId}/export/`, {method: "POST", body: JSON.stringify({quality: exportQuality, preset: exportPreset})});
            pollExport(data.job);
            refreshExportQueue();
          } catch (error) {
            if (exportStatus) exportStatus.textContent = t("export_failed", "Export failed");
            renderExport.disabled = false;
          }
        }
        function pollExport(job) {
          if (!job) return;
          if (exportProgressBar) exportProgressBar.style.width = `${Math.max(4, Number(job.progress || 0))}%`;
          if (exportStatus) exportStatus.textContent = job.error || job.message || t(job.status, job.status) || t("rendering", "Rendering...");
          if (job.status === "done") {
            if (exportDownload) {
              exportDownload.href = job.download_url;
              exportDownload.hidden = false;
              exportDownload.textContent = job.size_text ? `${t("download_mp4", "Download MP4")} (${job.size_text})` : t("download_mp4", "Download MP4");
            }
            renderExport.disabled = false;
            refreshExportQueue();
            return;
          }
          if (job.status === "failed") {
            renderExport.disabled = false;
            refreshExportQueue();
            return;
          }
          window.setTimeout(async () => {
            try {
              const data = await jsonFetch(`${api}${projectId}/export/${job.id}/`);
              pollExport(data.job);
            } catch (error) {
              if (exportStatus) exportStatus.textContent = t("export_status_failed", "Export status failed");
              renderExport.disabled = false;
            }
          }, 1200);
        }
        function classifyFile(file) {
          const type = (file?.type || "").toLowerCase();
          const name = (file?.name || "").toLowerCase();
          const extension = (name.match(/\.[a-z0-9]+$/) || [""])[0];
          const isVideo = type.startsWith("video/") || /\.(mp4|mov|m4v|webm|mkv|avi|gif)$/.test(name);
          const isAudio = type.startsWith("audio/") || /\.(mp3|wav|m4a|aac|ogg|flac)$/.test(name);
          const isImage = type.startsWith("image/") || /\.(jpg|jpeg|png|webp|gif|avif|bmp|tif|tiff|svg)$/.test(name);
          const isPdf = type === "application/pdf" || extension === ".pdf";
          const isDocument = type.startsWith("text/") || /\.(doc|docx|ppt|pptx|xls|xlsx|txt|csv|json|rtf)$/.test(name);
          const visualKind = isImage ? "image" : isPdf ? "pdf" : isDocument ? "document" : isVideo ? "video" : "file";
          const kind = isVideo ? "video" : isAudio ? "audio" : "image";
          return {kind, visualKind, isVisual: kind === "video" || kind === "image", isAudio, isVideo, extension};
        }
        function kindFromFile(file) {
          return classifyFile(file).kind;
        }
        function hasDraggedFiles(event) {
          const types = Array.from(event.dataTransfer?.types || []);
          const items = Array.from(event.dataTransfer?.items || []);
          return types.includes("Files") || items.some((item) => item.kind === "file");
        }
        function hasDraggedAsset(event) {
          return Array.from(event.dataTransfer?.types || []).includes("application/x-cherryx-asset");
        }
        function droppedFiles(event) {
          return Array.from(event.dataTransfer?.files || []).filter(Boolean);
        }
        function isImageAsset(asset) {
          return Boolean(asset && (asset.is_previewable_image || String(asset.media_type || "").startsWith("image/")));
        }
        async function handleTimelineDrop(file, lane, clientX, offset = 0) {
          const fileInfo = classifyFile(file);
          const kind = fileInfo.kind;
          if (!kind) return;
          setStatus(`${t("uploading", "Uploading")} ${file.name}`);
          const acceptsVisual = fileInfo.isVisual && ["video", "image"].includes(lane.dataset.trackType);
          const trackId = lane.dataset.trackType === kind || acceptsVisual ? lane.dataset.trackId : (state.tracks.find((track) => track.type === kind)?.id || lane.dataset.trackId);
          const rect = timeRuler.getBoundingClientRect();
          const start = pxToSeconds(clientX - rect.left) + offset;
          const thumbnail = kind === "video" ? await thumbnailFromVideo(file) : "";
          const mediaSeconds = await mediaDuration(file, kind);
          const asset = await uploadAsset(file, kind, thumbnail, mediaSeconds);
          if (!asset) {
            setStatus(`${t("upload_failed", "Upload failed")}: ${file.name}`, true);
            return;
          }
          const duration = kind === "image" ? 5 : Math.max(1, Number(asset.duration || mediaSeconds || 5));
          addClip({
            id: uid(kind),
            type: kind,
            trackId,
            assetId: asset.id,
            start,
            duration,
            sourceStart: 0,
            sourceEnd: duration,
            x: 50,
            y: 50,
            scale: kind === "image" ? 42 : 100,
            style: {},
            text: "",
          });
          setStatus(`${t("added_at", "Added at")} ${fmt(start)}`);
        }

        fileInput.addEventListener("change", () => Array.from(fileInput.files || []).forEach((file) => handleFile(file)));
        videoPanelInput.addEventListener("change", () => Array.from(videoPanelInput.files || []).forEach((file) => handleFile(file)));
        audioInput.addEventListener("change", () => {
          if (audioPanelName && audioInput.files[0]) audioPanelName.textContent = audioInput.files[0].name;
          handleFile(audioInput.files[0], "audio");
        });
        imageInput.addEventListener("change", () => handleFile(imageInput.files[0], "image"));
        dropzone.addEventListener("dragover", (event) => { event.preventDefault(); dropzone.classList.add("is-dragging"); });
        dropzone.addEventListener("dragleave", () => dropzone.classList.remove("is-dragging"));
        dropzone.addEventListener("drop", (event) => {
          event.preventDefault();
          dropzone.classList.remove("is-dragging");
          Array.from(event.dataTransfer.files || []).forEach((file) => handleFile(file));
        });
        play.addEventListener("click", () => playing ? pausePlayback() : startPlayback());
        seek.addEventListener("input", () => seekTo((Number(seek.value) / 1000) * timelineDuration()));
        playhead.addEventListener("pointerdown", startPlayheadDrag);
        timeline.addEventListener("pointerdown", (event) => {
          if (event.target.closest(".editor-playhead,.editor-layer-clip,button,input,label")) return;
          event.preventDefault();
          startMarqueeSelection(event);
        }, true);
        timeline.addEventListener("pointermove", (event) => {
          if (timeline.dataset.scrubbing === "true") seekFromClient(event.clientX);
        });
        timeline.addEventListener("pointerup", (event) => {
          timeline.dataset.scrubbing = "false";
          if (timeline.hasPointerCapture(event.pointerId)) timeline.releasePointerCapture(event.pointerId);
        });
        video.addEventListener("timeupdate", sync);
        video.addEventListener("loadedmetadata", sync);
        video.addEventListener("pointerdown", startVideoReframeDrag);
        video.addEventListener("pointermove", moveVideoReframe);
        video.addEventListener("pointerup", finishVideoReframe);
        video.addEventListener("pointercancel", finishVideoReframe);
        video.addEventListener("wheel", handleVideoReframeWheel, {passive: false});
        overlayRoot.addEventListener("pointerdown", startVideoReframeDrag);
        overlayRoot.addEventListener("pointermove", moveVideoReframe);
        overlayRoot.addEventListener("pointerup", finishVideoReframe);
        overlayRoot.addEventListener("pointercancel", finishVideoReframe);
        overlayRoot.addEventListener("wheel", handleVideoReframeWheel, {passive: false});
        video.addEventListener("pause", () => { if (playing && !internalVideoPause) pausePlayback(); });
        aspectToggle?.addEventListener("click", (event) => {
          event.stopPropagation();
          const open = Boolean(aspectOptions?.hidden);
          if (aspectOptions) aspectOptions.hidden = !open;
          aspectMenu?.classList.toggle("is-open", open);
          aspectToggle.setAttribute("aria-expanded", open ? "true" : "false");
        });
        aspectMenu?.addEventListener("click", (event) => event.stopPropagation());
        document.addEventListener("click", closeAspectMenu);
        document.addEventListener("click", closeAutoSubtitleLanguageChoice);
        document.addEventListener("click", closeTextFontChoice);
        setupAutoSubtitleLanguageChoice();
        setupTextFontChoice();
        setupPropertyTabScroller();
        root.querySelectorAll("[data-aspect]").forEach((button) => button.addEventListener("click", () => setAspectFromButton(button)));
        root.querySelectorAll("[data-editor-tool]").forEach((button) => button.addEventListener("click", () => {
          activateInspectorPanel(button.dataset.editorTool);
        }));
        root.querySelectorAll("[data-panel-tab]").forEach((button) => button.addEventListener("click", () => {
          activateInspectorPanel(button.dataset.panelTab);
        }));
        setupMobileVideoEditor();
        root.querySelectorAll("[data-add-kind]").forEach((button) => button.addEventListener("click", () => {
          const kind = button.dataset.addKind;
          if (kind === "text") addTextClip();
          if (kind === "video") videoPanelInput.click();
          if (kind === "image") imageInput.click();
          if (kind === "audio") audioInput.click();
          if (kind === "voice") root.querySelector("[data-record-audio]").click();
        }));
        root.querySelectorAll("[data-add-track]").forEach((button) => button.addEventListener("click", () => addTrack(button.dataset.addTrack)));
        mediaFilters?.querySelectorAll("[data-media-filter]").forEach((button) => button.addEventListener("click", () => {
          mediaFilter = button.dataset.mediaFilter || "all";
          mediaFilters.querySelectorAll("[data-media-filter]").forEach((item) => item.classList.toggle("is-active", item === button));
          renderMediaBin();
        }));
        root.querySelectorAll("[data-undo]").forEach((button) => button.addEventListener("click", undo));
        root.querySelectorAll("[data-redo]").forEach((button) => button.addEventListener("click", redo));
        root.querySelectorAll("[data-duplicate-clip]").forEach((button) => button.addEventListener("click", duplicateSelectedClip));
        root.querySelector("[data-toggle-snap]").addEventListener("click", (event) => {
          snapEnabled = !snapEnabled;
          event.currentTarget.classList.toggle("is-active", snapEnabled);
        });
        root.querySelector("[data-toggle-density]").addEventListener("click", (event) => {
          timelineDensity = timelineDensity === "compact" ? "normal" : "compact";
          localStorage.setItem("videoEditorDensity", timelineDensity);
          event.currentTarget.classList.toggle("is-active", timelineDensity === "compact");
          renderTracks();
        });
        root.querySelectorAll("[data-split-clip]").forEach((button) => button.addEventListener("click", splitSelectedClip));
        root.querySelectorAll("[data-trim-playhead]").forEach((button) => button.addEventListener("click", () => trimSelectedClipToPlayhead(button.dataset.trimPlayhead)));
        root.querySelectorAll("[data-zoom-timeline]").forEach((button) => button.addEventListener("click", () => zoomTimeline(Number(button.dataset.zoomTimeline))));
        root.querySelector("[data-zoom-fit]").addEventListener("click", () => {
          const rect = timeline.closest(".editor-timeline-scroll").getBoundingClientRect();
          setTimelineScale(Math.max(timelineScaleMin, (rect.width - 90) / timelineDuration()));
        });
        root.querySelector("[data-add-text]").addEventListener("click", addTextClip);
        root.querySelector("[data-add-caption]")?.addEventListener("click", () => addCaptionClip(t("caption", "Caption"), currentTime(), 3));
        autoSubtitleButton?.addEventListener("click", generateAutoSubtitles);
        subtitleInput?.addEventListener("change", async () => {
          const file = subtitleInput.files?.[0];
          if (!file) return;
          let cues = [];
          try {
            await ensureProject();
            const body = new FormData();
            body.append("file", file);
            const response = await fetch(`${api}${projectId}/subtitles/import/`, {
              method: "POST",
              headers: {"X-CSRFToken": csrfToken(), "X-Requested-With": "XMLHttpRequest"},
              body,
            });
            const payload = await response.json().catch(() => ({}));
            if (!response.ok) throw new Error(payload.error || t("subtitle_import_failed", "Subtitle import failed"));
            cues = Array.isArray(payload.cues) ? payload.cues : [];
          } catch (error) {
            const text = await file.text();
            cues = parseSubtitleText(text);
          }
          pushHistory();
          cues.forEach((cue) => addCaptionClip(cue.text, cue.start, Math.max(0.2, cue.end - cue.start), {...cue, history: false}));
          render();
          scheduleSave();
          if (cues.length) setAutoSubtitleStatus(`${t("auto_subtitles_done", "Subtitles added")}: ${cues.length}`, "ok");
          subtitleInput.value = "";
        });
        root.querySelectorAll("[data-export-subtitles]").forEach((button) => button.addEventListener("click", async () => {
          await ensureProject();
          await saveProject();
          const format = button.dataset.exportSubtitles || "srt";
          window.location.href = `${api}${projectId}/subtitles/export/?format=${encodeURIComponent(format)}`;
        }));
        root.querySelectorAll("[data-delete-clip]").forEach((button) => button.addEventListener("click", confirmDeleteSelectedClip));
        title.addEventListener("dblclick", startTitleEdit);
        saveRetry?.addEventListener("click", saveProject);
        exportShortcut?.addEventListener("click", () => {
          root.querySelector('[data-editor-tool="export"]')?.click();
          root.querySelector("[data-tool-panel='export']")?.scrollIntoView({block: "nearest"});
        });
        root.querySelectorAll("[data-export-quality]").forEach((button) => button.addEventListener("click", () => {
          exportQuality = button.dataset.exportQuality || "720p";
          root.querySelectorAll("[data-export-quality]").forEach((item) => item.classList.toggle("is-active", item === button));
        }));
        renderExport?.addEventListener("click", startExport);
        exportCover?.addEventListener("click", async () => {
          await ensureProject();
          const data = await jsonFetch(`${api}${projectId}/cover/`, {method: "POST", body: JSON.stringify({time: currentTime()})});
          renderExportQueue([data.job]);
          refreshExportQueue();
        });
        root.querySelectorAll("[data-export-preset]").forEach((button) => button.addEventListener("click", () => {
          exportPreset = button.dataset.exportPreset || "";
          const preset = EXPORT_PRESETS[exportPreset] || EXPORT_PRESETS.shorts;
          const aspect = preset.aspect;
          state.aspect = aspect;
          frame.style.setProperty("--editor-aspect", aspect);
          exportQuality = preset.quality || "1080p";
          root.querySelectorAll("[data-export-preset]").forEach((item) => item.classList.toggle("is-active", item === button));
          root.querySelectorAll("[data-export-quality]").forEach((item) => item.classList.toggle("is-active", item.dataset.exportQuality === exportQuality));
          syncAspectMenu();
          renderPreview();
          scheduleSave();
        }));
        confirmCancel.forEach((button) => button.addEventListener("click", () => closeConfirm(false)));
        confirmAction?.addEventListener("click", () => closeConfirm(true));
        ["start", "duration", "end", "x", "y", "scale", "rotation"].forEach((name) => {
          const input = root.querySelector(`[data-clip-${name}]`);
          input.addEventListener("change", () => {
            const clip = selectedClip();
            if (!clip) return;
            const value = Number(input.value);
            const patch = {[name]: value};
            updateClipPatch([clip.id], patch);
            if (clip.type === "video") syncMediaForProjectTime(playing);
          });
        });
        root.querySelector("[data-clip-fit]").addEventListener("change", (event) => {
          const clip = selectedClip();
          if (!clip) return;
          const fit = event.target.value;
          const patch = {style: {fit}};
          if (clip.type === "video" && ["cover", "crop"].includes(fit) && Number(clip.scale || 100) < 100) {
            patch.scale = 100;
          }
          updateClipPatch([clip.id], patch);
          syncMediaForProjectTime(playing);
        });
        root.querySelector("[data-clip-speed]").addEventListener("change", (event) => {
          const clip = selectedClip();
          if (!clip) return;
          updateClipPatch([clip.id], {style: {speed: Number(event.target.value)}});
          syncMediaForProjectTime(playing);
        });
        root.querySelectorAll(".editor-choice").forEach((choice) => {
          const input = choice.closest("label")?.querySelector("input[type='hidden']");
          const current = choice.querySelector("[data-choice-current]");
          current.addEventListener("click", () => choice.classList.toggle("is-open"));
          choice.querySelectorAll("[data-choice-value]").forEach((button) => {
            button.addEventListener("click", () => {
              if (!input || button.disabled) return;
              input.value = button.dataset.choiceValue;
              input.dispatchEvent(new Event("change", {bubbles: true}));
              choice.classList.remove("is-open");
            });
          });
        });
        document.addEventListener("click", (event) => {
          root.querySelectorAll(".editor-choice.is-open").forEach((choice) => {
            if (!choice.contains(event.target)) choice.classList.remove("is-open");
          });
        });
        root.querySelectorAll("[data-bg]").forEach((button) => button.addEventListener("click", () => {
          state.background = button.dataset.bg;
          state.backgroundValue = button.dataset.bg;
          applyBackgroundMode();
          scheduleSave();
        }));
        root.querySelectorAll("[data-bg-mode]").forEach((button) => button.addEventListener("click", () => {
          state.backgroundMode = button.dataset.bgMode || "solid";
          root.querySelectorAll("[data-bg-mode]").forEach((item) => item.classList.toggle("is-active", item === button));
          applyBackgroundMode();
          scheduleSave();
        }));
        root.querySelector("[data-fit-auto]")?.addEventListener("click", () => {
          const clip = selectedClip();
          if (!clip || !["video", "image"].includes(clip.type)) return;
          updateClipPatch([clip.id], {x: 50, y: 50, scale: clip.type === "image" ? 42 : 100, style: {fit: "contain"}});
          if (clip.type === "video") syncMediaForProjectTime(playing);
        });
        root.querySelector("[data-crop-mode]")?.addEventListener("click", (event) => {
          cropMode = !cropMode;
          event.currentTarget.classList.toggle("is-active", cropMode);
          const clip = selectedClip();
          if (clip && cropMode) {
            if (clip.type === "video") {
              if (!isClipActive(clip)) seekTo(clip.start + 0.01);
              clip.style = {...(clip.style || {}), fit: "crop"};
              clip.scale = Math.max(100, videoFrameScale(clip));
              ensureVideoReframeMode(clip);
              updateClipPatch([clip.id], {x: clip.x, y: clip.y, scale: clip.scale, style: {fit: "crop"}});
              syncMediaForProjectTime(playing);
            } else {
              updateClipPatch([clip.id], {style: {fit: "crop", crop: clip.style?.crop || {x: 10, y: 10, width: 80, height: 80}}});
            }
          } else {
            renderPreview();
          }
        });
        root.querySelectorAll("[data-filter]").forEach((button) => button.addEventListener("click", () => {
          const clip = selectedClip();
          if (!clip || !["video", "image"].includes(clip.type)) return;
          updateClipPatch([clip.id], {style: {filter: button.dataset.filter}}, {render: false});
          applyClipEffects();
        }));
        ["brightness", "contrast", "saturate", "opacity"].forEach((name) => {
          const input = root.querySelector(`[data-filter-${name}]`);
          input.addEventListener("input", () => {
            const clip = selectedClip();
            if (!clip || !["video", "image"].includes(clip.type)) return;
            updateClipPatch([clip.id], {style: {[name]: Number(input.value)}}, {render: false});
            applyClipEffects();
          });
        });
        root.querySelector("[data-editor-fit]").addEventListener("click", () => {
          const clip = selectedClip()?.type === "video" ? selectedClip() : activeVideoClip();
          if (!clip) {
            video.style.objectFit = video.style.objectFit === "cover" ? "contain" : "cover";
            return;
          }
          selectOnly(clip.id);
          const nextFit = videoFrameFit(clip) === "cover" ? "contain" : "crop";
          const patch = {style: {fit: nextFit}};
          if (nextFit === "crop") {
            patch.x = clip.x ?? 50;
            patch.y = clip.y ?? 50;
            patch.scale = videoFrameScale(clip);
          }
          updateClipPatch([clip.id], patch);
          syncMediaForProjectTime(playing);
        });
        root.querySelectorAll("[data-skip]").forEach((button) => button.addEventListener("click", () => seekTo(currentTime() + Number(button.dataset.skip))));
        root.querySelector("[data-volume]").addEventListener("input", (event) => {
          const clip = selectedClip();
          if (!clip || !["video", "audio"].includes(clip.type)) return;
          updateClipPatch([clip.id], {style: {volume: Number(event.target.value)}}, {render: false});
          syncMediaForProjectTime(playing);
          updateEffectControls(clip);
        });
        root.querySelector("[data-mute]").addEventListener("click", () => {
          video.muted = !video.muted;
          audioPool.forEach((media) => media.muted = video.muted);
          root.querySelector("[data-mute]").dataset.icon = video.muted ? "volume-x" : "volume-2";
        });
        ["fade-in", "fade-out"].forEach((name) => {
          const input = root.querySelector(`[data-${name}]`);
          input.addEventListener("input", () => {
            const clip = selectedClip();
            if (!clip) return;
            if (!input.dataset.historyStarted) {
              pushHistory();
              input.dataset.historyStarted = "true";
            }
            clip.style = clip.style || {};
            clip.style[name === "fade-in" ? "fadeIn" : "fadeOut"] = Number(input.value);
            updateClipControls(clip);
            renderPreview();
            syncMediaForProjectTime(playing);
            scheduleSave();
          });
          input.addEventListener("change", () => {
            delete input.dataset.historyStarted;
          });
        });
        root.querySelector("[data-transition]").addEventListener("change", (event) => {
          const clip = selectedClip();
          if (!clip || clip.type !== "video") return;
          pushHistory();
          clip.style = clip.style || {};
          clip.style.transition = event.target.value;
          renderTracks();
          scheduleSave();
        });
        clipMenu?.addEventListener("click", (event) => {
          const action = event.target.dataset.menuAction;
          if (!action) return;
          if (action === "duplicate") duplicateSelectedClip();
          if (action === "split") splitSelectedClip();
          if (action === "front") changeSelectedZ(1);
          if (action === "back") changeSelectedZ(-1);
          if (action === "edit-text") editSelectedTextOverlay();
          if (action === "preset-clean") applySelectedTextPreset("clean");
          if (action === "preset-caption") applySelectedTextPreset("caption");
          if (action === "delete") confirmDeleteSelectedClip();
          hideClipMenu();
        });
        document.addEventListener("click", (event) => {
          if (!clipMenu?.contains(event.target)) hideClipMenu();
        });
        document.addEventListener("pointerup", finishActiveOverlayDrag);
        document.addEventListener("pointercancel", finishActiveOverlayDrag);
        document.addEventListener("keydown", (event) => {
          if (event.key === "Escape" && confirmModal && !confirmModal.hidden) {
            closeConfirm(false);
            return;
          }
          if (event.key === "Escape") {
            hideClipMenu();
            selectOnly("");
            render();
            return;
          }
          if (!readOnly && isUndoShortcut(event)) {
            event.preventDefault();
            undo();
            return;
          }
          if (!readOnly && isRedoShortcut(event)) {
            event.preventDefault();
            redo();
            return;
          }
          if (event.target.closest("input,textarea,select,[contenteditable='true']")) return;
          if (event.code === "Space") {
            event.preventDefault();
            playing ? pausePlayback() : startPlayback();
          }
          if (readOnly) return;
          if (event.key.toLowerCase() === "s") splitSelectedClip();
          if (event.key === "Delete" || event.key === "Backspace") deleteSelectedClip();
          if (event.ctrlKey && event.key.toLowerCase() === "d") {
            event.preventDefault();
            duplicateSelectedClip();
          }
          if (event.ctrlKey && event.key.toLowerCase() === "c") {
            event.preventDefault();
            copiedClips = selectedClips().map((clip) => JSON.parse(JSON.stringify(clip)));
            copiedClip = copiedClips[0] ? JSON.stringify(copiedClips[0]) : null;
          }
          if (event.ctrlKey && event.key.toLowerCase() === "v" && (copiedClips.length || copiedClip)) {
            event.preventDefault();
            pushHistory();
            const source = copiedClips.length ? copiedClips : [JSON.parse(copiedClip)];
            const minStart = Math.min(...source.map((clip) => Number(clip.start || 0)));
            const maxEnd = Math.max(...source.map((clip) => Number(clip.start || 0) + Number(clip.duration || 0)));
            const offset = projectTime >= minStart && projectTime <= maxEnd ? 0.5 : projectTime - minStart;
            const pasted = source.map((clip) => normalizeClip({...clip, id: uid("paste"), start: Math.max(0, Number(clip.start || 0) + offset)}));
            state.clips.push(...pasted);
            setSelection(pasted.map((clip) => clip.id), pasted[0]?.id || "");
            render();
            scheduleSave();
          }
        });
        window.addEventListener("beforeunload", (event) => {
          persistProjectTime(true);
          if (!dirty && !saving && !saveFailed) return;
          event.preventDefault();
          event.returnValue = "";
        });
        root.querySelector("[data-record-audio]").addEventListener("click", async (event) => {
          if (recorder && recorder.state === "recording") {
            recorder.stop();
            event.currentTarget.dataset.icon = "mic";
            return;
          }
          const stream = await navigator.mediaDevices.getUserMedia({audio: true});
          recordChunks = [];
          recorder = new MediaRecorder(stream);
          recorder.addEventListener("dataavailable", (item) => item.data.size && recordChunks.push(item.data));
          recorder.addEventListener("stop", () => {
            stream.getTracks().forEach((track) => track.stop());
            const blob = new Blob(recordChunks, {type: recorder.mimeType || "audio/webm"});
            handleFile(new File([blob], `voice-${Date.now()}.webm`, {type: blob.type}), "audio");
          }, {once: true});
          recorder.start();
          event.currentTarget.dataset.icon = "square";
        });
        const textInputs = ["value", "font", "size", "color", "stroke", "stroke-width", "bg", "bg-alpha"].map((name) => root.querySelector(`[data-text-${name}]`)).filter(Boolean);
        textInputs.forEach((input) => input.addEventListener("input", () => {
          const clip = selectedClip();
          if (!clip || !["text", "caption"].includes(clip.type)) return;
          if (!input.dataset.historyStarted) {
            pushHistory();
            input.dataset.historyStarted = "true";
          }
          clip.text = root.querySelector("[data-text-value]").value;
          clip.style = {
            ...(clip.style || {}),
            font: root.querySelector("[data-text-font]").value,
            size: Number(root.querySelector("[data-text-size]").value),
            color: root.querySelector("[data-text-color]").value,
            stroke: root.querySelector("[data-text-stroke]").value,
            strokeWidth: Number(root.querySelector("[data-text-stroke-width]").value),
            bg: root.querySelector("[data-text-bg]").value,
            bgAlpha: Number(root.querySelector("[data-text-bg-alpha]").value),
          };
          renderPreview();
          renderTracks();
          updateTextControls(clip);
          scheduleSave();
        }));
        textInputs.forEach((input) => input.addEventListener("change", () => {
          delete input.dataset.historyStarted;
        }));

        if (readOnly) {
          root.classList.add("is-view-only");
          root.querySelectorAll("button, input, select, textarea").forEach((control) => {
            if (control.matches("[data-editor-play],[data-editor-seek]") || control.closest(".editor-playbar")) return;
            control.disabled = true;
          });
          if (saveStatus) saveStatus.textContent = t("view_only", "View only");
        }
        restoreProjectTime();
        render();
        refreshExportQueue();

        function setupMobileVideoEditor() {
          const mobileQuery = window.matchMedia("(max-width: 760px)");
          const syncMobileState = () => {
            document.body.classList.toggle("is-mobile-video-editor", mobileQuery.matches);
          };
          const revealActiveControls = () => {
            if (!mobileQuery.matches) return;
            const activePanel = root.querySelector(".editor-tool-panel.is-active");
            const activeTool = root.querySelector(".editor-rail .editor-icon-button.is-active");
            activePanel?.classList.remove("is-mobile-panel-enter");
            void activePanel?.offsetWidth;
            activePanel?.classList.add("is-mobile-panel-enter");
            activeTool?.scrollIntoView({behavior: "smooth", inline: "center", block: "nearest"});
          };
          syncMobileState();
          mobileQuery.addEventListener?.("change", syncMobileState);
          root.querySelectorAll("[data-editor-tool], [data-panel-tab]").forEach((button) => {
            button.addEventListener("click", () => window.setTimeout(revealActiveControls, 30));
          });
          root.querySelectorAll("[data-add-kind], [data-split-clip], [data-duplicate-clip], [data-delete-clip]").forEach((button) => {
            button.addEventListener("click", () => {
              if (!mobileQuery.matches) return;
              root.querySelector(".editor-timeline-panel")?.scrollIntoView({behavior: "smooth", block: "center"});
            });
          });
        }
      })();
