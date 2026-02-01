/* PreviewTheStash — visual crop overlay + tag preview generator */
(function () {
  "use strict";

  var PLUGIN_ID = "PreviewTheStash";
  var BUTTON_ID = "pts-tag-btn";

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

  // DOM refs
  var overlayContainer = null;
  var cropEl = null;
  var hudEl = null;
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

  function updateHud() {
    if (!hudEl) return;
    var params = cropToAnchorZoom();
    hudEl.textContent =
      "anchor-x: " + params.anchor_x.toFixed(2) +
      "\nanchor-y: " + params.anchor_y.toFixed(2) +
      "\nzoom:     " + params.zoom.toFixed(2);
  }

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

    hudEl = document.createElement("div");
    hudEl.className = "pts-hud";

    overlayContainer.appendChild(cropEl);
    overlayContainer.appendChild(hudEl);
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

    // --- Drag handling ---
    cropEl.addEventListener("mousedown", function (e) {
      if (e.target.classList.contains("pts-crop-handle")) return;
      e.preventDefault();
      e.stopPropagation();
      state.dragging = true;
      state.dragStart = { mx: e.clientX, my: e.clientY };
      state.cropStart = { x: crop.x, y: crop.y };
    });

    // --- Resize handling ---
    cropEl.addEventListener("mousedown", function (e) {
      if (!e.target.classList.contains("pts-crop-handle")) return;
      e.preventDefault();
      e.stopPropagation();
      state.resizing = e.target.dataset.dir;
      state.dragStart = { mx: e.clientX, my: e.clientY };
      state.cropStart = { x: crop.x, y: crop.y, size: crop.size };
    });

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup", onMouseUp);
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

  function onMouseMove(e) {
    if (!state.dragging && !state.resizing) return;
    var vr = getVideoRect();
    var clamped = clampMouseToVideoRect(e.clientX, e.clientY);

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

  function onMouseUp() {
    state.dragging = false;
    state.resizing = false;
  }

  function destroyOverlay() {
    if (overlayContainer) {
      overlayContainer.remove();
      overlayContainer = null;
      cropEl = null;
      hudEl = null;
    }
    document.removeEventListener("mousemove", onMouseMove);
    document.removeEventListener("mouseup", onMouseUp);
  }

  // ------- State machine -------

  function activateCropMode(btn) {
    videoEl = document.querySelector("video");
    if (!videoEl) return;
    createOverlay();
    overlayContainer.classList.add("pts-active");
    state.active = true;
    state.picking = false;
    btn.innerHTML = '<span style="font-size:11px;line-height:3em;color:#0f0;">CROP</span>';
    renderCrop();
  }

  function activatePickMode(btn) {
    // Freeze crop overlay (make it non-interactive) and enter tag pick mode
    overlayContainer.classList.remove("pts-active");
    state.picking = true;
    document.body.classList.add("pts-pick-mode");
    btn.innerHTML = '<span style="font-size:11px;line-height:3em;color:#ff0;">PICK</span>';
  }

  function deactivate(btn) {
    state.active = false;
    state.picking = false;
    document.body.classList.remove("pts-pick-mode");
    destroyOverlay();
    btn.innerHTML = '<span style="font-size:11px;line-height:3em;">TAG</span>';
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
    var startSeconds = videoEl ? videoEl.currentTime : 0;

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
    btn.innerHTML = '<span style="font-size:11px;line-height:3em;color:#f80;">RUN</span>';

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
          btn.innerHTML = '<span style="font-size:11px;line-height:3em;color:#f00;">ERR</span>';
        } else {
          btn.innerHTML = '<span style="font-size:11px;line-height:3em;color:#0f0;">OK</span>';
        }
        setTimeout(function () {
          btn.innerHTML = '<span style="font-size:11px;line-height:3em;">TAG</span>';
        }, 2000);
      })
      .catch(function (err) {
        console.error("PreviewTheStash fetch error:", err);
        btn.innerHTML = '<span style="font-size:11px;line-height:3em;color:#f00;">ERR</span>';
        setTimeout(function () {
          btn.innerHTML = '<span style="font-size:11px;line-height:3em;">TAG</span>';
        }, 2000);
      });
  }

  // ------- Setup -------

  function setup() {
    if (document.getElementById(BUTTON_ID)) return;
    var sceneId = window.location.pathname.replace("/scenes/", "").split("/")[0];
    if (!sceneId || isNaN(sceneId)) return;

    var controls = document.querySelector(".vjs-control-bar");
    if (!controls) return;

    var btn = document.createElement("button");
    btn.id = BUTTON_ID;
    btn.className = "vjs-control vjs-button";
    btn.title = "Preview The Stash — set tag preview image";
    btn.innerHTML = '<span style="font-size:11px;line-height:3em;">TAG</span>';
    btn.addEventListener("click", function () {
      if (state.picking) {
        // Cancel pick mode
        deactivate(btn);
      } else if (state.active) {
        // Crop positioned, move to tag pick
        activatePickMode(btn);
      } else {
        // Start crop mode
        activateCropMode(btn);
      }
    });
    controls.appendChild(btn);
  }

  function waitForElement(selector, callback) {
    var el = document.querySelector(selector);
    if (el) return callback(el);
    setTimeout(waitForElement, 100, selector, callback);
  }

  function onScenePage() {
    waitForElement(".vjs-control-bar", setup);
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
    if (e.detail.data.location.pathname.startsWith("/scenes/")) {
      onScenePage();
    }
  });
})();
