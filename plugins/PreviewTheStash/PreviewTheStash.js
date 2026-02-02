/* PreviewTheStash — visual crop overlay + tag preview generator */
(function () {
  "use strict";

  var PLUGIN_ID = "PreviewTheStash";
  var BUTTON_ID = "pts-tag-btn";
  var PREVIEW_DURATION = 5.4;

  // State
  var state = {
    active: false,     // crop overlay visible
    picking: false,    // tag pick mode
    dragging: false,
    resizing: false,
    dragStart: null,
    cropStart: null,
  };

  // Crop parameters (in video-relative coordinates 0..1)
  var crop = { x: 0.25, y: 0.25, size: 0.5 };

  // Loop playback state
  var loopStart = 0;
  var loopEnd = 0;
  var loopHandler = null;

  // DOM refs
  var overlayContainer = null;
  var cropEl = null;
  var videoEl = null;
  var videoWrapper = null;

  // ------- Utilities -------

  function getVideoRect() {
    // Get the actual rendered video area within the video element
    // (accounting for letterboxing/pillarboxing)
    var el = videoEl;
    var elW = el.clientWidth;
    var elH = el.clientHeight;
    var vidW = el.videoWidth;
    var vidH = el.videoHeight;
    if (!vidW || !vidH) return { x: 0, y: 0, w: elW, h: elH };

    var elAspect = elW / elH;
    var vidAspect = vidW / vidH;
    var w, h, x, y;
    if (vidAspect > elAspect) {
      // Pillarboxing (video wider than container) — actually letterboxing bars top/bottom
      w = elW;
      h = elW / vidAspect;
      x = 0;
      y = (elH - h) / 2;
    } else {
      // Letterboxing (video taller) — bars on sides
      h = elH;
      w = elH * vidAspect;
      x = (elW - w) / 2;
      y = 0;
    }
    return { x: x, y: y, w: w, h: h };
  }

  function cropToAnchorZoom() {
    // Convert crop rect (x, y, size in 0..1 of video) to anchor-x, anchor-y, zoom
    var videoAspect = videoEl.videoWidth / videoEl.videoHeight;
    // The ffmpeg crop uses min(iw,ih)/zoom as the crop size
    // In normalized coords: if video is wider than tall (aspect > 1),
    //   the "min" dimension is height (=1.0 in normalized h),
    //   so crop fraction = 1.0/zoom, and zoom = 1.0/size (when size is fraction of height)
    // For simplicity, we express size as fraction of the shorter dimension.
    var isWide = videoAspect >= 1;
    var sizeInShort;
    if (isWide) {
      // crop.size is fraction of video height (the short side)
      sizeInShort = crop.size;
    } else {
      // crop.size is fraction of video width (the short side)
      sizeInShort = crop.size;
    }
    var zoom = 1.0 / sizeInShort;

    // anchor_x = crop.x / (1 - sizeInVideo_w)
    // The ffmpeg formula: x_offset = (iw - cropSize) * anchor_x
    // In normalized width coords: x_offset_norm = crop.x
    // cropSize in width-normalized coords:
    var cropW, cropH;
    if (isWide) {
      cropH = 1.0 / zoom;        // fraction of video height
      cropW = cropH / videoAspect; // fraction of video width (since crop is square)
    } else {
      cropW = 1.0 / zoom;        // fraction of video width
      cropH = cropW * videoAspect; // fraction of video height
    }

    var ax = (1 - cropW) > 0.001 ? crop.x / (1 - cropW) : 0.5;
    var ay = (1 - cropH) > 0.001 ? crop.y / (1 - cropH) : 0.5;
    ax = Math.max(0, Math.min(1, ax));
    ay = Math.max(0, Math.min(1, ay));

    return { anchor_x: ax, anchor_y: ay, zoom: zoom };
  }

  function updateHud() {}

  // ------- Crop overlay rendering -------

  function renderCrop() {
    if (!cropEl || !videoEl) return;
    var vr = getVideoRect();
    // Clip overlay to actual video rect (exclude letterbox/pillarbox)
    overlayContainer.style.clipPath =
      "inset(" + vr.y + "px " + (videoEl.clientWidth - vr.x - vr.w) + "px " +
      (videoEl.clientHeight - vr.y - vr.h) + "px " + vr.x + "px)";
    // crop coords are fraction of video area
    var left = vr.x + crop.x * vr.w;
    var top = vr.y + crop.y * vr.h;
    // crop.size is fraction of video height (shorter dim for wide video)
    var sizePx = crop.size * vr.h;

    cropEl.style.left = left + "px";
    cropEl.style.top = top + "px";
    cropEl.style.width = sizePx + "px";
    cropEl.style.height = sizePx + "px";
    updateHud();
  }

  function clampCrop() {
    // Ensure crop stays within video bounds
    var vr = getVideoRect();
    var maxSizeH = vr.h; // max size is full video height
    var maxSizeW = vr.w; // but also can't exceed width
    var maxSizePx = Math.min(maxSizeH, maxSizeW);
    var sizePx = crop.size * vr.h;
    if (sizePx > maxSizePx) {
      crop.size = maxSizePx / vr.h;
      sizePx = maxSizePx;
    }
    if (sizePx < 20) {
      crop.size = 20 / vr.h;
      sizePx = 20;
    }
    // Clamp position
    var maxX = (vr.w - sizePx) / vr.w;
    var maxY = (vr.h - sizePx) / vr.h;
    crop.x = Math.max(0, Math.min(maxX, crop.x));
    crop.y = Math.max(0, Math.min(maxY, crop.y));
  }

  // ------- Create overlay DOM -------

  function createOverlay() {
    if (overlayContainer) return;
    // Select the main player video (inside .video-js), not wall preview videos
    videoWrapper = document.querySelector(".video-js");
    if (!videoWrapper) return;
    videoEl = videoWrapper.querySelector("video");
    if (!videoEl) return;
    if (getComputedStyle(videoWrapper).position === "static") {
      videoWrapper.style.position = "relative";
    }

    overlayContainer = document.createElement("div");
    overlayContainer.className = "pts-overlay-container";

    cropEl = document.createElement("div");
    cropEl.className = "pts-crop";

    var handles = ["nw", "n", "ne", "e", "se", "s", "sw", "w"];
    handles.forEach(function (dir) {
      var h = document.createElement("div");
      h.className = "pts-crop-handle pts-handle-" + dir;
      h.dataset.dir = dir;
      cropEl.appendChild(h);
    });

    overlayContainer.appendChild(cropEl);
    videoWrapper.appendChild(overlayContainer);

    // Wait for both video metadata and layout before initializing crop
    function tryInit() {
      if (videoEl.videoWidth > 0 && videoEl.clientWidth > 0) {
        initCropDefaults();
        return true;
      }
      return false;
    }
    if (!tryInit()) {
      var pollId = setInterval(function () {
        if (tryInit()) clearInterval(pollId);
      }, 100);
      // Give up after 10s
      setTimeout(function () { clearInterval(pollId); }, 10000);
    }

    // --- Pointer helpers (mouse + touch) ---
    function pointerXY(e) {
      if (e.touches && e.touches.length) return { x: e.touches[0].clientX, y: e.touches[0].clientY };
      return { x: e.clientX, y: e.clientY };
    }

    // --- Drag handling ---
    function onDragStart(e) {
      if (e.target.classList.contains("pts-crop-handle")) return;
      e.preventDefault();
      e.stopPropagation();
      var p = pointerXY(e);
      state.dragging = true;
      state.dragStart = { mx: p.x, my: p.y };
      state.cropStart = { x: crop.x, y: crop.y };
    }
    cropEl.addEventListener("mousedown", onDragStart);
    cropEl.addEventListener("touchstart", onDragStart, { passive: false });

    // --- Resize handling ---
    function onResizeStart(e) {
      if (!e.target.classList.contains("pts-crop-handle")) return;
      e.preventDefault();
      e.stopPropagation();
      var p = pointerXY(e);
      state.resizing = e.target.dataset.dir;
      state.dragStart = { mx: p.x, my: p.y };
      state.cropStart = { x: crop.x, y: crop.y, size: crop.size };
    }
    cropEl.addEventListener("mousedown", onResizeStart);
    cropEl.addEventListener("touchstart", onResizeStart, { passive: false });

    document.addEventListener("mousemove", onPointerMove);
    document.addEventListener("mouseup", onPointerUp);
    document.addEventListener("touchmove", onPointerMove, { passive: false });
    document.addEventListener("touchend", onPointerUp);

    // Prevent browser scroll/zoom while interacting with crop
    overlayContainer.style.touchAction = "none";
  }

  function initCropDefaults() {
    if (!videoEl) return;
    if (!videoEl.videoWidth || !videoEl.videoHeight) {
      console.warn("PreviewTheStash: video dimensions not available yet");
      return;
    }
    var vr = getVideoRect();
    if (vr.h < 1 || vr.w < 1) return;
    // Default: full-height 1:1 crop, centered horizontally (anchor-x = 0.5)
    crop.size = 1.0;
    var sizePx = crop.size * vr.h;
    crop.x = (vr.w - sizePx) / 2 / vr.w;
    crop.y = 0;
    clampCrop();
    renderCrop();
  }

  function clampMouseToVideoRect(clientX, clientY) {
    var vr = getVideoRect();
    var rect = videoEl.getBoundingClientRect();
    var minX = rect.left + vr.x;
    var maxX = minX + vr.w;
    var minY = rect.top + vr.y;
    var maxY = minY + vr.h;
    return {
      x: Math.max(minX, Math.min(maxX, clientX)),
      y: Math.max(minY, Math.min(maxY, clientY)),
    };
  }

  function onPointerMove(e) {
    if (!state.dragging && !state.resizing) return;
    if (e.touches) e.preventDefault();
    var vr = getVideoRect();
    var p = (e.touches && e.touches.length) ? { x: e.touches[0].clientX, y: e.touches[0].clientY } : { x: e.clientX, y: e.clientY };
    var clamped = clampMouseToVideoRect(p.x, p.y);

    if (state.dragging) {
      var dx = (clamped.x - state.dragStart.mx) / vr.w;
      var dy = (clamped.y - state.dragStart.my) / vr.h;
      crop.x = state.cropStart.x + dx;
      crop.y = state.cropStart.y + dy;
      clampCrop();
      renderCrop();
    }

    if (state.resizing) {
      var dir = state.resizing;
      var dx = (clamped.x - state.dragStart.mx) / vr.h;
      var dy = (clamped.y - state.dragStart.my) / vr.h;
      var dd = 0;
      // For square crop: pick the dominant axis delta based on handle direction
      if (dir === "se") dd = Math.max(dx, dy);
      else if (dir === "nw") dd = Math.min(-dx, -dy);
      else if (dir === "ne") dd = Math.max(dx, -dy);
      else if (dir === "sw") dd = Math.max(-dx, dy);
      else if (dir === "e") dd = dx;
      else if (dir === "w") dd = -dx;
      else if (dir === "s") dd = dy;
      else if (dir === "n") dd = -dy;

      var newSize = state.cropStart.size + dd;
      crop.size = newSize;
      clampCrop();
      // Anchor the opposite edge: compute position from the clamped size
      var ds = crop.size - state.cropStart.size;
      if (dir === "nw" || dir === "n" || dir === "ne") {
        crop.y = state.cropStart.y - ds;
      } else {
        crop.y = state.cropStart.y;
      }
      if (dir === "nw" || dir === "w" || dir === "sw") {
        crop.x = state.cropStart.x - ds * (vr.h / vr.w);
      } else {
        crop.x = state.cropStart.x;
      }
      clampCrop();
      renderCrop();
    }
  }

  function onPointerUp() {
    state.dragging = false;
    state.resizing = false;
  }

  function destroyOverlay() {
    if (overlayContainer) {
      overlayContainer.remove();
      overlayContainer = null;
      cropEl = null;
    }
    document.removeEventListener("mousemove", onPointerMove);
    document.removeEventListener("mouseup", onPointerUp);
    document.removeEventListener("touchmove", onPointerMove);
    document.removeEventListener("touchend", onPointerUp);
  }

  // ------- Preview loop playback -------

  function startLoop() {
    if (!videoEl) return;
    loopStart = videoEl.currentTime;
    loopEnd = loopStart + PREVIEW_DURATION;
    loopHandler = function () {
      if (videoEl.currentTime >= loopEnd || videoEl.currentTime < loopStart) {
        videoEl.currentTime = loopStart;
      }
    };
    videoEl.addEventListener("timeupdate", loopHandler);
    videoEl.play();
  }

  function stopLoop() {
    if (!videoEl || !loopHandler) return;
    videoEl.removeEventListener("timeupdate", loopHandler);
    loopHandler = null;
    videoEl.pause();
  }

  // ------- Button state helper -------

  function setBtnState(btn, label, color) {
    btn.textContent = label;
    btn.style.color = color || "";
  }

  // ------- Floating toolbar -------

  var toolbarEl = null;
  var toolbarStatusEl = null;

  function createToolbar() {
    if (toolbarEl) return;
    // Insert toolbar after the video player container
    var playerContainer = document.querySelector(".video-js");
    if (!playerContainer) return;
    var insertAfter = playerContainer.parentElement;

    toolbarEl = document.createElement("div");
    toolbarEl.className = "pts-toolbar";

    // Time nudge buttons
    var timeGroup = document.createElement("div");
    timeGroup.className = "pts-toolbar-group";
    var nudges = [
      { label: "−1s", delta: -1 },
      { label: "−.1s", delta: -0.1 },
      { label: "+.1s", delta: 0.1 },
      { label: "+1s", delta: 1 },
    ];
    nudges.forEach(function (n) {
      var b = document.createElement("button");
      b.className = "pts-toolbar-btn";
      b.textContent = n.label;
      b.addEventListener("click", function () { nudgeTime(n.delta); });
      timeGroup.appendChild(b);
    });

    // Status text
    toolbarStatusEl = document.createElement("div");
    toolbarStatusEl.className = "pts-toolbar-status";
    toolbarStatusEl.textContent = "Drag to position, resize corners to crop";

    // Action buttons
    var actionGroup = document.createElement("div");
    actionGroup.className = "pts-toolbar-group";

    var cancelBtn = document.createElement("button");
    cancelBtn.className = "pts-toolbar-btn pts-toolbar-cancel";
    cancelBtn.textContent = "Cancel";
    cancelBtn.addEventListener("click", function () {
      var btn = document.getElementById(BUTTON_ID);
      if (btn) deactivate(btn);
    });

    var confirmBtn = document.createElement("button");
    confirmBtn.className = "pts-toolbar-btn pts-toolbar-confirm";
    confirmBtn.id = "pts-confirm-btn";
    confirmBtn.textContent = "Confirm Crop";
    confirmBtn.addEventListener("click", function () {
      var btn = document.getElementById(BUTTON_ID);
      if (btn) onTagButtonClick();
    });

    actionGroup.appendChild(cancelBtn);
    actionGroup.appendChild(confirmBtn);

    toolbarEl.appendChild(timeGroup);
    toolbarEl.appendChild(toolbarStatusEl);
    toolbarEl.appendChild(actionGroup);

    insertAfter.insertBefore(toolbarEl, playerContainer.nextSibling);
  }

  function showToolbar(mode) {
    createToolbar();
    if (!toolbarEl) return;
    toolbarEl.style.display = "flex";
    var confirmBtn = document.getElementById("pts-confirm-btn");
    if (mode === "crop") {
      toolbarStatusEl.textContent = "Drag to position, resize corners to crop";
      if (confirmBtn) { confirmBtn.textContent = "Confirm Crop"; confirmBtn.style.display = ""; }
    } else if (mode === "pick") {
      toolbarStatusEl.textContent = "Tap a tag below to set its preview";
      if (confirmBtn) confirmBtn.style.display = "none";
    }
  }

  function hideToolbar() {
    if (toolbarEl) toolbarEl.style.display = "none";
  }

  function destroyToolbar() {
    if (toolbarEl) { toolbarEl.remove(); toolbarEl = null; toolbarStatusEl = null; }
  }

  function nudgeTime(delta) {
    if (!videoEl) return;
    loopStart = Math.max(0, loopStart + delta);
    loopEnd = loopStart + PREVIEW_DURATION;
    videoEl.currentTime = loopStart;
  }

  // ------- State machine -------

  function activateCropMode(btn) {
    videoEl = document.querySelector("video");
    if (!videoEl) return;
    createOverlay();
    overlayContainer.classList.add("pts-active");
    var playerRoot = videoWrapper && videoWrapper.closest(".VideoPlayer");
    if (playerRoot) playerRoot.classList.add("pts-mode-active");
    state.active = true;
    state.picking = false;
    setBtnState(btn, "CROP", "#0f0");
    startLoop();
    renderCrop();
    showToolbar("crop");
  }

  function activatePickMode(btn) {
    // Freeze crop overlay (make it non-interactive) and enter tag pick mode
    overlayContainer.classList.remove("pts-active");
    state.picking = true;
    document.body.classList.add("pts-pick-mode");
    setBtnState(btn, "PICK", "#ff0");
    showToolbar("pick");
  }

  function deactivate(btn) {
    stopLoop();
    state.active = false;
    state.picking = false;
    document.body.classList.remove("pts-pick-mode");
    var playerRoot = videoWrapper && videoWrapper.closest(".VideoPlayer");
    if (playerRoot) playerRoot.classList.remove("pts-mode-active");
    destroyOverlay();
    setBtnState(btn, "TAG", "");
    hideToolbar();
  }

  // ------- Tag picking -------

  document.addEventListener("click", function (e) {
    if (!state.picking) return;
    var tagEl = e.target.closest("span.tag-item");
    if (!tagEl) return;
    e.preventDefault();
    e.stopPropagation();

    var tagName = tagEl.textContent.trim();
    var btn = document.getElementById(BUTTON_ID);
    var params = cropToAnchorZoom();
    var sceneId = window.location.pathname.replace("/scenes/", "").split("/")[0];
    var startSeconds = loopStart;

    deactivate(btn);
    runBackendTask(sceneId, startSeconds, params.anchor_x, params.anchor_y, params.zoom, tagName, btn);
  }, true);

  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      var btn = document.getElementById(BUTTON_ID);
      if (btn && (state.active || state.picking)) {
        deactivate(btn);
      }
    }
  });

  // ------- Backend communication -------

  function runBackendTask(sceneId, startSeconds, anchorX, anchorY, zoom, tagName, btn) {
    setBtnState(btn, "RUN", "#f80");

    var mutation = [
      "mutation RunPluginTask(",
      "  $plugin_id: ID!,",
      "  $task_name: String!,",
      "  $args_map: Map",
      ") {",
      "  runPluginTask(",
      "    plugin_id: $plugin_id,",
      "    task_name: $task_name,",
      "    args_map: $args_map",
      "  )",
      "}",
    ].join("\n");

    var variables = {
      plugin_id: PLUGIN_ID,
      task_name: "Set Tag Preview",
      args_map: {
        mode: "set_tag_preview",
        scene_id: sceneId,
        start_seconds: String(startSeconds),
        tag_name: tagName,
        anchor_x: String(anchorX),
        anchor_y: String(anchorY),
        zoom: String(zoom),
      },
    };

    fetch("/graphql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: mutation, variables: variables }),
    })
      .then(function (r) { return r.json(); })
      .then(function (data) {
        if (data.errors) {
          console.error("PreviewTheStash error:", data.errors);
          setBtnState(btn, "ERR", "#f00");
        } else {
          setBtnState(btn, "OK", "#0f0");
        }
        setTimeout(function () {
          setBtnState(btn, "TAG", "");
        }, 2000);
      })
      .catch(function (err) {
        console.error("PreviewTheStash fetch error:", err);
        setBtnState(btn, "ERR", "#f00");
        setTimeout(function () {
          setBtnState(btn, "TAG", "");
        }, 2000);
      });
  }

  // ------- Setup -------

  function setup() {
    if (document.getElementById(BUTTON_ID)) return;
    var sceneId = window.location.pathname.replace("/scenes/", "").split("/")[0];
    if (!sceneId || isNaN(sceneId)) return;

    // Place button in scene toolbar next to Organized
    var organizedBtn = document.querySelector(".scene-toolbar-group .organized-button");
    var toolbar = organizedBtn ? organizedBtn.parentElement : (
      document.querySelector(".scene-toolbar-group") ||
      document.querySelector(".ml-auto .btn-group")
    );
    if (!toolbar) return;

    var btn = document.createElement("button");
    btn.id = BUTTON_ID;
    btn.className = "minimal btn btn-secondary pts-tag-btn";
    btn.title = "Preview The Stash — set tag preview image";
    btn.innerHTML = "TAG";
    btn.addEventListener("click", onTagButtonClick);
    if (organizedBtn) {
      toolbar.insertBefore(btn, organizedBtn);
    } else {
      toolbar.appendChild(btn);
    }
  }

  function onTagButtonClick() {
    var btn = document.getElementById(BUTTON_ID);
    if (!btn) return;
    if (state.picking) {
      deactivate(btn);
    } else if (state.active) {
      activatePickMode(btn);
    } else {
      activateCropMode(btn);
    }
  }

  function waitForElement(selector, callback) {
    var el = document.querySelector(selector);
    if (el) return callback(el);
    setTimeout(waitForElement, 100, selector, callback);
  }

  function onScenePage() {
    waitForElement(".scene-toolbar-group, .ml-auto .btn-group", setup);
  }

  // Initial load
  if (window.location.pathname.startsWith("/scenes/")) {
    onScenePage();
  }

  // SPA navigation
  PluginApi.Event.addEventListener("stash:location", function (e) {
    // Clean up old overlay when navigating away
    var btn = document.getElementById(BUTTON_ID);
    if (btn && (state.active || state.picking)) {
      deactivate(btn);
    }
    destroyToolbar();
    if (e.detail.data.location.pathname.startsWith("/scenes/")) {
      onScenePage();
    }
  });
})();
