/* MarkTheStash - Stash Marker Studio scene link */
(function () {
  "use strict";

  var PLUGIN_ID = "MarkTheStash";
  var BUTTON_ID = "mts-sms-btn";
  var CONFIG_KEY = "stashMarkerStudioUrl";
  var configPromise = null;

  function getBaseUrl() {
    return document.querySelector("base")?.getAttribute("href") || "/";
  }

  function graphql(query, variables) {
    return fetch(getBaseUrl() + "graphql", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query: query, variables: variables || {} }),
    })
      .then(function (response) {
        return response.json();
      })
      .then(function (json) {
        if (json.errors && json.errors.length) {
          throw new Error(json.errors.map(function (error) {
            return error.message;
          }).join("; "));
        }
        return json.data;
      });
  }

  function findPluginConfig(plugins) {
    if (!plugins || typeof plugins !== "object") return {};
    if (plugins[PLUGIN_ID]) return plugins[PLUGIN_ID];

    var matchingKey = Object.keys(plugins).find(function (key) {
      return String(key).toLowerCase() === PLUGIN_ID.toLowerCase();
    });
    return matchingKey ? plugins[matchingKey] : {};
  }

  function loadConfig() {
    if (!configPromise) {
      configPromise = graphql("query MarkTheStashConfig { configuration { plugins } }")
        .then(function (data) {
          return findPluginConfig(data.configuration && data.configuration.plugins);
        });
    }
    return configPromise;
  }

  function getSceneId() {
    var match = window.location.pathname.match(/^\/scenes\/(\d+)/);
    return match ? match[1] : null;
  }

  function normalizeSmsUrl(url) {
    return String(url || "").trim().replace(/\/+$/, "");
  }

  function setButtonState(btn, label, color) {
    btn.textContent = label;
    btn.style.color = color || "";
  }

  function showTemporaryError(btn) {
    setButtonState(btn, "ERR", "#f00");
    setTimeout(function () {
      setButtonState(btn, "SMS", "");
    }, 2000);
  }

  function openMarkerStudio(btn) {
    var sceneId = getSceneId();
    if (!sceneId) {
      showTemporaryError(btn);
      return;
    }

    loadConfig()
      .then(function (config) {
        var baseUrl = normalizeSmsUrl(config[CONFIG_KEY]);
        if (!baseUrl) {
          console.error("MarkTheStash: stashMarkerStudioUrl is not configured");
          showTemporaryError(btn);
          return;
        }

        window.open(baseUrl + "/marker/" + sceneId, "_blank", "noopener,noreferrer");
      })
      .catch(function (error) {
        console.error("MarkTheStash: could not load plugin configuration", error);
        showTemporaryError(btn);
      });
  }

  function setup() {
    if (document.getElementById(BUTTON_ID)) return;

    var sceneId = getSceneId();
    if (!sceneId) return;

    var toolbarGroup = document.querySelector(".scene-toolbar-group") ||
      document.querySelector(".ml-auto");
    if (!toolbarGroup) return;

    var btn = document.createElement("button");
    btn.id = BUTTON_ID;
    btn.className = "minimal btn btn-secondary mts-sms-btn";
    btn.title = "Open in Stash Marker Studio";
    btn.textContent = "SMS";
    btn.addEventListener("click", function () {
      openMarkerStudio(btn);
    });

    var group = document.createElement("div");
    group.className = "btn-group";
    group.setAttribute("role", "group");
    group.appendChild(btn);

    var organizedBtn = toolbarGroup.querySelector(".organized-button");
    if (organizedBtn && organizedBtn.closest(".btn-group")) {
      toolbarGroup.insertBefore(group, organizedBtn.closest(".btn-group"));
    } else {
      toolbarGroup.appendChild(group);
    }
  }

  function waitForElement(selector, callback) {
    var element = document.querySelector(selector);
    if (element) return callback(element);
    setTimeout(waitForElement, 100, selector, callback);
  }

  function onScenePage() {
    waitForElement(".scene-toolbar-group, .ml-auto .btn-group", setup);
  }

  if (getSceneId()) {
    onScenePage();
  }

  PluginApi.Event.addEventListener("stash:location", function (event) {
    if (event.detail.data.location.pathname.match(/^\/scenes\/(\d+)/)) {
      onScenePage();
    }
  });
})();
