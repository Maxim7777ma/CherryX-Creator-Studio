"use strict";

class CherryXMusicStudio {
  constructor() {
    this.container = document.querySelector("[data-music-editor]");
    if (!this.container) return;

    this.projectId = this.container.dataset.projectId || "";
    this.projectsApiUrl = this.normalizeApiUrl(this.container.dataset.projectsApiUrl || "");
    this.projectTitle = this.container.dataset.projectTitle || "Untitled Beat";
    this.toneSrc = this.container.dataset.toneSrc || "https://cdn.jsdelivr.net/npm/tone@14/build/Tone.js";

    this.baseCellWidth = 42;
    this.cellWidth = 42;
    this.whiteKeyHeight = 36;
    this.blackKeyHeight = 24;
    this.rowHeight = this.whiteKeyHeight;
    this.pianoRows = [];
    this.trackRowHeight = 68;
    this.steps = 16;
    this.timelineBars = 64;
    this.timelineSeconds = 300;
    this.tracks = 6;
    this.trackNames = [];
    this.zoom = 1;
    this.projectLyrics = "";
    this.lyricsPanel = { open: false, minimized: false, x: null, y: null, width: 390, height: 460 };
    this.lyricsSaveTimer = null;

    this.bpm = 120;
    this.currentTime = 0;
    this.isPlaying = false;
    this.clockTimer = null;
    this.stepTimer = null;
    this.playTick = 0;

    this.tool = "draw";
    this.arrangeTool = "select";
    this.activeView = "playlist";
    this.noteLengthBeats = 1;
    this.selectedChannelId = null;
    this.selectedPatternId = null;
    this.selectedClipId = null;
    this.selectedNoteId = null;
    this.selectedClipIds = new Set();
    this.selectedNoteIds = new Set();

    this.channels = [
      this.createChannel("Piano", "instrument", "#ff7a18", "piano"),
      this.createChannel("Bass", "instrument", "#36d399", "bass"),
      this.createChannel("Kick", "drum", "#60a5fa", "kick"),
      this.createChannel("Snare", "drum", "#a855f7", "snare"),
      this.createChannel("Hi-Hat", "drum", "#ffd166", "hat"),
      this.createChannel("Clap", "drum", "#ef4444", "clap")
    ];

    this.patterns = [];
    this.clips = [];
    this.assets = [];
    this.synths = {};
    this.players = {};
    this.master = null;
    this.audioReady = false;
    this.audioGraphReady = false;
    this.audioUnlockPromise = null;
    this.toneLoadPromise = null;
    this.mediaRecorder = null;
    this.recordChunks = [];
    this.recordStream = null;
    this.isRecording = false;
    this.assetPreviewAudio = null;
    this.assetPreviewButton = null;
    this.audioInputs = [];
    this.midiInputs = [];
    this.activeAudioInputId = "";
    this.activeMidiInputId = "";
    this.audioInputRole = "vocal";
    this.monitorInput = false;
    this.noiseReduction = false;
    this.deviceTestStream = null;
    this.deviceAudioContext = null;
    this.deviceAnalyser = null;
    this.deviceMonitorSource = null;
    this.deviceMeterTimer = null;
    this.midiAccess = null;
    this.recordingStartTime = 0;
    this.recordingEndTime = 0;
    this.recordingTrack = 0;
    this.recordingClipId = null;
    this.history = [];
    this.historyIndex = -1;
    this.maxUndoSteps = 5;
    this.maxHistory = this.maxUndoSteps + 1;
    this.readyForAutosave = false;
    this.isDirty = false;
    this.autoSaveTimer = null;
    this.contextMenu = null;
    this.elements = {};
    this.i18n = window.CX_MUSIC_MESSAGES || {};

    this.init();
  }

  init() {
    this.cacheElements();
    this.loadInitialState();
    this.ensureDefaultProject();
    this.selectedChannelId = this.selectedChannelId || this.channels[0]?.id || null;
    this.selectedPatternId = this.selectedPatternId || this.patterns[0]?.id || null;
    this.bindEvents();
    this.initCustomSelects();
    this.applyLocalizedControlTitles();
    this.loadUiPrefs();
    this.renderAll();
    this.applyUiPrefs();
    this.saveHistory();
    this.readyForAutosave = true;
    this.startAutoSave();
    this.updateInspectorDefault();
  }

  normalizeApiUrl(url) {
    return url && !url.endsWith("/") ? `${url}/` : url;
  }

  t(key, fallback = key, vars = {}) {
    let value = this.i18n[key] || fallback || key;
    Object.entries(vars).forEach(([name, replacement]) => {
      value = value.replaceAll(`{${name}}`, String(replacement));
    });
    return value;
  }

  cacheElements() {
    const q = selector => this.container.querySelector(selector);
    this.elements.timeDisplay = q("[data-time-display]");
    this.elements.bpmInput = q("[data-bpm]");
    this.elements.projectName = q("[data-project-name]");
    this.elements.snap = q("[data-snap]");
    this.elements.ruler = q("[data-timeline-ruler]");
    this.elements.playhead = q("[data-playhead]");
    this.elements.playlistGrid = q("[data-playlist-grid]");
    this.elements.pianoKeys = q("[data-piano-keys]");
    this.elements.pianoRoll = q("[data-piano-roll]");
    this.elements.pianoRuler = q("[data-piano-ruler]");
    this.elements.pianoPlayhead = q("[data-piano-playhead]");
    this.elements.noteLayer = q("[data-piano-notes]");
    this.elements.channelList = q("[data-channel-list]");
    this.elements.stepSequencer = q("[data-step-sequencer]");
    this.elements.mixer = q("[data-mixer]");
    this.elements.assetList = q("[data-asset-list]");
    this.elements.assetSearch = q("[data-asset-search]");
    this.elements.audioInput = q("[data-audio-input]");
    this.elements.deviceStatus = q("[data-device-status]");
    this.elements.recordLabel = q("[data-record-label]");
    this.elements.deviceModal = q("[data-device-modal]");
    this.elements.deviceSummary = q("[data-device-summary]");
    this.elements.audioInputList = q("[data-audio-input-list]");
    this.elements.midiInputList = q("[data-midi-input-list]");
    this.elements.inputMeter = q("[data-input-meter]");
    this.elements.deviceMonitor = q("[data-device-monitor]");
    this.elements.deviceNoise = q("[data-device-noise]");
    this.elements.midiReadout = q("[data-midi-readout]");
    this.elements.inspector = q("[data-inspector]");
    this.elements.activePatternLabel = q("[data-active-pattern-label]");
    this.elements.zoomLevel = q("[data-zoom-level]");
    this.elements.patternSelect = q("[data-pattern-select]");
    this.elements.channelSelect = q("[data-channel-select]");
    this.elements.noteLength = q("[data-note-length]");
    this.elements.lyricsPad = q("[data-lyrics-pad]");
    this.elements.lyricsEditor = q("[data-lyrics-editor]");
    this.elements.lyricsCount = q("[data-lyrics-count]");
  }

  bindEvents() {
    this.container.querySelectorAll("[data-transport]").forEach(button => {
      button.addEventListener("click", () => this.handleTransport(button.dataset.transport));
    });
    this.container.querySelectorAll("[data-view]").forEach(button => {
      button.addEventListener("click", () => this.switchView(button.dataset.view, button));
    });
    this.container.querySelectorAll("[data-tool]").forEach(button => {
      button.addEventListener("click", () => this.setTool(button.dataset.tool, button));
    });
    this.container.querySelectorAll("[data-arrange-tool]").forEach(button => {
      button.addEventListener("click", () => this.setArrangeTool(button.dataset.arrangeTool, button));
    });
    this.container.querySelectorAll("[data-zoom]").forEach(button => {
      button.addEventListener("click", () => this.changeZoom(button.dataset.zoom === "in" ? 0.25 : -0.25));
    });
    this.container.querySelectorAll("[data-preset]").forEach(button => {
      button.addEventListener("click", () => this.applyPreset(button.dataset.preset));
    });
    this.container.querySelectorAll("[data-drum]").forEach(button => {
      button.addEventListener("click", () => this.addDrumChannel(button.dataset.drum));
    });

    const applyBpm = (value, save = true) => {
      this.bpm = this.clamp(parseInt(value, 10) || 120, 40, 300);
      if (this.elements.bpmInput) this.elements.bpmInput.value = this.bpm;
      if (this.audioReady && window.Tone) Tone.Transport.bpm.value = this.bpm;
      this.updateTimelineLength();
      this.applyTimelineMetrics();
      this.generateRuler();
      this.renderTrackGrid();
      this.renderPlaylist();
      this.updatePlayhead();
      if (this.isPlaying) this.startStepPlayback();
      if (save) this.saveHistory();
    };
    this.elements.bpmInput?.addEventListener("change", event => applyBpm(event.target.value));
    this.container.querySelectorAll("[data-bpm-step]").forEach(button => {
      button.addEventListener("click", event => {
        event.preventDefault();
        applyBpm(this.bpm + Number(button.dataset.bpmStep || 0));
      });
    });
    this.elements.projectName?.addEventListener("input", event => {
      this.projectTitle = event.target.value.trim() || "Untitled Beat";
      this.container.querySelectorAll("[data-project-title]").forEach(el => {
        el.textContent = this.projectTitle;
      });
      this.markDirty();
    });
    this.elements.audioInput?.addEventListener("change", event => this.handleAudioUpload(event));
    this.elements.pianoRoll?.addEventListener("click", event => this.handlePianoRollClick(event));
    this.elements.pianoRoll?.addEventListener("contextmenu", event => this.showPianoRollContextMenu(event));
    this.elements.pianoRoll?.addEventListener("mousedown", event => {
      if (event.shiftKey) {
        this.startSurfacePan(event, this.elements.pianoRoll);
        return;
      }
      if (event.ctrlKey || event.metaKey) this.startNoteBoxSelect(event);
    });
    this.elements.pianoRoll?.addEventListener("pointerdown", event => {
      if (event.ctrlKey || event.metaKey) this.startNoteBoxSelect(event);
    });
    this.elements.pianoRoll?.addEventListener("scroll", () => this.syncPianoScroll());
    this.elements.pianoRuler?.addEventListener("mousedown", event => this.startPianoSeek(event));
    this.elements.pianoPlayhead?.addEventListener("mousedown", event => this.startPianoSeek(event));
    this.elements.playlistGrid?.addEventListener("scroll", () => this.syncTimelineScroll());
    this.elements.playlistGrid?.addEventListener("mousedown", event => {
      if (event.shiftKey) {
        this.startSurfacePan(event, this.elements.playlistGrid);
        return;
      }
      if (event.ctrlKey || event.metaKey) this.startClipBoxSelect(event);
    }, true);
    this.elements.playlistGrid?.addEventListener("pointerdown", event => {
      if (event.ctrlKey || event.metaKey) this.startClipBoxSelect(event);
    }, true);
    this.elements.playlistGrid?.addEventListener("dragover", event => event.preventDefault());
    this.elements.playlistGrid?.addEventListener("drop", event => this.handlePlaylistDrop(event));
    this.elements.assetList?.addEventListener("dragover", event => event.preventDefault());
    this.elements.assetList?.addEventListener("drop", event => this.handleAssetListDrop(event));
    this.elements.ruler?.addEventListener("mousedown", event => {
      if (event.shiftKey) this.startSurfacePan(event, this.elements.playlistGrid);
    }, true);
    this.elements.ruler?.addEventListener("mousedown", event => this.startTimelineSeek(event));
    this.elements.playhead?.addEventListener("mousedown", event => this.startTimelineSeek(event));
    window.addEventListener("resize", () => this.applyLyricsPanelMetrics());

    this.container.querySelector("[data-save-project]")?.addEventListener("click", () => this.saveProject());
    this.container.querySelector("[data-add-channel]")?.addEventListener("click", () => this.addChannel());
    this.elements.playlistGrid?.addEventListener("click", event => {
      if (event.target.closest("[data-add-track]")) this.addTrack();
      const deleteButton = event.target.closest("[data-delete-track]");
      if (deleteButton) this.deleteTrack(Number(deleteButton.dataset.deleteTrack));
    });
    this.container.querySelector('[data-action="new-pattern"]')?.addEventListener("click", () => this.addPatternClip());
    this.container.querySelectorAll('[data-action="upload-audio"]').forEach(button => {
      button.addEventListener("click", event => {
        event.preventDefault();
        this.elements.audioInput?.click();
      });
    });
    this.container.querySelector('[data-action="scan-devices"]')?.addEventListener("click", () => this.openDevicesModal());
    this.container.querySelector('[data-action="record-audio"]')?.addEventListener("click", () => this.toggleAudioRecording());
    this.container.querySelector("[data-device-close]")?.addEventListener("click", () => this.closeDevicesModal());
    this.elements.deviceModal?.addEventListener("click", event => {
      if (event.target === this.elements.deviceModal) this.closeDevicesModal();
    });
    this.container.querySelector("[data-device-refresh]")?.addEventListener("click", () => this.scanAudioDevices({ render: true, notify: true }));
    this.container.querySelector("[data-device-test]")?.addEventListener("click", () => this.toggleDeviceTest());
    this.container.querySelector("[data-device-record]")?.addEventListener("click", () => this.toggleAudioRecording());
    this.container.querySelector("[data-midi-test]")?.addEventListener("click", () => this.listenToMidiInputs());
    this.container.querySelectorAll("[data-input-role]").forEach(button => {
      button.addEventListener("click", () => {
        this.audioInputRole = button.dataset.inputRole || "vocal";
        this.renderDevicesModal();
        this.markDirty();
      });
    });
    this.elements.deviceMonitor?.addEventListener("change", event => {
      this.monitorInput = Boolean(event.target.checked);
      if (this.deviceTestStream) this.attachInputMonitor();
      this.markDirty();
    });
    this.elements.deviceNoise?.addEventListener("change", event => {
      this.noiseReduction = Boolean(event.target.checked);
      this.markDirty();
    });
    this.container.querySelector('[data-action="toggle-lyrics"]')?.addEventListener("click", () => this.toggleLyricsPad());
    this.elements.lyricsEditor?.addEventListener("input", () => this.handleLyricsInput());
    this.elements.lyricsEditor?.addEventListener("blur", () => this.commitLyricsNow());
    this.container.querySelectorAll("[data-lyrics-command]").forEach(button => {
      button.addEventListener("click", () => this.applyLyricsCommand(button.dataset.lyricsCommand, button.dataset.commandValue || null));
    });
    this.container.querySelector('[data-lyrics-window="close"]')?.addEventListener("click", () => this.closeLyricsPad());
    this.container.querySelector('[data-lyrics-window="minimize"]')?.addEventListener("click", () => this.minimizeLyricsPad());
    this.container.querySelector("[data-lyrics-drag]")?.addEventListener("pointerdown", event => this.startLyricsDrag(event));
    this.elements.lyricsPad?.addEventListener("mouseup", () => this.storeLyricsPanelMetrics());
    this.elements.lyricsPad?.addEventListener("touchend", () => this.storeLyricsPanelMetrics(), { passive: true });
    this.container.querySelector('[data-action="export-audio"]')?.addEventListener("click", () => {
      this.toast(this.t("audio_export_unavailable", "Audio export is not connected yet."), "info");
    });
    this.container.querySelector('[data-action="drum-fill"]')?.addEventListener("click", () => this.fillDrumLoop());
    this.container.querySelector('[data-action="clear-pattern"]')?.addEventListener("click", () => this.clearActivePattern());
    this.container.querySelector('[data-action="send-pattern-to-playlist"]')?.addEventListener("click", () => this.sendActivePatternToPlaylist());
    this.container.querySelector('[data-action="quantize-notes"]')?.addEventListener("click", () => this.quantizeActivePatternNotes());
    this.container.querySelector('[data-action="octave-up"]')?.addEventListener("click", () => this.moveSelectedNotesOctave(-12));
    this.container.querySelector('[data-action="octave-down"]')?.addEventListener("click", () => this.moveSelectedNotesOctave(12));
    this.container.querySelector('[data-action="toggle-step-length"]')?.addEventListener("click", () => this.toggleActivePatternLength());
    this.container.querySelector('[data-action="fill-hats"]')?.addEventListener("click", () => this.fillTwoStepHats());
    this.container.querySelector('[data-action="four-kick"]')?.addEventListener("click", () => this.fillFourOnFloorKick());
    this.container.querySelector('[data-action="clear-row"]')?.addEventListener("click", () => this.clearSelectedChannelRow());
    this.container.querySelector('[data-action="random-velocity"]')?.addEventListener("click", () => this.humanizeSelectedChannelSteps());
    this.container.querySelector('[data-action="duplicate-channel-pattern"]')?.addEventListener("click", () => this.duplicateSelectedChannelRow());
    this.elements.patternSelect?.addEventListener("change", event => {
      this.selectedPatternId = event.target.value;
      this.renderAll();
      this.saveUiPrefs();
      this.saveHistory();
    });
    this.elements.channelSelect?.addEventListener("change", event => {
      this.selectedChannelId = event.target.value;
      this.renderChannels();
      this.renderMixer();
      this.updatePatternControls();
      this.saveUiPrefs();
      this.saveHistory();
    });
    this.elements.noteLength?.addEventListener("change", event => {
      this.noteLengthBeats = Number(event.target.value) || 1;
      this.saveUiPrefs();
    });
    this.elements.snap?.addEventListener("change", () => {
      this.applyTimelineMetrics();
      this.syncCustomSelects();
      this.saveUiPrefs();
    });
    this.elements.assetSearch?.addEventListener("input", () => this.renderAssets());

    document.addEventListener("keydown", event => this.handleHotkeys(event));
    document.addEventListener("click", () => {
      this.hideContextMenu();
      this.closeCustomSelects();
    });
    window.addEventListener("resize", () => this.positionOpenCustomSelects());
    window.addEventListener("scroll", () => this.positionOpenCustomSelects(), true);
    window.addEventListener("beforeunload", () => this.writeLocalBackup());
  }

  initCustomSelects() {
    this.container.querySelectorAll("select[data-custom-select]").forEach(select => this.ensureCustomSelect(select));
    this.syncCustomSelects();
  }

  ensureCustomSelect(select) {
    if (!select || select.dataset.customSelectReady === "1") return select._customSelect;
    select.dataset.customSelectReady = "1";
    select.classList.add("cx-native-select");
    const wrap = document.createElement("div");
    wrap.className = "cx-custom-select";
    wrap.dataset.customSelectFor = select.dataset.selectLabel || select.title || "";
    const button = document.createElement("button");
    button.type = "button";
    button.className = "cx-custom-select-trigger";
    button.setAttribute("aria-haspopup", "listbox");
    button.setAttribute("aria-expanded", "false");
    button.title = select.title || select.dataset.selectLabel || this.t("select", "Select");
    button.innerHTML = `
      <span class="cx-custom-select-label"></span>
      <strong></strong>
    `;
    const menu = document.createElement("div");
    menu.className = "cx-custom-select-menu";
    menu.setAttribute("role", "listbox");
    wrap.append(button, menu);
    select.insertAdjacentElement("afterend", wrap);
    const openMenu = event => {
      event.preventDefault();
      event.stopPropagation();
      const isOpen = wrap.classList.contains("is-open");
      this.closeCustomSelects(wrap);
      wrap.classList.toggle("is-open", !isOpen);
      button.setAttribute("aria-expanded", String(!isOpen));
      if (!isOpen) this.positionCustomSelect(select);
    };
    button.addEventListener("click", openMenu);
    menu.addEventListener("click", event => {
      const item = event.target.closest("[data-custom-option]");
      if (!item) return;
      event.preventDefault();
      event.stopPropagation();
      select.value = item.dataset.customOption;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      this.syncCustomSelect(select);
      this.closeCustomSelects();
    });
    select._customSelect = { wrap, button, menu };
    this.syncCustomSelect(select);
    return select._customSelect;
  }

  syncCustomSelects() {
    this.container.querySelectorAll("select[data-custom-select]").forEach(select => this.syncCustomSelect(select));
  }

  syncCustomSelect(select) {
    const custom = this.ensureCustomSelect(select);
    if (!custom) return;
    const selected = select.selectedOptions?.[0] || select.options?.[0];
    const label = select.dataset.selectLabel || select.title || this.t("select", "Select");
    custom.button.querySelector(".cx-custom-select-label").textContent = label;
    custom.button.querySelector("strong").textContent = selected?.textContent?.trim() || label;
    custom.button.title = `${label}: ${selected?.textContent?.trim() || ""}`.trim();
    custom.menu.innerHTML = [...select.options].map(option => {
      const text = option.textContent.trim();
      return `
      <button type="button" role="option" data-custom-option="${this.escapeHtml(option.value)}" class="${option.selected ? "is-selected" : ""}" aria-selected="${option.selected ? "true" : "false"}" title="${this.escapeHtml(text)}">
        ${this.escapeHtml(text)}
      </button>
    `;
    }).join("");
  }

  closeCustomSelects(except = null) {
    this.container.querySelectorAll(".cx-custom-select.is-open").forEach(wrap => {
      if (wrap === except) return;
      wrap.classList.remove("is-open");
      wrap.classList.remove("is-floating", "opens-up");
      const menu = wrap.querySelector(".cx-custom-select-menu");
      if (menu) {
        menu.style.left = "";
        menu.style.top = "";
        menu.style.bottom = "";
        menu.style.width = "";
        menu.style.maxHeight = "";
      }
      wrap.querySelector(".cx-custom-select-trigger")?.setAttribute("aria-expanded", "false");
    });
  }

  positionOpenCustomSelects() {
    this.container.querySelectorAll("select[data-custom-select]").forEach(select => {
      if (select._customSelect?.wrap?.classList.contains("is-open")) this.positionCustomSelect(select);
    });
  }

  positionCustomSelect(select) {
    const custom = select?._customSelect;
    if (!custom) return;
    const { wrap, button, menu } = custom;
    wrap.classList.remove("is-floating", "opens-up");
    menu.style.left = "";
    menu.style.top = "";
    menu.style.bottom = "";
    menu.style.width = "";
    menu.style.maxHeight = "";
    if (window.innerWidth > 760) return;

    const rect = button.getBoundingClientRect();
    const gap = 8;
    const sidePad = 12;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight;
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth;
    const below = viewportHeight - rect.bottom - gap;
    const above = rect.top - gap;
    const openUp = below < 176 && above > below;
    const maxHeight = Math.max(132, Math.min(240, (openUp ? above : below) - sidePad));
    const width = Math.min(Math.max(rect.width, 176), viewportWidth - sidePad * 2);
    const left = Math.min(Math.max(sidePad, rect.left), viewportWidth - width - sidePad);

    wrap.classList.add("is-floating");
    if (openUp) wrap.classList.add("opens-up");
    menu.style.left = `${left}px`;
    menu.style.width = `${width}px`;
    menu.style.maxHeight = `${maxHeight}px`;
    if (openUp) {
      menu.style.top = "auto";
      menu.style.bottom = `${Math.max(sidePad, viewportHeight - rect.top + gap)}px`;
    } else {
      menu.style.top = `${Math.min(rect.bottom + gap, viewportHeight - maxHeight - sidePad)}px`;
      menu.style.bottom = "auto";
    }
  }

  uiPrefsKey() {
    return `cherryx-music-ui:${this.projectId || "draft"}`;
  }

  loadUiPrefs() {
    try {
      const prefs = JSON.parse(localStorage.getItem(this.uiPrefsKey()) || "{}");
      if (prefs.activeView) this.activeView = prefs.activeView;
      if (prefs.tool) this.tool = prefs.tool;
      if (prefs.arrangeTool) this.arrangeTool = prefs.arrangeTool;
      if (prefs.noteLengthBeats) this.noteLengthBeats = Number(prefs.noteLengthBeats) || this.noteLengthBeats;
      if (prefs.selectedPatternId) this.selectedPatternId = prefs.selectedPatternId;
      if (prefs.selectedChannelId) this.selectedChannelId = prefs.selectedChannelId;
      if (prefs.snap && this.elements.snap?.querySelector(`option[value="${CSS.escape(prefs.snap)}"]`)) this.elements.snap.value = prefs.snap;
    } catch (error) {
      console.warn("Could not load music editor UI prefs", error);
    }
  }

  saveUiPrefs() {
    try {
      localStorage.setItem(this.uiPrefsKey(), JSON.stringify({
        activeView: this.activeView,
        tool: this.tool,
        arrangeTool: this.arrangeTool,
        noteLengthBeats: this.noteLengthBeats,
        selectedPatternId: this.selectedPatternId,
        selectedChannelId: this.selectedChannelId,
        snap: this.elements.snap?.value || "1/32"
      }));
    } catch (error) {
      console.warn("Could not save music editor UI prefs", error);
    }
  }

  applyUiPrefs() {
    if (!this.patterns.some(pattern => pattern.id === this.selectedPatternId)) this.selectedPatternId = this.patterns[0]?.id || null;
    if (!this.channels.some(channel => channel.id === this.selectedChannelId)) this.selectedChannelId = this.channels[0]?.id || null;
    this.switchView(this.activeView || "playlist", this.container.querySelector(`[data-view="${this.activeView || "playlist"}"]`));
    this.setTool(this.tool || "draw", this.container.querySelector(`[data-tool="${this.tool || "draw"}"]`));
    this.setArrangeTool(this.arrangeTool || "select", this.container.querySelector(`[data-arrange-tool="${this.arrangeTool || "select"}"]`));
    this.updatePatternControls();
  }

  applyLocalizedControlTitles() {
    const titles = {
      "playlist": this.t("playlist", "Playlist"),
      "piano-roll": this.t("piano_roll", "Piano Roll"),
      "step-seq": this.t("channel_rack", "Channel Rack"),
      "mixer": this.t("mixer", "Mixer")
    };
    this.container.querySelectorAll("[data-view]").forEach(button => {
      const title = titles[button.dataset.view] || button.textContent.trim();
      button.title = button.title || title;
      button.setAttribute("aria-label", button.getAttribute("aria-label") || title);
    });
    const actionTitles = {
      "send-pattern-to-playlist": this.t("send_to_playlist", "Send pattern to playlist"),
      "quantize-notes": this.t("quantize_notes", "Quantize notes"),
      "octave-up": this.t("octave_up", "Octave up"),
      "octave-down": this.t("octave_down", "Octave down")
    };
    Object.entries(actionTitles).forEach(([action, title]) => {
      this.container.querySelectorAll(`[data-action="${action}"]`).forEach(button => {
        button.title = button.title || title;
        button.setAttribute("aria-label", button.getAttribute("aria-label") || title);
      });
    });
    this.container.querySelectorAll("[data-tool]").forEach(button => {
      const title = button.textContent.trim();
      button.title = button.title || title;
      button.setAttribute("aria-label", button.getAttribute("aria-label") || title);
    });
  }

  handleHotkeys(event) {
    const key = event.key.toLowerCase();
    const hasModifier = event.ctrlKey || event.metaKey;
    const isEditable = this.isEditableTarget(event.target);
    if (isEditable) return;
    if (event.code === "Space") {
      event.preventDefault();
      this.isPlaying ? this.pause() : this.play();
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      this.deleteSelected();
    }
    if (hasModifier && key === "s") {
      event.preventDefault();
      this.saveProject();
    }
    if (hasModifier && key === "d") {
      event.preventDefault();
      this.duplicateSelected();
    }
    if (hasModifier && key === "z") {
      event.preventDefault();
      event.shiftKey ? this.redo() : this.undo();
    }
    if (hasModifier && key === "y") {
      event.preventDefault();
      this.redo();
    }
    if (hasModifier && (event.key === "+" || event.key === "=")) {
      event.preventDefault();
      this.changeZoom(0.25);
    }
    if (hasModifier && event.key === "-") {
      event.preventDefault();
      this.changeZoom(-0.25);
    }
    if (this.activeView === "piano-roll" && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) {
      const hasSelection = this.selectedNoteId || this.selectedNoteIds.size;
      if (hasSelection) {
        event.preventDefault();
        if (event.shiftKey && (event.key === "ArrowLeft" || event.key === "ArrowRight")) {
          this.resizeSelectedNotes(event.key === "ArrowRight" ? this.snapGridSize() : -this.snapGridSize());
          return;
        }
        const dx = event.key === "ArrowLeft" ? -this.snapGridSize() : event.key === "ArrowRight" ? this.snapGridSize() : 0;
        const dr = event.key === "ArrowUp" ? -1 : event.key === "ArrowDown" ? 1 : 0;
        this.nudgeSelectedNotes(dx, dr);
      }
    }
  }

  isEditableTarget(target) {
    if (!target) return false;
    const tag = target.tagName;
    return ["INPUT", "TEXTAREA", "SELECT"].includes(tag) || Boolean(target.closest?.("[contenteditable='true']"));
  }

  createChannel(name, type = "instrument", color = "#ff7a18", preset = "piano") {
    return {
      id: this.uuid(),
      name,
      type,
      color,
      preset,
      volume: 80,
      pan: 0,
      muted: false,
      solo: false,
      send: { reverb: 0, delay: 0 },
      fx: { lowpass: 20000, highpass: 20, drive: 0 }
    };
  }

  createPattern(name = "Pattern") {
    const colors = ["#ff7a18", "#36d399", "#60a5fa", "#a855f7", "#ef4444", "#facc15"];
    return { id: this.uuid(), name, color: colors[this.patterns.length % colors.length], lengthSteps: this.steps, notes: [], stepsByChannel: {}, stepVelocity: {} };
  }

  ensureDefaultProject() {
    if (this.patterns.length) return;
    const pattern = this.createPattern("Pattern 1");
    this.patterns.push(pattern);
    this.selectedPatternId = pattern.id;
    this.clips.push({ id: this.uuid(), type: "pattern", name: pattern.name, patternId: pattern.id, track: 0, x: this.cellWidth, width: this.cellWidth * 4, color: pattern.color });
  }

  uuid() {
    if (window.crypto?.randomUUID) return crypto.randomUUID();
    return `id_${Date.now()}_${Math.random().toString(16).slice(2)}`;
  }

  initAudioGraph() {
    if (!window.Tone || !this.audioReady || this.audioGraphReady) return;
    this.audioGraphReady = true;
    try {
      this.master = new Tone.Volume(-4).toDestination();
      this.channels.forEach(channel => this.ensureSynth(channel));
      Tone.Transport.bpm.value = this.bpm;
    } catch (error) {
      this.audioGraphReady = false;
      console.warn("Tone graph error:", error);
    }
  }

  loadTone() {
    if (window.Tone) return Promise.resolve(window.Tone);
    if (this.toneLoadPromise) return this.toneLoadPromise;
    this.toneLoadPromise = new Promise((resolve, reject) => {
      const existing = document.querySelector(`script[src="${this.toneSrc}"]`);
      if (existing) {
        existing.addEventListener("load", () => resolve(window.Tone), { once: true });
        existing.addEventListener("error", () => reject(new Error("Tone.js failed to load")), { once: true });
        return;
      }
      const script = document.createElement("script");
      script.src = this.toneSrc;
      script.async = true;
      script.onload = () => resolve(window.Tone);
      script.onerror = () => reject(new Error("Tone.js failed to load"));
      document.head.appendChild(script);
    }).finally(() => {
      this.toneLoadPromise = null;
    });
    return this.toneLoadPromise;
  }

  async unlockAudio() {
    if (this.audioReady) return;
    if (this.audioUnlockPromise) return this.audioUnlockPromise;
    this.audioUnlockPromise = (async () => {
      try {
        await this.loadTone();
        if (!window.Tone) return;
        await Tone.start();
        this.audioReady = true;
        this.initAudioGraph();
      } catch (error) {
        console.warn("Tone start error:", error);
      } finally {
        this.audioUnlockPromise = null;
      }
    })();
    return this.audioUnlockPromise;
  }

  ensureSynth(channel) {
    if (!window.Tone || !channel || !this.audioReady) return null;
    this.initAudioGraph();
    this.normalizeChannel(channel);
    if (this.synths[channel.id]) return this.synths[channel.id];
    let synth;
    try {
      if (channel.type === "drum") {
        if (channel.preset === "hat") {
          synth = new Tone.MetalSynth({ frequency: 220, envelope: { attack: 0.001, decay: 0.08, release: 0.02 }, harmonicity: 4, modulationIndex: 20, resonance: 3500, octaves: 1.5 });
        } else if (channel.preset === "snare" || channel.preset === "clap") {
          synth = new Tone.NoiseSynth({ noise: { type: "white" }, envelope: { attack: 0.001, decay: 0.15, sustain: 0, release: 0.05 } });
        } else {
          synth = new Tone.MembraneSynth({ pitchDecay: 0.05, octaves: 6, oscillator: { type: "sine" }, envelope: { attack: 0.001, decay: 0.35, sustain: 0.01, release: 0.1 } });
        }
      } else {
        synth = new Tone.PolySynth(Tone.Synth, this.instrumentConfig(channel.preset));
      }
      const volume = new Tone.Volume(this.volumeToDb(channel.volume));
      const highpass = new Tone.Filter(channel.fx?.highpass || 20, "highpass");
      const lowpass = new Tone.Filter(channel.fx?.lowpass || 20000, "lowpass");
      const delay = new Tone.FeedbackDelay("8n", this.clamp(Number(channel.send?.delay || 0), 0, 100) / 250);
      const reverb = new Tone.Reverb({ decay: 1.8, wet: this.clamp(Number(channel.send?.reverb || 0), 0, 100) / 100 });
      const pan = new Tone.Panner(channel.pan / 100);
      synth.chain(volume, highpass, lowpass, delay, reverb, pan, this.master || Tone.Destination);
      this.synths[channel.id] = { synth, volume, highpass, lowpass, delay, reverb, pan };
      return this.synths[channel.id];
    } catch (error) {
      console.warn("Tone synth error:", error);
      return null;
    }
  }

  normalizeChannel(channel) {
    channel.volume = this.clamp(Number(channel.volume ?? 80), 0, 100);
    channel.pan = this.clamp(Number(channel.pan ?? 0), -100, 100);
    channel.muted = Boolean(channel.muted);
    channel.solo = Boolean(channel.solo);
    channel.send = channel.send || {};
    channel.send.reverb = this.clamp(Number(channel.send.reverb || 0), 0, 100);
    channel.send.delay = this.clamp(Number(channel.send.delay || 0), 0, 100);
    channel.fx = channel.fx || {};
    channel.fx.lowpass = this.clamp(Number(channel.fx.lowpass || 20000), 200, 20000);
    channel.fx.highpass = this.clamp(Number(channel.fx.highpass || 20), 20, 8000);
    channel.fx.drive = this.clamp(Number(channel.fx.drive || 0), 0, 100);
  }

  normalizePattern(pattern) {
    if (!pattern) return;
    pattern.color = pattern.color || "#ff7a18";
    pattern.lengthSteps = this.clamp(Number(pattern.lengthSteps || this.steps), 16, 32);
    pattern.notes = Array.isArray(pattern.notes) ? pattern.notes : [];
    pattern.stepsByChannel = pattern.stepsByChannel || {};
    pattern.stepVelocity = pattern.stepVelocity || {};
  }

  instrumentConfig(preset) {
    const configs = {
      piano: { oscillator: { type: "triangle" }, envelope: { attack: 0.005, decay: 0.3, sustain: 0.15, release: 0.5 } },
      bass: { oscillator: { type: "sawtooth" }, envelope: { attack: 0.01, decay: 0.2, sustain: 0.4, release: 0.3 } },
      lead: { oscillator: { type: "sawtooth" }, envelope: { attack: 0.01, decay: 0.15, sustain: 0.5, release: 0.4 } },
      pluck: { oscillator: { type: "triangle" }, envelope: { attack: 0.001, decay: 0.2, sustain: 0.05, release: 0.3 } },
      pad: { oscillator: { type: "sine" }, envelope: { attack: 0.3, decay: 0.2, sustain: 0.7, release: 1.5 } }
    };
    return configs[preset] || configs.piano;
  }

  handleTransport(action) {
    if (action === "play") this.play();
    if (action === "pause") this.pause();
    if (action === "stop") this.stop();
    if (action === "pause-stop") this.isPlaying ? this.pause() : this.stop();
    if (action === "rewind") this.rewind();
  }

  async play() {
    await this.unlockAudio();
    if (this.isPlaying) {
      this.pause();
      return;
    }
    this.isPlaying = true;
    this.playTick = Math.floor(this.currentTime / this.tickSeconds());
    this.updateTransportButtons();
    this.startClock();
    this.startStepPlayback();
    if (this.transportPlaysArrangement()) {
      this.startAudioClips();
    } else {
      this.stopAudioPlayers();
    }
  }

  pause() {
    if (this.isRecording) this.stopAudioRecording();
    this.isPlaying = false;
    this.stopClock();
    this.stopStepPlayback();
    this.stopAudioPlayers();
    this.updateTransportButtons();
  }

  stop() {
    if (this.isRecording) this.stopAudioRecording();
    this.isPlaying = false;
    this.currentTime = 0;
    this.playTick = 0;
    this.stopClock();
    this.stopStepPlayback();
    this.stopAudioPlayers();
    this.clearPlayingStep();
    this.updateTransportButtons();
    this.updateTimeDisplay();
    this.updatePlayhead();
  }

  rewind() {
    this.currentTime = 0;
    this.playTick = 0;
    this.updateTimeDisplay();
    this.updatePlayhead();
  }

  updateTransportButtons() {
    const play = this.container.querySelector('[data-transport="play"]');
    const pauseStop = this.container.querySelector('[data-transport="pause-stop"]');
    if (play) {
      play.classList.toggle("is-playing", this.isPlaying);
      play.setAttribute("aria-label", this.isPlaying ? this.t("pause", "Pause") : this.t("play", "Play"));
      play.title = this.isPlaying ? this.t("pause", "Pause") : this.t("play", "Play");
    }
    if (pauseStop) {
      pauseStop.classList.toggle("is-playing", this.isPlaying);
      pauseStop.textContent = this.isPlaying ? this.t("pause", "Pause") : this.t("stop", "Stop");
      pauseStop.setAttribute("aria-label", this.isPlaying ? this.t("pause", "Pause") : this.t("stop", "Stop"));
      pauseStop.title = this.isPlaying ? this.t("pause", "Pause") : this.t("stop", "Stop");
    }
  }

  startClock() {
    this.stopClock();
    this.clockTimer = setInterval(() => {
      this.currentTime += 0.05;
      this.updateTimeDisplay();
      this.updatePlayhead();
      this.updateRecordingClip();
    }, 50);
  }

  stopClock() {
    if (this.clockTimer) clearInterval(this.clockTimer);
    this.clockTimer = null;
  }

  startStepPlayback() {
    this.stopStepPlayback();
    this.stepTimer = setInterval(() => {
      try {
        this.playTransportTick(this.playTick);
        this.playTick += 1;
      } catch (error) {
        console.warn("Playback tick error:", error);
      }
    }, Math.max(40, this.tickSeconds() * 1000));
  }

  stopStepPlayback() {
    if (this.stepTimer) clearInterval(this.stepTimer);
    this.stepTimer = null;
  }

  transportPlaysPattern() {
    return this.activeView === "step-seq" || this.activeView === "piano-roll";
  }

  transportPlaysArrangement() {
    return !this.transportPlaysPattern();
  }

  playTransportTick(globalTick) {
    if (this.transportPlaysPattern()) {
      const pattern = this.getActivePattern();
      const stepCount = this.patternStepCount(pattern);
      this.clearPlayingStep();
      this.playPatternTick(pattern, globalTick % stepCount, globalTick);
      return;
    }
    this.playArrangementTick(globalTick);
  }

  playArrangementTick(globalTick) {
    this.clearPlayingStep();
    const activeClips = this.clips.filter(clip => {
      if (clip.type !== "pattern" || clip.muted) return false;
      const start = this.beatsToTicks(clip.x / this.cellWidth);
      const end = start + this.beatsToTicks(clip.width / this.cellWidth);
      return globalTick >= start && globalTick < end;
    });
    if (!activeClips.length) {
      const pattern = this.getActivePattern();
      this.playPatternTick(pattern, globalTick % this.patternStepCount(pattern));
      return;
    }
    activeClips.forEach(clip => {
      const pattern = this.patterns.find(item => item.id === clip.patternId);
      const stepCount = this.patternStepCount(pattern);
      const localTick = globalTick - this.beatsToTicks(clip.x / this.cellWidth);
      this.playPatternTick(pattern, localTick % stepCount, localTick);
    });
  }

  playPatternTick(pattern, stepIndex, localTick = stepIndex) {
    if (!pattern) return;
    const safeStepIndex = this.clamp(Math.floor(Number(stepIndex) || 0), 0, this.patternStepCount(pattern) - 1);
    if (pattern.id === this.getActivePattern()?.id) {
      this.container.querySelectorAll(`[data-step-index="${safeStepIndex}"]`).forEach(pad => pad.classList.add("playing"));
    }
    const hasSolo = this.channels.some(channel => channel.solo);
    this.channels.forEach(channel => {
      if (channel.muted || (hasSolo && !channel.solo)) return;
      if (this.getPatternSteps(pattern, channel.id)[safeStepIndex]) this.triggerChannel(channel, this.getStepVelocity(pattern, channel.id, safeStepIndex));
    });
    (pattern.notes || []).forEach(note => {
      const noteTick = this.beatsToTicks(note.x / this.cellWidth) % this.patternStepCount(pattern);
      if (noteTick !== safeStepIndex) return;
      const channel = this.channels.find(item => item.id === note.channelId) || this.getSelectedChannel();
      if (!channel || channel.muted || (hasSolo && !channel.solo)) return;
      this.triggerNote(channel, note);
    });
  }

  async triggerChannel(channel, velocityValue = 90) {
    await this.unlockAudio();
    const pack = this.ensureSynth(channel);
    if (!pack) return;
    const velocity = this.clamp(Number(velocityValue) || 90, 1, 100) / 100;
    if (channel.type === "drum") {
      if (channel.preset === "hat") pack.synth.triggerAttackRelease(0.05, undefined, velocity);
      else if (channel.preset === "snare" || channel.preset === "clap") pack.synth.triggerAttackRelease("16n", undefined, velocity);
      else pack.synth.triggerAttackRelease("C2", "16n", undefined, velocity);
    } else {
      pack.synth.triggerAttackRelease("C4", "16n", undefined, velocity);
    }
    this.flashMixer(channel.id);
  }

  async triggerNote(channel, note) {
    await this.unlockAudio();
    if (channel.type === "drum") {
      this.triggerChannel(channel);
      return;
    }
    const pack = this.ensureSynth(channel);
    if (!pack) return;
    const velocity = this.clamp(Number(note.velocity) || 85, 1, 100) / 100;
    const duration = Math.max(this.tickSeconds(), this.pixelsToSeconds(note.width || this.cellWidth));
    pack.synth.triggerAttackRelease(note.note || "C4", duration, undefined, velocity);
    this.flashPianoKey(note.note);
    this.flashMixer(channel.id);
  }

  clearPlayingStep() {
    this.container.querySelectorAll(".cx-step-pad.playing").forEach(pad => pad.classList.remove("playing"));
  }

  startAudioClips() {
    this.stopAudioPlayers();
    this.clips.filter(clip => clip.type === "audio").forEach(clip => {
      if (clip.muted) return;
      const asset = this.assets.find(item => item.id === clip.assetId || String(item.serverId) === String(clip.assetId));
      if (!asset?.url) return;
      const clipStart = this.pixelsToSeconds(clip.x);
      const clipLength = this.pixelsToSeconds(clip.width);
      const delay = Math.max(0, clipStart - this.currentTime);
      const playbackOffset = Math.max(0, this.currentTime - clipStart);
      const audio = new Audio(asset.url);
      const baseVolume = this.clamp(Number(clip.volume ?? 85), 0, 120) / 100;
      const trimStart = Math.max(0, Number(clip.trimStart || 0));
      const trimEnd = Math.max(0, Number(clip.trimEnd || 0));
      const clipDuration = Math.max(0.05, clipLength - trimEnd - playbackOffset);
      if (playbackOffset >= clipLength - trimEnd) return;
      audio.volume = Math.min(1, baseVolume);
      audio.currentTime = trimStart + playbackOffset;
      const timeout = setTimeout(() => {
        if (!this.isPlaying) return;
        audio.currentTime = trimStart + playbackOffset;
        audio.play().catch(() => {});
        this.applyAudioFade(audio, clip, baseVolume);
      }, delay * 1000);
      const stopTimeout = setTimeout(() => {
        try { audio.pause(); } catch (_) {}
      }, (delay + clipDuration) * 1000);
      this.players[clip.id] = { audio, timeout, stopTimeout };
    });
  }

  applyAudioFade(audio, clip, baseVolume) {
    const startedAt = performance.now();
    const fadeIn = Math.max(0, Number(clip.fadeIn || 0));
    const fadeOut = Math.max(0, Number(clip.fadeOut || 0));
    const duration = Math.max(0.05, this.pixelsToSeconds(clip.width) - Number(clip.trimEnd || 0));
    if (!fadeIn && !fadeOut) return;
    const interval = setInterval(() => {
      if (audio.paused || !this.isPlaying) {
        clearInterval(interval);
        return;
      }
      const elapsed = (performance.now() - startedAt) / 1000;
      let multiplier = 1;
      if (fadeIn > 0 && elapsed < fadeIn) multiplier = Math.min(multiplier, elapsed / fadeIn);
      if (fadeOut > 0 && elapsed > duration - fadeOut) multiplier = Math.min(multiplier, Math.max(0, (duration - elapsed) / fadeOut));
      audio.volume = Math.max(0, Math.min(1, baseVolume * multiplier));
    }, 40);
    this.players[clip.id] = { ...(this.players[clip.id] || {}), fadeInterval: interval };
  }

  stopAudioPlayers() {
    Object.values(this.players).forEach(player => {
      clearTimeout(player.timeout);
      clearTimeout(player.stopTimeout);
      clearInterval(player.fadeInterval);
      try {
        player.audio.pause();
        player.audio.currentTime = 0;
      } catch (_) {}
    });
    this.players = {};
  }

  tickSeconds() {
    return 60 / this.bpm / 4;
  }

  pixelsToSeconds(px) {
    return (px / this.cellWidth) * (60 / this.bpm);
  }

  secondsToPixels(seconds) {
    return (seconds * this.bpm / 60) * this.cellWidth;
  }

  patternDurationSeconds(pattern = this.getActivePattern()) {
    return Math.max(this.tickSeconds(), this.patternStepCount(pattern) * this.tickSeconds());
  }

  patternPlaybackTime(seconds = this.currentTime) {
    const duration = this.patternDurationSeconds();
    return ((seconds % duration) + duration) % duration;
  }

  maxTimelineX() {
    return this.timelineBars * this.cellWidth;
  }

  updateTimelineLength() {
    const minBeatsForDuration = Math.ceil((this.timelineSeconds * this.bpm) / 60);
    const contentEndBeats = this.clips.reduce((max, clip) => {
      const end = (Number(clip.x) || 0) + (Number(clip.width) || 0);
      return Math.max(max, Math.ceil(end / this.cellWidth));
    }, 0);
    const nextBeats = Math.ceil(Math.max(64, minBeatsForDuration, contentEndBeats + 16) / 4) * 4;
    const changed = nextBeats !== this.timelineBars;
    this.timelineBars = nextBeats;
    return changed;
  }

  getTrackRowHeight() {
    const firstLane = this.elements.playlistGrid?.querySelector("[data-track-lane]");
    const measured = firstLane?.getBoundingClientRect().height;
    if (measured) {
      this.trackRowHeight = measured;
      return measured;
    }
    const raw = getComputedStyle(this.container).getPropertyValue("--cx-track-row");
    const parsed = parseFloat(raw);
    this.trackRowHeight = Number.isFinite(parsed) ? parsed : this.trackRowHeight;
    return this.trackRowHeight;
  }

  getTrackHeaderWidth() {
    const raw = getComputedStyle(this.container).getPropertyValue("--cx-track-head");
    const parsed = parseFloat(raw);
    return Number.isFinite(parsed) ? parsed : 136;
  }

  seekToPixels(px, snap = true) {
    const rawX = this.clamp(Number(px) || 0, 0, this.maxTimelineX());
    const x = snap ? this.snapX(rawX) : rawX;
    this.currentTime = this.pixelsToSeconds(x);
    this.playTick = Math.floor(this.currentTime / this.tickSeconds());
    this.updateTimeDisplay();
    this.updatePlayhead();
    if (this.isPlaying) {
      this.stopStepPlayback();
      this.stopAudioPlayers();
      this.startStepPlayback();
      if (this.transportPlaysArrangement()) this.startAudioClips();
    }
  }

  timelinePointFromEvent(event) {
    const source = this.elements.ruler || this.elements.playlistGrid;
    if (!source) return 0;
    const rect = source.getBoundingClientRect();
    const scrollLeft = this.elements.playlistGrid?.scrollLeft || 0;
    return event.clientX - rect.left + scrollLeft;
  }

  pianoPointFromEvent(event) {
    if (!this.elements.pianoRoll) return 0;
    const rect = this.elements.pianoRoll.getBoundingClientRect();
    return event.clientX - rect.left + this.elements.pianoRoll.scrollLeft;
  }

  startTimelineSeek(event) {
    if (event.button !== 0) return;
    if (event.shiftKey) return;
    event.preventDefault();
    event.stopPropagation();
    const seek = moveEvent => this.seekToPixels(this.timelinePointFromEvent(moveEvent), true);
    seek(event);
    const onMove = moveEvent => seek(moveEvent);
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  startPianoSeek(event) {
    if (event.button !== 0) return;
    if (event.shiftKey) return;
    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();
    const seek = moveEvent => this.seekToPixels(this.pianoPointFromEvent(moveEvent), true);
    seek(event);
    const onMove = moveEvent => seek(moveEvent);
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      this.suppressNoteClick = true;
      window.setTimeout(() => { this.suppressNoteClick = false; }, 120);
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  startSurfacePan(event, surface) {
    if (!surface || event.button !== 0) return;
    if (this.isEditableTarget(event.target)) return;
    event.preventDefault();
    event.stopPropagation();
    if (typeof event.stopImmediatePropagation === "function") event.stopImmediatePropagation();

    const startX = event.clientX;
    const startY = event.clientY;
    const startLeft = surface.scrollLeft;
    const startTop = surface.scrollTop;
    let moved = false;
    surface.classList.add("is-panning");
    document.body.classList.add("cx-surface-panning");

    const pan = moveEvent => {
      moveEvent.preventDefault();
      const dx = moveEvent.clientX - startX;
      const dy = moveEvent.clientY - startY;
      if (Math.abs(dx) > 2 || Math.abs(dy) > 2) moved = true;
      surface.scrollLeft = startLeft - dx;
      surface.scrollTop = startTop - dy;
      if (surface === this.elements.playlistGrid) this.syncTimelineScroll();
      if (surface === this.elements.pianoRoll) this.syncPianoScroll();
    };
    const stop = () => {
      document.removeEventListener("mousemove", pan);
      document.removeEventListener("mouseup", stop);
      surface.classList.remove("is-panning");
      document.body.classList.remove("cx-surface-panning");
      if (moved) {
        this.suppressClipClick = true;
        this.suppressNoteClick = true;
        window.setTimeout(() => {
          this.suppressClipClick = false;
          this.suppressNoteClick = false;
        }, 120);
      }
    };
    document.addEventListener("mousemove", pan);
    document.addEventListener("mouseup", stop);
  }

  beatsToTicks(beats) {
    return Math.round((Number(beats) || 0) * 4);
  }

  renderAll() {
    this.channels.forEach(channel => this.normalizeChannel(channel));
    this.patterns.forEach(pattern => this.normalizePattern(pattern));
    this.updateTimelineLength();
    this.applyZoom();
    this.generateRuler();
    this.generatePianoKeys();
    this.renderTrackGrid();
    this.renderPlaylist();
    this.renderNotes();
    this.renderChannels();
    this.renderStepSequencer();
    this.renderMixer();
    this.renderAssets();
    this.renderDevicesModal();
    this.renderLyricsPad();
    this.updateTimeDisplay();
    this.updatePlayhead();
    this.updateActivePatternLabel();
    this.updatePatternControls();
    if (this.elements.bpmInput) this.elements.bpmInput.value = this.bpm;
    if (this.elements.projectName) this.elements.projectName.value = this.projectTitle;
  }

  renderTrackGrid() {
    if (!this.elements.playlistGrid) return;
    this.ensureTrackNames();
    this.elements.playlistGrid.innerHTML = "";
    for (let index = 0; index < this.tracks; index += 1) {
      const name = document.createElement("div");
      name.className = "cx-track-name";
      name.dataset.trackName = String(index);
      const title = document.createElement("button");
      title.type = "button";
      title.className = "cx-track-title";
      title.dataset.renameTrack = String(index);
      title.title = this.t("double_click_rename", "Double-click to rename");
      title.textContent = this.trackNames[index] || `${this.t("track", "Track")} ${index + 1}`;
      title.addEventListener("dblclick", event => this.startTrackRename(event, index));
      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "cx-track-delete";
      remove.dataset.deleteTrack = String(index);
      remove.title = this.t("delete", "Delete");
      remove.setAttribute("aria-label", `${this.t("delete", "Delete")} ${title.textContent}`);
      remove.disabled = this.tracks <= 1;
      name.append(title, remove);
      const lane = document.createElement("div");
      lane.className = "cx-track-lane";
      lane.dataset.trackLane = String(index);
      this.elements.playlistGrid.append(name, lane);
    }
    const addCell = document.createElement("div");
    addCell.className = "cx-track-add-cell";
    const addButton = document.createElement("button");
    addButton.type = "button";
    addButton.dataset.addTrack = "";
    addButton.title = this.t("track_added", "Add track");
    addButton.setAttribute("aria-label", this.t("track_added", "Add track"));
    addButton.textContent = this.t("track", "Track");
    addCell.appendChild(addButton);
    const addLane = document.createElement("div");
    addLane.className = "cx-track-add-lane";
    this.elements.playlistGrid.append(addCell, addLane);
  }

  addTrack() {
    this.tracks = this.clamp(this.tracks + 1, 1, 24);
    this.ensureTrackNames();
    this.trackNames[this.tracks - 1] = `${this.t("track", "Track")} ${this.tracks}`;
    this.renderTrackGrid();
    this.renderPlaylist();
    this.toast(this.t("track_added", "Track added"), "success");
    this.saveHistory();
  }

  ensureTrackNames() {
    this.trackNames = Array.isArray(this.trackNames) ? this.trackNames : [];
    for (let index = 0; index < this.tracks; index += 1) {
      if (!this.trackNames[index]) this.trackNames[index] = `${this.t("track", "Track")} ${index + 1}`;
    }
    this.trackNames = this.trackNames.slice(0, this.tracks);
  }

  startTrackRename(event, index) {
    event.preventDefault();
    event.stopPropagation();
    const button = event.currentTarget;
    const original = this.trackNames[index] || button.textContent.trim();
    const input = document.createElement("input");
    input.className = "cx-track-title-input";
    input.type = "text";
    input.maxLength = 48;
    input.value = original;
    input.setAttribute("aria-label", this.t("track", "Track"));
    button.replaceWith(input);
    input.focus();
    input.select();

    let closed = false;
    const finish = save => {
      if (closed) return;
      closed = true;
      const next = input.value.trim() || original;
      if (save) this.trackNames[index] = next;
      this.renderTrackGrid();
      this.renderPlaylist();
      if (save && next !== original) this.saveHistory();
    };
    input.addEventListener("keydown", keyEvent => {
      if (keyEvent.key === "Enter") finish(true);
      if (keyEvent.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
  }

  deleteTrack(index) {
    if (this.tracks <= 1 || !Number.isFinite(index)) return;
    const removedName = this.trackNames[index] || `${this.t("track", "Track")} ${index + 1}`;
    this.clips = this.clips
      .filter(clip => Number(clip.track || 0) !== index)
      .map(clip => ({ ...clip, track: Number(clip.track || 0) > index ? Number(clip.track || 0) - 1 : Number(clip.track || 0) }));
    this.trackNames.splice(index, 1);
    this.tracks = Math.max(1, this.tracks - 1);
    this.selectedClipId = null;
    this.renderTrackGrid();
    this.renderPlaylist();
    this.updateInspectorDefault();
    this.toast(`${this.t("delete", "Delete")}: ${removedName}`, "info");
    this.saveHistory();
  }

  changeZoom(delta) {
    const oldWidth = this.cellWidth;
    this.zoom = this.clamp(Number((this.zoom + delta).toFixed(2)), 0.25, 6);
    this.cellWidth = Math.round(this.baseCellWidth * this.zoom);
    this.scaleProjectX(this.cellWidth / oldWidth);
    this.applyZoom();
    this.renderPlaylist();
    this.renderNotes();
    this.updatePlayhead();
  }

  scaleProjectX(ratio) {
    if (!Number.isFinite(ratio) || ratio === 1) return;
    this.clips.forEach(clip => {
      clip.x = Math.round(clip.x * ratio);
      clip.width = Math.max(this.cellWidth, Math.round(clip.width * ratio));
    });
    this.patterns.forEach(pattern => {
      (pattern.notes || []).forEach(note => {
        note.x = Math.round(note.x * ratio);
        note.width = Math.max(this.cellWidth / 2, Math.round((note.width || this.cellWidth) * ratio));
      });
    });
  }

  applyZoom() {
    this.container.style.setProperty("--cx-cell", `${this.cellWidth}px`);
    this.applyTimelineMetrics();
    if (this.elements.zoomLevel) this.elements.zoomLevel.textContent = `${Math.round(this.zoom * 100)}%`;
  }

  applyTimelineMetrics() {
    const width = this.maxTimelineX();
    this.container.style.setProperty("--cx-timeline-beats", String(this.timelineBars));
    this.container.style.setProperty("--cx-timeline-width", `${width}px`);
    this.container.style.setProperty("--cx-snap", `${this.snapGridSize()}px`);
    if (this.elements.ruler) {
      this.elements.ruler.style.width = `${width}px`;
      this.elements.ruler.style.minWidth = `${width}px`;
      this.elements.ruler.style.gridTemplateColumns = `repeat(${this.timelineBars}, var(--cx-cell))`;
    }
    if (this.elements.pianoRuler) {
      this.elements.pianoRuler.style.width = `${width}px`;
      this.elements.pianoRuler.style.minWidth = `${width}px`;
      this.elements.pianoRuler.style.gridTemplateColumns = `repeat(${this.timelineBars}, var(--cx-cell))`;
    }
  }

  generateRuler() {
    this.applyTimelineMetrics();
    if (this.elements.ruler) this.elements.ruler.innerHTML = "";
    if (this.elements.pianoRuler) this.elements.pianoRuler.innerHTML = "";
    for (let i = 1; i <= this.timelineBars; i++) {
      if (this.elements.ruler) {
        const span = document.createElement("span");
        span.textContent = i;
        span.title = this.formatTimelineBeat(i - 1);
        this.elements.ruler.appendChild(span);
      }
      if (this.elements.pianoRuler) {
        const tick = document.createElement("span");
        tick.textContent = i % 4 === 1 ? String(Math.floor((i - 1) / 4) + 1) : "";
        tick.title = this.formatTimelineBeat(i - 1);
        this.elements.pianoRuler.appendChild(tick);
      }
    }
  }

  formatTimelineBeat(beatIndex) {
    const seconds = this.pixelsToSeconds(beatIndex * this.cellWidth);
    const minutes = Math.floor(seconds / 60);
    const rest = Math.floor(seconds % 60);
    const centiseconds = Math.floor((seconds % 1) * 100);
    return `${minutes}:${String(rest).padStart(2, "0")}.${String(centiseconds).padStart(2, "0")}`;
  }

  generatePianoKeys() {
    if (!this.elements.pianoKeys) return;
    this.elements.pianoKeys.innerHTML = "";
    this.pianoRows = [];
    let top = 0;
    const notes = ["C", "B", "A#", "A", "G#", "G", "F#", "F", "E", "D#", "D", "C#"];
    for (let octave = 7; octave >= 1; octave--) {
      notes.forEach(name => {
        const note = `${name}${octave}`;
        const isBlack = name.includes("#");
        const height = isBlack ? this.blackKeyHeight : this.whiteKeyHeight;
        const row = this.pianoRows.length;
        const key = document.createElement("div");
        key.className = `cx-piano-key ${isBlack ? "black-key" : "white-key"} ${name === "C" ? "c-note" : ""}`;
        key.dataset.note = note;
        key.dataset.row = String(row);
        key.style.height = `${height}px`;
        key.textContent = note;
        key.addEventListener("click", () => this.playNote(note));
        this.elements.pianoKeys.appendChild(key);
        this.pianoRows.push({ note, top, height, isBlack });
        top += height;
      });
    }
    this.container.style.setProperty("--cx-piano-height", `${top}px`);
  }

  async playNote(note) {
    await this.unlockAudio();
    const channel = this.getSelectedChannel();
    const pack = this.ensureSynth(channel);
    if (!pack || channel?.muted) return;
    pack.synth.triggerAttackRelease(note, "8n");
    this.flashPianoKey(note);
    this.flashMixer(channel.id);
  }

  flashPianoKey(note) {
    const key = this.elements.pianoKeys?.querySelector(`[data-note="${note}"]`);
    if (!key) return;
    key.classList.add("active");
    setTimeout(() => key.classList.remove("active"), 180);
  }

  switchView(viewName, button) {
    this.activeView = viewName;
    this.container.querySelectorAll("[data-view]").forEach(item => item.classList.remove("active"));
    this.container.querySelectorAll(`[data-view="${viewName}"]`).forEach(item => item.classList.add("active"));
    button?.classList.add("active");
    this.container.querySelectorAll("[data-editor-view]").forEach(view => view.classList.remove("active"));
    this.container.querySelector(`[data-editor-view="${viewName}"]`)?.classList.add("active");
    if (viewName === "piano-roll") {
      this.renderNotes();
      this.updateActivePatternLabel();
    }
    if (this.isPlaying) {
      this.clearPlayingStep();
      this.stopAudioPlayers();
      if (this.transportPlaysArrangement()) this.startAudioClips();
    }
    this.updatePlayhead();
    this.saveUiPrefs();
  }

  setTool(tool, button) {
    this.tool = tool;
    this.container.querySelectorAll("[data-tool]").forEach(item => item.classList.remove("active"));
    button?.classList.add("active");
    this.saveUiPrefs();
  }

  setArrangeTool(tool, button) {
    this.arrangeTool = tool;
    this.container.querySelectorAll("[data-arrange-tool]").forEach(item => item.classList.remove("active"));
    button?.classList.add("active");
    if (this.elements.playlistGrid) this.elements.playlistGrid.dataset.arrangeTool = tool;
    this.saveUiPrefs();
  }

  updatePatternControls() {
    if (this.elements.patternSelect) {
      const current = this.selectedPatternId;
      this.elements.patternSelect.innerHTML = this.patterns
        .map(pattern => `<option value="${pattern.id}" ${pattern.id === current ? "selected" : ""}>${this.escapeHtml(pattern.name)}</option>`)
        .join("");
    }
    if (this.elements.channelSelect) {
      const current = this.selectedChannelId;
      this.elements.channelSelect.innerHTML = this.channels
        .map(channel => `<option value="${channel.id}" ${channel.id === current ? "selected" : ""}>${this.escapeHtml(channel.name)}</option>`)
        .join("");
    }
    if (this.elements.noteLength) this.elements.noteLength.value = String(this.noteLengthBeats);
    this.syncCustomSelects();
  }

  handlePianoRollClick(event) {
    if (this.suppressNoteClick) {
      this.suppressNoteClick = false;
      return;
    }
    if (event.ctrlKey || event.metaKey) return;
    const pattern = this.getActivePattern();
    if (!pattern || !this.elements.pianoRoll || event.target.closest(".cx-note, .cx-piano-ruler, .cx-piano-playhead")) return;
    if (this.tool === "select") return;
    const point = this.relativePoint(event, this.elements.pianoRoll);
    const row = this.pianoRowFromY(point.y);
    const noteName = this.noteFromRow(row);
    if (!noteName) return;
    const snappedX = this.snapX(point.x);
    if (this.tool === "delete") {
      const found = pattern.notes.find(note => Math.abs(note.x - snappedX) < this.cellWidth && note.row === row);
      if (found) {
        pattern.notes = pattern.notes.filter(note => note.id !== found.id);
        this.selectedNoteId = null;
        this.renderNotes();
        this.saveHistory();
      }
      return;
    }
    const note = { id: this.uuid(), channelId: this.selectedChannelId, note: noteName, row, x: snappedX, y: this.pianoRowAt(row).top, width: this.cellWidth * this.noteLengthBeats, velocity: 85 };
    pattern.notes.push(note);
    this.renderNotes();
    this.selectNote(note.id);
    this.playNote(noteName);
    this.saveHistory();
  }

  startNoteBoxSelect(event) {
    if (event.button !== 0 || event.target.closest(".cx-note-resize")) return;
    const pattern = this.getActivePattern();
    if (!pattern || !this.elements.pianoRoll) return;
    event.preventDefault();
    event.stopPropagation();
    this.startBoxSelection(event, this.elements.pianoRoll, ".cx-note", boxRect => {
      this.selectedNoteIds.clear();
      this.selectedClipIds.clear();
      this.selectedClipId = null;
      this.selectedNoteId = null;
      this.elements.noteLayer.querySelectorAll(".cx-note").forEach(el => {
        const selected = this.rectsIntersect(boxRect, el.getBoundingClientRect());
        el.classList.toggle("selected", selected);
        if (selected) this.selectedNoteIds.add(el.dataset.noteId);
      });
    }, () => {
      this.updateInspectorDefault();
    });
  }

  startClipBoxSelect(event) {
    if (event.button !== 0 || this.isClipResizeEdge(event)) return;
    if (!this.elements.playlistGrid) return;
    event.preventDefault();
    event.stopPropagation();
    this.startBoxSelection(event, this.elements.playlistGrid, ".cx-pattern-clip,.cx-audio-clip,.cx-recording-clip", boxRect => {
      this.selectedClipIds.clear();
      this.selectedNoteIds.clear();
      this.selectedClipId = null;
      this.selectedNoteId = null;
      this.elements.playlistGrid.querySelectorAll(".cx-pattern-clip,.cx-audio-clip,.cx-recording-clip").forEach(el => {
        const selected = this.rectsIntersect(boxRect, el.getBoundingClientRect());
        el.classList.toggle("cx-clip-selected", selected);
        if (selected) this.selectedClipIds.add(el.dataset.clipId);
      });
    }, () => {
      this.updateInspectorDefault();
    });
  }

  startBoxSelection(event, container, itemSelector, onChange, onFinish = () => {}) {
    if (this.selectionBoxActive) return;
    this.selectionBoxActive = true;
    const start = this.relativePoint(event, container);
    const box = document.createElement("div");
    box.className = "cx-selection-box";
    container.appendChild(box);
    const paint = point => {
      const left = Math.min(start.x, point.x);
      const top = Math.min(start.y, point.y);
      const width = Math.abs(point.x - start.x);
      const height = Math.abs(point.y - start.y);
      box.style.left = `${left}px`;
      box.style.top = `${top}px`;
      box.style.width = `${width}px`;
      box.style.height = `${height}px`;
    };
    paint(start);
    const update = () => onChange(box.getBoundingClientRect(), itemSelector);
    const onMove = moveEvent => {
      paint(this.relativePoint(moveEvent, container));
      update();
    };
    const onUp = upEvent => {
      if (upEvent) paint(this.relativePoint(upEvent, container));
      update();
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      box.remove();
      this.selectionBoxActive = false;
      onFinish();
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  }

  rectsIntersect(a, b) {
    return a.left <= b.right && a.right >= b.left && a.top <= b.bottom && a.bottom >= b.top;
  }

  showPianoRollContextMenu(event) {
    if (event.target.closest(".cx-note")) return;
    event.preventDefault();
    const pattern = this.getActivePattern();
    const point = this.relativePoint(event, this.elements.pianoRoll);
    const row = this.clamp(this.pianoRowFromY(point.y), 0, (this.elements.pianoKeys?.children.length || 1) - 1);
    const noteName = this.noteFromRow(row);
    const x = this.snapX(point.x);
    this.showContextMenu(event.clientX, event.clientY, [
      pattern && noteName ? { label: `${this.t("note", "Note")} ${noteName}`, icon: "https://api.iconify.design/lucide/circle-plus.svg", action: () => this.createNoteAt(x, row) } : null,
      pattern ? { label: this.t("quantize_notes", "Quantize notes"), icon: "https://api.iconify.design/lucide/magnet.svg", action: () => this.quantizeActivePatternNotes() } : null,
      pattern ? { label: this.t("octave_up", "Octave up"), icon: "https://api.iconify.design/lucide/arrow-up.svg", action: () => this.moveSelectedNotesOctave(-12) } : null,
      pattern ? { label: this.t("octave_down", "Octave down"), icon: "https://api.iconify.design/lucide/arrow-down.svg", action: () => this.moveSelectedNotesOctave(12) } : null,
      pattern ? { label: this.t("send_to_playlist", "Send pattern to playlist"), icon: "https://api.iconify.design/lucide/send-horizontal.svg", action: () => this.sendActivePatternToPlaylist() } : null,
      { label: this.t("open_channel_rack", "Open Channel Rack"), icon: "https://api.iconify.design/lucide/grid-3x3.svg", action: () => this.switchView("step-seq", this.container.querySelector('[data-view="step-seq"]')) }
    ].filter(Boolean));
  }

  showNoteContextMenu(event, noteId) {
    event.preventDefault();
    event.stopPropagation();
    const pattern = this.getActivePattern();
    const note = pattern?.notes.find(item => item.id === noteId);
    if (!note) return;
    if (!this.selectedNoteIds.has(noteId)) this.selectNote(noteId);
    const multiple = this.selectedNoteIds.size > 1;
    this.showContextMenu(event.clientX, event.clientY, [
      { label: multiple ? this.t("duplicate", "Duplicate") : `${this.t("duplicate", "Duplicate")} ${note.note}`, icon: "https://api.iconify.design/lucide/copy-plus.svg", action: () => this.duplicateSelected() },
      { label: this.t("quantize_notes", "Quantize notes"), icon: "https://api.iconify.design/lucide/magnet.svg", action: () => this.quantizeActivePatternNotes() },
      { label: this.t("octave_up", "Octave up"), icon: "https://api.iconify.design/lucide/arrow-up.svg", action: () => this.moveSelectedNotesOctave(-12) },
      { label: this.t("octave_down", "Octave down"), icon: "https://api.iconify.design/lucide/arrow-down.svg", action: () => this.moveSelectedNotesOctave(12) },
      { label: this.t("send_to_playlist", "Send pattern to playlist"), icon: "https://api.iconify.design/lucide/send-horizontal.svg", action: () => this.sendActivePatternToPlaylist() },
      { label: this.t("delete", "Delete"), icon: "https://api.iconify.design/lucide/trash-2.svg", danger: true, action: () => this.deleteSelected() }
    ]);
  }

  createNoteAt(x, row) {
    const pattern = this.getActivePattern();
    const noteName = this.noteFromRow(row);
    if (!pattern || !noteName) return;
    const note = {
      id: this.uuid(),
      channelId: this.selectedChannelId,
      note: noteName,
      row,
      x: this.snapX(x),
      y: this.pianoRowAt(row).top,
      width: this.cellWidth * this.noteLengthBeats,
      velocity: 85
    };
    pattern.notes.push(note);
    this.renderNotes();
    this.selectNote(note.id);
    this.flashPianoKey(noteName);
    this.saveHistory();
  }

  renderNotes() {
    if (!this.elements.noteLayer) return;
    const pattern = this.getActivePattern();
    this.elements.noteLayer.innerHTML = "";
    this.renderPianoGridRows();
    if (!pattern) return;
    (pattern.notes || []).forEach(note => {
      const channel = this.channels.find(item => item.id === note.channelId);
      const el = document.createElement("div");
      const rowMeta = this.pianoRowAt(Number(note.row || 0));
      const rowTop = rowMeta.top;
      const noteHeight = Math.max(10, Math.min(16, rowMeta.height - 8));
      const rowInset = Math.max(2, Math.round((rowMeta.height - noteHeight) / 2));
      const noteLabel = note.note || "";
      note.y = rowTop;
      el.className = `cx-note ${rowMeta.isBlack ? "is-black-row" : "is-white-row"} ${note.id === this.selectedNoteId || this.selectedNoteIds.has(note.id) ? "selected" : ""}`;
      el.dataset.noteId = note.id;
      el.dataset.noteLabel = noteLabel;
      el.title = noteLabel;
      el.setAttribute("aria-label", noteLabel);
      el.style.left = `${note.x}px`;
      el.style.top = `${rowTop + rowInset}px`;
      el.style.height = `${noteHeight}px`;
      el.style.width = `${note.width || this.cellWidth}px`;
      el.style.setProperty("--note-color", channel?.color || "#ff7a18");
      el.addEventListener("click", event => {
        event.stopPropagation();
        if (this.suppressNoteClick) {
          this.suppressNoteClick = false;
          return;
        }
        if (event.ctrlKey || event.metaKey) this.toggleNoteSelection(note.id);
        else this.selectNote(note.id);
      });
      el.addEventListener("dblclick", event => {
        event.stopPropagation();
        pattern.notes = pattern.notes.filter(item => item.id !== note.id);
        this.selectedNoteId = null;
        this.renderNotes();
        this.updateInspectorDefault();
        this.saveHistory();
      });
      el.addEventListener("contextmenu", event => this.showNoteContextMenu(event, note.id));
      el.addEventListener("mousedown", event => this.startNoteDrag(event, note.id));
      const handle = document.createElement("span");
      handle.className = "cx-note-resize";
      handle.addEventListener("mousedown", event => this.startNoteResize(event, note.id));
      el.appendChild(handle);
      this.elements.noteLayer.appendChild(el);
    });
  }

  renderPianoGridRows() {
    if (!this.elements.noteLayer) return;
    const fragment = document.createDocumentFragment();
    (this.pianoRows || []).forEach((row, index) => {
      const line = document.createElement("span");
      line.className = `cx-note-row ${row.isBlack ? "is-black" : "is-white"} ${String(row.note || "").startsWith("C") ? "is-c" : ""}`;
      line.dataset.row = String(index);
      line.style.top = `${row.top}px`;
      line.style.height = `${row.height}px`;
      fragment.appendChild(line);
    });
    this.elements.noteLayer.appendChild(fragment);
  }

  startNoteDrag(event, noteId) {
    if (event.button !== 0 || event.target.closest(".cx-note-resize")) return;
    if (event.ctrlKey || event.metaKey) return;
    const pattern = this.getActivePattern();
    const note = pattern?.notes.find(item => item.id === noteId);
    if (!note) return;
    const isGroupDrag = this.selectedNoteIds.size > 1 && this.selectedNoteIds.has(noteId);
    if (!isGroupDrag) this.selectNote(noteId);
    const notes = isGroupDrag
      ? pattern.notes.filter(item => this.selectedNoteIds.has(item.id))
      : [note];
    const origins = new Map(notes.map(item => [item.id, { x: item.x, row: item.row, y: item.y, note: item.note }]));
    const startX = event.clientX;
    const startY = event.clientY;
    const origin = origins.get(noteId);
    let didDrag = false;
    const onMove = moveEvent => {
      didDrag = didDrag || Math.abs(moveEvent.clientX - startX) > 3 || Math.abs(moveEvent.clientY - startY) > 3;
      const anchorX = this.snapX(origin.x + moveEvent.clientX - startX);
      const deltaX = anchorX - origin.x;
      const anchorRow = this.clamp(this.pianoRowFromY(origin.y + moveEvent.clientY - startY), 0, this.elements.pianoKeys.children.length - 1);
      const deltaRow = anchorRow - origin.row;
      notes.forEach(item => {
        const itemOrigin = origins.get(item.id);
        item.x = Math.max(0, this.snapX(itemOrigin.x + deltaX));
        const row = this.clamp(itemOrigin.row + deltaRow, 0, this.elements.pianoKeys.children.length - 1);
        item.row = row;
        item.y = this.pianoRowAt(row).top;
        item.note = this.noteFromRow(row) || item.note;
      });
      this.renderNotes();
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      if (isGroupDrag) this.updateInspectorDefault();
      else this.showNoteInspector(note);
      if (didDrag) {
        this.suppressNoteClick = true;
        setTimeout(() => { this.suppressNoteClick = false; }, 120);
      }
      this.saveHistory();
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  startNoteResize(event, noteId) {
    event.stopPropagation();
    const pattern = this.getActivePattern();
    const note = pattern?.notes.find(item => item.id === noteId);
    if (!note) return;
    const startX = event.clientX;
    const originWidth = note.width || this.cellWidth;
    const onMove = moveEvent => {
      note.width = Math.max(this.cellWidth / 2, this.snapX(originWidth + moveEvent.clientX - startX) || this.cellWidth / 2);
      this.renderNotes();
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      this.showNoteInspector(note);
      this.saveHistory();
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  renderPlaylist() {
    if (this.updateTimelineLength()) this.generateRuler();
    this.applyTimelineMetrics();
    const lanes = this.container.querySelectorAll("[data-track-lane]");
    lanes.forEach(lane => {
      lane.innerHTML = "";
      lane.ondblclick = event => this.createPatternClipFromLane(event, lane);
      lane.onclick = event => this.handleLaneClick(event, lane);
      lane.ondragover = event => event.preventDefault();
      lane.ondrop = event => this.handleLaneDrop(event, lane);
      lane.oncontextmenu = event => this.showLaneContextMenu(event, lane);
    });
    this.clips.forEach(clip => {
      const lane = this.container.querySelector(`[data-track-lane="${clip.track}"]`);
      if (!lane) return;
      const el = document.createElement("div");
      const clipClass = clip.type === "audio" ? "cx-audio-clip" : (clip.type === "recording" ? "cx-recording-clip" : "cx-pattern-clip");
      el.className = `${clipClass} ${clip.id === this.selectedClipId || this.selectedClipIds.has(clip.id) ? "cx-clip-selected" : ""}`;
      el.classList.toggle("is-muted", Boolean(clip.muted));
      el.dataset.clipId = clip.id;
      el.style.left = `${clip.x}px`;
      el.style.width = `${clip.width}px`;
      el.style.setProperty("--clip-color", this.clipColor(clip));
      el.innerHTML = this.clipMarkup(clip);
      el.addEventListener("click", event => {
        event.stopPropagation();
        if (this.suppressClipClick) {
          this.suppressClipClick = false;
          return;
        }
        if (event.ctrlKey || event.metaKey) {
          this.toggleClipSelection(clip.id);
          return;
        }
        if (this.handleClipToolClick(event, clip)) return;
        this.selectClip(clip.id);
      });
      el.addEventListener("contextmenu", event => this.showClipContextMenu(event, clip.id));
      el.addEventListener("dblclick", event => {
        event.stopPropagation();
        if (clip.type === "pattern") {
          this.selectedPatternId = clip.patternId;
          this.switchView("piano-roll", this.container.querySelector('[data-view="piano-roll"]'));
          this.renderStepSequencer();
        }
      });
      el.addEventListener("mousedown", event => this.startClipDrag(event, clip.id));
      el.addEventListener("mousemove", event => {
        el.classList.toggle("is-resize-edge", this.isClipResizeEdge(event));
      });
      el.addEventListener("mouseleave", () => el.classList.remove("is-resize-edge"));
      lane.appendChild(el);
    });
  }

  clipMarkup(clip) {
    const title = this.escapeHtml(clip.name || "Clip");
    if (clip.type === "recording") {
      return `
        <span class="cx-recording-dot"></span>
        <span class="cx-clip-title">${title}</span>
        <span class="cx-recording-time">${this.escapeHtml(this.formatTime(Math.max(0, this.currentTime - this.recordingStartTime)))}</span>
      `;
    }
    if (clip.type === "audio") {
      const fadeIn = Math.max(0, Number(clip.fadeIn || 0));
      const fadeOut = Math.max(0, Number(clip.fadeOut || 0));
      const volume = this.clamp(Number(clip.volume ?? 85), 0, 120);
      return `
        <span class="cx-clip-title">${title}</span>
        <span class="cx-audio-wave">${this.waveBars(clip.id).map(height => `<i style="height:${height}%"></i>`).join("")}</span>
        <span class="cx-volume-line" style="bottom:${Math.min(58, 8 + volume * 0.38)}px"></span>
        <span class="cx-fade-shape cx-fade-in" style="width:${Math.min(45, fadeIn * 8)}%"></span>
        <span class="cx-fade-shape cx-fade-out" style="width:${Math.min(45, fadeOut * 8)}%"></span>
        <span class="cx-clip-badge">${volume}%</span>
      `;
    }

    const pattern = this.patterns.find(item => item.id === clip.patternId);
    const noteCount = (pattern?.notes || []).length;
    const activeSteps = Object.values(pattern?.stepsByChannel || {}).reduce((sum, steps) => sum + steps.filter(Boolean).length, 0);
    const contentCount = noteCount + activeSteps;
    return `
      <span class="cx-clip-titlebar">
        <span class="cx-clip-name">${title}</span>
        <span class="cx-clip-count">${contentCount}</span>
      </span>
      <span class="cx-pattern-mini" aria-hidden="true">${this.patternMiniPreview(clip, pattern)}</span>
    `;
  }

  clipColor(clip) {
    if (clip.color) return clip.color;
    if (clip.type === "pattern") {
      const pattern = this.patterns.find(item => item.id === clip.patternId);
      return pattern?.color || this.getSelectedChannel()?.color || "#ff7a18";
    }
    return "#36d399";
  }

  handleLaneClick(event, lane) {
    if (this.suppressClipClick) {
      this.suppressClipClick = false;
      return;
    }
    if (event.target.closest(".cx-pattern-clip, .cx-audio-clip, .cx-recording-clip")) return;
    if (this.arrangeTool !== "draw") return;
    const point = this.relativePoint(event, lane);
    this.createPatternAt(Number(lane.dataset.trackLane || 0), this.snapX(point.x));
  }

  handleClipToolClick(event, clip) {
    const lane = event.target.closest("[data-track-lane]");
    const point = lane ? this.relativePoint(event, lane) : { x: clip.x + clip.width / 2 };
    if (this.arrangeTool === "mute") {
      this.toggleClipMute(clip.id);
      return true;
    }
    if (this.arrangeTool === "slice") {
      this.splitClipAt(clip.id, this.snapX(point.x));
      return true;
    }
    if (this.arrangeTool === "fade" && clip.type === "audio") {
      const isLeftHalf = point.x < clip.x + clip.width / 2;
      this.setClipFade(clip.id, isLeftHalf ? "fadeIn" : "fadeOut", 2);
      return true;
    }
    if (this.arrangeTool === "automation") {
      this.selectClip(clip.id);
      this.toast(this.t("automation_target_hint", "Automation target: clip volume/fades in Inspector"), "info");
      return true;
    }
    return false;
  }

  waveBars(seed = "") {
    let value = String(seed).split("").reduce((sum, char) => sum + char.charCodeAt(0), 19);
    return Array.from({ length: 28 }, (_, index) => {
      value = (value * 31 + index * 17) % 97;
      return 18 + (value % 72);
    });
  }

  patternMiniPreview(clip, pattern) {
    if (!pattern) return '<span class="cx-pattern-mini-empty"></span>';
    const pct = value => `${this.clamp(Number(value) || 0, 0, 100).toFixed(3)}%`;
    const stepCount = this.patternStepCount(pattern);
    const patternBeats = Math.max(1, stepCount / 4);
    const clipBeats = Math.max(0.25, Number(clip?.width || this.cellWidth * patternBeats) / this.cellWidth);
    const notes = Array.isArray(pattern.notes) ? pattern.notes : [];
    const stepEntries = Object.entries(pattern.stepsByChannel || {});
    const activeStepCount = stepEntries.reduce((sum, [, steps]) => sum + (Array.isArray(steps) ? steps.filter(Boolean).length : 0), 0);

    if (!notes.length && !activeStepCount) {
      return `<span class="cx-pattern-wave-midline"></span><span class="cx-pattern-mini-empty"></span>`;
    }

    const sampleCount = Math.min(128, Math.max(36, Math.round(Number(clip?.width || this.cellWidth * patternBeats) / 5)));
    const wrapPosition = (localBeat, start, length) => {
      let position = localBeat - start;
      if (position < 0 && start + length > patternBeats) position = localBeat + patternBeats - start;
      return position;
    };
    const noteEnvelope = (position, length) => {
      const attack = Math.min(0.08, length * 0.24);
      const release = Math.min(0.32, length * 0.34);
      if (position < 0 || position > length) return 0;
      if (position < attack) return attack ? position / attack : 1;
      if (position > length - release) return release ? Math.max(0, (length - position) / release) : 0;
      return 0.68 + 0.22 * Math.abs(Math.sin((position / Math.max(length, 0.125)) * Math.PI * 2));
    };
    const drumShape = channel => {
      if (channel?.preset === "kick") return { length: 0.72, decay: 0.16, gain: 1 };
      if (channel?.preset === "snare" || channel?.preset === "clap") return { length: 0.46, decay: 0.11, gain: 0.78 };
      if (channel?.preset === "hat") return { length: 0.2, decay: 0.045, gain: 0.48 };
      return { length: 0.42, decay: 0.12, gain: 0.62 };
    };
    const localAmplitude = localBeat => {
      let value = 0;
      notes.forEach(note => {
        const channel = this.channels.find(item => item.id === note.channelId);
        const start = (((Number(note.x) || 0) / this.cellWidth) % patternBeats + patternBeats) % patternBeats;
        const length = Math.max(0.125, (Number(note.width) || this.cellWidth) / this.cellWidth);
        const position = wrapPosition(localBeat, start, length);
        const envelope = noteEnvelope(position, length);
        if (!envelope) return;
        const velocity = this.clamp(Number(note.velocity) || 85, 1, 100) / 100;
        const channelVolume = this.clamp(Number(channel?.volume ?? 80), 0, 100) / 100;
        const vibration = 0.76 + 0.24 * Math.abs(Math.sin((localBeat * 18.7) + (Number(note.row) || 0)));
        value += envelope * velocity * (0.65 + channelVolume * 0.35) * vibration * 0.78;
      });
      stepEntries.forEach(([channelId, steps]) => {
        if (!Array.isArray(steps)) return;
        const channel = this.channels.find(item => item.id === channelId);
        const shape = drumShape(channel);
        steps.forEach((active, index) => {
          if (!active) return;
          const start = index / 4;
          const position = wrapPosition(localBeat, start, shape.length);
          if (position < 0 || position > shape.length) return;
          const velocity = this.clamp(Number(pattern.stepVelocity?.[channelId]?.[index] || 88), 1, 100) / 100;
          const transient = Math.exp(-position / shape.decay);
          const vibration = 0.72 + 0.28 * Math.abs(Math.sin((localBeat + index) * 33.1));
          value += transient * shape.gain * velocity * vibration;
        });
      });
      return value;
    };

    const raw = Array.from({ length: sampleCount }, (_, index) => {
      let value = 0;
      for (let sub = 0; sub < 3; sub += 1) {
        const beat = ((index + (sub + 1) / 4) / sampleCount) * clipBeats;
        const localBeat = ((beat % patternBeats) + patternBeats) % patternBeats;
        value = Math.max(value, localAmplitude(localBeat));
      }
      return value;
    });
    const smoothed = raw.map((value, index) => ((raw[index - 1] || value) + value * 2 + (raw[index + 1] || value)) / 4);
    const max = Math.max(...smoothed, 0.01);
    const points = smoothed.map((value, index) => {
      const x = sampleCount <= 1 ? 0 : (index / (sampleCount - 1)) * 100;
      const pulse = 0.86 + 0.14 * Math.sin(index * 1.91 + stepCount);
      const amp = this.clamp((value / max) * 34 * pulse, 1.5, 38);
      const direction = Math.sin(index * 1.37 + stepCount * 0.31) >= 0 ? 1 : -1;
      const y = this.clamp(50 - amp * direction, 8, 92);
      return { x, y };
    });
    let path = points.length ? `M ${points[0].x.toFixed(3)} ${points[0].y.toFixed(3)}` : "";
    for (let index = 1; index < points.length; index += 1) {
      const previous = points[index - 1];
      const point = points[index];
      const controlX = ((previous.x + point.x) / 2).toFixed(3);
      const controlY = previous.y.toFixed(3);
      path += ` Q ${controlX} ${controlY} ${point.x.toFixed(3)} ${point.y.toFixed(3)}`;
    }

    return `
      <span class="cx-pattern-wave-midline"></span>
      <svg class="cx-pattern-wave-svg" viewBox="0 0 100 100" preserveAspectRatio="none" focusable="false" aria-hidden="true">
        <path class="cx-pattern-wave-glow" d="${path}"></path>
        <path class="cx-pattern-wave-line" d="${path}"></path>
      </svg>
    `;
  }

  createPatternClipFromLane(event, lane) {
    if (event.target.closest(".cx-pattern-clip, .cx-audio-clip, .cx-recording-clip")) return;
    const pattern = this.createPattern(`Pattern ${this.patterns.length + 1}`);
    this.patterns.push(pattern);
    this.selectedPatternId = pattern.id;
    const point = this.relativePoint(event, lane);
    const clip = { id: this.uuid(), type: "pattern", name: pattern.name, patternId: pattern.id, track: Number(lane.dataset.trackLane || 0), x: this.snapX(point.x), width: this.cellWidth * 4, color: pattern.color };
    this.clips.push(clip);
    this.renderPlaylist();
    this.renderNotes();
    this.renderStepSequencer();
    this.selectClip(clip.id);
    this.saveHistory();
  }

  handlePlaylistDrop(event) {
    const files = [...(event.dataTransfer?.files || [])];
    if (files.length) {
      event.preventDefault();
      const lane = event.target.closest("[data-track-lane]");
      const point = lane ? this.relativePoint(event, lane) : { x: this.cellWidth };
      const track = lane ? Number(lane.dataset.trackLane || 0) : Math.min(this.tracks - 1, 1);
      this.handleImportFiles(files, { track, x: this.snapX(Math.max(0, point.x)) });
      return;
    }
    const lane = event.target.closest("[data-track-lane]");
    if (lane) this.handleLaneDrop(event, lane);
  }

  handleLaneDrop(event, lane) {
    event.preventDefault();
    const files = [...(event.dataTransfer?.files || [])];
    if (files.length) {
      const point = this.relativePoint(event, lane);
      this.handleImportFiles(files, { track: Number(lane.dataset.trackLane || 0), x: this.snapX(Math.max(0, point.x)) });
      return;
    }
    const assetId = event.dataTransfer?.getData("text/cx-asset-id");
    if (!assetId) return;
    const point = this.relativePoint(event, lane);
    this.addAudioClipFromAsset(assetId, Number(lane.dataset.trackLane || 0), this.snapX(point.x));
  }

  handleAssetListDrop(event) {
    const files = [...(event.dataTransfer?.files || [])];
    if (!files.length) return;
    event.preventDefault();
    this.handleImportFiles(files, { addToPlaylist: false });
  }

  addAudioClipFromAsset(assetId, track = 1, x = this.cellWidth, options = {}) {
    const asset = this.assets.find(item => String(item.id) === String(assetId) || String(item.serverId) === String(assetId));
    if (!asset || !this.isAudioAsset(asset)) {
      this.toast(this.t("audio_only_clip", "Only audio files can be placed on the playlist."), "info");
      return;
    }
    const durationWidth = Number(asset.duration || 0) ? Math.max(this.cellWidth * 2, this.secondsToPixels(Number(asset.duration || 0))) : this.cellWidth * 8;
    const clip = {
      id: this.uuid(),
      type: "audio",
      name: asset.name,
      track: this.clamp(track, 0, this.tracks - 1),
      x,
      width: options.width || durationWidth,
      assetId: asset.serverId || asset.id,
      volume: 85,
      fadeIn: 0,
      fadeOut: 0,
      trimStart: 0,
      trimEnd: 0
    };
    this.clips.push(clip);
    this.renderPlaylist();
    if (options.select !== false) this.selectClip(clip.id);
    if (options.saveHistory !== false) this.saveHistory();
    return clip;
  }

  showLaneContextMenu(event, lane) {
    if (event.target.closest(".cx-pattern-clip, .cx-audio-clip, .cx-recording-clip")) return;
    event.preventDefault();
    const point = this.relativePoint(event, lane);
    const track = Number(lane.dataset.trackLane || 0);
    const x = this.snapX(point.x);
    const firstAsset = this.assets[0];
    this.showContextMenu(event.clientX, event.clientY, [
      { label: this.t("create_pattern_here", "Create pattern here"), action: () => this.createPatternAt(track, x) },
      firstAsset ? { label: this.t("place_first_audio", "Place first audio file"), action: () => this.addAudioClipFromAsset(firstAsset.serverId || firstAsset.id, track, x) } : null,
      { label: this.t("go_to_playlist", "Go to playlist"), action: () => this.switchView("playlist", this.container.querySelector('[data-view="playlist"]')) }
    ].filter(Boolean));
  }

  showClipContextMenu(event, clipId) {
    event.preventDefault();
    event.stopPropagation();
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip) return;
    this.selectClip(clipId);
    const lane = event.target.closest("[data-track-lane]");
    const point = lane ? this.relativePoint(event, lane) : { x: clip.x + clip.width / 2 };
    this.showContextMenu(event.clientX, event.clientY, [
      clip.type === "pattern" ? { label: this.t("open_piano_roll", "Open in Piano Roll"), action: () => this.openPatternClip(clipId, "piano-roll") } : null,
      clip.type === "pattern" ? { label: this.t("open_channel_rack", "Open Channel Rack"), action: () => this.openPatternClip(clipId, "step-seq") } : null,
      { label: this.t("duplicate", "Duplicate"), action: () => this.duplicateClip(clipId) },
      { label: this.t("split_here", "Split here"), action: () => this.splitClipAt(clipId, this.snapX(point.x)) },
      { label: clip.muted ? this.t("unmute", "Unmute") : this.t("mute", "Mute"), action: () => this.toggleClipMute(clipId) },
      { label: this.t("color_from_channel", "Color from channel"), action: () => this.colorClipFromChannel(clipId) },
      clip.type === "audio" ? { label: this.t("fade_in", "Fade in"), action: () => this.setClipFade(clipId, "fadeIn", 2) } : null,
      clip.type === "audio" ? { label: this.t("fade_out", "Fade out"), action: () => this.setClipFade(clipId, "fadeOut", 2) } : null,
      clip.type === "audio" ? { label: this.t("volume_up", "Volume +10%"), action: () => this.adjustClipVolume(clipId, 10) } : null,
      clip.type === "audio" ? { label: this.t("volume_down", "Volume -10%"), action: () => this.adjustClipVolume(clipId, -10) } : null,
      { label: this.t("delete", "Delete"), danger: true, action: () => this.removeClip(clipId) }
    ].filter(Boolean));
  }

  openPatternClip(clipId, viewName = "piano-roll") {
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip || clip.type !== "pattern") return;
    this.selectedClipId = clipId;
    this.selectedPatternId = clip.patternId;
    this.switchView(viewName, this.container.querySelector(`[data-view="${viewName}"]`));
    this.renderNotes();
    this.renderStepSequencer();
    this.updatePatternControls();
    this.updateActivePatternLabel();
  }

  toggleClipMute(clipId) {
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip) return;
    clip.muted = !clip.muted;
    this.renderPlaylist();
    this.showClipInspector(clip);
    this.saveHistory();
  }

  colorClipFromChannel(clipId) {
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip) return;
    clip.color = this.getSelectedChannel()?.color || this.clipColor(clip);
    this.renderPlaylist();
    this.saveHistory();
  }

  showContextMenu(x, y, items) {
    this.hideContextMenu();
    const menu = document.createElement("div");
    menu.className = "cx-context-menu";
    menu.style.left = `${Math.min(x, window.innerWidth - 220)}px`;
    menu.style.top = `${Math.min(y, window.innerHeight - 260)}px`;
    items.forEach(item => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `cx-context-menu-item ${item.danger ? "is-danger" : ""}`;
      if (item.icon) button.style.setProperty("--menu-icon", `url("${item.icon}")`);
      button.innerHTML = `${item.icon ? '<span class="menu-icon" aria-hidden="true"></span>' : ""}<span>${this.escapeHtml(item.label)}</span>`;
      button.addEventListener("click", event => {
        event.stopPropagation();
        this.hideContextMenu();
        item.action();
      });
      menu.appendChild(button);
    });
    document.body.appendChild(menu);
    this.contextMenu = menu;
  }

  hideContextMenu() {
    this.contextMenu?.remove();
    this.contextMenu = null;
  }

  createPatternAt(track, x) {
    const pattern = this.createPattern(`Pattern ${this.patterns.length + 1}`);
    this.patterns.push(pattern);
    this.selectedPatternId = pattern.id;
    const clip = { id: this.uuid(), type: "pattern", name: pattern.name, patternId: pattern.id, track, x, width: this.cellWidth * 4, color: pattern.color };
    this.clips.push(clip);
    this.renderPlaylist();
    this.renderStepSequencer();
    this.selectClip(clip.id);
    this.saveHistory();
  }

  duplicateClip(clipId) {
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip) return;
    const copy = { ...clip, id: this.uuid(), name: `${clip.name} Copy`, x: clip.x + this.cellWidth };
    if (clip.type === "pattern") {
      const original = this.patterns.find(item => item.id === clip.patternId);
      if (original) {
        const newPattern = this.createPattern(`${original.name} Copy`);
        newPattern.notes = JSON.parse(JSON.stringify(original.notes || []));
        newPattern.stepsByChannel = JSON.parse(JSON.stringify(original.stepsByChannel || {}));
        newPattern.stepVelocity = JSON.parse(JSON.stringify(original.stepVelocity || {}));
        newPattern.lengthSteps = original.lengthSteps || this.steps;
        newPattern.color = original.color || newPattern.color;
        this.patterns.push(newPattern);
        copy.patternId = newPattern.id;
      }
    }
    this.clips.push(copy);
    this.selectClip(copy.id);
    this.saveHistory();
  }

  splitClipAt(clipId, x) {
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip || x <= clip.x + this.cellWidth / 2 || x >= clip.x + clip.width - this.cellWidth / 2) return;
    const leftWidth = x - clip.x;
    const rightWidth = clip.width - leftWidth;
    const copy = {
      ...clip,
      id: this.uuid(),
      name: `${clip.name} Cut`,
      x,
      width: rightWidth
    };
    clip.width = leftWidth;
    if (clip.type === "audio") {
      copy.trimStart = Number(clip.trimStart || 0) + this.pixelsToSeconds(leftWidth);
    }
    this.clips.push(copy);
    this.renderPlaylist();
    this.selectClip(copy.id);
    this.saveHistory();
  }

  setClipFade(clipId, key, value) {
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip) return;
    clip[key] = value;
    this.renderPlaylist();
    this.showClipInspector(clip);
    this.saveHistory();
  }

  adjustClipVolume(clipId, delta) {
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip) return;
    clip.volume = this.clamp(Number(clip.volume ?? 85) + delta, 0, 120);
    this.renderPlaylist();
    this.showClipInspector(clip);
    this.saveHistory();
  }

  removeClip(clipId) {
    this.selectedClipId = clipId;
    this.deleteSelected();
  }

  addPatternClip() {
    const pattern = this.createPattern(`Pattern ${this.patterns.length + 1}`);
    this.patterns.push(pattern);
    this.selectedPatternId = pattern.id;
    const clip = { id: this.uuid(), type: "pattern", name: pattern.name, patternId: pattern.id, track: 0, x: this.cellWidth, width: this.cellWidth * 4, color: pattern.color };
    this.clips.push(clip);
    this.renderPlaylist();
    this.renderNotes();
    this.renderStepSequencer();
    this.selectClip(clip.id);
    this.toast(`${this.t("created", "Created")} ${pattern.name}`, "success");
    this.saveHistory();
  }

  startClipDrag(event, clipId) {
    if (event.button !== 0) return;
    if (this.isClipResizeEdge(event)) {
      this.startClipResize(event, clipId);
      return;
    }
    if (event.ctrlKey || event.metaKey) return;
    if (["slice", "mute", "fade", "automation"].includes(this.arrangeTool)) return;
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip) return;
    const isGroupDrag = this.selectedClipIds.size > 1 && this.selectedClipIds.has(clipId);
    if (!isGroupDrag) this.selectClip(clipId);
    const clips = isGroupDrag
      ? this.clips.filter(item => this.selectedClipIds.has(item.id))
      : [clip];
    const origins = new Map(clips.map(item => [item.id, { x: item.x, track: item.track }]));
    const startX = event.clientX;
    const startY = event.clientY;
    const origin = origins.get(clipId);
    const rowHeight = this.getTrackRowHeight();
    let didDrag = false;
    const onMove = moveEvent => {
      didDrag = didDrag || Math.abs(moveEvent.clientX - startX) > 3 || Math.abs(moveEvent.clientY - startY) > 3;
      const anchorX = this.snapX(origin.x + moveEvent.clientX - startX);
      const deltaX = anchorX - origin.x;
      const deltaTrack = Math.round((moveEvent.clientY - startY) / rowHeight);
      clips.forEach(item => {
        const itemOrigin = origins.get(item.id);
        item.x = Math.max(0, this.snapX(itemOrigin.x + deltaX));
        item.track = this.clamp(itemOrigin.track + deltaTrack, 0, this.tracks - 1);
      });
      this.renderPlaylist();
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      if (isGroupDrag) this.updateInspectorDefault();
      else this.showClipInspector(clip);
      if (didDrag) {
        this.suppressClipClick = true;
        setTimeout(() => { this.suppressClipClick = false; }, 120);
      }
      this.saveHistory();
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  isClipResizeEdge(event) {
    const clipEl = event.target.closest?.(".cx-pattern-clip, .cx-audio-clip, .cx-recording-clip");
    if (!clipEl) return false;
    const rect = clipEl.getBoundingClientRect();
    const threshold = Math.min(12, Math.max(8, rect.width * 0.16));
    return event.clientX >= rect.right - threshold;
  }

  startClipResize(event, clipId) {
    event.stopPropagation();
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip) return;
    const startX = event.clientX;
    const originWidth = clip.width;
    const onMove = moveEvent => {
      clip.width = Math.max(this.cellWidth, this.snapX(originWidth + moveEvent.clientX - startX) || this.cellWidth);
      this.renderPlaylist();
    };
    const onUp = () => {
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      this.showClipInspector(clip);
      this.saveHistory();
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
  }

  selectClip(clipId) {
    this.selectedClipIds.clear();
    this.selectedNoteIds.clear();
    this.selectedClipId = clipId;
    this.selectedNoteId = null;
    const clip = this.clips.find(item => item.id === clipId);
    if (clip?.type === "pattern") {
      this.selectedPatternId = clip.patternId;
      this.renderNotes();
      this.renderStepSequencer();
      this.updateActivePatternLabel();
    }
    this.renderPlaylist();
    if (clip) this.showClipInspector(clip);
  }

  selectNote(noteId) {
    this.selectedNoteIds.clear();
    this.selectedClipIds.clear();
    this.selectedNoteId = noteId;
    this.selectedClipId = null;
    this.renderNotes();
    const note = this.getActivePattern()?.notes.find(item => item.id === noteId);
    if (note) this.showNoteInspector(note);
  }

  toggleClipSelection(clipId) {
    this.selectedNoteIds.clear();
    this.selectedNoteId = null;
    this.selectedClipId = null;
    this.selectedClipIds.has(clipId) ? this.selectedClipIds.delete(clipId) : this.selectedClipIds.add(clipId);
    this.renderPlaylist();
    this.updateInspectorDefault();
  }

  toggleNoteSelection(noteId) {
    this.selectedClipIds.clear();
    this.selectedClipId = null;
    this.selectedNoteId = null;
    this.selectedNoteIds.has(noteId) ? this.selectedNoteIds.delete(noteId) : this.selectedNoteIds.add(noteId);
    this.renderNotes();
    this.updateInspectorDefault();
  }

  clearMultiSelection() {
    this.selectedClipIds.clear();
    this.selectedNoteIds.clear();
  }

  renderChannels() {
    if (!this.elements.channelList) return;
    this.elements.channelList.innerHTML = "";
    this.channels.forEach(channel => {
      const card = document.createElement("div");
      card.className = `cx-channel-card ${channel.id === this.selectedChannelId ? "selected" : ""}`;
      card.style.setProperty("--channel-color", channel.color);
      card.classList.toggle("is-muted", Boolean(channel.muted));
      card.innerHTML = `
        <div class="cx-channel-strip"></div>
        <div>
          <div class="cx-channel-name">${this.escapeHtml(channel.name)}</div>
          <div class="cx-channel-type">${this.escapeHtml(channel.preset)}</div>
        </div>
        <button type="button" title="${channel.muted ? "Unmute channel" : "Mute channel"}">M</button>
      `;
      card.addEventListener("click", () => {
        this.selectedChannelId = channel.id;
        this.renderChannels();
        this.renderMixer();
        this.showChannelInspector(channel);
      });
      card.querySelector("button")?.addEventListener("click", event => {
        event.stopPropagation();
        channel.muted = !channel.muted;
        this.renderChannels();
        this.renderMixer();
        this.saveHistory();
      });
      this.elements.channelList.appendChild(card);
    });
  }

  renderStepSequencer() {
    if (!this.elements.stepSequencer) return;
    const pattern = this.getActivePattern();
    this.elements.stepSequencer.innerHTML = "";
    if (!pattern) {
      this.elements.stepSequencer.innerHTML = `<p class='cx-empty'>${this.escapeHtml(this.t("no_pattern_selected", "No pattern selected"))}</p>`;
      return;
    }
    const stepCount = this.patternStepCount(pattern);
    this.channels.forEach(channel => {
      const steps = this.getPatternSteps(pattern, channel.id);
      const row = document.createElement("div");
      row.className = "cx-step-row";
      row.style.setProperty("--step-count", stepCount);
      const label = document.createElement("div");
      label.className = "cx-step-label";
      const activeCount = steps.filter(Boolean).length;
      label.innerHTML = `<span class="cx-color-dot" style="--dot:${channel.color}"></span><span>${this.escapeHtml(channel.name)}</span><small>${activeCount}/${stepCount}</small>`;
      label.addEventListener("click", () => {
        this.selectedChannelId = channel.id;
        this.renderChannels();
        this.showChannelInspector(channel);
        this.updatePatternControls();
      });
      row.appendChild(label);
      for (let i = 0; i < stepCount; i++) {
        const velocity = this.getStepVelocity(pattern, channel.id, i);
        const pad = document.createElement("button");
        pad.type = "button";
        pad.className = `cx-step-pad ${steps[i] ? "active" : ""}`;
        pad.dataset.stepIndex = String(i);
        pad.style.setProperty("--step-color", channel.color);
        pad.style.setProperty("--velocity", `${velocity}%`);
        pad.title = `${channel.name} step ${i + 1} velocity ${velocity}`;
        pad.addEventListener("click", async () => {
          await this.unlockAudio();
          steps[i] = !steps[i];
          if (steps[i]) this.setStepVelocity(pattern, channel.id, i, 88);
          if (steps[i]) this.playPatternTick(pattern, i);
          this.renderStepSequencer();
          this.saveHistory();
        });
        row.appendChild(pad);
      }
      this.elements.stepSequencer.appendChild(row);
    });
  }

  renderMixer() {
    if (!this.elements.mixer) return;
    this.elements.mixer.innerHTML = "";
    this.channels.forEach(channel => {
      const pack = this.ensureSynth(channel);
      const panLabel = channel.pan === 0 ? "C" : channel.pan < 0 ? `L ${Math.abs(channel.pan)}` : `R ${channel.pan}`;
      const hpLabel = channel.fx.highpass >= 1000 ? `${(channel.fx.highpass / 1000).toFixed(1)}k` : `${channel.fx.highpass}`;
      const lpLabel = channel.fx.lowpass >= 1000 ? `${(channel.fx.lowpass / 1000).toFixed(1)}k` : `${channel.fx.lowpass}`;
      const meterLevel = channel.muted ? 4 : Math.max(8, channel.volume);
      const controlPercent = (value, min, max) => `${this.clamp(((Number(value) - min) / (max - min)) * 100, 0, 100)}%`;
      const channelPatterns = this.patterns.filter(pattern => {
        const hasNotes = (pattern.notes || []).some(note => note.channelId === channel.id);
        const hasSteps = (pattern.stepsByChannel?.[channel.id] || []).some(Boolean);
        return hasNotes || hasSteps;
      });
      const channelPatternIds = new Set(channelPatterns.map(pattern => pattern.id));
      const channelNotes = this.patterns.reduce((sum, pattern) => sum + (pattern.notes || []).filter(note => note.channelId === channel.id).length, 0);
      const channelSteps = this.patterns.reduce((sum, pattern) => sum + (pattern.stepsByChannel?.[channel.id] || []).filter(Boolean).length, 0);
      const channelClips = this.clips.filter(clip => clip.type === "pattern" && channelPatternIds.has(clip.patternId)).length;
      const el = document.createElement("div");
      el.className = `cx-mixer-channel ${channel.id === this.selectedChannelId ? "selected" : ""}`;
      el.style.setProperty("--channel-color", channel.color);
      el.style.setProperty("--meter-level", `${meterLevel}%`);
      el.style.setProperty("--pan-position", `${(channel.pan + 100) / 2}%`);
      el.dataset.channelId = channel.id;
      el.innerHTML = `
        <div class="cx-mixer-head">
          <button type="button" class="cx-mixer-drag" data-mixer-drag title="${this.escapeHtml(this.t("drag_to_reorder", "Drag to reorder"))}" aria-label="${this.escapeHtml(this.t("drag_to_reorder", "Drag to reorder"))}"></button>
          <span class="cx-mixer-color" aria-hidden="true"></span>
          <div class="cx-mixer-name-wrap">
            <div class="cx-mixer-name">${this.escapeHtml(channel.name)}</div>
            <div class="cx-mixer-sub">${this.escapeHtml(channel.type)} / ${this.escapeHtml(channel.preset)}</div>
          </div>
          <div class="cx-mixer-head-actions">
            <button type="button" data-duplicate-channel title="${this.escapeHtml(this.t("duplicate_channel", "Duplicate channel"))}" aria-label="${this.escapeHtml(this.t("duplicate_channel", "Duplicate channel"))}"></button>
            <button type="button" data-delete-channel title="${this.escapeHtml(this.t("delete_channel", "Delete channel"))}" aria-label="${this.escapeHtml(this.t("delete_channel", "Delete channel"))}" ${this.channels.length <= 1 ? "disabled" : ""}></button>
          </div>
        </div>
        <div class="cx-mixer-meter" aria-hidden="true">
          <div class="cx-meter-fill left"></div>
          <div class="cx-meter-fill right"></div>
          <div class="cx-meter-peak"></div>
        </div>
        <div class="cx-mixer-main">
          <label class="cx-mixer-row">
            <span>Vol</span>
            <input class="cx-mixer-slider cx-fader" data-mix-control="volume" type="range" min="0" max="100" value="${channel.volume}" style="--control-value:${controlPercent(channel.volume, 0, 100)}">
            <output data-mix-output="volume">${channel.volume}%</output>
          </label>
          <label class="cx-mixer-row cx-pan-row">
            <span>Pan</span>
            <input class="cx-mixer-slider cx-pan" data-mix-control="pan" type="range" min="-100" max="100" value="${channel.pan}" style="--control-value:${controlPercent(channel.pan, -100, 100)}">
            <output data-mix-output="pan">${panLabel}</output>
          </label>
        </div>
        <div class="cx-mixer-controls">
          <button type="button" data-mute class="${channel.muted ? "active" : ""}" title="Mute">M</button>
          <button type="button" data-solo class="${channel.solo ? "solo-active" : ""}" title="Solo">S</button>
          <span class="cx-mixer-state">${channel.muted ? "Muted" : channel.solo ? "Solo" : "Live"}</span>
        </div>
        <div class="cx-mixer-route" aria-label="${this.escapeHtml(this.t("channel_contents", "Channel contents"))}">
          <button type="button" data-mixer-jump="playlist" title="${this.escapeHtml(this.t("go_to_playlist", "Go to playlist"))}"><b>${channelClips}</b><span>${this.escapeHtml(this.t("clips", "Clips"))}</span></button>
          <button type="button" data-mixer-jump="piano-roll" title="${this.escapeHtml(this.t("piano_roll", "Piano Roll"))}"><b>${channelNotes}</b><span>${this.escapeHtml(this.t("notes", "Notes"))}</span></button>
          <button type="button" data-mixer-jump="step-seq" title="${this.escapeHtml(this.t("channel_rack", "Channel Rack"))}"><b>${channelSteps}</b><span>${this.escapeHtml(this.t("steps", "Steps"))}</span></button>
        </div>
        <div class="cx-mixer-fx">
          <label class="cx-mixer-fx-row"><span>HP</span><input class="cx-mixer-slider" data-fx="highpass" type="range" min="20" max="8000" value="${channel.fx.highpass}" style="--control-value:${controlPercent(channel.fx.highpass, 20, 8000)}"><output data-mix-output="highpass">${hpLabel}</output></label>
          <label class="cx-mixer-fx-row"><span>LP</span><input class="cx-mixer-slider" data-fx="lowpass" type="range" min="200" max="20000" value="${channel.fx.lowpass}" style="--control-value:${controlPercent(channel.fx.lowpass, 200, 20000)}"><output data-mix-output="lowpass">${lpLabel}</output></label>
          <label class="cx-mixer-fx-row"><span>Rev</span><input class="cx-mixer-slider" data-send="reverb" type="range" min="0" max="100" value="${channel.send.reverb}" style="--control-value:${controlPercent(channel.send.reverb, 0, 100)}"><output data-mix-output="reverb">${channel.send.reverb}%</output></label>
          <label class="cx-mixer-fx-row"><span>Dly</span><input class="cx-mixer-slider" data-send="delay" type="range" min="0" max="100" value="${channel.send.delay}" style="--control-value:${controlPercent(channel.send.delay, 0, 100)}"><output data-mix-output="delay">${channel.send.delay}%</output></label>
        </div>
      `;
      const formatPan = value => value === 0 ? "C" : value < 0 ? `L ${Math.abs(value)}` : `R ${value}`;
      const formatFreq = value => value >= 1000 ? `${(value / 1000).toFixed(1)}k` : String(value);
      el.querySelectorAll("input").forEach(input => {
        input.addEventListener("click", event => event.stopPropagation());
        input.addEventListener("pointerdown", event => event.stopPropagation());
      });
      el.querySelectorAll("button").forEach(button => {
        button.addEventListener("click", event => event.stopPropagation());
      });
      const updateMixerReadout = () => {
        const activeLevel = channel.muted ? 4 : Math.max(8, channel.volume);
        el.style.setProperty("--meter-level", `${activeLevel}%`);
        el.style.setProperty("--pan-position", `${(channel.pan + 100) / 2}%`);
        el.querySelector('[data-mix-output="volume"]').textContent = `${channel.volume}%`;
        el.querySelector('[data-mix-output="pan"]').textContent = formatPan(channel.pan);
        el.querySelector('[data-mix-output="highpass"]').textContent = formatFreq(channel.fx.highpass);
        el.querySelector('[data-mix-output="lowpass"]').textContent = formatFreq(channel.fx.lowpass);
        el.querySelector('[data-mix-output="reverb"]').textContent = `${channel.send.reverb}%`;
        el.querySelector('[data-mix-output="delay"]').textContent = `${channel.send.delay}%`;
        el.querySelector('[data-mix-control="volume"]')?.style.setProperty("--control-value", controlPercent(channel.volume, 0, 100));
        el.querySelector('[data-mix-control="pan"]')?.style.setProperty("--control-value", controlPercent(channel.pan, -100, 100));
        el.querySelector('[data-fx="highpass"]')?.style.setProperty("--control-value", controlPercent(channel.fx.highpass, 20, 8000));
        el.querySelector('[data-fx="lowpass"]')?.style.setProperty("--control-value", controlPercent(channel.fx.lowpass, 200, 20000));
        el.querySelector('[data-send="reverb"]')?.style.setProperty("--control-value", controlPercent(channel.send.reverb, 0, 100));
        el.querySelector('[data-send="delay"]')?.style.setProperty("--control-value", controlPercent(channel.send.delay, 0, 100));
        if (channel.id === this.selectedChannelId) {
          this.updateInspectorOutput("channel-volume", channel.volume, "%");
          this.updateInspectorOutput("channel-pan", channel.pan);
          this.updateInspectorOutput("channel-highpass", channel.fx.highpass, "Hz");
          this.updateInspectorOutput("channel-lowpass", channel.fx.lowpass, "Hz");
          this.updateInspectorOutput("channel-reverb", channel.send.reverb, "%");
          this.updateInspectorOutput("channel-delay", channel.send.delay, "%");
        }
      };
      const resetMixerInput = input => {
        if (input.dataset.mixControl === "volume") {
          channel.volume = 80;
          input.value = channel.volume;
          if (pack?.volume) pack.volume.volume.value = this.volumeToDb(channel.volume);
        }
        if (input.dataset.mixControl === "pan") {
          channel.pan = 0;
          input.value = channel.pan;
          if (pack?.pan) pack.pan.pan.value = 0;
        }
        if (input.dataset.fx === "highpass") {
          channel.fx.highpass = 20;
          input.value = channel.fx.highpass;
          this.applyChannelFx(channel);
        }
        if (input.dataset.fx === "lowpass") {
          channel.fx.lowpass = 20000;
          input.value = channel.fx.lowpass;
          this.applyChannelFx(channel);
        }
        if (input.dataset.send) {
          channel.send[input.dataset.send] = 0;
          input.value = 0;
          this.applyChannelFx(channel);
        }
        updateMixerReadout();
        if (channel.id === this.selectedChannelId) this.showChannelInspector(channel);
        this.saveHistory();
      };
      el.querySelectorAll(".cx-mixer-slider").forEach(input => {
        const label = input.closest("label")?.querySelector("span")?.textContent || "";
        input.title = `${label} - ${this.t("double_click_reset", "Double click to reset")}`;
        input.addEventListener("dblclick", event => {
          event.preventDefault();
          event.stopPropagation();
          resetMixerInput(input);
        });
      });
      el.querySelector('[data-mix-control="volume"]')?.addEventListener("input", event => {
        channel.volume = this.clamp(Number(event.target.value), 0, 100);
        if (pack?.volume) pack.volume.volume.value = this.volumeToDb(channel.volume);
        updateMixerReadout();
      });
      el.querySelector('[data-mix-control="volume"]')?.addEventListener("change", () => this.saveHistory());
      el.querySelector('[data-mix-control="pan"]')?.addEventListener("input", event => {
        channel.pan = this.clamp(Number(event.target.value), -100, 100);
        if (pack?.pan) pack.pan.pan.value = channel.pan / 100;
        updateMixerReadout();
      });
      el.querySelector('[data-mix-control="pan"]')?.addEventListener("change", () => this.saveHistory());
      el.querySelectorAll("[data-fx]").forEach(input => {
        input.addEventListener("input", event => {
          const key = event.target.dataset.fx;
          const min = key === "highpass" ? 20 : 200;
          const max = key === "highpass" ? 8000 : 20000;
          channel.fx[key] = this.clamp(Number(event.target.value), min, max);
          this.applyChannelFx(channel);
          updateMixerReadout();
        });
        input.addEventListener("change", () => this.saveHistory());
      });
      el.querySelectorAll("[data-send]").forEach(input => {
        input.addEventListener("input", event => {
          const key = event.target.dataset.send;
          channel.send[key] = this.clamp(Number(event.target.value), 0, 100);
          this.applyChannelFx(channel);
          updateMixerReadout();
        });
        input.addEventListener("change", () => this.saveHistory());
      });
      el.querySelector("[data-mute]")?.addEventListener("click", event => {
        event.stopPropagation();
        channel.muted = !channel.muted;
        this.renderMixer();
        this.renderChannels();
        if (channel.id === this.selectedChannelId) this.showChannelInspector(channel);
        this.saveHistory();
      });
      el.querySelector("[data-solo]")?.addEventListener("click", event => {
        event.stopPropagation();
        channel.solo = !channel.solo;
        this.renderMixer();
        this.renderChannels();
        if (channel.id === this.selectedChannelId) this.showChannelInspector(channel);
        this.saveHistory();
      });
      el.querySelector("[data-duplicate-channel]")?.addEventListener("click", event => {
        event.stopPropagation();
        this.duplicateChannel(channel.id);
      });
      el.querySelector("[data-delete-channel]")?.addEventListener("click", event => {
        event.stopPropagation();
        this.deleteChannel(channel.id);
      });
      el.querySelectorAll("[data-mixer-jump]").forEach(button => {
        button.addEventListener("click", event => {
          event.stopPropagation();
          this.selectedChannelId = channel.id;
          const target = button.dataset.mixerJump;
          const pattern = channelPatterns[0] || this.getActivePattern();
          if (pattern) this.selectedPatternId = pattern.id;
          if (target === "playlist") {
            const clip = this.clips.find(item => item.type === "pattern" && channelPatternIds.has(item.patternId));
            if (clip) this.selectedClipId = clip.id;
          }
          this.renderAll();
          this.switchView(target, this.container.querySelector(`[data-view="${target}"]`));
          this.showChannelInspector(channel);
          this.saveUiPrefs();
        });
      });
      el.addEventListener("click", () => {
        this.selectedChannelId = channel.id;
        this.renderChannels();
        this.renderMixer();
        this.showChannelInspector(channel);
      });
      const dragHandle = el.querySelector("[data-mixer-drag]");
      dragHandle?.addEventListener("pointerdown", event => this.startChannelReorderDrag(event, channel.id));
      if (dragHandle) dragHandle.draggable = false;
      dragHandle?.addEventListener("dragstart", event => {
        event.dataTransfer?.setData("text/cx-channel-id", channel.id);
        event.dataTransfer?.setData("text/plain", channel.id);
        event.dataTransfer.effectAllowed = "move";
        el.classList.add("dragging");
      });
      dragHandle?.addEventListener("dragend", () => {
        this.elements.mixer?.querySelectorAll(".cx-mixer-channel").forEach(item => item.classList.remove("dragging", "drop-before", "drop-after"));
      });
      el.addEventListener("dragover", event => {
        const sourceId = event.dataTransfer?.getData("text/cx-channel-id") || event.dataTransfer?.getData("text/plain");
        if (!sourceId || sourceId === channel.id) return;
        event.preventDefault();
        const rect = el.getBoundingClientRect();
        const before = event.clientX < rect.left + rect.width / 2;
        el.classList.toggle("drop-before", before);
        el.classList.toggle("drop-after", !before);
      });
      el.addEventListener("dragleave", () => {
        el.classList.remove("drop-before", "drop-after");
      });
      el.addEventListener("drop", event => {
        const sourceId = event.dataTransfer?.getData("text/cx-channel-id") || event.dataTransfer?.getData("text/plain");
        if (!sourceId || sourceId === channel.id) return;
        event.preventDefault();
        const rect = el.getBoundingClientRect();
        this.reorderChannel(sourceId, channel.id, event.clientX >= rect.left + rect.width / 2);
      });
      this.elements.mixer.appendChild(el);
    });
  }

  applyChannelFx(channel) {
    const pack = this.ensureSynth(channel);
    if (!pack) return;
    if (pack.highpass) pack.highpass.frequency.value = this.clamp(Number(channel.fx?.highpass || 20), 20, 8000);
    if (pack.lowpass) pack.lowpass.frequency.value = this.clamp(Number(channel.fx?.lowpass || 20000), 200, 20000);
    if (pack.delay) pack.delay.feedback.value = this.clamp(Number(channel.send?.delay || 0), 0, 100) / 250;
    if (pack.reverb) pack.reverb.wet.value = this.clamp(Number(channel.send?.reverb || 0), 0, 100) / 100;
    if (pack.pan) pack.pan.pan.value = this.clamp(Number(channel.pan || 0), -100, 100) / 100;
    if (pack.volume) pack.volume.volume.value = this.volumeToDb(channel.volume);
  }

  async handleAudioUpload(event) {
    const files = [...(event.target.files || [])];
    if (!files.length) return;
    await this.handleImportFiles(files);
    event.target.value = "";
  }

  async handleImportFiles(files, placement = {}) {
    let imported = 0;
    let changed = 0;
    const shouldPlace = placement.addToPlaylist !== false;
    for (const file of files) {
      const isAudio = this.isAudioFile(file);
      const isPackage = this.isImportPackage(file);
      if (isAudio && !isPackage) {
        const asset = this.localAudioAsset(file);
        this.assets.push(asset);
        if (shouldPlace) {
          const track = Number.isFinite(Number(placement.track)) ? Number(placement.track) : Math.min(this.tracks - 1, Math.max(0, this.assets.length - 1));
          const x = Number.isFinite(Number(placement.x)) ? Number(placement.x) : this.cellWidth;
          this.addAudioClipFromAsset(asset.id, track, x);
        }
        this.renderAssets();
        this.renderPlaylist();
        imported += 1;
        changed += 1;
        await this.uploadAssetToServer(file, asset);
      } else {
        const result = await this.uploadAssetToServer(file, null);
        const serverAssets = Array.isArray(result?.assets) ? result.assets : (result?.asset ? [result.asset] : []);
        const audioAssets = serverAssets.filter(item => this.isAudioAsset(item));
        const sourceAssets = serverAssets.filter(item => !this.isAudioAsset(item));
        if (audioAssets.length || sourceAssets.length) {
          this.mergeServerAssets(serverAssets);
          if (shouldPlace) {
            audioAssets.forEach((asset, index) => {
              const track = Number.isFinite(Number(placement.track)) && audioAssets.length === 1
                ? Number(placement.track)
                : this.ensureImportTrack(asset.name || file.name, index);
              const x = Number.isFinite(Number(placement.x)) ? Number(placement.x) : 0;
              this.addAudioClipFromAsset(asset.id, track, x);
            });
          }
          imported += audioAssets.length;
          changed += serverAssets.length;
          this.renderAssets();
          this.renderPlaylist();
        }
      }
    }
    if (changed) {
      this.saveHistory();
      this.toast(this.t("audio_imported", "Imported {count} audio file(s)", { count: imported }), imported ? "success" : "info");
    }
  }

  localAudioAsset(file) {
    return { id: this.uuid(), serverId: null, kind: "audio", name: file.name, size: file.size, type: file.type, media_type: file.type, url: URL.createObjectURL(file), uploaded: false };
  }

  isAudioFile(file) {
    const name = String(file?.name || "").toLowerCase();
    return String(file?.type || "").startsWith("audio/") || /\.(wav|mp3|ogg|oga|flac|m4a|aac|aiff|aif|webm)$/.test(name);
  }

  isImportPackage(file) {
    const name = String(file?.name || "").toLowerCase();
    return /\.(zip|flp|mid|midi)$/.test(name);
  }

  isAudioAsset(asset) {
    return asset && (asset.kind === "audio" || String(asset.media_type || asset.type || "").startsWith("audio/"));
  }

  mergeServerAssets(serverAssets) {
    serverAssets.forEach(serverAsset => {
      const id = serverAsset.id;
      const existing = this.assets.find(item => String(item.serverId || item.id) === String(id));
      const normalized = {
        id,
        serverId: id,
        kind: serverAsset.kind || "audio",
        name: serverAsset.name || "Audio",
        size: serverAsset.size || 0,
        type: serverAsset.media_type || "",
        media_type: serverAsset.media_type || "",
        url: serverAsset.preview_url || "",
        uploaded: true,
        duration: Number(serverAsset.duration || 0),
      };
      if (existing) Object.assign(existing, normalized);
      else this.assets.push(normalized);
    });
  }

  ensureImportTrack(name, offset = 0) {
    const clean = String(name || "").replace(/\.[^.]+$/, "").replace(/[_-]+/g, " ").trim();
    const index = Math.min(23, Math.max(0, offset));
    while (this.tracks <= index) {
      this.tracks += 1;
      this.trackNames[this.tracks - 1] = `${this.t("track", "Track")} ${this.tracks}`;
    }
    this.trackNames[index] = clean || this.trackNames[index] || `${this.t("track", "Track")} ${index + 1}`;
    return index;
  }

  async uploadAssetToServer(file, asset = null) {
    if (!this.projectId) {
      this.toast(this.t("save_first_audio_local", "Save the project first; this audio is local for now."), "info");
      return null;
    }
    try {
      const formData = new FormData();
      formData.append("file", file);
      const uploadResponse = await fetch(`${this.projectsApiUrl}${this.projectId}/assets/`, {
        method: "POST",
        headers: { "X-CSRFToken": this.getCsrfToken() },
        body: formData
      });
      if (!uploadResponse.ok) throw new Error(`Upload failed: ${uploadResponse.status}`);
      const data = await uploadResponse.json();
      if (asset && data.asset) {
        asset.uploaded = true;
        asset.serverId = data.asset.id || null;
        asset.kind = data.asset.kind || asset.kind || "audio";
        asset.url = data.asset.preview_url || asset.url;
        this.renderAssets();
      }
      return data;
    } catch (error) {
      console.warn(error);
      this.toast(this.t("audio_local_upload_error", "Audio stayed local. Upload API error."), "error");
      return null;
    }
  }

  async openDevicesModal() {
    this.elements.deviceModal?.classList.remove("is-hidden");
    await this.scanAudioDevices({ render: true, notify: false });
  }

  closeDevicesModal() {
    this.elements.deviceModal?.classList.add("is-hidden");
    this.stopDeviceTest();
  }

  async scanAudioDevices(options = {}) {
    const lines = [];
    try {
      if (navigator.mediaDevices?.enumerateDevices) {
        try {
          const permissionStream = await navigator.mediaDevices.getUserMedia({ audio: true });
          permissionStream.getTracks().forEach(track => track.stop());
        } catch (_) {}
        const devices = await navigator.mediaDevices.enumerateDevices();
        this.audioInputs = devices.filter(device => device.kind === "audioinput");
        if (!this.activeAudioInputId && this.audioInputs[0]?.deviceId) this.activeAudioInputId = this.audioInputs[0].deviceId;
        lines.push(`${this.audioInputs.length || 0} mic/input`);
      } else {
        lines.push("mic API unavailable");
      }
    } catch (error) {
      lines.push("mic permission needed");
    }
    try {
      if (navigator.requestMIDIAccess) {
        this.midiAccess = await navigator.requestMIDIAccess();
        this.midiInputs = [...this.midiAccess.inputs.values()];
        if (!this.activeMidiInputId && this.midiInputs[0]?.id) this.activeMidiInputId = this.midiInputs[0].id;
        lines.push(`${this.midiInputs.length || 0} MIDI in`);
      } else {
        lines.push("MIDI not supported");
      }
    } catch (error) {
      lines.push("MIDI blocked");
    }
    const status = lines.join(" - ");
    if (this.elements.deviceStatus) this.elements.deviceStatus.textContent = status;
    if (this.elements.deviceSummary) this.elements.deviceSummary.textContent = status;
    if (options.render) this.renderDevicesModal();
    if (options.notify) this.toast(status, "info");
    return status;
  }

  renderDevicesModal() {
    if (this.elements.deviceMonitor) this.elements.deviceMonitor.checked = Boolean(this.monitorInput);
    if (this.elements.deviceNoise) this.elements.deviceNoise.checked = Boolean(this.noiseReduction);
    this.container.querySelectorAll("[data-input-role]").forEach(button => {
      button.classList.toggle("active", button.dataset.inputRole === this.audioInputRole);
    });
    if (this.elements.audioInputList) {
      this.elements.audioInputList.innerHTML = this.audioInputs.length
        ? this.audioInputs.map((device, index) => `
          <button type="button" class="${device.deviceId === this.activeAudioInputId ? "active" : ""}" data-audio-device-id="${this.escapeHtml(device.deviceId)}">
            <b>${this.escapeHtml(device.label || `Audio input ${index + 1}`)}</b>
            <span>${this.escapeHtml(device.deviceId === this.activeAudioInputId ? "Selected for Record" : "Use for recording")}</span>
          </button>
        `).join("")
        : `<p>No audio inputs found. Allow microphone access and refresh.</p>`;
      this.elements.audioInputList.querySelectorAll("[data-audio-device-id]").forEach(button => {
        button.addEventListener("click", () => {
          this.activeAudioInputId = button.dataset.audioDeviceId || "";
          this.stopDeviceTest();
          this.renderDevicesModal();
          this.markDirty();
        });
      });
    }
    if (this.elements.midiInputList) {
      this.elements.midiInputList.innerHTML = this.midiInputs.length
        ? this.midiInputs.map((input, index) => `
          <button type="button" class="${input.id === this.activeMidiInputId ? "active" : ""}" data-midi-device-id="${this.escapeHtml(input.id)}">
            <b>${this.escapeHtml(input.name || `MIDI input ${index + 1}`)}</b>
            <span>${this.escapeHtml(input.id === this.activeMidiInputId ? "Selected" : "Use keyboard")}</span>
          </button>
        `).join("")
        : `<p>No MIDI input found. Connect a keyboard and refresh.</p>`;
      this.elements.midiInputList.querySelectorAll("[data-midi-device-id]").forEach(button => {
        button.addEventListener("click", () => {
          this.activeMidiInputId = button.dataset.midiDeviceId || "";
          this.listenToMidiInputs();
          this.renderDevicesModal();
          this.markDirty();
        });
      });
    }
    this.updateDeviceStatusLabel();
  }

  updateDeviceStatusLabel() {
    const audio = this.audioInputs.find(device => device.deviceId === this.activeAudioInputId);
    const midi = this.midiInputs.find(input => input.id === this.activeMidiInputId);
    const role = this.audioInputRoleLabel(this.audioInputRole);
    const label = `${role} - ${audio?.label || "Default mic"}${midi ? ` - ${midi.name || "MIDI"}` : ""}`;
    if (this.elements.deviceStatus) this.elements.deviceStatus.textContent = label;
    if (this.elements.deviceSummary) this.elements.deviceSummary.textContent = label;
  }

  audioInputRoleLabel(role) {
    return ({ vocal: "Vocal", guitar: "Guitar", line: "Line", instrument: "Instrument" })[role] || "Input";
  }

  audioInputConstraints() {
    const audio = {
      echoCancellation: Boolean(this.noiseReduction),
      noiseSuppression: Boolean(this.noiseReduction),
      autoGainControl: Boolean(this.noiseReduction)
    };
    if (this.activeAudioInputId) audio.deviceId = { exact: this.activeAudioInputId };
    return { audio };
  }

  async getSelectedAudioStream() {
    try {
      return await navigator.mediaDevices.getUserMedia(this.audioInputConstraints());
    } catch (error) {
      if (!this.activeAudioInputId) throw error;
      this.activeAudioInputId = "";
      this.renderDevicesModal();
      return navigator.mediaDevices.getUserMedia(this.audioInputConstraints());
    }
  }

  async toggleDeviceTest() {
    if (this.deviceTestStream) {
      this.stopDeviceTest();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia) {
      this.toast(this.t("recording_unavailable", "Recording is not available in this browser."), "error");
      return;
    }
    try {
      this.deviceTestStream = await this.getSelectedAudioStream();
      this.startInputMeter();
      this.attachInputMonitor();
      this.container.querySelector("[data-device-test]")?.classList.add("is-active");
      this.toast("Input test started", "success");
    } catch (error) {
      this.toast(this.t("recording_permission", "Allow microphone access to record."), "error");
    }
  }

  stopDeviceTest() {
    if (this.deviceMeterTimer) cancelAnimationFrame(this.deviceMeterTimer);
    this.deviceMeterTimer = null;
    try { this.deviceMonitorSource?.disconnect(); } catch (_) {}
    this.deviceMonitorSource = null;
    this.deviceAnalyser = null;
    this.deviceTestStream?.getTracks().forEach(track => track.stop());
    this.deviceTestStream = null;
    if (this.elements.inputMeter) this.elements.inputMeter.style.width = "0%";
    this.container.querySelector("[data-device-test]")?.classList.remove("is-active");
  }

  startInputMeter() {
    if (!this.deviceTestStream) return;
    this.deviceAudioContext = this.deviceAudioContext || new (window.AudioContext || window.webkitAudioContext)();
    this.deviceAnalyser = this.deviceAudioContext.createAnalyser();
    this.deviceAnalyser.fftSize = 256;
    const source = this.deviceAudioContext.createMediaStreamSource(this.deviceTestStream);
    source.connect(this.deviceAnalyser);
    const data = new Uint8Array(this.deviceAnalyser.frequencyBinCount);
    const tick = () => {
      if (!this.deviceAnalyser) return;
      this.deviceAnalyser.getByteTimeDomainData(data);
      let peak = 0;
      data.forEach(value => {
        peak = Math.max(peak, Math.abs(value - 128));
      });
      const level = this.clamp(Math.round((peak / 70) * 100), 0, 100);
      if (this.elements.inputMeter) this.elements.inputMeter.style.width = `${level}%`;
      this.deviceMeterTimer = requestAnimationFrame(tick);
    };
    tick();
  }

  attachInputMonitor() {
    if (!this.deviceTestStream || !this.deviceAudioContext) return;
    try { this.deviceMonitorSource?.disconnect(); } catch (_) {}
    this.deviceMonitorSource = null;
    if (!this.monitorInput) return;
    this.deviceMonitorSource = this.deviceAudioContext.createMediaStreamSource(this.deviceTestStream);
    this.deviceMonitorSource.connect(this.deviceAudioContext.destination);
  }

  listenToMidiInputs() {
    if (!this.midiAccess) {
      this.scanAudioDevices({ render: true, notify: false }).then(() => this.listenToMidiInputs());
      return;
    }
    this.midiInputs.forEach(input => {
      input.onmidimessage = message => this.handleMidiMessage(message, input);
    });
    this.container.querySelector("[data-midi-test]")?.classList.add("is-active");
    if (this.elements.midiReadout) this.elements.midiReadout.textContent = "Live MIDI sound is on. Use the selected studio instrument.";
  }

  handleMidiMessage(message, input) {
    if (this.activeMidiInputId && input.id !== this.activeMidiInputId) return;
    const [status, note, velocity] = message.data || [];
    const command = status & 0xf0;
    if (command !== 0x90 && command !== 0x80) return;
    const isOn = command === 0x90 && velocity > 0;
    const noteName = this.midiNoteName(note);
    if (isOn) this.playMidiLiveNote(noteName, velocity);
    if (this.elements.midiReadout) {
      this.elements.midiReadout.textContent = `${isOn ? "Key" : "Release"} ${noteName} - velocity ${velocity || 0}`;
    }
  }

  async playMidiLiveNote(noteName, velocity = 90) {
    await this.unlockAudio();
    const channel = this.getSelectedChannel() || this.channels.find(item => item.type === "instrument") || this.channels[0];
    if (!channel) return;
    const pack = this.ensureSynth(channel);
    if (!pack?.synth) return;
    try {
      pack.synth.triggerAttackRelease(noteName, "8n", undefined, this.clamp(Number(velocity || 90) / 127, 0.08, 1));
    } catch (_) {}
  }

  midiNoteName(note) {
    const names = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"];
    const value = Number(note || 0);
    const octave = Math.floor(value / 12) - 1;
    return `${names[value % 12]}${octave}`;
  }

  async legacyScanAudioDevices() {
    const lines = [];
    try {
      if (navigator.mediaDevices?.enumerateDevices) {
        const devices = await navigator.mediaDevices.enumerateDevices();
        const inputs = devices.filter(device => device.kind === "audioinput");
        lines.push(`${inputs.length || 0} mic/input`);
      } else {
        lines.push("mic API unavailable");
      }
    } catch (error) {
      lines.push("mic permission needed");
    }
    try {
      if (navigator.requestMIDIAccess) {
        const midi = await navigator.requestMIDIAccess();
        lines.push(`${midi.inputs.size || 0} MIDI in`);
      } else {
        lines.push("MIDI not supported");
      }
    } catch (error) {
      lines.push("MIDI blocked");
    }
    const status = lines.join(" · ");
    if (this.elements.deviceStatus) this.elements.deviceStatus.textContent = status;
    this.toast(status, "info");
  }

  async toggleAudioRecording() {
    if (this.isRecording) {
      this.pause();
      return;
    }
    if (!navigator.mediaDevices?.getUserMedia || !window.MediaRecorder) {
      this.toast(this.t("recording_unavailable", "Recording is not available in this browser."), "error");
      return;
    }
    try {
      this.stopDeviceTest();
      this.recordStream = await this.getSelectedAudioStream();
      this.recordChunks = [];
      this.recordingStartTime = Math.max(0, Number(this.currentTime || 0));
      this.recordingEndTime = this.recordingStartTime;
      this.recordingTrack = this.ensureRecordingTrack();
      this.createRecordingPlaceholder();
      const type = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "";
      this.mediaRecorder = new MediaRecorder(this.recordStream, type ? { mimeType: type } : undefined);
      this.mediaRecorder.addEventListener("dataavailable", event => {
        if (event.data && event.data.size) this.recordChunks.push(event.data);
      });
      this.mediaRecorder.addEventListener("stop", () => this.finishAudioRecording());
      this.mediaRecorder.start();
      this.isRecording = true;
      this.container.classList.add("is-recording");
      if (this.elements.recordLabel) this.elements.recordLabel.textContent = this.t("stop", "Stop");
      this.container.querySelector('[data-action="record-audio"]')?.classList.add("is-recording");
      if (this.elements.deviceStatus) this.elements.deviceStatus.textContent = this.t("recording_from", "Recording from {time}", { time: this.formatTime(this.recordingStartTime) });
      this.toast(this.t("recording_started", "Recording started"), "success");
      if (!this.isPlaying) await this.play();
    } catch (error) {
      this.removeRecordingPlaceholder();
      this.toast(this.t("recording_permission", "Allow microphone access to record."), "error");
    }
  }

  stopAudioRecording() {
    this.recordingEndTime = Math.max(this.recordingStartTime, Number(this.currentTime || this.recordingStartTime));
    try {
      this.mediaRecorder?.stop();
    } catch (_) {}
  }

  async finishAudioRecording() {
    this.isRecording = false;
    this.container.classList.remove("is-recording");
    this.recordStream?.getTracks().forEach(track => track.stop());
    this.recordStream = null;
    this.mediaRecorder = null;
    if (this.elements.recordLabel) this.elements.recordLabel.textContent = this.t("mic", "Mic");
    this.container.querySelector('[data-action="record-audio"]')?.classList.remove("is-recording");
    const blob = new Blob(this.recordChunks, { type: this.recordChunks[0]?.type || "audio/webm" });
    this.recordChunks = [];
    const startTime = this.recordingStartTime;
    const endTime = Math.max(this.recordingEndTime, startTime + 0.05);
    const track = this.recordingTrack;
    this.removeRecordingPlaceholder();
    if (!blob.size) return;
    const file = new File([blob], `recording-${new Date().toISOString().replace(/[:.]/g, "-")}.webm`, { type: blob.type || "audio/webm" });
    if (this.elements.deviceStatus) this.elements.deviceStatus.textContent = this.t("recording_saved", "Recording added to files.");
    await this.addRecordedFile(file, startTime, endTime, track);
  }

  ensureRecordingTrack() {
    const existing = this.trackNames.findIndex(name => /record|запис/i.test(String(name || "")));
    if (existing >= 0) return existing;
    if (this.tracks < 12) {
      const index = this.tracks;
      this.tracks += 1;
      this.trackNames[index] = this.t("recording_track", "Recording");
      this.renderTrackGrid();
      this.renderPlaylist();
      return index;
    }
    return Math.max(0, this.tracks - 1);
  }

  createRecordingPlaceholder() {
    this.removeRecordingPlaceholder();
    const clip = {
      id: this.uuid(),
      type: "recording",
      name: this.t("recording", "Recording"),
      track: this.clamp(this.recordingTrack, 0, this.tracks - 1),
      x: this.secondsToPixels(this.recordingStartTime),
      width: Math.max(this.cellWidth, 2),
      color: "#ef4444"
    };
    this.recordingClipId = clip.id;
    this.clips.push(clip);
    this.renderPlaylist();
    this.updateRecordingClip();
  }

  updateRecordingClip() {
    if (!this.isRecording || !this.recordingClipId) return;
    const clip = this.clips.find(item => item.id === this.recordingClipId);
    if (!clip) return;
    clip.width = Math.max(this.cellWidth, this.secondsToPixels(Math.max(0.05, this.currentTime - this.recordingStartTime)));
    const el = this.container.querySelector(`[data-clip-id="${clip.id}"]`);
    if (!el) {
      this.renderPlaylist();
      return;
    }
    el.style.width = `${clip.width}px`;
    const time = el.querySelector(".cx-recording-time");
    if (time) time.textContent = this.formatTime(Math.max(0, this.currentTime - this.recordingStartTime));
  }

  removeRecordingPlaceholder() {
    if (!this.recordingClipId) return;
    this.clips = this.clips.filter(clip => clip.id !== this.recordingClipId);
    this.recordingClipId = null;
    this.renderPlaylist();
  }

  async addRecordedFile(file, startTime, endTime, track) {
    const asset = this.localAudioAsset(file);
    this.assets.push(asset);
    this.renderAssets();
    const width = Math.max(this.cellWidth, this.secondsToPixels(Math.max(0.1, endTime - startTime)));
    const clip = this.addAudioClipFromAsset(asset.id, track, this.secondsToPixels(startTime), { width, saveHistory: false });
    await this.uploadAssetToServer(file, asset);
    if (clip) {
      clip.assetId = asset.serverId || asset.id;
      this.renderPlaylist();
      this.selectClip(clip.id);
    }
    this.saveHistory();
  }

  renderLyricsPad() {
    if (!this.elements.lyricsPad || !this.elements.lyricsEditor) return;
    this.elements.lyricsPad.classList.toggle("is-hidden", !this.lyricsPanel.open);
    this.elements.lyricsPad.classList.toggle("is-minimized", Boolean(this.lyricsPanel.minimized));
    this.container.querySelector('[data-action="toggle-lyrics"]')?.classList.toggle("is-active", Boolean(this.lyricsPanel.open));
    if (this.elements.lyricsEditor.innerHTML !== this.projectLyrics) {
      this.elements.lyricsEditor.innerHTML = this.projectLyrics || "";
    }
    this.applyLyricsPanelMetrics();
    this.updateLyricsCount();
  }

  toggleLyricsPad() {
    this.lyricsPanel.open = !this.lyricsPanel.open;
    if (this.lyricsPanel.open) this.lyricsPanel.minimized = false;
    this.renderLyricsPad();
    this.markDirty();
    if (this.lyricsPanel.open) {
      window.setTimeout(() => this.elements.lyricsEditor?.focus(), 80);
    }
  }

  closeLyricsPad() {
    this.commitLyricsNow();
    this.lyricsPanel.open = false;
    this.renderLyricsPad();
    this.markDirty();
  }

  minimizeLyricsPad() {
    this.commitLyricsNow();
    this.lyricsPanel.minimized = !this.lyricsPanel.minimized;
    this.renderLyricsPad();
    this.markDirty();
  }

  handleLyricsInput() {
    this.projectLyrics = this.sanitizeLyricsHtml(this.elements.lyricsEditor?.innerHTML || "");
    this.updateLyricsCount();
    clearTimeout(this.lyricsSaveTimer);
    this.lyricsSaveTimer = setTimeout(() => {
      this.projectLyrics = this.sanitizeLyricsHtml(this.elements.lyricsEditor?.innerHTML || "");
      this.markDirty();
    }, 420);
  }

  commitLyricsNow() {
    clearTimeout(this.lyricsSaveTimer);
    if (!this.elements.lyricsEditor) return;
    const next = this.sanitizeLyricsHtml(this.elements.lyricsEditor.innerHTML || "");
    if (next !== this.projectLyrics) {
      this.projectLyrics = next;
      this.markDirty();
    }
    this.updateLyricsCount();
  }

  applyLyricsCommand(command, value = null) {
    if (!this.elements.lyricsEditor) return;
    this.elements.lyricsEditor.focus();
    if (command === "formatBlock") {
      document.execCommand(command, false, value || "p");
    } else {
      document.execCommand(command, false, value);
    }
    this.handleLyricsInput();
  }

  updateLyricsCount() {
    if (!this.elements.lyricsCount) return;
    const text = (this.elements.lyricsEditor?.innerText || "").trim();
    const words = text ? text.split(/\s+/).filter(Boolean).length : 0;
    this.elements.lyricsCount.textContent = `${words} ${words === 1 ? "word" : "words"}`;
  }

  startLyricsDrag(event) {
    if (!this.elements.lyricsPad || event.target.closest("button")) return;
    event.preventDefault();
    this.lyricsPanel.open = true;
    const pad = this.elements.lyricsPad;
    const rect = pad.getBoundingClientRect();
    const startX = event.clientX;
    const startY = event.clientY;
    const originX = rect.left;
    const originY = rect.top;
    try { pad.setPointerCapture?.(event.pointerId); } catch (_) {}
    pad.classList.add("is-dragging");
    const move = moveEvent => {
      const nextX = this.clamp(originX + moveEvent.clientX - startX, 8, Math.max(8, window.innerWidth - rect.width - 8));
      const nextY = this.clamp(originY + moveEvent.clientY - startY, 8, Math.max(8, window.innerHeight - 56));
      this.lyricsPanel.x = Math.round(nextX);
      this.lyricsPanel.y = Math.round(nextY);
      this.applyLyricsPanelMetrics();
    };
    const stop = () => {
      pad.classList.remove("is-dragging");
      document.removeEventListener("pointermove", move);
      document.removeEventListener("pointerup", stop);
      document.removeEventListener("pointercancel", stop);
      this.storeLyricsPanelMetrics();
      this.markDirty();
    };
    document.addEventListener("pointermove", move);
    document.addEventListener("pointerup", stop);
    document.addEventListener("pointercancel", stop);
  }

  applyLyricsPanelMetrics() {
    const pad = this.elements.lyricsPad;
    if (!pad) return;
    const isMobile = window.matchMedia?.("(max-width: 760px)")?.matches;
    const width = this.clamp(Number(this.lyricsPanel.width || 390), isMobile ? 280 : 320, Math.max(300, window.innerWidth - 16));
    const height = this.clamp(Number(this.lyricsPanel.height || 460), 170, Math.max(220, window.innerHeight - 16));
    const defaultX = Math.max(8, window.innerWidth - width - 22);
    const defaultY = isMobile ? 82 : 96;
    const x = this.clamp(Number(this.lyricsPanel.x ?? defaultX), 8, Math.max(8, window.innerWidth - width - 8));
    const y = this.clamp(Number(this.lyricsPanel.y ?? defaultY), 8, Math.max(8, window.innerHeight - 56));
    pad.style.width = `${width}px`;
    pad.style.height = this.lyricsPanel.minimized ? "48px" : `${height}px`;
    pad.style.left = `${x}px`;
    pad.style.top = `${y}px`;
  }

  storeLyricsPanelMetrics() {
    const pad = this.elements.lyricsPad;
    if (!pad || !this.lyricsPanel.open) return;
    const rect = pad.getBoundingClientRect();
    this.lyricsPanel.x = Math.round(rect.left);
    this.lyricsPanel.y = Math.round(rect.top);
    if (!this.lyricsPanel.minimized) {
      this.lyricsPanel.width = Math.round(rect.width);
      this.lyricsPanel.height = Math.round(rect.height);
    }
    this.markDirty();
  }

  sanitizeLyricsHtml(html) {
    const template = document.createElement("template");
    template.innerHTML = html || "";
    template.content.querySelectorAll("script, style, iframe, object, embed, link, meta").forEach(node => node.remove());
    template.content.querySelectorAll("*").forEach(node => {
      [...node.attributes].forEach(attr => {
        const name = attr.name.toLowerCase();
        const value = attr.value || "";
        if (name.startsWith("on") || /javascript:/i.test(value)) node.removeAttribute(attr.name);
      });
    });
    return template.innerHTML;
  }

  renderAssets() {
    if (!this.elements.assetList) return;
    this.elements.assetList.innerHTML = "";
    if (!this.assets.length) {
      this.elements.assetList.innerHTML = `<p>${this.escapeHtml(this.t("no_audio_uploaded", "No audio uploaded yet"))}</p>`;
      return;
    }
    const query = String(this.elements.assetSearch?.value || "").trim().toLowerCase();
    const visibleAssets = query
      ? this.assets.filter(asset => String(asset.name || "").toLowerCase().includes(query))
      : this.assets;
    if (!visibleAssets.length) {
      this.elements.assetList.innerHTML = `<p>${this.escapeHtml(this.t("no_audio_matches", "No audio matches this search"))}</p>`;
      return;
    }
    visibleAssets.forEach(asset => {
      const playable = this.isAudioAsset(asset);
      const item = document.createElement("div");
      item.className = `cx-asset-item ${playable ? "is-audio" : "is-source"}`;
      item.draggable = playable;
      item.dataset.assetId = asset.serverId || asset.id;
      item.innerHTML = `
        <div class="cx-asset-icon"><span></span></div>
        <div class="cx-asset-copy">
          <div class="cx-asset-title">${this.escapeHtml(asset.name)}</div>
          <div class="cx-asset-meta">${this.escapeHtml(playable ? this.t("audio", "Audio") : this.t("source_file", "Source"))} - ${this.formatBytes(asset.size)} - ${asset.uploaded ? this.escapeHtml(this.t("uploaded", "uploaded")) : this.escapeHtml(this.t("local", "local"))}</div>
        </div>
        <div class="cx-asset-actions">
          ${playable ? `<button type="button" class="cx-asset-add" title="${this.escapeHtml(this.t("add_to_playlist", "Add to playlist"))}" aria-label="${this.escapeHtml(this.t("add_to_playlist", "Add to playlist"))}"></button>` : ""}
          <button type="button" class="cx-asset-preview" title="${this.escapeHtml(playable ? this.t("preview", "Preview") : this.t("open", "Open"))}" aria-label="${this.escapeHtml(playable ? this.t("preview", "Preview") : this.t("open", "Open"))}"></button>
        </div>
      `;
      item.addEventListener("dragstart", event => {
        if (!playable) return;
        event.dataTransfer?.setData("text/cx-asset-id", String(asset.serverId || asset.id));
        event.dataTransfer?.setData("text/plain", String(asset.serverId || asset.id));
      });
      item.addEventListener("dblclick", () => {
        if (playable) this.addAudioClipFromAsset(asset.serverId || asset.id, 1, this.cellWidth);
      });
      item.querySelector(".cx-asset-add")?.addEventListener("click", event => {
        event.stopPropagation();
        this.addAudioClipFromAsset(asset.serverId || asset.id, 1, this.cellWidth);
      });
      item.querySelector(".cx-asset-preview")?.addEventListener("click", event => {
        event.stopPropagation();
        if (playable) this.toggleAssetPreview(asset, event.currentTarget);
        else if (asset.url) window.open(asset.url, "_blank", "noopener");
      });
      this.elements.assetList.appendChild(item);
    });
  }

  toggleAssetPreview(asset, button) {
    if (!asset?.url) return;
    if (this.assetPreviewAudio && this.assetPreviewButton === button) {
      this.stopAssetPreview();
      return;
    }
    this.stopAssetPreview();
    const audio = new Audio(asset.url);
    this.assetPreviewAudio = audio;
    this.assetPreviewButton = button;
    button.classList.add("is-playing");
    audio.addEventListener("ended", () => this.stopAssetPreview(), { once: true });
    audio.play().catch(() => this.stopAssetPreview());
  }

  stopAssetPreview() {
    if (this.assetPreviewAudio) {
      try {
        this.assetPreviewAudio.pause();
        this.assetPreviewAudio.currentTime = 0;
      } catch (_) {}
    }
    this.assetPreviewButton?.classList.remove("is-playing");
    this.assetPreviewAudio = null;
    this.assetPreviewButton = null;
  }

  addChannel() {
    const colors = ["#ff7a18", "#36d399", "#60a5fa", "#a855f7", "#ef4444", "#facc15"];
    const channel = this.createChannel(`Channel ${this.channels.length + 1}`, "instrument", colors[this.channels.length % colors.length], "piano");
    this.channels.push(channel);
    this.selectedChannelId = channel.id;
    this.ensureSynth(channel);
    this.renderChannels();
    this.renderStepSequencer();
    this.renderMixer();
    this.showChannelInspector(channel);
    this.saveHistory();
  }

  addDrumChannel(type) {
    const names = { kick: "Kick", snare: "Snare", hat: "Hi-Hat", clap: "Clap" };
    const colors = { kick: "#60a5fa", snare: "#a855f7", hat: "#ffd166", clap: "#ef4444" };
    const channel = this.createChannel(names[type] || "Drum", "drum", colors[type] || "#60a5fa", type);
    this.channels.push(channel);
    this.selectedChannelId = channel.id;
    this.ensureSynth(channel);
    this.renderChannels();
    this.renderStepSequencer();
    this.renderMixer();
    this.showChannelInspector(channel);
    this.saveHistory();
  }

  duplicateChannel(channelId) {
    const source = this.channels.find(channel => channel.id === channelId);
    if (!source) return;
    const copy = this.createChannel(`${source.name} Copy`, source.type, source.color, source.preset);
    copy.volume = source.volume;
    copy.pan = source.pan;
    copy.muted = false;
    copy.solo = false;
    copy.fx = JSON.parse(JSON.stringify(source.fx || {}));
    copy.send = JSON.parse(JSON.stringify(source.send || {}));
    const index = this.channels.findIndex(channel => channel.id === channelId);
    this.channels.splice(index + 1, 0, copy);
    this.selectedChannelId = copy.id;
    this.ensureSynth(copy);
    this.renderChannels();
    this.renderStepSequencer();
    this.renderMixer();
    this.showChannelInspector(copy);
    this.toast(this.t("channel_duplicated", "Channel duplicated"), "success");
    this.saveHistory();
  }

  deleteChannel(channelId) {
    if (this.channels.length <= 1) {
      this.toast(this.t("cannot_delete_last_channel", "Cannot delete the last channel"), "info");
      return;
    }
    const channel = this.channels.find(item => item.id === channelId);
    if (!channel) return;
    const hasContent = this.patterns.some(pattern =>
      (pattern.notes || []).some(note => note.channelId === channelId) ||
      (pattern.stepsByChannel?.[channelId] || []).some(Boolean)
    );
    if (hasContent && !window.confirm(this.t("delete_channel_with_content", "Delete this channel and its notes/steps?"))) return;
    this.patterns.forEach(pattern => {
      pattern.notes = (pattern.notes || []).filter(note => note.channelId !== channelId);
      if (pattern.stepsByChannel) delete pattern.stepsByChannel[channelId];
      if (pattern.stepVelocity) delete pattern.stepVelocity[channelId];
    });
    this.channels = this.channels.filter(item => item.id !== channelId);
    const pack = this.synths[channelId];
    if (pack) {
      try { pack.synth.dispose(); } catch (_) {}
      delete this.synths[channelId];
    }
    if (this.selectedChannelId === channelId) this.selectedChannelId = this.channels[0]?.id || null;
    this.selectedNoteIds.clear();
    this.selectedNoteId = null;
    this.renderChannels();
    this.renderStepSequencer();
    this.renderMixer();
    this.renderNotes();
    this.renderPlaylist();
    const selected = this.getSelectedChannel();
    selected ? this.showChannelInspector(selected) : this.updateInspectorDefault();
    this.toast(this.t("channel_deleted", "Channel deleted"), "info");
    this.saveHistory();
  }

  reorderChannel(sourceId, targetId, after = false) {
    const fromIndex = this.channels.findIndex(channel => channel.id === sourceId);
    const targetIndex = this.channels.findIndex(channel => channel.id === targetId);
    if (fromIndex < 0 || targetIndex < 0 || fromIndex === targetIndex) return;
    const [channel] = this.channels.splice(fromIndex, 1);
    let insertIndex = this.channels.findIndex(item => item.id === targetId);
    if (after) insertIndex += 1;
    this.channels.splice(insertIndex, 0, channel);
    this.selectedChannelId = sourceId;
    this.renderChannels();
    this.renderStepSequencer();
    this.renderMixer();
    this.showChannelInspector(channel);
    this.toast(this.t("channel_reordered", "Channel reordered"), "success");
    this.saveHistory();
  }

  startChannelReorderDrag(event, channelId) {
    if (event.button !== 0) return;
    event.preventDefault();
    event.stopPropagation();
    const sourceEl = event.currentTarget.closest(".cx-mixer-channel");
    sourceEl?.classList.add("dragging");
    const clearMarkers = () => {
      this.elements.mixer?.querySelectorAll(".cx-mixer-channel").forEach(item => item.classList.remove("drop-before", "drop-after"));
    };
    const pickTarget = pointerEvent => {
      const element = document.elementFromPoint(pointerEvent.clientX, pointerEvent.clientY);
      const target = element?.closest?.(".cx-mixer-channel");
      if (!target || target.dataset.channelId === channelId || !this.elements.mixer?.contains(target)) return null;
      const rect = target.getBoundingClientRect();
      return {
        element: target,
        id: target.dataset.channelId,
        after: pointerEvent.clientX >= rect.left + rect.width / 2
      };
    };
    const onMove = moveEvent => {
      moveEvent.preventDefault();
      clearMarkers();
      const target = pickTarget(moveEvent);
      if (!target) return;
      target.element.classList.toggle("drop-before", !target.after);
      target.element.classList.toggle("drop-after", target.after);
    };
    const onUp = upEvent => {
      document.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerup", onUp);
      sourceEl?.classList.remove("dragging");
      const target = pickTarget(upEvent);
      clearMarkers();
      if (target) this.reorderChannel(channelId, target.id, target.after);
    };
    document.addEventListener("pointermove", onMove);
    document.addEventListener("pointerup", onUp);
  }

  applyPreset(preset) {
    const channel = this.getSelectedChannel();
    if (!channel) return;
    channel.preset = preset;
    channel.type = ["kick", "snare", "hat", "clap"].includes(preset) ? "drum" : "instrument";
    channel.name = this.prettyPresetName(preset);
    if (this.synths[channel.id]) {
      try { this.synths[channel.id].synth.dispose(); } catch (_) {}
      delete this.synths[channel.id];
    }
    this.ensureSynth(channel);
    this.renderChannels();
    this.renderMixer();
    this.showChannelInspector(channel);
    this.saveHistory();
  }

  fillDrumLoop() {
    const pattern = this.getActivePattern();
    if (!pattern) return;
    this.channels.forEach(channel => {
      if (channel.type !== "drum") return;
      const steps = this.getPatternSteps(pattern, channel.id);
      for (let i = 0; i < steps.length; i++) steps[i] = false;
      if (channel.preset === "kick") [0, 8].forEach(i => steps[i] = true);
      if (channel.preset === "snare" || channel.preset === "clap") [4, 12].forEach(i => steps[i] = true);
      if (channel.preset === "hat") [2, 6, 10, 14].forEach(i => steps[i] = true);
    });
    this.renderStepSequencer();
    this.saveHistory();
    this.toast(this.t("basic_drum_loop_added", "Basic drum loop added"), "success");
  }

  clearActivePattern() {
    const pattern = this.getActivePattern();
    if (!pattern) return;
    pattern.notes = [];
    pattern.stepsByChannel = {};
    pattern.stepVelocity = {};
    this.selectedNoteId = null;
    this.renderNotes();
    this.renderStepSequencer();
    this.renderPlaylist();
    this.saveHistory();
  }

  sendActivePatternToPlaylist() {
    const pattern = this.getActivePattern();
    if (!pattern) return;
    const existing = this.clips.find(clip => clip.type === "pattern" && clip.patternId === pattern.id);
    if (existing) {
      this.selectClip(existing.id);
      this.switchView("playlist", this.container.querySelector('[data-view="playlist"]'));
      return;
    }
    const clip = {
      id: this.uuid(),
      type: "pattern",
      name: pattern.name,
      patternId: pattern.id,
      track: 0,
      x: Math.max(this.cellWidth, this.snapX(this.currentTime * (this.bpm / 60) * this.cellWidth)),
      width: this.cellWidth * Math.max(4, this.patternStepCount(pattern) / 4),
      color: pattern.color
    };
    this.clips.push(clip);
    this.renderPlaylist();
    this.selectClip(clip.id);
    this.switchView("playlist", this.container.querySelector('[data-view="playlist"]'));
    this.saveHistory();
    this.toast(this.t("pattern_sent", "Pattern sent to Playlist"), "success");
  }

  quantizeActivePatternNotes() {
    const pattern = this.getActivePattern();
    if (!pattern) return;
    const notes = this.selectedNoteIds.size
      ? (pattern.notes || []).filter(note => this.selectedNoteIds.has(note.id))
      : (pattern.notes || []);
    notes.forEach(note => {
      note.x = this.snapX(note.x || 0);
      note.y = this.pianoRowAt(Number(note.row || 0)).top;
      note.width = Math.max(this.cellWidth / 2, this.snapX(note.width || this.cellWidth) || this.cellWidth / 2);
    });
    this.renderNotes();
    this.renderPlaylist();
    this.saveHistory();
    this.toast(this.t("notes_quantized", "Notes quantized"), "success");
  }

  selectedNotes() {
    const pattern = this.getActivePattern();
    if (!pattern) return [];
    if (this.selectedNoteIds.size) return pattern.notes.filter(note => this.selectedNoteIds.has(note.id));
    return this.selectedNoteId ? pattern.notes.filter(note => note.id === this.selectedNoteId) : [];
  }

  nudgeSelectedNotes(deltaX = 0, deltaRow = 0) {
    const notes = this.selectedNotes();
    if (!notes.length) return;
    const maxRow = Math.max(0, (this.pianoRows?.length || this.elements.pianoKeys?.children.length || 1) - 1);
    notes.forEach(note => {
      note.x = Math.max(0, this.snapX((Number(note.x) || 0) + deltaX));
      const row = this.clamp(Number(note.row || 0) + deltaRow, 0, maxRow);
      note.row = row;
      note.y = this.pianoRowAt(row).top;
      note.note = this.noteFromRow(row) || note.note;
    });
    this.renderNotes();
    if (notes.length === 1) this.showNoteInspector(notes[0]);
    this.saveHistory();
  }

  resizeSelectedNotes(deltaWidth = 0) {
    const notes = this.selectedNotes();
    if (!notes.length) return;
    notes.forEach(note => {
      note.width = Math.max(this.cellWidth / 2, this.snapX((Number(note.width) || this.cellWidth) + deltaWidth));
    });
    this.renderNotes();
    if (notes.length === 1) this.showNoteInspector(notes[0]);
    this.saveHistory();
  }

  moveSelectedNotesOctave(deltaRows) {
    const pattern = this.getActivePattern();
    if (!pattern) return;
    const notes = this.selectedNoteIds.size
      ? pattern.notes.filter(note => this.selectedNoteIds.has(note.id))
      : this.selectedNoteId ? pattern.notes.filter(note => note.id === this.selectedNoteId) : pattern.notes;
    const maxRow = Math.max(0, (this.elements.pianoKeys?.children.length || 1) - 1);
    notes.forEach(note => {
      note.row = this.clamp(Number(note.row || 0) + deltaRows, 0, maxRow);
      note.y = this.pianoRowAt(note.row).top;
      note.note = this.noteFromRow(note.row) || note.note;
    });
    this.renderNotes();
    this.renderPlaylist();
    this.saveHistory();
  }

  toggleActivePatternLength() {
    const pattern = this.getActivePattern();
    if (!pattern) return;
    pattern.lengthSteps = this.patternStepCount(pattern) === 16 ? 32 : 16;
    Object.keys(pattern.stepsByChannel || {}).forEach(channelId => this.getPatternSteps(pattern, channelId));
    this.renderStepSequencer();
    this.renderPlaylist();
    this.saveHistory();
    this.toast(`${pattern.name}: ${pattern.lengthSteps} steps`, "info");
  }

  fillTwoStepHats() {
    const pattern = this.getActivePattern();
    const hat = this.channels.find(channel => channel.preset === "hat") || this.getSelectedChannel();
    if (!pattern || !hat) return;
    const steps = this.getPatternSteps(pattern, hat.id);
    steps.forEach((_, index) => {
      steps[index] = index % 2 === 0;
      if (steps[index]) this.setStepVelocity(pattern, hat.id, index, index % 4 === 0 ? 78 : 62);
    });
    this.selectedChannelId = hat.id;
    this.renderChannels();
    this.renderStepSequencer();
    this.renderPlaylist();
    this.saveHistory();
  }

  fillFourOnFloorKick() {
    const pattern = this.getActivePattern();
    const kick = this.channels.find(channel => channel.preset === "kick") || this.getSelectedChannel();
    if (!pattern || !kick) return;
    const steps = this.getPatternSteps(pattern, kick.id);
    steps.forEach((_, index) => {
      steps[index] = index % 4 === 0;
      if (steps[index]) this.setStepVelocity(pattern, kick.id, index, 95);
    });
    this.selectedChannelId = kick.id;
    this.renderChannels();
    this.renderStepSequencer();
    this.renderPlaylist();
    this.saveHistory();
  }

  clearSelectedChannelRow() {
    const pattern = this.getActivePattern();
    const channel = this.getSelectedChannel();
    if (!pattern || !channel) return;
    const steps = this.getPatternSteps(pattern, channel.id);
    steps.fill(false);
    if (pattern.stepVelocity) delete pattern.stepVelocity[channel.id];
    this.renderStepSequencer();
    this.renderPlaylist();
    this.saveHistory();
  }

  humanizeSelectedChannelSteps() {
    const pattern = this.getActivePattern();
    const channel = this.getSelectedChannel();
    if (!pattern || !channel) return;
    const steps = this.getPatternSteps(pattern, channel.id);
    steps.forEach((active, index) => {
      if (active) this.setStepVelocity(pattern, channel.id, index, 58 + Math.round(Math.random() * 40));
    });
    this.renderStepSequencer();
    this.saveHistory();
  }

  duplicateSelectedChannelRow() {
    const pattern = this.getActivePattern();
    const source = this.getSelectedChannel();
    if (!pattern || !source) return;
    const target = this.channels.find(channel => channel.id !== source.id && channel.type === source.type) || this.channels.find(channel => channel.id !== source.id);
    if (!target) return;
    pattern.stepsByChannel[target.id] = [...this.getPatternSteps(pattern, source.id)];
    pattern.stepVelocity[target.id] = [...(pattern.stepVelocity?.[source.id] || [])];
    this.selectedChannelId = target.id;
    this.renderChannels();
    this.renderStepSequencer();
    this.renderPlaylist();
    this.saveHistory();
    this.toast(this.t("copied_row_to", `Copied row to ${target.name}`, { name: target.name }), "success");
  }

  inspectorHeader(kind, title, subtitle = "", color = "#36d399") {
    return `
      <section class="cx-inspector-hero" style="--inspector-color:${this.escapeHtml(color)}">
        <span class="cx-inspector-icon" data-kind="${this.escapeHtml(kind)}"></span>
        <div>
          <small>${this.escapeHtml(kind)}</small>
          <strong>${this.escapeHtml(title)}</strong>
          ${subtitle ? `<em>${this.escapeHtml(subtitle)}</em>` : ""}
        </div>
      </section>
    `;
  }

  inspectorSection(title, body, extraClass = "") {
    return `
      <section class="cx-inspector-section ${extraClass}">
        <h3>${this.escapeHtml(title)}</h3>
        ${body}
      </section>
    `;
  }

  inspectorStats(items) {
    return `<div class="cx-inspector-stats">${items.map(item => `
      <span><b>${this.escapeHtml(item.value)}</b><small>${this.escapeHtml(item.label)}</small></span>
    `).join("")}</div>`;
  }

  controlPercent(value, min, max) {
    return `${this.clamp(((Number(value) - min) / (max - min)) * 100, 0, 100)}%`;
  }

  formatPanValue(value) {
    const pan = Number(value) || 0;
    return pan === 0 ? "C" : pan < 0 ? `L ${Math.abs(pan)}` : `R ${pan}`;
  }

  formatFreqValue(value) {
    const freq = Number(value) || 0;
    return freq >= 1000 ? `${(freq / 1000).toFixed(1)}kHz` : `${freq}Hz`;
  }

  inspectorRange(label, selector, value, min, max, unit = "") {
    const cleanValue = Number(value) || 0;
    return `
      <div class="cx-field cx-range-field">
        <label><span>${this.escapeHtml(label)}</span><output data-value-for="${this.escapeHtml(selector)}">${this.escapeHtml(`${cleanValue}${unit}`)}</output></label>
        <input type="range" min="${min}" max="${max}" data-edit-${this.escapeHtml(selector)} value="${cleanValue}" style="--control-value:${this.controlPercent(cleanValue, min, max)}">
      </div>
    `;
  }

  updateInspectorOutput(selector, value, unit = "") {
    const output = this.elements.inspector?.querySelector(`[data-value-for="${selector}"]`);
    if (output) output.textContent = `${value}${unit}`;
  }

  showNoteInspector(note) {
    if (!this.elements.inspector) return;
    const beats = ((note.x || 0) / this.cellWidth).toFixed(2);
    const length = ((note.width || this.cellWidth) / this.cellWidth).toFixed(2);
    this.elements.inspector.innerHTML = `
      ${this.inspectorHeader("note", note.note, `${this.t("beat", "Beat")} ${beats}`, "#60a5fa")}
      ${this.inspectorStats([
        { label: this.t("velocity", "Velocity"), value: String(note.velocity || 85) },
        { label: this.t("length_beats", "Length beats"), value: length },
        { label: this.t("row", "Row"), value: String(note.row) }
      ])}
      ${this.inspectorSection(this.t("edit", "Редактирование"), `
        <div class="cx-field"><label>${this.escapeHtml(this.t("note", "Note"))}</label><input data-edit-note-name value="${this.escapeHtml(note.note)}"></div>
        ${this.inspectorRange(this.t("velocity", "Velocity"), "note-velocity", note.velocity || 85, 1, 100)}
        <div class="cx-field"><label>${this.escapeHtml(this.t("length_beats", "Length beats"))}</label><input type="number" min="0.25" max="16" step="0.25" data-edit-note-width value="${length}"></div>
      `)}
      <div class="cx-inspector-actions">
        <button type="button" data-inspector-action="quantize">${this.escapeHtml(this.t("quantize", "Quantize"))}</button>
        <button type="button" class="is-danger" data-inspector-action="delete-note">${this.escapeHtml(this.t("delete", "Delete"))}</button>
      </div>
    `;
    this.elements.inspector.querySelector("[data-edit-note-name]")?.addEventListener("change", event => {
      note.note = event.target.value.trim() || note.note;
      this.renderNotes();
      this.saveHistory();
      this.showNoteInspector(note);
    });
    this.elements.inspector.querySelector("[data-edit-note-velocity]")?.addEventListener("input", event => {
      note.velocity = this.clamp(Number(event.target.value) || 85, 1, 100);
      this.updateInspectorOutput("note-velocity", note.velocity);
    });
    this.elements.inspector.querySelector("[data-edit-note-velocity]")?.addEventListener("change", () => this.saveHistory());
    this.elements.inspector.querySelector("[data-edit-note-width]")?.addEventListener("change", event => {
      note.width = Math.max(this.cellWidth / 2, (Number(event.target.value) || 1) * this.cellWidth);
      this.renderNotes();
      this.saveHistory();
      this.showNoteInspector(note);
    });
    this.elements.inspector.querySelector('[data-inspector-action="quantize"]')?.addEventListener("click", () => this.quantizeActivePatternNotes());
    this.elements.inspector.querySelector('[data-inspector-action="delete-note"]')?.addEventListener("click", () => this.deleteSelected());
  }

  showNoteInspector(note) {
    if (!this.elements.inspector) return;
    const beats = ((note.x || 0) / this.cellWidth).toFixed(2);
    const length = Number(((note.width || this.cellWidth) / this.cellWidth).toFixed(2));
    const channel = this.channels.find(item => item.id === note.channelId) || this.getSelectedChannel();
    this.elements.inspector.innerHTML = `
      ${this.inspectorHeader("note", note.note, `${this.t("beat", "Beat")} ${beats}`, channel?.color || "#60a5fa")}
      ${this.inspectorStats([
        { label: "VEL", value: String(note.velocity || 85) },
        { label: "LEN", value: String(length) },
        { label: "CH", value: channel?.name || "-" }
      ])}
      <div class="cx-inspector-actions cx-note-quick-actions">
        <button type="button" data-inspector-action="play-note" data-icon="play">${this.escapeHtml(this.t("play", "Play"))}</button>
        <button type="button" data-inspector-action="duplicate-note" data-icon="copy-plus">${this.escapeHtml(this.t("duplicate", "Duplicate"))}</button>
        <button type="button" data-inspector-action="quantize" data-icon="magnet">${this.escapeHtml(this.t("quantize", "Quantize"))}</button>
      </div>
      ${this.inspectorSection(this.t("edit", "Редактирование"), `
        <div class="cx-field"><label>${this.escapeHtml(this.t("note", "Note"))}</label><input data-edit-note-name value="${this.escapeHtml(note.note)}"></div>
        ${this.inspectorRange(this.t("velocity", "Velocity"), "note-velocity", note.velocity || 85, 1, 100)}
        ${this.inspectorRange(this.t("length_beats", "Length beats"), "note-length", length, 0.25, 16)}
      `)}
      <div class="cx-inspector-actions">
        <button type="button" data-inspector-action="octave-up" data-icon="arrow-up">${this.escapeHtml(this.t("octave_up", "Octave up"))}</button>
        <button type="button" data-inspector-action="octave-down" data-icon="arrow-down">${this.escapeHtml(this.t("octave_down", "Octave down"))}</button>
        <button type="button" class="is-danger" data-inspector-action="delete-note" data-icon="trash-2">${this.escapeHtml(this.t("delete", "Delete"))}</button>
      </div>
    `;
    this.elements.inspector.querySelector("[data-edit-note-name]")?.addEventListener("change", event => {
      note.note = event.target.value.trim() || note.note;
      this.renderNotes();
      this.saveHistory();
      this.showNoteInspector(note);
    });
    this.elements.inspector.querySelector("[data-edit-note-velocity]")?.addEventListener("input", event => {
      note.velocity = this.clamp(Number(event.target.value) || 85, 1, 100);
      event.target.style.setProperty("--control-value", this.controlPercent(note.velocity, 1, 100));
      this.updateInspectorOutput("note-velocity", note.velocity);
    });
    this.elements.inspector.querySelector("[data-edit-note-velocity]")?.addEventListener("change", () => this.saveHistory());
    this.elements.inspector.querySelector("[data-edit-note-length]")?.addEventListener("input", event => {
      const nextLength = this.clamp(Number(event.target.value) || 1, 0.25, 16);
      note.width = Math.max(this.cellWidth / 2, nextLength * this.cellWidth);
      event.target.style.setProperty("--control-value", this.controlPercent(nextLength, 0.25, 16));
      this.updateInspectorOutput("note-length", nextLength);
      this.renderNotes();
    });
    this.elements.inspector.querySelector("[data-edit-note-length]")?.addEventListener("change", () => {
      this.saveHistory();
      this.showNoteInspector(note);
    });
    this.elements.inspector.querySelector('[data-inspector-action="play-note"]')?.addEventListener("click", () => this.triggerNote(channel, note));
    this.elements.inspector.querySelector('[data-inspector-action="duplicate-note"]')?.addEventListener("click", () => this.duplicateSelected());
    this.elements.inspector.querySelector('[data-inspector-action="quantize"]')?.addEventListener("click", () => this.quantizeActivePatternNotes());
    this.elements.inspector.querySelector('[data-inspector-action="octave-up"]')?.addEventListener("click", () => this.moveSelectedNotesOctave(-12));
    this.elements.inspector.querySelector('[data-inspector-action="octave-down"]')?.addEventListener("click", () => this.moveSelectedNotesOctave(12));
    this.elements.inspector.querySelector('[data-inspector-action="delete-note"]')?.addEventListener("click", () => this.deleteSelected());
  }

  showChannelInspector(channel) {
    if (!this.elements.inspector) return;
    this.normalizeChannel(channel);
    const presetOptions = [
      ["piano", "Grand Piano"],
      ["bass", "Deep Bass"],
      ["lead", "Soft Lead"],
      ["pluck", "Pluck"],
      ["pad", "Warm Pad"],
      ["kick", "Kick"],
      ["snare", "Snare"],
      ["hat", "Hi-Hat"],
      ["clap", "Clap"]
    ];
    this.elements.inspector.innerHTML = `
      ${this.inspectorHeader("channel", channel.name, `${channel.type} - ${channel.preset}`, channel.color || "#ff7a18")}
      ${this.inspectorStats([
        { label: this.t("volume", "Volume"), value: `${channel.volume}%` },
        { label: this.t("pan", "Pan"), value: this.formatPanValue(channel.pan) },
        { label: this.t("status", "Status"), value: channel.muted ? "Muted" : channel.solo ? "Solo" : "Live" }
      ])}
      <div class="cx-inspector-actions cx-channel-quick-actions">
        <button type="button" data-inspector-action="audition-channel" data-icon="play">${this.escapeHtml(this.t("play", "Play"))}</button>
        <button type="button" class="${channel.muted ? "active" : ""}" data-inspector-action="toggle-channel-mute" data-icon="volume-x">${this.escapeHtml(channel.muted ? this.t("unmute", "Unmute") : this.t("mute", "Mute"))}</button>
        <button type="button" class="${channel.solo ? "active" : ""}" data-inspector-action="toggle-channel-solo" data-icon="headphones">Solo</button>
      </div>
      ${this.inspectorSection(this.t("identity", "Основное"), `
        <div class="cx-field"><label>${this.escapeHtml(this.t("project_name", "Name"))}</label><input data-edit-channel-name value="${this.escapeHtml(channel.name)}"></div>
        <div class="cx-field cx-color-field"><label>${this.escapeHtml(this.t("color", "Color"))}</label><input type="color" data-edit-channel-color value="${channel.color || "#ff7a18"}"></div>
        <div class="cx-field"><label>${this.escapeHtml(this.t("preset", "Preset"))}</label><select data-edit-channel-preset>${presetOptions.map(([value, label]) => `<option value="${value}" ${channel.preset === value ? "selected" : ""}>${this.escapeHtml(label)}</option>`).join("")}</select></div>
      `)}
      ${this.inspectorSection(this.t("mix", "Микс"), `
        ${this.inspectorRange(this.t("volume", "Volume"), "channel-volume", channel.volume, 0, 100, "%")}
        ${this.inspectorRange(this.t("pan", "Pan"), "channel-pan", channel.pan, -100, 100)}
      `)}
      ${this.inspectorSection("FX", `
        ${this.inspectorRange(this.t("highpass", "Highpass"), "channel-highpass", channel.fx.highpass, 20, 8000, "Hz")}
        ${this.inspectorRange(this.t("lowpass", "Lowpass"), "channel-lowpass", channel.fx.lowpass, 200, 20000, "Hz")}
        ${this.inspectorRange(this.t("reverb_send", "Reverb send"), "channel-reverb", channel.send.reverb, 0, 100, "%")}
        ${this.inspectorRange(this.t("delay_send", "Delay send"), "channel-delay", channel.send.delay, 0, 100, "%")}
      `)}
      <div class="cx-inspector-actions">
        <button type="button" data-inspector-action="reset-channel" data-icon="rotate-ccw">${this.escapeHtml(this.t("reset", "Reset"))}</button>
        <button type="button" data-inspector-action="duplicate-channel" data-icon="copy-plus">${this.escapeHtml(this.t("duplicate", "Duplicate"))}</button>
        <button type="button" data-inspector-action="open-step-seq" data-icon="rows-3">${this.escapeHtml(this.t("channel_rack", "Channel Rack"))}</button>
        <button type="button" data-inspector-action="open-mixer" data-icon="sliders-horizontal">${this.escapeHtml(this.t("mixer", "Mixer"))}</button>
      </div>
    `;
    this.elements.inspector.querySelector("[data-edit-channel-name]")?.addEventListener("input", event => {
      channel.name = event.target.value.trim() || channel.name;
      this.renderChannels();
      this.renderMixer();
      this.renderStepSequencer();
    });
    this.elements.inspector.querySelector("[data-edit-channel-name]")?.addEventListener("change", () => {
      this.saveHistory();
      this.showChannelInspector(channel);
    });
    this.elements.inspector.querySelector("[data-edit-channel-color]")?.addEventListener("input", event => {
      channel.color = event.target.value;
      this.renderChannels();
      this.renderMixer();
      this.renderStepSequencer();
      this.renderPlaylist();
    });
    this.elements.inspector.querySelector("[data-edit-channel-color]")?.addEventListener("change", () => {
      this.saveHistory();
      this.showChannelInspector(channel);
    });
    this.elements.inspector.querySelector("[data-edit-channel-preset]")?.addEventListener("change", event => {
      this.selectedChannelId = channel.id;
      channel.preset = event.target.value;
      channel.type = ["kick", "snare", "hat", "clap"].includes(channel.preset) ? "drum" : "instrument";
      if (!channel.name || ["Piano", "Bass", "Kick", "Snare", "Hi-Hat", "Clap"].includes(channel.name)) {
        channel.name = this.prettyPresetName(channel.preset);
      }
      if (this.synths[channel.id]) {
        try { this.synths[channel.id].synth.dispose(); } catch (_) {}
        delete this.synths[channel.id];
      }
      this.ensureSynth(channel);
      this.renderChannels();
      this.renderMixer();
      this.renderStepSequencer();
      this.showChannelInspector(channel);
      this.saveHistory();
    });
    const bindRange = (selector, apply, unit = "") => {
      const input = this.elements.inspector.querySelector(`[data-edit-${selector}]`);
      input?.addEventListener("input", event => {
        const value = Number(event.target.value);
        apply(value);
        const min = Number(event.target.min);
        const max = Number(event.target.max);
        event.target.style.setProperty("--control-value", this.controlPercent(value, min, max));
        const displayValue = selector === "channel-pan"
          ? this.formatPanValue(value)
          : selector === "channel-highpass" || selector === "channel-lowpass"
            ? this.formatFreqValue(value)
            : event.target.value;
        this.updateInspectorOutput(selector, displayValue, selector === "channel-pan" || selector === "channel-highpass" || selector === "channel-lowpass" ? "" : unit);
        this.applyChannelFx(channel);
        this.renderMixer();
        this.renderChannels();
      });
      input?.addEventListener("change", () => this.saveHistory());
    };
    bindRange("channel-volume", value => { channel.volume = this.clamp(value, 0, 100); }, "%");
    bindRange("channel-pan", value => { channel.pan = this.clamp(value, -100, 100); });
    bindRange("channel-highpass", value => { channel.fx.highpass = this.clamp(value, 20, 8000); }, "Hz");
    bindRange("channel-lowpass", value => { channel.fx.lowpass = this.clamp(value, 200, 20000); }, "Hz");
    bindRange("channel-reverb", value => { channel.send.reverb = this.clamp(value, 0, 100); }, "%");
    bindRange("channel-delay", value => { channel.send.delay = this.clamp(value, 0, 100); }, "%");
    this.updateInspectorOutput("channel-pan", this.formatPanValue(channel.pan));
    this.updateInspectorOutput("channel-highpass", this.formatFreqValue(channel.fx.highpass));
    this.updateInspectorOutput("channel-lowpass", this.formatFreqValue(channel.fx.lowpass));
    this.elements.inspector.querySelector('[data-inspector-action="audition-channel"]')?.addEventListener("click", () => this.triggerChannel(channel, 96));
    this.elements.inspector.querySelector('[data-inspector-action="toggle-channel-mute"]')?.addEventListener("click", () => {
      channel.muted = !channel.muted;
      this.renderChannels();
      this.renderMixer();
      this.showChannelInspector(channel);
      this.saveHistory();
    });
    this.elements.inspector.querySelector('[data-inspector-action="toggle-channel-solo"]')?.addEventListener("click", () => {
      channel.solo = !channel.solo;
      this.renderChannels();
      this.renderMixer();
      this.showChannelInspector(channel);
      this.saveHistory();
    });
    this.elements.inspector.querySelector('[data-inspector-action="reset-channel"]')?.addEventListener("click", () => {
      channel.volume = 80;
      channel.pan = 0;
      channel.fx.highpass = 20;
      channel.fx.lowpass = 20000;
      channel.send.reverb = 0;
      channel.send.delay = 0;
      this.applyChannelFx(channel);
      this.renderChannels();
      this.renderMixer();
      this.showChannelInspector(channel);
      this.saveHistory();
    });
    this.elements.inspector.querySelector('[data-inspector-action="duplicate-channel"]')?.addEventListener("click", () => this.duplicateChannel(channel.id));
    this.elements.inspector.querySelector('[data-inspector-action="open-step-seq"]')?.addEventListener("click", () => this.switchView("step-seq", this.container.querySelector('[data-view="step-seq"]')));
    this.elements.inspector.querySelector('[data-inspector-action="open-mixer"]')?.addEventListener("click", () => this.switchView("mixer", this.container.querySelector('[data-view="mixer"]')));
  }

  showClipInspector(clip) {
    if (!this.elements.inspector) return;
    const beats = Number((clip.width / this.cellWidth).toFixed(2));
    const startBeat = Number((clip.x / this.cellWidth).toFixed(2));
    const endBeat = Number(((clip.x + clip.width) / this.cellWidth).toFixed(2));
    const trackName = this.trackNames?.[clip.track] || `${this.t("track", "Track")} ${clip.track + 1}`;
    const pattern = clip.type === "pattern" ? this.patterns.find(item => item.id === clip.patternId) : null;
    const patternNotes = pattern ? (pattern.notes || []).length : 0;
    const patternSteps = pattern ? Object.values(pattern.stepsByChannel || {}).reduce((sum, steps) => sum + steps.filter(Boolean).length, 0) : 0;
    const color = this.clipColor(clip);
    const audioControls = clip.type === "audio" ? this.inspectorSection(this.t("audio", "Аудио"), `
      ${this.inspectorRange(this.t("volume", "Volume"), "clip-volume", clip.volume ?? 85, 0, 120, "%")}
      <div class="cx-field"><label>${this.escapeHtml(this.t("fade_in_seconds", "Fade in seconds"))}</label><input type="number" min="0" max="12" step="0.1" data-edit-clip-fade-in value="${clip.fadeIn || 0}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("fade_out_seconds", "Fade out seconds"))}</label><input type="number" min="0" max="12" step="0.1" data-edit-clip-fade-out value="${clip.fadeOut || 0}"></div>
      <div class="cx-inspector-two">
        <div class="cx-field"><label>${this.escapeHtml(this.t("trim_start_seconds", "Trim start seconds"))}</label><input type="number" min="0" max="600" step="0.1" data-edit-clip-trim-start value="${clip.trimStart || 0}"></div>
        <div class="cx-field"><label>${this.escapeHtml(this.t("trim_end_seconds", "Trim end seconds"))}</label><input type="number" min="0" max="600" step="0.1" data-edit-clip-trim-end value="${clip.trimEnd || 0}"></div>
      </div>
    `) : "";
    const patternControls = clip.type === "pattern" ? this.inspectorSection(this.t("pattern", "Pattern"), `
      <div class="cx-clip-micro-grid">
        <span><b>${patternNotes}</b><small>${this.escapeHtml(this.t("note", "Note"))}</small></span>
        <span><b>${patternSteps}</b><small>Steps</small></span>
        <span><b>${this.patternStepCount(pattern)}</b><small>16/32</small></span>
      </div>
      <div class="cx-inspector-actions cx-compact-actions">
        <button type="button" data-inspector-action="open-pattern">${this.escapeHtml(this.t("piano_roll", "Piano Roll"))}</button>
        <button type="button" data-inspector-action="open-step-seq">${this.escapeHtml(this.t("channel_rack", "Channel Rack"))}</button>
        <button type="button" data-inspector-action="quantize-pattern">${this.escapeHtml(this.t("quantize", "Quantize"))}</button>
        <button type="button" data-inspector-action="clear-pattern">${this.escapeHtml(this.t("clear", "Clear"))}</button>
      </div>
    `, "cx-pattern-inspector-section") : "";
    this.elements.inspector.innerHTML = `
      ${this.inspectorHeader("clip", clip.name || "Clip", `${clip.type} - ${trackName}`, color)}
      ${this.inspectorStats([
        { label: this.t("track", "Track"), value: String(clip.track + 1) },
        { label: this.t("beat", "Beat"), value: String(startBeat) },
        { label: this.t("length_beats", "Length beats"), value: String(beats) }
      ])}
      ${this.inspectorSection(this.t("edit", "Редактирование"), `
        <div class="cx-field"><label>${this.escapeHtml(this.t("clip_name", "Clip name"))}</label><input data-edit-clip-name value="${this.escapeHtml(clip.name)}"></div>
        <div class="cx-inspector-two">
          <div class="cx-field"><label>${this.escapeHtml(this.t("track", "Track"))}</label><input type="number" min="1" max="${this.tracks}" data-edit-clip-track value="${clip.track + 1}"></div>
          <div class="cx-field"><label>${this.escapeHtml(this.t("start", "Start"))}</label><input type="number" min="0" max="256" step="0.25" data-edit-clip-start value="${startBeat}"></div>
        </div>
        <div class="cx-inspector-two">
          <div class="cx-field"><label>${this.escapeHtml(this.t("length_beats", "Length beats"))}</label><input type="number" min="0.25" max="256" step="0.25" data-edit-clip-width value="${beats}"></div>
          <div class="cx-field"><label>${this.escapeHtml(this.t("end", "End"))}</label><input type="number" min="0.25" max="256" step="0.25" data-edit-clip-end value="${endBeat}"></div>
        </div>
        <div class="cx-clip-nudge-row">
          <button type="button" data-clip-nudge="-1">-1</button>
          <button type="button" data-clip-nudge="-0.25">-1/4</button>
          <button type="button" data-clip-nudge="0.25">+1/4</button>
          <button type="button" data-clip-nudge="1">+1</button>
        </div>
        <div class="cx-clip-nudge-row">
          <button type="button" data-clip-length="0.5">1/2</button>
          <button type="button" data-clip-length="2">x2</button>
          <button type="button" data-clip-fit-pattern>${this.escapeHtml(this.t("fit_to_pattern", "Fit"))}</button>
          <button type="button" data-clip-align-grid>${this.escapeHtml(this.t("align_to_grid", "Grid"))}</button>
        </div>
        <div class="cx-field cx-color-field"><label>${this.escapeHtml(this.t("color", "Color"))}</label><input type="color" data-edit-clip-color value="${color}"></div>
        <div class="cx-clip-nudge-row">
          <button type="button" data-clip-color-source="channel">${this.escapeHtml(this.t("color_from_channel", "Color from channel"))}</button>
          ${clip.type === "pattern" ? `<button type="button" data-clip-color-source="pattern">${this.escapeHtml(this.t("pattern", "Pattern"))}</button>` : ""}
        </div>
      `)}
      ${patternControls}
      ${audioControls}
      <div class="cx-inspector-actions">
        <button type="button" data-inspector-action="duplicate-clip">${this.escapeHtml(this.t("duplicate", "Duplicate"))}</button>
        <button type="button" data-inspector-action="mute-clip">${this.escapeHtml(clip.muted ? this.t("unmute", "Unmute") : this.t("mute", "Mute"))}</button>
        <button type="button" class="is-danger" data-inspector-action="delete-clip">${this.escapeHtml(this.t("delete", "Delete"))}</button>
      </div>
    `;
    this.elements.inspector.querySelector("[data-edit-clip-name]")?.addEventListener("input", event => {
      clip.name = event.target.value.trim() || clip.name;
      if (clip.type === "pattern") {
        const pattern = this.patterns.find(item => item.id === clip.patternId);
        if (pattern) pattern.name = clip.name;
      }
      this.renderPlaylist();
      this.updateActivePatternLabel();
    });
    this.elements.inspector.querySelector("[data-edit-clip-name]")?.addEventListener("change", () => this.saveHistory());
    this.elements.inspector.querySelector("[data-edit-clip-track]")?.addEventListener("change", event => {
      clip.track = this.clamp(Number(event.target.value) - 1, 0, this.tracks - 1);
      this.renderPlaylist();
      this.saveHistory();
      this.showClipInspector(clip);
    });
    this.elements.inspector.querySelector("[data-edit-clip-start]")?.addEventListener("change", event => {
      clip.x = Math.max(0, (Number(event.target.value) || 0) * this.cellWidth);
      this.renderPlaylist();
      this.saveHistory();
      this.showClipInspector(clip);
    });
    this.elements.inspector.querySelector("[data-edit-clip-width]")?.addEventListener("change", event => {
      clip.width = Math.max(this.cellWidth / 4, (Number(event.target.value) || 4) * this.cellWidth);
      this.renderPlaylist();
      this.saveHistory();
      this.showClipInspector(clip);
    });
    this.elements.inspector.querySelector("[data-edit-clip-end]")?.addEventListener("change", event => {
      const end = Math.max(0.25, Number(event.target.value) || endBeat);
      clip.width = Math.max(this.cellWidth / 4, end * this.cellWidth - clip.x);
      this.renderPlaylist();
      this.saveHistory();
      this.showClipInspector(clip);
    });
    this.elements.inspector.querySelector("[data-edit-clip-color]")?.addEventListener("input", event => {
      clip.color = event.target.value;
      this.renderPlaylist();
    });
    this.elements.inspector.querySelector("[data-edit-clip-color]")?.addEventListener("change", () => this.saveHistory());
    this.elements.inspector.querySelectorAll("[data-clip-nudge]").forEach(button => {
      button.addEventListener("click", () => {
        clip.x = Math.max(0, this.snapX(clip.x + Number(button.dataset.clipNudge) * this.cellWidth));
        this.renderPlaylist();
        this.saveHistory();
        this.showClipInspector(clip);
      });
    });
    this.elements.inspector.querySelectorAll("[data-clip-length]").forEach(button => {
      button.addEventListener("click", () => {
        clip.width = Math.max(this.cellWidth / 4, this.snapX(clip.width * Number(button.dataset.clipLength)));
        this.renderPlaylist();
        this.saveHistory();
        this.showClipInspector(clip);
      });
    });
    this.elements.inspector.querySelector("[data-clip-fit-pattern]")?.addEventListener("click", () => {
      const patternLength = clip.type === "pattern" ? this.patternStepCount(pattern) / 4 : 4;
      clip.width = Math.max(this.cellWidth, patternLength * this.cellWidth);
      this.renderPlaylist();
      this.saveHistory();
      this.showClipInspector(clip);
    });
    this.elements.inspector.querySelector("[data-clip-align-grid]")?.addEventListener("click", () => {
      clip.x = this.snapX(clip.x);
      clip.width = Math.max(this.cellWidth / 4, this.snapX(clip.width) || this.cellWidth);
      this.renderPlaylist();
      this.saveHistory();
      this.showClipInspector(clip);
    });
    this.elements.inspector.querySelectorAll("[data-clip-color-source]").forEach(button => {
      button.addEventListener("click", () => {
        if (button.dataset.clipColorSource === "pattern" && pattern) clip.color = pattern.color;
        if (button.dataset.clipColorSource === "channel") clip.color = this.getSelectedChannel()?.color || this.clipColor(clip);
        this.renderPlaylist();
        this.saveHistory();
        this.showClipInspector(clip);
      });
    });
    this.elements.inspector.querySelector("[data-edit-clip-volume]")?.addEventListener("input", event => {
      clip.volume = this.clamp(Number(event.target.value) || 0, 0, 120);
      this.updateInspectorOutput("clip-volume", clip.volume, "%");
      this.renderPlaylist();
    });
    this.elements.inspector.querySelector("[data-edit-clip-volume]")?.addEventListener("change", () => this.saveHistory());
    this.elements.inspector.querySelector("[data-edit-clip-fade-in]")?.addEventListener("change", event => {
      clip.fadeIn = this.clamp(Number(event.target.value) || 0, 0, 12);
      this.renderPlaylist();
      this.saveHistory();
    });
    this.elements.inspector.querySelector("[data-edit-clip-fade-out]")?.addEventListener("change", event => {
      clip.fadeOut = this.clamp(Number(event.target.value) || 0, 0, 12);
      this.renderPlaylist();
      this.saveHistory();
    });
    this.elements.inspector.querySelector("[data-edit-clip-trim-start]")?.addEventListener("change", event => {
      clip.trimStart = this.clamp(Number(event.target.value) || 0, 0, 600);
      this.saveHistory();
    });
    this.elements.inspector.querySelector("[data-edit-clip-trim-end]")?.addEventListener("change", event => {
      clip.trimEnd = this.clamp(Number(event.target.value) || 0, 0, 600);
      this.saveHistory();
    });
    this.elements.inspector.querySelector('[data-inspector-action="open-pattern"]')?.addEventListener("click", () => this.openPatternClip(clip.id, "piano-roll"));
    this.elements.inspector.querySelector('[data-inspector-action="open-step-seq"]')?.addEventListener("click", () => this.openPatternClip(clip.id, "step-seq"));
    this.elements.inspector.querySelector('[data-inspector-action="quantize-pattern"]')?.addEventListener("click", () => {
      this.selectedPatternId = clip.patternId;
      this.quantizeActivePatternNotes();
      this.showClipInspector(clip);
    });
    this.elements.inspector.querySelector('[data-inspector-action="clear-pattern"]')?.addEventListener("click", () => {
      this.selectedPatternId = clip.patternId;
      this.clearActivePattern();
      this.showClipInspector(clip);
    });
    this.elements.inspector.querySelector('[data-inspector-action="duplicate-clip"]')?.addEventListener("click", () => this.duplicateClip(clip.id));
    this.elements.inspector.querySelector('[data-inspector-action="mute-clip"]')?.addEventListener("click", () => this.toggleClipMute(clip.id));
    this.elements.inspector.querySelector('[data-inspector-action="delete-clip"]')?.addEventListener("click", () => this.removeClip(clip.id));
  }

  updateInspectorDefault() {
    if (!this.elements.inspector) return;
    this.elements.inspector.innerHTML = `
      ${this.inspectorHeader("ready", this.t("inspector", "Inspector"), this.t("select_item_hint", "Select a note, pattern, clip or channel."), "#36d399")}
      ${this.inspectorSection("Hotkeys", `
        <div class="cx-hotkey-list">
          <span><kbd>Space</kbd><b>${this.escapeHtml(this.t("play", "Play"))} / ${this.escapeHtml(this.t("pause", "Pause"))}</b></span>
          <span><kbd>Delete</kbd><b>${this.escapeHtml(this.t("delete", "Delete"))}</b></span>
          <span><kbd>Ctrl</kbd><kbd>S</kbd><b>${this.escapeHtml(this.t("save", "Save"))}</b></span>
          <span><kbd>Ctrl</kbd><kbd>D</kbd><b>${this.escapeHtml(this.t("duplicate", "Duplicate"))}</b></span>
          <span><kbd>Ctrl</kbd><kbd>Z</kbd><b>Undo</b></span>
        </div>
      `)}
      ${this.inspectorSection(this.t("quick_start", "Быстрый старт"), `
        <div class="cx-inspector-actions">
          <button type="button" data-inspector-action="new-pattern">${this.escapeHtml(this.t("pattern", "Pattern"))}</button>
          <button type="button" data-inspector-action="open-mixer">${this.escapeHtml(this.t("mixer", "Mixer"))}</button>
        </div>
      `)}
    `;
    this.elements.inspector.querySelector('[data-inspector-action="new-pattern"]')?.addEventListener("click", () => this.addPatternClip());
    this.elements.inspector.querySelector('[data-inspector-action="open-mixer"]')?.addEventListener("click", () => this.switchView("mixer", this.container.querySelector('[data-view="mixer"]')));
  }

  deleteSelected() {
    const pattern = this.getActivePattern();
    if (this.selectedNoteIds.size && pattern) {
      pattern.notes = pattern.notes.filter(note => !this.selectedNoteIds.has(note.id));
      this.selectedNoteIds.clear();
      this.selectedNoteId = null;
      this.renderNotes();
      this.updateInspectorDefault();
      this.saveHistory();
      return;
    }
    if (this.selectedClipIds.size) {
      const deletedPatternIds = new Set(this.clips.filter(item => this.selectedClipIds.has(item.id) && item.type === "pattern").map(item => item.patternId));
      this.clips = this.clips.filter(item => !this.selectedClipIds.has(item.id));
      deletedPatternIds.forEach(patternId => {
        if (!this.clips.some(item => item.patternId === patternId)) this.patterns = this.patterns.filter(item => item.id !== patternId);
      });
      this.selectedClipIds.clear();
      this.selectedClipId = null;
      this.selectedPatternId = this.patterns[0]?.id || null;
      this.renderPlaylist();
      this.renderNotes();
      this.renderStepSequencer();
      this.updateInspectorDefault();
      this.saveHistory();
      return;
    }
    if (this.selectedNoteId && pattern) {
      pattern.notes = pattern.notes.filter(note => note.id !== this.selectedNoteId);
      this.selectedNoteId = null;
      this.renderNotes();
      this.updateInspectorDefault();
      this.saveHistory();
      return;
    }
    if (this.selectedClipId) {
      const clip = this.clips.find(item => item.id === this.selectedClipId);
      this.clips = this.clips.filter(item => item.id !== this.selectedClipId);
      if (clip?.type === "pattern" && !this.clips.some(item => item.patternId === clip.patternId)) {
        this.patterns = this.patterns.filter(item => item.id !== clip.patternId);
      }
      this.selectedClipId = null;
      this.selectedPatternId = this.patterns[0]?.id || null;
      this.renderPlaylist();
      this.renderNotes();
      this.renderStepSequencer();
      this.updateInspectorDefault();
      this.saveHistory();
    }
  }

  duplicateSelected() {
    const pattern = this.getActivePattern();
    if (this.selectedNoteIds.size && pattern) {
      const copies = pattern.notes
        .filter(note => this.selectedNoteIds.has(note.id))
        .map(note => ({ ...note, id: this.uuid(), x: note.x + this.cellWidth }));
      pattern.notes.push(...copies);
      this.selectedNoteIds = new Set(copies.map(note => note.id));
      this.selectedNoteId = null;
      this.renderNotes();
      this.saveHistory();
      return;
    }
    if (this.selectedClipIds.size) {
      const copies = [];
      this.clips.filter(clip => this.selectedClipIds.has(clip.id)).forEach(clip => {
        const copy = { ...clip, id: this.uuid(), name: `${clip.name} Copy`, x: clip.x + this.cellWidth };
        if (clip.type === "pattern") {
          const original = this.patterns.find(item => item.id === clip.patternId);
          if (original) {
            const newPattern = this.createPattern(`${original.name} Copy`);
            newPattern.notes = JSON.parse(JSON.stringify(original.notes || []));
            newPattern.stepsByChannel = JSON.parse(JSON.stringify(original.stepsByChannel || {}));
            newPattern.stepVelocity = JSON.parse(JSON.stringify(original.stepVelocity || {}));
            newPattern.lengthSteps = original.lengthSteps || this.steps;
            newPattern.color = original.color || newPattern.color;
            this.patterns.push(newPattern);
            copy.patternId = newPattern.id;
          }
        }
        copies.push(copy);
      });
      this.clips.push(...copies);
      this.selectedClipIds = new Set(copies.map(clip => clip.id));
      this.selectedClipId = null;
      this.renderPlaylist();
      this.saveHistory();
      return;
    }
    if (this.selectedNoteId && pattern) {
      const note = pattern.notes.find(item => item.id === this.selectedNoteId);
      if (!note) return;
      const copy = { ...note, id: this.uuid(), x: note.x + this.cellWidth };
      pattern.notes.push(copy);
      this.selectNote(copy.id);
      this.saveHistory();
      return;
    }
    if (this.selectedClipId) {
      const clip = this.clips.find(item => item.id === this.selectedClipId);
      if (!clip) return;
      const copy = { ...clip, id: this.uuid(), name: `${clip.name} Copy`, x: clip.x + this.cellWidth };
      if (clip.type === "pattern") {
        const original = this.patterns.find(item => item.id === clip.patternId);
        if (original) {
          const newPattern = this.createPattern(`${original.name} Copy`);
          newPattern.notes = JSON.parse(JSON.stringify(original.notes || []));
          newPattern.stepsByChannel = JSON.parse(JSON.stringify(original.stepsByChannel || {}));
          newPattern.stepVelocity = JSON.parse(JSON.stringify(original.stepVelocity || {}));
          newPattern.lengthSteps = original.lengthSteps || this.steps;
          newPattern.color = original.color || newPattern.color;
          this.patterns.push(newPattern);
          copy.patternId = newPattern.id;
        }
      }
      this.clips.push(copy);
      this.selectClip(copy.id);
      this.saveHistory();
    }
  }

  saveHistory() {
    const snapshot = JSON.stringify({
      title: this.projectTitle,
      bpm: this.bpm,
      tracks: this.tracks,
      trackNames: this.trackNames,
      channels: this.channels,
      patterns: this.patterns,
      clips: this.clips,
      assets: this.assets,
      activeView: this.activeView,
      arrangeTool: this.arrangeTool,
      tool: this.tool,
      noteLengthBeats: this.noteLengthBeats,
      selectedPatternId: this.selectedPatternId,
      selectedChannelId: this.selectedChannelId,
      selectedClipId: this.selectedClipId,
      selectedNoteId: this.selectedNoteId,
      selectedClipIds: [...this.selectedClipIds],
      selectedNoteIds: [...this.selectedNoteIds]
    });
    if (snapshot === this.history[this.historyIndex]) return;
    this.history = this.history.slice(0, this.historyIndex + 1);
    this.history.push(snapshot);
    if (this.history.length > this.maxHistory) this.history.shift();
    this.historyIndex = this.history.length - 1;
    this.markDirty();
  }

  markDirty() {
    this.writeLocalBackup();
    if (!this.readyForAutosave) return;
    this.isDirty = true;
    clearTimeout(this.autoSaveTimer);
    this.autoSaveTimer = setTimeout(() => this.autoSave(this.t("auto_saved", "Auto-saved")), 1800);
  }

  startAutoSave() {
    window.setInterval(() => {
      if (this.isDirty) this.autoSave(this.t("auto_saved", "Auto-saved"));
    }, 25000);
  }

  async autoSave(message = "Auto-saved") {
    if (!this.readyForAutosave || !this.isDirty || !this.projectsApiUrl) return;
    try {
      await this.saveProject({ silent: true });
      this.isDirty = false;
      this.toast(message, "success");
    } catch (_) {
      this.writeLocalBackup();
    }
  }

  localBackupKey() {
    return `cx_music_project_${this.projectId || "draft"}`;
  }

  writeLocalBackup() {
    try {
      localStorage.setItem(this.localBackupKey(), JSON.stringify(this.getState()));
    } catch (_) {}
  }

  readLocalBackup() {
    try {
      const raw = localStorage.getItem(this.localBackupKey());
      return raw ? JSON.parse(raw) : null;
    } catch (_) {
      return null;
    }
  }

  hasMeaningfulState(state) {
    return Boolean(
      state &&
      typeof state === "object" &&
      (
        (Array.isArray(state.patterns) && state.patterns.length) ||
        (Array.isArray(state.clips) && state.clips.length) ||
        (Array.isArray(state.assets) && state.assets.length) ||
        Boolean(String(state.lyrics?.html || state.projectLyrics || "").replace(/<[^>]+>/g, "").trim())
      )
    );
  }

  stateWeight(state) {
    if (!state || typeof state !== "object") return 0;
    const notes = (state.patterns || []).reduce((sum, pattern) => sum + (pattern.notes || []).length + Object.values(pattern.stepsByChannel || {}).flat().filter(Boolean).length, 0);
    const lyricWeight = String(state.lyrics?.html || state.projectLyrics || "").replace(/<[^>]+>/g, "").trim() ? 2 : 0;
    return (state.patterns || []).length + (state.clips || []).length * 3 + (state.assets || []).length * 2 + notes + lyricWeight;
  }

  undo() {
    if (this.historyIndex <= 0) {
      this.toast(this.t("nothing_to_undo", "Nothing to undo"), "info");
      return;
    }
    this.historyIndex -= 1;
    this.restoreHistory(this.history[this.historyIndex]);
    this.markDirty();
    this.toast(this.t("undo_applied", "Undo"), "info");
  }

  redo() {
    if (this.historyIndex >= this.history.length - 1) {
      this.toast(this.t("nothing_to_redo", "Nothing to redo"), "info");
      return;
    }
    this.historyIndex += 1;
    this.restoreHistory(this.history[this.historyIndex]);
    this.markDirty();
    this.toast(this.t("redo_applied", "Redo"), "info");
  }

  restoreHistory(snapshot) {
    try {
      const state = JSON.parse(snapshot);
      this.projectTitle = state.title || this.projectTitle;
      this.bpm = Number(state.bpm || this.bpm);
      this.channels = state.channels || this.channels;
      this.patterns = state.patterns || this.patterns;
      this.clips = state.clips || this.clips;
      this.assets = state.assets || this.assets;
      this.tracks = this.clamp(Number(state.tracks || this.tracks), 1, 24);
      this.trackNames = Array.isArray(state.trackNames) ? state.trackNames : this.trackNames;
      this.activeView = state.activeView || this.activeView;
      this.arrangeTool = state.arrangeTool || this.arrangeTool;
      this.tool = state.tool || this.tool;
      this.projectLyrics = this.sanitizeLyricsHtml(state.lyrics?.html || state.projectLyrics || this.projectLyrics || "");
      this.lyricsPanel = { ...this.lyricsPanel, ...(state.lyricsPanel || {}) };
      this.activeAudioInputId = state.devices?.audioInputId || this.activeAudioInputId;
      this.activeMidiInputId = state.devices?.midiInputId || this.activeMidiInputId;
      this.audioInputRole = state.devices?.audioInputRole || this.audioInputRole;
      this.monitorInput = Boolean(state.devices?.monitorInput ?? this.monitorInput);
      this.noiseReduction = Boolean(state.devices?.noiseReduction ?? this.noiseReduction);
      this.noteLengthBeats = Number(state.noteLengthBeats || this.noteLengthBeats);
      this.selectedPatternId = state.selectedPatternId || this.patterns[0]?.id || null;
      this.selectedChannelId = state.selectedChannelId || this.channels[0]?.id || null;
      this.selectedClipId = state.selectedClipId || null;
      this.selectedNoteId = state.selectedNoteId || null;
      this.selectedClipIds = new Set(Array.isArray(state.selectedClipIds) ? state.selectedClipIds : []);
      this.selectedNoteIds = new Set(Array.isArray(state.selectedNoteIds) ? state.selectedNoteIds : []);
      if (!this.clips.some(clip => clip.id === this.selectedClipId)) this.selectedClipId = null;
      if (!this.patterns.some(pattern => pattern.id === this.selectedPatternId)) this.selectedPatternId = this.patterns[0]?.id || null;
      const activePattern = this.getActivePattern();
      if (!activePattern?.notes?.some(note => note.id === this.selectedNoteId)) this.selectedNoteId = null;
      this.selectedClipIds = new Set([...this.selectedClipIds].filter(id => this.clips.some(clip => clip.id === id)));
      this.selectedNoteIds = new Set([...this.selectedNoteIds].filter(id => activePattern?.notes?.some(note => note.id === id)));
      Object.values(this.synths).forEach(pack => {
        try { pack.synth.dispose(); } catch (_) {}
      });
      this.synths = {};
      this.channels.forEach(channel => this.ensureSynth(channel));
      if (this.audioReady && window.Tone) Tone.Transport.bpm.value = this.bpm;
      this.renderAll();
      this.restoreViewAfterHistory();
      this.updateInspectorAfterHistory();
      this.saveUiPrefs();
    } catch (error) {
      console.warn(error);
    }
  }

  restoreViewAfterHistory() {
    const viewButton = this.container.querySelector(`[data-view="${this.activeView}"]`);
    if (viewButton) this.switchView(this.activeView, viewButton);
    this.container.querySelectorAll("[data-arrange-tool]").forEach(button => button.classList.toggle("active", button.dataset.arrangeTool === this.arrangeTool));
    this.container.querySelectorAll("[data-tool]").forEach(button => button.classList.toggle("active", button.dataset.tool === this.tool));
  }

  updateInspectorAfterHistory() {
    const clip = this.selectedClipId ? this.clips.find(item => item.id === this.selectedClipId) : null;
    if (clip) {
      this.showClipInspector(clip);
      return;
    }
    const pattern = this.getActivePattern();
    const note = this.selectedNoteId && pattern ? pattern.notes.find(item => item.id === this.selectedNoteId) : null;
    if (note) {
      this.showNoteInspector(note);
      return;
    }
    const channel = this.getSelectedChannel();
    if (channel && this.activeView === "mixer") {
      this.showChannelInspector(channel);
      return;
    }
    this.updateInspectorDefault();
  }

  loadInitialState() {
    const payload = window.CX_MUSIC_INITIAL_STATE || {};
    let state = payload.state && typeof payload.state === "object" ? payload.state : payload;
    const backup = this.readLocalBackup();
    if (this.hasMeaningfulState(backup)) {
      const backupTime = Date.parse(backup.updatedAt || "") || 0;
      const stateTime = Date.parse(state.updatedAt || payload.updated_at || "") || 0;
      if (!this.hasMeaningfulState(state) || (backupTime > stateTime && this.stateWeight(backup) >= this.stateWeight(state))) {
        state = backup;
        this.toast(this.t("restored_local_autosave", "Restored local autosave"), "info");
      }
    }
    if (!state || typeof state !== "object") return;
    this.projectTitle = state.title || payload.title || this.projectTitle;
    this.bpm = Number(state.bpm || this.bpm);
    this.tracks = this.clamp(Number(state.tracks || this.tracks), 1, 24);
    this.trackNames = Array.isArray(state.trackNames) ? state.trackNames : this.trackNames;
    if (Array.isArray(state.channels) && state.channels.length) this.channels = state.channels;
    if (Array.isArray(state.patterns) && state.patterns.length) this.patterns = state.patterns;
    if (Array.isArray(state.clips)) this.clips = state.clips;
    if (Array.isArray(state.assets)) {
      this.assets = state.assets.map(asset => ({
        ...asset,
        kind: asset.kind || (String(asset.media_type || asset.type || "").startsWith("audio/") ? "audio" : "source"),
        serverId: asset.serverId || asset.id,
        url: asset.url || asset.preview_url || "",
        uploaded: asset.uploaded !== false,
      }));
    }
    this.noteLengthBeats = Number(state.noteLengthBeats || this.noteLengthBeats);
    this.projectLyrics = this.sanitizeLyricsHtml(state.lyrics?.html || state.projectLyrics || "");
    this.lyricsPanel = { ...this.lyricsPanel, ...(state.lyricsPanel || {}) };
    this.activeAudioInputId = state.devices?.audioInputId || this.activeAudioInputId;
    this.activeMidiInputId = state.devices?.midiInputId || this.activeMidiInputId;
    this.audioInputRole = state.devices?.audioInputRole || this.audioInputRole;
    this.monitorInput = Boolean(state.devices?.monitorInput ?? this.monitorInput);
    this.noiseReduction = Boolean(state.devices?.noiseReduction ?? this.noiseReduction);
    if (!this.assets.length && Array.isArray(payload.assets)) {
      this.assets = payload.assets.map(asset => ({
        id: String(asset.id),
        serverId: asset.id,
        kind: asset.kind || "audio",
        name: asset.name,
        size: asset.size,
        type: asset.media_type,
        media_type: asset.media_type,
        url: asset.preview_url,
        duration: Number(asset.duration || 0),
        uploaded: true
      }));
    }
    this.channels.forEach(channel => this.normalizeChannel(channel));
    this.patterns.forEach(pattern => this.normalizePattern(pattern));
    this.clips.forEach(clip => {
      clip.type = clip.type || (clip.assetId ? "audio" : "pattern");
      clip.track = this.clamp(Number(clip.track || 0), 0, this.tracks - 1);
      clip.x = Math.max(0, Number(clip.x || this.cellWidth));
      clip.width = Math.max(this.cellWidth, Number(clip.width || this.cellWidth * 4));
      clip.muted = Boolean(clip.muted);
      clip.volume = this.clamp(Number(clip.volume ?? 85), 0, 120);
      clip.fadeIn = Math.max(0, Number(clip.fadeIn || 0));
      clip.fadeOut = Math.max(0, Number(clip.fadeOut || 0));
      clip.trimStart = Math.max(0, Number(clip.trimStart || 0));
      clip.trimEnd = Math.max(0, Number(clip.trimEnd || 0));
    });
    this.assets.forEach(asset => {
      if (!asset.url && asset.preview_url) asset.url = asset.preview_url;
      asset.uploaded = asset.uploaded ?? Boolean(asset.serverId);
    });
    this.selectedPatternId = state.selectedPatternId || this.patterns[0]?.id || null;
    this.selectedChannelId = state.selectedChannelId || this.channels[0]?.id || null;
  }

  getState() {
    if (this.elements.lyricsEditor) {
      this.projectLyrics = this.sanitizeLyricsHtml(this.elements.lyricsEditor.innerHTML || "");
    }
    const ratio = this.baseCellWidth / this.cellWidth;
    const clips = this.clips.map(clip => ({
      ...clip,
      x: Math.round((clip.x || 0) * ratio),
      width: Math.max(this.baseCellWidth, Math.round((clip.width || this.cellWidth) * ratio))
    }));
    const patterns = this.patterns.map(pattern => ({
      ...pattern,
      notes: (pattern.notes || []).map(note => ({
        ...note,
        x: Math.round((note.x || 0) * ratio),
        y: this.pianoRowAt(Number(note.row || 0)).top,
        width: Math.max(this.baseCellWidth / 2, Math.round((note.width || this.cellWidth) * ratio))
      }))
    }));

    return {
      title: this.projectTitle,
      bpm: this.bpm,
      tracks: this.tracks,
      trackNames: this.trackNames,
      channels: this.channels,
      patterns,
      clips,
      assets: this.assets.map(asset => ({
        id: asset.id,
        serverId: asset.serverId || null,
        name: asset.name,
        size: asset.size,
        type: asset.type,
        url: asset.uploaded ? asset.url : "",
        uploaded: Boolean(asset.uploaded)
      })),
      lyrics: {
        html: this.projectLyrics,
        text: this.elements.lyricsEditor?.innerText || ""
      },
      lyricsPanel: this.lyricsPanel,
      devices: {
        audioInputId: this.activeAudioInputId,
        midiInputId: this.activeMidiInputId,
        audioInputRole: this.audioInputRole,
        monitorInput: Boolean(this.monitorInput),
        noiseReduction: Boolean(this.noiseReduction)
      },
      selectedPatternId: this.selectedPatternId,
      selectedChannelId: this.selectedChannelId,
      noteLengthBeats: this.noteLengthBeats,
      updatedAt: new Date().toISOString()
    };
  }

  async saveProject(options = {}) {
    const endpoint = this.projectId ? `${this.projectsApiUrl}${this.projectId}/save/` : `${this.projectsApiUrl}create/`;
    if (!this.projectsApiUrl) {
      if (!options.silent) this.toast("No API URL", "error");
      return;
    }
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": this.getCsrfToken() },
        body: JSON.stringify({ title: this.projectTitle, state: this.getState() })
      });
      if (!response.ok) throw new Error(`Save failed: ${response.status}`);
      const data = await response.json();
      if (data.project?.id) {
        const oldKey = this.localBackupKey();
        this.projectId = String(data.project.id);
        this.container.dataset.projectId = this.projectId;
        const url = new URL(window.location.href);
        url.searchParams.set("project", this.projectId);
        window.history.replaceState({}, "", url.toString());
        try {
          if (oldKey !== this.localBackupKey()) localStorage.removeItem(oldKey);
        } catch (_) {}
      }
      this.isDirty = false;
      this.writeLocalBackup();
      if (!options.silent) this.toast(this.t("project_saved", "Project saved"), "success");
    } catch (error) {
      console.error(error);
      if (!options.silent) this.toast(this.t("project_save_error", "Project save error"), "error");
      throw error;
    }
  }

  getPatternSteps(pattern, channelId) {
    if (!pattern.stepsByChannel) pattern.stepsByChannel = {};
    const stepCount = this.patternStepCount(pattern);
    if (!pattern.stepsByChannel[channelId]) pattern.stepsByChannel[channelId] = Array.from({ length: stepCount }, () => false);
    if (pattern.stepsByChannel[channelId].length !== stepCount) {
      pattern.stepsByChannel[channelId] = Array.from({ length: stepCount }, (_, index) => Boolean(pattern.stepsByChannel[channelId][index]));
    }
    return pattern.stepsByChannel[channelId];
  }

  patternStepCount(pattern) {
    return this.clamp(Number(pattern?.lengthSteps || this.steps), 16, 32);
  }

  getStepVelocity(pattern, channelId, index) {
    if (!pattern?.stepVelocity) pattern.stepVelocity = {};
    const value = pattern.stepVelocity[channelId]?.[index];
    return this.clamp(Number(value || 88), 1, 100);
  }

  setStepVelocity(pattern, channelId, index, value) {
    if (!pattern.stepVelocity) pattern.stepVelocity = {};
    if (!pattern.stepVelocity[channelId]) pattern.stepVelocity[channelId] = Array.from({ length: this.patternStepCount(pattern) }, () => 88);
    pattern.stepVelocity[channelId][index] = this.clamp(Number(value) || 88, 1, 100);
  }

  getSelectedChannel() {
    return this.channels.find(channel => channel.id === this.selectedChannelId) || this.channels[0];
  }

  getActivePattern() {
    return this.patterns.find(pattern => pattern.id === this.selectedPatternId) || this.patterns[0];
  }

  updateActivePatternLabel() {
    const pattern = this.getActivePattern();
    if (this.elements.activePatternLabel) this.elements.activePatternLabel.textContent = pattern ? `${this.t("editing", "Editing")}: ${pattern.name}` : this.t("no_pattern_selected", "No pattern selected");
  }

  updateTimeDisplay() {
    if (!this.elements.timeDisplay) return;
    const minutes = Math.floor(this.currentTime / 60);
    const seconds = (this.currentTime % 60).toFixed(2);
    this.elements.timeDisplay.textContent = `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(5, "0")}`;
  }

  updatePlayhead() {
    const scrollLeft = this.elements.playlistGrid?.scrollLeft || 0;
    if (this.elements.playhead) {
      const x = this.secondsToPixels(this.currentTime) - scrollLeft - 1;
      const viewport = this.elements.playlistGrid ? Math.max(0, this.elements.playlistGrid.clientWidth - this.getTrackHeaderWidth()) : Infinity;
      const visible = x >= 0 && x <= viewport;
      this.elements.playhead.style.opacity = visible ? "1" : "0";
      this.elements.playhead.style.pointerEvents = visible ? "auto" : "none";
      this.elements.playhead.style.transform = `translateX(${this.clamp(x, 0, viewport)}px)`;
    }
    this.updatePianoPlayhead();
  }

  updatePianoPlayhead() {
    if (!this.elements.pianoPlayhead || !this.elements.pianoRoll) return;
    const time = this.transportPlaysPattern() ? this.patternPlaybackTime() : this.currentTime;
    const x = this.secondsToPixels(time) - this.elements.pianoRoll.scrollLeft - 1;
    const viewport = this.elements.pianoRoll.clientWidth;
    const visible = x >= 0 && x <= viewport;
    this.elements.pianoPlayhead.style.opacity = visible ? "1" : "0";
    this.elements.pianoPlayhead.style.transform = `translateX(${this.clamp(x, 0, viewport)}px)`;
  }

  syncTimelineScroll() {
    if (this.elements.ruler && this.elements.playlistGrid) this.elements.ruler.style.transform = `translateX(${-this.elements.playlistGrid.scrollLeft}px)`;
    this.updatePlayhead();
  }

  syncPianoScroll() {
    if (this.elements.pianoKeys && this.elements.pianoRoll) this.elements.pianoKeys.scrollTop = this.elements.pianoRoll.scrollTop;
    this.updatePianoPlayhead();
  }

  snapX(x) {
    const grid = this.snapGridSize();
    return Math.round(x / grid) * grid;
  }

  snapGridSize() {
    return this.cellWidth * this.snapMultiplier();
  }

  snapMultiplier() {
    const denominator = Number(String(this.elements.snap?.value || "1/32").split("/")[1]) || 32;
    return this.clamp(4 / denominator, 1 / 64, 1);
  }

  noteFromRow(row) {
    return this.elements.pianoKeys?.children[row]?.dataset?.note || null;
  }

  pianoRowAt(row) {
    return this.pianoRows[row] || {
      note: this.noteFromRow(row),
      top: Number(row || 0) * this.rowHeight,
      height: this.rowHeight,
      isBlack: false
    };
  }

  pianoRowFromY(y) {
    const value = Math.max(0, Number(y) || 0);
    const rows = this.pianoRows || [];
    if (!rows.length) return 0;
    let low = 0;
    let high = rows.length - 1;
    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      const row = rows[mid];
      if (value < row.top) high = mid - 1;
      else if (value >= row.top + row.height) low = mid + 1;
      else return mid;
    }
    return this.clamp(low, 0, rows.length - 1);
  }

  relativePoint(event, el) {
    const rect = el.getBoundingClientRect();
    return { x: event.clientX - rect.left + el.scrollLeft, y: event.clientY - rect.top + el.scrollTop };
  }

  prettyPresetName(preset) {
    return { piano: "Grand Piano", bass: "Deep Bass", lead: "Lead", pluck: "Pluck", pad: "Pad", kick: "Kick", snare: "Snare", hat: "Hi-Hat", clap: "Clap" }[preset] || "Instrument";
  }

  volumeToDb(value) {
    const normalized = this.clamp(Number(value) || 0, 0, 100) / 100;
    return normalized <= 0 ? -Infinity : 20 * Math.log10(normalized);
  }

  flashMixer(channelId) {
    const el = this.elements.mixer?.querySelector(`[data-channel-id="${channelId}"]`);
    if (!el) return;
    el.querySelectorAll(".cx-meter-bar").forEach(bar => bar.style.setProperty("--level", "100%"));
    setTimeout(() => {
      const channel = this.channels.find(item => item.id === channelId);
      el.querySelectorAll(".cx-meter-bar").forEach(bar => bar.style.setProperty("--level", `${Math.max(8, (channel?.volume || 40) * 0.8)}%`));
    }, 120);
  }

  getCsrfToken() {
    const input = document.querySelector("[name=csrfmiddlewaretoken]");
    if (input?.value) return input.value;
    const cookie = document.cookie.split("; ").find(row => row.startsWith("csrftoken="));
    return cookie ? decodeURIComponent(cookie.split("=")[1]) : "";
  }

  toast(message, type = "success") {
    document.querySelector(".cx-toast")?.remove();
    const toast = document.createElement("div");
    toast.className = `cx-toast ${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 2600);
  }

  clamp(value, min, max) {
    return Math.min(max, Math.max(min, value));
  }

  formatBytes(bytes) {
    const value = Number(bytes) || 0;
    if (value < 1024) return `${value} B`;
    if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
    return `${(value / 1024 / 1024).toFixed(1)} MB`;
  }

  escapeHtml(value) {
    return String(value ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  window.cherryXMusicStudio = new CherryXMusicStudio();
});
