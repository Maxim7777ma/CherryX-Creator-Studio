"use strict";

class CherryXMusicStudio {
  constructor() {
    this.container = document.querySelector("[data-music-editor]");
    if (!this.container) return;

    this.projectId = this.container.dataset.projectId || "";
    this.projectsApiUrl = this.normalizeApiUrl(this.container.dataset.projectsApiUrl || "");
    this.projectTitle = this.container.dataset.projectTitle || "Untitled Beat";

    this.baseCellWidth = 42;
    this.cellWidth = 42;
    this.rowHeight = 34;
    this.steps = 16;
    this.timelineBars = 64;
    this.tracks = 6;
    this.zoom = 1;

    this.bpm = 120;
    this.currentTime = 0;
    this.isPlaying = false;
    this.clockTimer = null;
    this.stepTimer = null;
    this.playTick = 0;

    this.tool = "draw";
    this.arrangeTool = "select";
    this.noteLengthBeats = 1;
    this.selectedChannelId = null;
    this.selectedPatternId = null;
    this.selectedClipId = null;
    this.selectedNoteId = null;

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
    this.history = [];
    this.historyIndex = -1;
    this.maxHistory = 50;
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
    this.initAudioGraph();
    this.bindEvents();
    this.renderAll();
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
    this.elements.noteLayer = q("[data-piano-notes]");
    this.elements.channelList = q("[data-channel-list]");
    this.elements.stepSequencer = q("[data-step-sequencer]");
    this.elements.mixer = q("[data-mixer]");
    this.elements.assetList = q("[data-asset-list]");
    this.elements.audioInput = q("[data-audio-input]");
    this.elements.inspector = q("[data-inspector]");
    this.elements.activePatternLabel = q("[data-active-pattern-label]");
    this.elements.zoomLevel = q("[data-zoom-level]");
    this.elements.patternSelect = q("[data-pattern-select]");
    this.elements.channelSelect = q("[data-channel-select]");
    this.elements.noteLength = q("[data-note-length]");
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
      button.addEventListener("click", () => this.changeZoom(button.dataset.zoom === "in" ? 0.12 : -0.12));
    });
    this.container.querySelectorAll("[data-preset]").forEach(button => {
      button.addEventListener("click", () => this.applyPreset(button.dataset.preset));
    });
    this.container.querySelectorAll("[data-drum]").forEach(button => {
      button.addEventListener("click", () => this.addDrumChannel(button.dataset.drum));
    });

    this.elements.bpmInput?.addEventListener("change", event => {
      this.bpm = this.clamp(parseInt(event.target.value, 10) || 120, 40, 300);
      event.target.value = this.bpm;
      if (window.Tone) Tone.Transport.bpm.value = this.bpm;
      if (this.isPlaying) this.startStepPlayback();
      this.saveHistory();
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
    this.elements.pianoRoll?.addEventListener("scroll", () => this.syncPianoScroll());
    this.elements.playlistGrid?.addEventListener("scroll", () => this.syncTimelineScroll());
    this.elements.playlistGrid?.addEventListener("dragover", event => event.preventDefault());
    this.elements.playlistGrid?.addEventListener("drop", event => this.handlePlaylistDrop(event));

    this.container.querySelector("[data-save-project]")?.addEventListener("click", () => this.saveProject());
    this.container.querySelector("[data-add-channel]")?.addEventListener("click", () => this.addChannel());
    this.container.querySelector('[data-action="new-pattern"]')?.addEventListener("click", () => this.addPatternClip());
    this.container.querySelector('[data-action="upload-audio"]')?.addEventListener("click", () => this.elements.audioInput?.click());
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
      this.saveHistory();
    });
    this.elements.channelSelect?.addEventListener("change", event => {
      this.selectedChannelId = event.target.value;
      this.renderChannels();
      this.renderMixer();
      this.updatePatternControls();
      this.saveHistory();
    });
    this.elements.noteLength?.addEventListener("change", event => {
      this.noteLengthBeats = Number(event.target.value) || 1;
    });

    document.addEventListener("keydown", event => this.handleHotkeys(event));
    document.addEventListener("click", () => this.hideContextMenu());
    window.addEventListener("beforeunload", () => this.writeLocalBackup());
  }

  handleHotkeys(event) {
    if (["INPUT", "TEXTAREA", "SELECT"].includes(event.target?.tagName)) return;
    if (event.code === "Space") {
      event.preventDefault();
      this.isPlaying ? this.pause() : this.play();
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      this.deleteSelected();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      this.saveProject();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "d") {
      event.preventDefault();
      this.duplicateSelected();
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      event.shiftKey ? this.redo() : this.undo();
    }
    if ((event.ctrlKey || event.metaKey) && (event.key === "+" || event.key === "=")) {
      event.preventDefault();
      this.changeZoom(0.12);
    }
    if ((event.ctrlKey || event.metaKey) && event.key === "-") {
      event.preventDefault();
      this.changeZoom(-0.12);
    }
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
    if (!window.Tone) return;
    this.master = new Tone.Volume(-4).toDestination();
    this.channels.forEach(channel => this.ensureSynth(channel));
    Tone.Transport.bpm.value = this.bpm;
  }

  async unlockAudio() {
    if (!window.Tone || this.audioReady) return;
    try {
      await Tone.start();
      this.audioReady = true;
    } catch (error) {
      console.warn("Tone start error:", error);
    }
  }

  ensureSynth(channel) {
    if (!window.Tone || !channel) return null;
    this.normalizeChannel(channel);
    if (this.synths[channel.id]) return this.synths[channel.id];
    let synth;
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
    this.startAudioClips();
  }

  pause() {
    this.isPlaying = false;
    this.stopClock();
    this.stopStepPlayback();
    this.stopAudioPlayers();
    this.updateTransportButtons();
  }

  stop() {
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
    if (!play) return;
    play.classList.toggle("is-playing", this.isPlaying);
    play.textContent = this.isPlaying ? this.t("pause", "Pause") : this.t("play", "Play");
  }

  startClock() {
    this.stopClock();
    this.clockTimer = setInterval(() => {
      this.currentTime += 0.05;
      this.updateTimeDisplay();
      this.updatePlayhead();
    }, 50);
  }

  stopClock() {
    if (this.clockTimer) clearInterval(this.clockTimer);
    this.clockTimer = null;
  }

  startStepPlayback() {
    this.stopStepPlayback();
    this.stepTimer = setInterval(() => {
      this.playArrangementTick(this.playTick);
      this.playTick += 1;
    }, this.tickSeconds() * 1000);
  }

  stopStepPlayback() {
    if (this.stepTimer) clearInterval(this.stepTimer);
    this.stepTimer = null;
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
    this.container.querySelectorAll(`[data-step-index="${stepIndex}"]`).forEach(pad => pad.classList.add("playing"));
    const hasSolo = this.channels.some(channel => channel.solo);
    this.channels.forEach(channel => {
      if (channel.muted || (hasSolo && !channel.solo)) return;
      if (this.getPatternSteps(pattern, channel.id)[stepIndex]) this.triggerChannel(channel, this.getStepVelocity(pattern, channel.id, stepIndex));
    });
    (pattern.notes || []).forEach(note => {
      const noteTick = this.beatsToTicks(note.x / this.cellWidth) % this.patternStepCount(pattern);
      if (noteTick !== stepIndex) return;
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
      const delay = Math.max(0, this.pixelsToSeconds(clip.x) - this.currentTime);
      const audio = new Audio(asset.url);
      const baseVolume = this.clamp(Number(clip.volume ?? 85), 0, 120) / 100;
      const trimStart = Math.max(0, Number(clip.trimStart || 0));
      const trimEnd = Math.max(0, Number(clip.trimEnd || 0));
      const clipDuration = Math.max(0.05, this.pixelsToSeconds(clip.width) - trimEnd);
      audio.volume = Math.min(1, baseVolume);
      audio.currentTime = trimStart;
      const timeout = setTimeout(() => {
        if (!this.isPlaying) return;
        audio.currentTime = trimStart;
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

  beatsToTicks(beats) {
    return Math.round((Number(beats) || 0) * 4);
  }

  renderAll() {
    this.channels.forEach(channel => this.normalizeChannel(channel));
    this.patterns.forEach(pattern => this.normalizePattern(pattern));
    this.applyZoom();
    this.generateRuler();
    this.generatePianoKeys();
    this.renderPlaylist();
    this.renderNotes();
    this.renderChannels();
    this.renderStepSequencer();
    this.renderMixer();
    this.renderAssets();
    this.updateTimeDisplay();
    this.updatePlayhead();
    this.updateActivePatternLabel();
    this.updatePatternControls();
    if (this.elements.bpmInput) this.elements.bpmInput.value = this.bpm;
    if (this.elements.projectName) this.elements.projectName.value = this.projectTitle;
  }

  changeZoom(delta) {
    const oldWidth = this.cellWidth;
    this.zoom = this.clamp(Number((this.zoom + delta).toFixed(2)), 0.62, 1.9);
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
    if (this.elements.zoomLevel) this.elements.zoomLevel.textContent = `${Math.round(this.zoom * 100)}%`;
  }

  generateRuler() {
    if (!this.elements.ruler) return;
    this.elements.ruler.innerHTML = "";
    for (let i = 1; i <= this.timelineBars; i++) {
      const span = document.createElement("span");
      span.textContent = i;
      this.elements.ruler.appendChild(span);
    }
  }

  generatePianoKeys() {
    if (!this.elements.pianoKeys) return;
    this.elements.pianoKeys.innerHTML = "";
    const notes = ["C", "B", "A#", "A", "G#", "G", "F#", "F", "E", "D#", "D", "C#"];
    for (let octave = 7; octave >= 1; octave--) {
      notes.forEach(name => {
        const note = `${name}${octave}`;
        const key = document.createElement("div");
        key.className = `cx-piano-key ${name.includes("#") ? "black-key" : "white-key"} ${name === "C" ? "c-note" : ""}`;
        key.dataset.note = note;
        key.textContent = note;
        key.addEventListener("click", () => this.playNote(note));
        this.elements.pianoKeys.appendChild(key);
      });
    }
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
    this.container.querySelectorAll("[data-view]").forEach(item => item.classList.remove("active"));
    this.container.querySelectorAll(`[data-view="${viewName}"]`).forEach(item => item.classList.add("active"));
    button?.classList.add("active");
    this.container.querySelectorAll("[data-editor-view]").forEach(view => view.classList.remove("active"));
    this.container.querySelector(`[data-editor-view="${viewName}"]`)?.classList.add("active");
    if (viewName === "piano-roll") {
      this.renderNotes();
      this.updateActivePatternLabel();
    }
  }

  setTool(tool, button) {
    this.tool = tool;
    this.container.querySelectorAll("[data-tool]").forEach(item => item.classList.remove("active"));
    button?.classList.add("active");
  }

  setArrangeTool(tool, button) {
    this.arrangeTool = tool;
    this.container.querySelectorAll("[data-arrange-tool]").forEach(item => item.classList.remove("active"));
    button?.classList.add("active");
    if (this.elements.playlistGrid) this.elements.playlistGrid.dataset.arrangeTool = tool;
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
  }

  handlePianoRollClick(event) {
    const pattern = this.getActivePattern();
    if (!pattern || !this.elements.pianoRoll || event.target.closest(".cx-note")) return;
    if (this.tool === "select") return;
    const point = this.relativePoint(event, this.elements.pianoRoll);
    const row = Math.floor(point.y / this.rowHeight);
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
    const note = { id: this.uuid(), channelId: this.selectedChannelId, note: noteName, row, x: snappedX, y: row * this.rowHeight, width: this.cellWidth * this.noteLengthBeats, velocity: 85 };
    pattern.notes.push(note);
    this.renderNotes();
    this.selectNote(note.id);
    this.playNote(noteName);
    this.saveHistory();
  }

  renderNotes() {
    if (!this.elements.noteLayer) return;
    const pattern = this.getActivePattern();
    this.elements.noteLayer.innerHTML = "";
    if (!pattern) return;
    (pattern.notes || []).forEach(note => {
      const channel = this.channels.find(item => item.id === note.channelId);
      const el = document.createElement("div");
      el.className = `cx-note ${note.id === this.selectedNoteId ? "selected" : ""}`;
      el.dataset.noteId = note.id;
      el.style.left = `${note.x}px`;
      el.style.top = `${note.y}px`;
      el.style.width = `${note.width || this.cellWidth}px`;
      el.style.setProperty("--note-color", channel?.color || "#ff7a18");
      el.textContent = note.note;
      el.addEventListener("click", event => {
        event.stopPropagation();
        this.selectNote(note.id);
      });
      el.addEventListener("dblclick", event => {
        event.stopPropagation();
        pattern.notes = pattern.notes.filter(item => item.id !== note.id);
        this.selectedNoteId = null;
        this.renderNotes();
        this.updateInspectorDefault();
        this.saveHistory();
      });
      el.addEventListener("mousedown", event => this.startNoteDrag(event, note.id));
      const handle = document.createElement("span");
      handle.className = "cx-note-resize";
      handle.addEventListener("mousedown", event => this.startNoteResize(event, note.id));
      el.appendChild(handle);
      this.elements.noteLayer.appendChild(el);
    });
  }

  startNoteDrag(event, noteId) {
    if (event.button !== 0 || event.target.closest(".cx-note-resize")) return;
    const pattern = this.getActivePattern();
    const note = pattern?.notes.find(item => item.id === noteId);
    if (!note) return;
    this.selectNote(noteId);
    const startX = event.clientX;
    const startY = event.clientY;
    const originX = note.x;
    const originY = note.y;
    const onMove = moveEvent => {
      note.x = Math.max(0, this.snapX(originX + moveEvent.clientX - startX));
      const row = this.clamp(Math.floor((originY + moveEvent.clientY - startY) / this.rowHeight), 0, this.elements.pianoKeys.children.length - 1);
      note.row = row;
      note.y = row * this.rowHeight;
      note.note = this.noteFromRow(row) || note.note;
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
      el.className = `${clip.type === "audio" ? "cx-audio-clip" : "cx-pattern-clip"} ${clip.id === this.selectedClipId ? "cx-clip-selected" : ""}`;
      el.classList.toggle("is-muted", Boolean(clip.muted));
      el.dataset.clipId = clip.id;
      el.style.left = `${clip.x}px`;
      el.style.width = `${clip.width}px`;
      el.style.setProperty("--clip-color", this.clipColor(clip));
      el.innerHTML = this.clipMarkup(clip);
      el.addEventListener("click", event => {
        event.stopPropagation();
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
      const handle = document.createElement("span");
      handle.className = "cx-clip-resize";
      handle.addEventListener("mousedown", event => this.startClipResize(event, clip.id));
      el.appendChild(handle);
      lane.appendChild(el);
    });
  }

  clipMarkup(clip) {
    const title = this.escapeHtml(clip.name || "Clip");
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
    return `
      <span class="cx-clip-title">${title}</span>
      <span class="cx-pattern-mini">${this.patternMiniBars(pattern)}</span>
      <span class="cx-clip-badge">${noteCount + activeSteps}</span>
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
    if (event.target.closest(".cx-pattern-clip, .cx-audio-clip")) return;
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

  patternMiniBars(pattern) {
    const stepCount = this.patternStepCount(pattern);
    const previewCount = 16;
    const ticks = Array.from({ length: previewCount }, () => 0);
    Object.values(pattern?.stepsByChannel || {}).forEach(steps => {
      steps.forEach((active, index) => {
        if (active) ticks[Math.floor(index / stepCount * previewCount)] += 1;
      });
    });
    (pattern?.notes || []).forEach(note => {
      ticks[Math.floor((this.beatsToTicks(note.x / this.cellWidth) % stepCount) / stepCount * previewCount)] += 1;
    });
    return ticks.map(count => `<i style="height:${Math.min(90, 18 + count * 18)}%"></i>`).join("");
  }

  createPatternClipFromLane(event, lane) {
    if (event.target.closest(".cx-pattern-clip, .cx-audio-clip")) return;
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
    const lane = event.target.closest("[data-track-lane]");
    if (lane) this.handleLaneDrop(event, lane);
  }

  handleLaneDrop(event, lane) {
    event.preventDefault();
    const assetId = event.dataTransfer?.getData("text/cx-asset-id");
    if (!assetId) return;
    const point = this.relativePoint(event, lane);
    this.addAudioClipFromAsset(assetId, Number(lane.dataset.trackLane || 0), this.snapX(point.x));
  }

  addAudioClipFromAsset(assetId, track = 1, x = this.cellWidth) {
    const asset = this.assets.find(item => String(item.id) === String(assetId) || String(item.serverId) === String(assetId));
    if (!asset) return;
    const clip = {
      id: this.uuid(),
      type: "audio",
      name: asset.name,
      track: this.clamp(track, 0, this.tracks - 1),
      x,
      width: this.cellWidth * 8,
      assetId: asset.serverId || asset.id,
      volume: 85,
      fadeIn: 0,
      fadeOut: 0,
      trimStart: 0,
      trimEnd: 0
    };
    this.clips.push(clip);
    this.renderPlaylist();
    this.selectClip(clip.id);
    this.saveHistory();
  }

  showLaneContextMenu(event, lane) {
    if (event.target.closest(".cx-pattern-clip, .cx-audio-clip")) return;
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
      button.textContent = item.label;
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
    if (event.button !== 0 || event.target.closest(".cx-clip-resize")) return;
    if (["slice", "mute", "fade", "automation"].includes(this.arrangeTool)) return;
    const clip = this.clips.find(item => item.id === clipId);
    if (!clip) return;
    this.selectClip(clipId);
    const startX = event.clientX;
    const startY = event.clientY;
    const originX = clip.x;
    const originTrack = clip.track;
    const onMove = moveEvent => {
      clip.x = Math.max(0, this.snapX(originX + moveEvent.clientX - startX));
      clip.track = this.clamp(originTrack + Math.round((moveEvent.clientY - startY) / 84), 0, this.tracks - 1);
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
    this.selectedNoteId = noteId;
    this.selectedClipId = null;
    this.renderNotes();
    const note = this.getActivePattern()?.notes.find(item => item.id === noteId);
    if (note) this.showNoteInspector(note);
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
      const el = document.createElement("div");
      el.className = `cx-mixer-channel ${channel.id === this.selectedChannelId ? "selected" : ""}`;
      el.style.setProperty("--channel-color", channel.color);
      el.dataset.channelId = channel.id;
      el.innerHTML = `
        <div class="cx-mixer-title"><span></span>${this.escapeHtml(channel.name)}</div>
        <div class="cx-mixer-preset">${this.escapeHtml(channel.preset)}</div>
        <div class="cx-meter-group">
          <div class="cx-meter-bar left" style="--level:${Math.max(8, channel.volume * 0.8)}%"></div>
          <div class="cx-meter-bar right" style="--level:${Math.max(8, channel.volume * 0.7)}%"></div>
        </div>
        <div class="cx-mixer-fx">
          <label>HP <input data-fx="highpass" type="range" min="20" max="8000" value="${channel.fx.highpass}"></label>
          <label>LP <input data-fx="lowpass" type="range" min="200" max="20000" value="${channel.fx.lowpass}"></label>
          <label>Rev <input data-send="reverb" type="range" min="0" max="100" value="${channel.send.reverb}"></label>
          <label>Dly <input data-send="delay" type="range" min="0" max="100" value="${channel.send.delay}"></label>
        </div>
        <div class="cx-fader-container"><input class="cx-fader" type="range" min="0" max="100" value="${channel.volume}"></div>
        <div class="cx-fader-value">${channel.volume}%</div>
        <div class="cx-mixer-controls">
          <button type="button" data-mute class="${channel.muted ? "active" : ""}">M</button>
          <button type="button" data-solo class="${channel.solo ? "solo-active" : ""}">S</button>
        </div>
        <div class="cx-pan-container"><label>L</label><input class="cx-pan" type="range" min="-100" max="100" value="${channel.pan}"><label>R</label></div>
      `;
      el.querySelector(".cx-fader")?.addEventListener("input", event => {
        channel.volume = Number(event.target.value);
        if (pack?.volume) pack.volume.volume.value = this.volumeToDb(channel.volume);
        el.querySelectorAll(".cx-meter-bar").forEach(bar => bar.style.setProperty("--level", `${Math.max(8, channel.volume * 0.8)}%`));
        const value = el.querySelector(".cx-fader-value");
        if (value) value.textContent = `${channel.volume}%`;
      });
      el.querySelector(".cx-fader")?.addEventListener("change", () => this.saveHistory());
      el.querySelector(".cx-pan")?.addEventListener("input", event => {
        channel.pan = Number(event.target.value);
        if (pack?.pan) pack.pan.pan.value = channel.pan / 100;
      });
      el.querySelector(".cx-pan")?.addEventListener("change", () => this.saveHistory());
      el.querySelectorAll("[data-fx]").forEach(input => {
        input.addEventListener("input", event => {
          const key = event.target.dataset.fx;
          channel.fx[key] = Number(event.target.value);
          this.applyChannelFx(channel);
        });
        input.addEventListener("change", () => this.saveHistory());
      });
      el.querySelectorAll("[data-send]").forEach(input => {
        input.addEventListener("input", event => {
          const key = event.target.dataset.send;
          channel.send[key] = Number(event.target.value);
          this.applyChannelFx(channel);
        });
        input.addEventListener("change", () => this.saveHistory());
      });
      el.querySelector("[data-mute]")?.addEventListener("click", event => {
        event.stopPropagation();
        channel.muted = !channel.muted;
        this.renderMixer();
        this.renderChannels();
        this.saveHistory();
      });
      el.querySelector("[data-solo]")?.addEventListener("click", event => {
        event.stopPropagation();
        channel.solo = !channel.solo;
        this.renderMixer();
        this.saveHistory();
      });
      el.addEventListener("click", () => {
        this.selectedChannelId = channel.id;
        this.renderChannels();
        this.renderMixer();
        this.showChannelInspector(channel);
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
    const file = event.target.files?.[0];
    if (!file) return;
    const asset = { id: this.uuid(), serverId: null, name: file.name, size: file.size, type: file.type, url: URL.createObjectURL(file), uploaded: false };
    this.assets.push(asset);
    this.clips.push({ id: this.uuid(), type: "audio", name: file.name, track: 1, x: this.cellWidth, width: this.cellWidth * 6, assetId: asset.id, volume: 85, fadeIn: 0, fadeOut: 0, trimStart: 0, trimEnd: 0, muted: false });
    this.renderAssets();
    this.renderPlaylist();
    this.saveHistory();
    await this.uploadAssetToServer(file, asset);
    event.target.value = "";
  }

  async uploadAssetToServer(file, asset) {
    if (!this.projectId) {
      this.toast(this.t("save_first_audio_local", "Save the project first; this audio is local for now."), "info");
      return;
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
      asset.uploaded = true;
      asset.serverId = data.asset?.id || null;
      asset.url = data.asset?.preview_url || asset.url;
      this.renderAssets();
      this.toast(this.t("audio_uploaded", "Audio uploaded"), "success");
    } catch (error) {
      console.warn(error);
      this.toast(this.t("audio_local_upload_error", "Audio stayed local. Upload API error."), "error");
    }
  }

  renderAssets() {
    if (!this.elements.assetList) return;
    this.elements.assetList.innerHTML = "";
    if (!this.assets.length) {
      this.elements.assetList.innerHTML = `<p>${this.escapeHtml(this.t("no_audio_uploaded", "No audio uploaded yet"))}</p>`;
      return;
    }
    this.assets.forEach(asset => {
      const item = document.createElement("div");
      item.className = "cx-asset-item";
      item.draggable = true;
      item.dataset.assetId = asset.serverId || asset.id;
      item.innerHTML = `
        <div class="cx-asset-icon"><span></span></div>
        <div class="cx-asset-copy">
          <div class="cx-asset-title">${this.escapeHtml(asset.name)}</div>
          <div class="cx-asset-meta">${this.formatBytes(asset.size)} - ${asset.uploaded ? this.escapeHtml(this.t("uploaded", "uploaded")) : this.escapeHtml(this.t("local", "local"))}</div>
        </div>
        <div class="cx-asset-actions">
          <button type="button" class="cx-asset-add" title="${this.escapeHtml(this.t("add_to_playlist", "Add to playlist"))}">+</button>
          <button type="button" class="cx-asset-preview" title="${this.escapeHtml(this.t("preview", "Preview"))}">${this.escapeHtml(this.t("play", "Play"))}</button>
        </div>
      `;
      item.addEventListener("dragstart", event => {
        event.dataTransfer?.setData("text/cx-asset-id", String(asset.serverId || asset.id));
        event.dataTransfer?.setData("text/plain", String(asset.serverId || asset.id));
      });
      item.addEventListener("dblclick", () => {
        this.addAudioClipFromAsset(asset.serverId || asset.id, 1, this.cellWidth);
      });
      item.querySelector(".cx-asset-add")?.addEventListener("click", event => {
        event.stopPropagation();
        this.addAudioClipFromAsset(asset.serverId || asset.id, 1, this.cellWidth);
      });
      item.querySelector(".cx-asset-preview")?.addEventListener("click", event => {
        event.stopPropagation();
        new Audio(asset.url).play().catch(() => {});
      });
      this.elements.assetList.appendChild(item);
    });
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
    (pattern.notes || []).forEach(note => {
      note.x = this.snapX(note.x || 0);
      note.y = Number(note.row || 0) * this.rowHeight;
      note.width = Math.max(this.cellWidth / 2, this.snapX(note.width || this.cellWidth) || this.cellWidth / 2);
    });
    this.renderNotes();
    this.renderPlaylist();
    this.saveHistory();
    this.toast(this.t("notes_quantized", "Notes quantized"), "success");
  }

  moveSelectedNotesOctave(deltaRows) {
    const pattern = this.getActivePattern();
    if (!pattern) return;
    const notes = this.selectedNoteId ? pattern.notes.filter(note => note.id === this.selectedNoteId) : pattern.notes;
    const maxRow = Math.max(0, (this.elements.pianoKeys?.children.length || 1) - 1);
    notes.forEach(note => {
      note.row = this.clamp(Number(note.row || 0) + deltaRows, 0, maxRow);
      note.y = note.row * this.rowHeight;
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

  showNoteInspector(note) {
    if (!this.elements.inspector) return;
    this.elements.inspector.innerHTML = `
      <div class="cx-field"><label>${this.escapeHtml(this.t("note", "Note"))}</label><input data-edit-note-name value="${this.escapeHtml(note.note)}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("velocity", "Velocity"))}</label><input type="number" min="1" max="100" data-edit-note-velocity value="${note.velocity || 85}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("length_beats", "Length beats"))}</label><input type="number" min="0.25" max="16" step="0.25" data-edit-note-width value="${((note.width || this.cellWidth) / this.cellWidth).toFixed(2)}"></div>
      <div class="cx-inspector-row"><strong>${this.escapeHtml(this.t("position", "Position"))}</strong>${this.escapeHtml(this.t("beat", "Beat"))} ${((note.x || 0) / this.cellWidth).toFixed(2)} / ${this.escapeHtml(this.t("row", "Row"))} ${note.row}</div>
    `;
    this.elements.inspector.querySelector("[data-edit-note-name]")?.addEventListener("change", event => {
      note.note = event.target.value.trim() || note.note;
      this.renderNotes();
      this.saveHistory();
    });
    this.elements.inspector.querySelector("[data-edit-note-velocity]")?.addEventListener("change", event => {
      note.velocity = this.clamp(Number(event.target.value) || 85, 1, 100);
      this.saveHistory();
    });
    this.elements.inspector.querySelector("[data-edit-note-width]")?.addEventListener("change", event => {
      note.width = Math.max(this.cellWidth / 2, (Number(event.target.value) || 1) * this.cellWidth);
      this.renderNotes();
      this.saveHistory();
    });
  }

  showChannelInspector(channel) {
    if (!this.elements.inspector) return;
    this.normalizeChannel(channel);
    this.elements.inspector.innerHTML = `
      <div class="cx-field"><label>${this.escapeHtml(this.t("project_name", "Name"))}</label><input data-edit-channel-name value="${this.escapeHtml(channel.name)}"></div>
      <div class="cx-inspector-row"><strong>${this.escapeHtml(this.t("type", "Type"))}</strong>${this.escapeHtml(channel.type)}</div>
      <div class="cx-inspector-row"><strong>${this.escapeHtml(this.t("preset", "Preset"))}</strong>${this.escapeHtml(channel.preset)}</div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("color", "Color"))}</label><input type="color" data-edit-channel-color value="${channel.color || "#ff7a18"}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("volume", "Volume"))}</label><input type="range" min="0" max="100" data-edit-channel-volume value="${channel.volume}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("pan", "Pan"))}</label><input type="range" min="-100" max="100" data-edit-channel-pan value="${channel.pan}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("highpass", "Highpass"))}</label><input type="range" min="20" max="8000" data-edit-channel-highpass value="${channel.fx.highpass}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("lowpass", "Lowpass"))}</label><input type="range" min="200" max="20000" data-edit-channel-lowpass value="${channel.fx.lowpass}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("reverb_send", "Reverb send"))}</label><input type="range" min="0" max="100" data-edit-channel-reverb value="${channel.send.reverb}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("delay_send", "Delay send"))}</label><input type="range" min="0" max="100" data-edit-channel-delay value="${channel.send.delay}"></div>
    `;
    this.elements.inspector.querySelector("[data-edit-channel-name]")?.addEventListener("input", event => {
      channel.name = event.target.value.trim() || channel.name;
      this.renderChannels();
      this.renderMixer();
      this.renderStepSequencer();
    });
    this.elements.inspector.querySelector("[data-edit-channel-name]")?.addEventListener("change", () => this.saveHistory());
    this.elements.inspector.querySelector("[data-edit-channel-color]")?.addEventListener("input", event => {
      channel.color = event.target.value;
      this.renderChannels();
      this.renderMixer();
      this.renderStepSequencer();
      this.renderPlaylist();
    });
    this.elements.inspector.querySelector("[data-edit-channel-color]")?.addEventListener("change", () => this.saveHistory());
    const bindRange = (selector, apply) => {
      const input = this.elements.inspector.querySelector(selector);
      input?.addEventListener("input", event => {
        apply(Number(event.target.value));
        this.applyChannelFx(channel);
        this.renderMixer();
        this.renderChannels();
      });
      input?.addEventListener("change", () => this.saveHistory());
    };
    bindRange("[data-edit-channel-volume]", value => { channel.volume = this.clamp(value, 0, 100); });
    bindRange("[data-edit-channel-pan]", value => { channel.pan = this.clamp(value, -100, 100); });
    bindRange("[data-edit-channel-highpass]", value => { channel.fx.highpass = this.clamp(value, 20, 8000); });
    bindRange("[data-edit-channel-lowpass]", value => { channel.fx.lowpass = this.clamp(value, 200, 20000); });
    bindRange("[data-edit-channel-reverb]", value => { channel.send.reverb = this.clamp(value, 0, 100); });
    bindRange("[data-edit-channel-delay]", value => { channel.send.delay = this.clamp(value, 0, 100); });
  }

  showClipInspector(clip) {
    if (!this.elements.inspector) return;
    const audioControls = clip.type === "audio" ? `
      <div class="cx-field"><label>${this.escapeHtml(this.t("volume", "Volume"))}</label><input type="range" min="0" max="120" data-edit-clip-volume value="${clip.volume ?? 85}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("fade_in_seconds", "Fade in seconds"))}</label><input type="number" min="0" max="12" step="0.1" data-edit-clip-fade-in value="${clip.fadeIn || 0}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("fade_out_seconds", "Fade out seconds"))}</label><input type="number" min="0" max="12" step="0.1" data-edit-clip-fade-out value="${clip.fadeOut || 0}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("trim_start_seconds", "Trim start seconds"))}</label><input type="number" min="0" max="600" step="0.1" data-edit-clip-trim-start value="${clip.trimStart || 0}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("trim_end_seconds", "Trim end seconds"))}</label><input type="number" min="0" max="600" step="0.1" data-edit-clip-trim-end value="${clip.trimEnd || 0}"></div>
    ` : "";
    this.elements.inspector.innerHTML = `
      <div class="cx-field"><label>${this.escapeHtml(this.t("clip_name", "Clip name"))}</label><input data-edit-clip-name value="${this.escapeHtml(clip.name)}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("track", "Track"))}</label><input type="number" min="1" max="${this.tracks}" data-edit-clip-track value="${clip.track + 1}"></div>
      <div class="cx-field"><label>${this.escapeHtml(this.t("length_beats", "Length beats"))}</label><input type="number" min="1" max="64" data-edit-clip-width value="${Math.round(clip.width / this.cellWidth)}"></div>
      ${audioControls}
      <div class="cx-inspector-row"><strong>${this.escapeHtml(this.t("type", "Type"))}</strong>${this.escapeHtml(clip.type)}</div>
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
    this.elements.inspector.querySelector("[data-edit-clip-track]")?.addEventListener("change", event => {
      clip.track = this.clamp(Number(event.target.value) - 1, 0, this.tracks - 1);
      this.renderPlaylist();
      this.saveHistory();
    });
    this.elements.inspector.querySelector("[data-edit-clip-width]")?.addEventListener("change", event => {
      clip.width = Math.max(this.cellWidth, (Number(event.target.value) || 4) * this.cellWidth);
      this.renderPlaylist();
      this.saveHistory();
    });
    this.elements.inspector.querySelector("[data-edit-clip-volume]")?.addEventListener("input", event => {
      clip.volume = this.clamp(Number(event.target.value) || 0, 0, 120);
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
  }

  updateInspectorDefault() {
    if (!this.elements.inspector) return;
    this.elements.inspector.innerHTML = `
      <p>${this.escapeHtml(this.t("select_item_hint", "Select a note, pattern, clip or channel."))}</p>
      <div class="cx-inspector-row">
        <strong>Hotkeys</strong>
        Space - ${this.escapeHtml(this.t("play", "Play"))} / ${this.escapeHtml(this.t("pause", "Pause"))}<br>
        Delete - ${this.escapeHtml(this.t("delete", "Delete"))}<br>
        Ctrl+S - ${this.escapeHtml(this.t("save", "Save"))}<br>
        Ctrl+D - ${this.escapeHtml(this.t("duplicate", "Duplicate"))}<br>
        Ctrl+Z - Undo<br>
        Ctrl+Shift+Z - Redo
      </div>
    `;
  }

  deleteSelected() {
    const pattern = this.getActivePattern();
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
      channels: this.channels,
      patterns: this.patterns,
      clips: this.clips,
      assets: this.assets,
      selectedPatternId: this.selectedPatternId,
      selectedChannelId: this.selectedChannelId
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
        (Array.isArray(state.assets) && state.assets.length)
      )
    );
  }

  stateWeight(state) {
    if (!state || typeof state !== "object") return 0;
    const notes = (state.patterns || []).reduce((sum, pattern) => sum + (pattern.notes || []).length + Object.values(pattern.stepsByChannel || {}).flat().filter(Boolean).length, 0);
    return (state.patterns || []).length + (state.clips || []).length * 3 + (state.assets || []).length * 2 + notes;
  }

  undo() {
    if (this.historyIndex <= 0) return;
    this.historyIndex -= 1;
    this.restoreHistory(this.history[this.historyIndex]);
    this.markDirty();
  }

  redo() {
    if (this.historyIndex >= this.history.length - 1) return;
    this.historyIndex += 1;
    this.restoreHistory(this.history[this.historyIndex]);
    this.markDirty();
  }

  restoreHistory(snapshot) {
    try {
      const state = JSON.parse(snapshot);
      this.channels = state.channels || this.channels;
      this.patterns = state.patterns || this.patterns;
      this.clips = state.clips || this.clips;
      this.assets = state.assets || this.assets;
      this.selectedPatternId = state.selectedPatternId || this.patterns[0]?.id || null;
      this.selectedChannelId = state.selectedChannelId || this.channels[0]?.id || null;
      Object.values(this.synths).forEach(pack => {
        try { pack.synth.dispose(); } catch (_) {}
      });
      this.synths = {};
      this.channels.forEach(channel => this.ensureSynth(channel));
      this.renderAll();
    } catch (error) {
      console.warn(error);
    }
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
    if (Array.isArray(state.channels) && state.channels.length) this.channels = state.channels;
    if (Array.isArray(state.patterns) && state.patterns.length) this.patterns = state.patterns;
    if (Array.isArray(state.clips)) this.clips = state.clips;
    if (Array.isArray(state.assets)) this.assets = state.assets;
    this.noteLengthBeats = Number(state.noteLengthBeats || this.noteLengthBeats);
    if (!this.assets.length && Array.isArray(payload.assets)) {
      this.assets = payload.assets.map(asset => ({
        id: String(asset.id),
        serverId: asset.id,
        name: asset.name,
        size: asset.size,
        type: asset.media_type,
        url: asset.preview_url,
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
        y: Number(note.row || 0) * this.rowHeight,
        width: Math.max(this.baseCellWidth / 2, Math.round((note.width || this.cellWidth) * ratio))
      }))
    }));

    return {
      title: this.projectTitle,
      bpm: this.bpm,
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
    if (!this.elements.playhead) return;
    const x = this.currentTime * (this.bpm / 60) * this.cellWidth;
    this.elements.playhead.style.transform = `translateX(${x}px)`;
  }

  syncTimelineScroll() {
    if (this.elements.ruler && this.elements.playlistGrid) this.elements.ruler.style.transform = `translateX(${-this.elements.playlistGrid.scrollLeft}px)`;
  }

  syncPianoScroll() {
    if (this.elements.pianoKeys && this.elements.pianoRoll) this.elements.pianoKeys.scrollTop = this.elements.pianoRoll.scrollTop;
  }

  snapX(x) {
    const snap = this.elements.snap?.value || "1/8";
    const multiplier = snap === "1/4" ? 1 : snap === "1/16" ? 0.25 : 0.5;
    const grid = this.cellWidth * multiplier;
    return Math.round(x / grid) * grid;
  }

  noteFromRow(row) {
    return this.elements.pianoKeys?.children[row]?.dataset?.note || null;
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
