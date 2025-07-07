(function () {
  "use strict";

  const {
    stash,
    waitForElementByXpath,
    getElementByXpath,
    getElementsByXpath,
    getClosestAncestor,
    sortElementChildren,
    createElementFromHTML,
  } = window.stash7dJx1qP;

  document.body.appendChild(document.createElement("style")).textContent = `
    .search-item > div.row:first-child > div.col-md-6.my-1 > div:first-child { display: flex; flex-direction: column; }
    .tagger-remove { order: 10; }
    .fix-button-highlight {
      animation: pulse 1s infinite;
      border-color: #ffc107 !important;
      background-color: rgba(255, 193, 7, 0.1) !important;
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(255, 193, 7, 0.7); }
      70% { box-shadow: 0 0 0 10px rgba(255, 193, 7, 0); }
      100% { box-shadow: 0 0 0 0 rgba(255, 193, 7, 0); }
    }
    `;

  // Parse fixes from window.stashFixesData
  function parseFixesFromWindow() {
    // Check for fixes data in window.stashFixesData
    if (window.stashFixesData && Array.isArray(window.stashFixesData)) {
      console.log(
        "FixTheStash: Found fixes in window.stashFixesData:",
        window.stashFixesData
      );
      return window.stashFixesData;
    }

    return null; // Return null if data not available yet
  }

  // Wait for fixes data to be populated
  let sceneFixes = [];
  let fixesDataReady = false;

  function waitForFixesData() {
    const maxAttempts = 50; // 100ms per attempt
    let attempts = 0;

    function checkForData() {
      attempts++;
      const fixes = parseFixesFromWindow();

      if (fixes !== null) {
        sceneFixes = fixes;
        fixesDataReady = true;
        console.log("FixTheStash: Fixes data loaded successfully");

        // Log individual fixes for debugging
        sceneFixes.forEach((fix, index) => {
          console.log(`FixTheStash: Fix ${index + 1}:`, {
            name: fix.name,
            addTags: fix.addTags || [],
            removeTags: fix.removeTags || [],
          });
        });

        return;
      }

      if (attempts >= maxAttempts) {
        console.log(
          "FixTheStash: Timeout waiting for fixes data, proceeding without fixes"
        );
        fixesDataReady = true;
        return;
      }

      // Try again in 100ms
      setTimeout(checkForData, 100);
    }

    checkForData();
  }

  // Start waiting for fixes data
  console.log("FixTheStash: Waiting for fixes data");
  waitForFixesData();

  // Function to get all selected scenes
  function getSelectedScenes() {
    const selectedScenes = [];

    // Find all scene cards with checked checkboxes
    const sceneCards = document.querySelectorAll(".scene-card");

    // Also try alternative selectors
    const wallItems = document.querySelectorAll(".wall-item");

    // Check for any checkboxes at all
    sceneCards.forEach((card) => {
      const checkbox = card.querySelector(".card-check");

      if (checkbox) {
        if (checkbox.checked) {
          // Extract scene information
          const sceneInfo = extractSceneInfo(card);
          if (sceneInfo) {
            selectedScenes.push(sceneInfo);
          }
        }
      }
    });

    // If no scene cards found, try wall items (wall view)
    if (sceneCards.length === 0 && wallItems.length > 0) {
      // In wall view, selection might be handled differently
      // Let's check if there's a global selection state or different checkbox locations
      const selectedCount = document.querySelector(".selected-items-info span");
      if (selectedCount) {
      }

      // Try to find checkboxes in wall items or other locations
      wallItems.forEach((item) => {
        const checkbox = item.querySelector('input[type="checkbox"]');

        if (checkbox && checkbox.checked) {
          // Try to extract scene info from wall item
          const sceneInfo = extractSceneInfoFromWallItem(item);
          if (sceneInfo) {
            selectedScenes.push(sceneInfo);
          }
        }
      });
    }

    return selectedScenes;
  }

  // Function to extract scene information from a scene card
  function extractSceneInfo(sceneCard) {
    try {
      const sceneLink = sceneCard.querySelector(".scene-card-link");
      const titleElement = sceneCard.querySelector(
        ".card-section-title .TruncatedText"
      );
      const dateElement = sceneCard.querySelector(".scene-card__date");
      const filePathElement = sceneCard.querySelector(".file-path");
      const descriptionElement = sceneCard.querySelector(
        ".scene-card__description"
      );

      // Extract scene ID from the link href
      let sceneId = null;
      if (sceneLink) {
        const hrefMatch = sceneLink.href.match(/\/scenes\/(\d+)/);
        if (hrefMatch) {
          sceneId = parseInt(hrefMatch[1]);
        }
      }

      const sceneInfo = {
        id: sceneId,
        title: titleElement ? titleElement.textContent.trim() : null,
        date: dateElement ? dateElement.textContent.trim() : null,
        filePath: filePathElement ? filePathElement.textContent.trim() : null,
        description: descriptionElement
          ? descriptionElement.textContent.trim()
          : null,
        element: sceneCard,
      };

      return sceneInfo;
    } catch (error) {
      console.error("Error extracting scene info:", error);
      return null;
    }
  }

  // Function to extract scene information from a wall item
  function extractSceneInfoFromWallItem(wallItem) {
    try {
      const sceneLink = wallItem.querySelector('a[href*="/scenes/"]');
      const titleElement = wallItem.querySelector(".wall-item-title");

      // Extract scene ID from the link href
      let sceneId = null;
      if (sceneLink) {
        const hrefMatch = sceneLink.href.match(/\/scenes\/(\d+)/);
        if (hrefMatch) {
          sceneId = parseInt(hrefMatch[1]);
        }
      }

      const sceneInfo = {
        id: sceneId,
        title: titleElement ? titleElement.textContent.trim() : null,
        date: null, // Wall items might not have date in the same format
        filePath: null, // Wall items might not have file path visible
        description: null, // Wall items might not have description
        element: wallItem,
      };

      return sceneInfo;
    } catch (error) {
      console.error("Error extracting wall item scene info:", error);
      return null;
    }
  }

  // Function to refresh the scenes query
  function refreshScenes() {
    setTimeout(() => {
      const client = window.PluginApi.utils.StashService.getClient();
      const cache = client.cache;

      window.PluginApi.utils.StashService.evictQueries(cache, [
        window.PluginApi.GQL.FindScenesDocument,
      ]);
    }, 0);
  }

  // Function to apply a fix to selected scenes
  async function applyFix(fix) {
    // Find all selected scenes
    const selectedScenes = getSelectedScenes();

    if (selectedScenes.length === 0) {
      console.log("No scenes selected");
      return;
    }

    // Use csLib to call GraphQL
    if (fix.addTags && fix.addTags.length > 0) {
      const variables = {
        input: {
          ids: selectedScenes.map((o) => o.id),
          tag_ids: { mode: "ADD", ids: fix.addTags.map((o) => o.id) || [] },
        },
      };
      const query = `mutation BulkSceneUpdate($input: BulkSceneUpdateInput!) {bulkSceneUpdate(input: $input) { id title }}`;
      await csLib.callGQL({ query, variables });
    }

    if (fix.removeTags && fix.removeTags.length > 0) {
      const variables = {
        input: {
          ids: selectedScenes.map((o) => o.id),
          tag_ids: {
            mode: "REMOVE",
            ids: fix.removeTags.map((o) => o.id) || [],
          },
        },
      };
      const query = `mutation BulkSceneUpdate($input: BulkSceneUpdateInput!) {bulkSceneUpdate(input: $input) { id title }}`;
      await csLib.callGQL({ query, variables });
    }

    document.querySelector('button[title="Select None"]').click();
    refreshScenes();
  }

  // Function to highlight fix buttons
  function highlightFixButtons() {
    const fixButtons = document.querySelectorAll("[data-fix-number]");
    fixButtons.forEach((button) => {
      button.classList.add("fix-button-highlight");
    });
  }

  // Function to remove highlight from fix buttons
  function removeFixButtonHighlight() {
    const fixButtons = document.querySelectorAll("[data-fix-number]");
    fixButtons.forEach((button) => {
      button.classList.remove("fix-button-highlight");
    });
  }

  // Keyboard shortcut handling
  let qPressed = false;
  let qTimeout = null;
  document.addEventListener("keydown", (event) => {
    // Check if we're on a scenes page
    if (!document.querySelector(".scene-list-header")) {
      return;
    }

    // Check if we're focused on an input field
    if (
      event.target.tagName === "INPUT" ||
      event.target.tagName === "TEXTAREA"
    ) {
      return;
    }

    if (event.key.toLowerCase() === "q" && !qPressed) {
      qPressed = true;
      event.preventDefault();
      console.log("Q pressed, waiting for number key...");

      // Highlight fix buttons
      highlightFixButtons();

      // Set a timeout to reset qPressed after 2 seconds
      qTimeout = setTimeout(() => {
        qPressed = false;
        removeFixButtonHighlight();
      }, 2000);
    } else if (qPressed && event.key >= "1" && event.key <= "9") {
      event.preventDefault();
      const fixNumber = parseInt(event.key);

      // Clear timeout and remove highlight
      clearTimeout(qTimeout);
      removeFixButtonHighlight();

      // Check if this fix number exists
      if (fixNumber <= sceneFixes.length) {
        const fix = sceneFixes[fixNumber - 1];
        console.log(`Applying fix ${fixNumber} via keyboard shortcut`);
        applyFix(fix);
      } else {
        console.log(`Fix ${fixNumber} does not exist`);
      }

      qPressed = false;
    } else if (qPressed && event.key === "Escape") {
      // Cancel keyboard shortcut mode with Escape
      event.preventDefault();
      clearTimeout(qTimeout);
      removeFixButtonHighlight();
      qPressed = false;
      console.log("Keyboard shortcut mode cancelled");
    }
  });

  // Add fix buttons functionality
  function createFixButtons() {
    // Only proceed if fixes data is ready and we have fixes
    if (!fixesDataReady || !sceneFixes || sceneFixes.length === 0) {
      return;
    }

    // Check if we're on a scene list page and the second toolbar exists
    const listHeader = document.querySelector(".scene-list-header");
    if (!listHeader) {
      return;
    }

    // Check if fix buttons div already exists
    const existingFixButtons = document.querySelector(".fix-buttons-container");
    if (existingFixButtons) {
      return;
    }

    // Create the fix buttons container
    const fixButtonsContainer = document.createElement("div");
    fixButtonsContainer.className = "fix-buttons-container";
    fixButtonsContainer.style.cssText = `
      background: #1a1a1a;
      border-top: 1px solid #444;
      padding: 10px;
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
    `;

    // Create left side container for label and fix buttons
    const leftContainer = document.createElement("div");
    leftContainer.style.cssText = `
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    `;

    // Add a label
    const label = document.createElement("span");
    label.textContent = "Fixes:";
    label.style.cssText = "color: #fff; font-weight: bold; margin-right: 10px;";
    leftContainer.appendChild(label);

    // Create buttons for each fix
    sceneFixes.forEach((fix, index) => {
      const fixNumber = index + 1;
      const button = document.createElement("button");
      button.className = "btn btn-sm btn-outline-primary";
      button.textContent = `${fixNumber}. ${fix.name || `Fix ${fixNumber}`}`;
      button.style.cssText = "margin-right: 5px;";
      button.setAttribute("data-fix-number", fixNumber);

      // Add click handler
      button.addEventListener("click", async () => {
        await applyFix(fix, fixNumber);
      });

      leftContainer.appendChild(button);
    });

    // Create refresh button
    const refreshButton = document.createElement("button");
    refreshButton.className = "btn btn-sm btn-outline-secondary";
    refreshButton.textContent = "🔄 Refresh";
    refreshButton.style.cssText = "margin-left: auto;";
    refreshButton.title = "Refresh scenes query";

    // Add click handler for refresh
    refreshButton.addEventListener("click", () => {
      refreshScenes();
    });

    // Add containers to main container
    fixButtonsContainer.appendChild(leftContainer);
    fixButtonsContainer.appendChild(refreshButton);

    // Insert after the last toolbar (scene-list-header)
    const headerToolbar = document.querySelector(".scene-list-header");
    if (headerToolbar) {
      // Find the next sibling after the toolbar to insert before it
      const nextSibling = headerToolbar.nextElementSibling;
      if (nextSibling) {
        // Insert the fix buttons container before the next sibling
        headerToolbar.parentNode.insertBefore(fixButtonsContainer, nextSibling);
      } else {
        // If no next sibling, append to the parent
        headerToolbar.parentNode.appendChild(fixButtonsContainer);
      }
    }
  }

  // Function to initialize fix buttons when conditions are met
  function initFixButtons() {
    // Wait for fixes data to be ready
    if (!fixesDataReady) {
      setTimeout(initFixButtons, 100);
      return;
    }

    // Wait for scene list to be ready
    const listHeaderElement = document.querySelector(".scene-list-header");
    if (!listHeaderElement) {
      setTimeout(initFixButtons, 100);
      return;
    }

    createFixButtons();
  }

  // Listen for page changes to initialize fix buttons
  stash.addEventListener("page:scenes", function () {
    setTimeout(initFixButtons, 200);
  });

  // Also check when fixes data becomes ready
  const originalWaitForFixesData = waitForFixesData;
  waitForFixesData = function () {
    originalWaitForFixesData();

    // Add additional check for creating fix buttons after data is loaded
    const checkInterval = setInterval(() => {
      if (fixesDataReady) {
        clearInterval(checkInterval);
        setTimeout(initFixButtons, 200);
      }
    }, 100);
  };

  // Re-run waitForFixesData with the modified version
  waitForFixesData();
})();
