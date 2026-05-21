(function () {
	"use strict";

	var target = document.getElementById("server-status");
	var map = document.getElementById("hagga-map");
	var mapContent = document.getElementById("hagga-map-content");
	var poiOverlay = document.getElementById("poi-overlay");
	var poiToggles = document.getElementById("poi-toggles");
	var poiSummary = document.getElementById("poi-summary");
	var poiAll = document.getElementById("poi-all");
	var poiPreset = document.getElementById("poi-preset");
	var poiClear = document.getElementById("poi-clear");
	var poiEnableFiltered = document.getElementById("poi-enable-filtered");
	var poiDisableFiltered = document.getElementById("poi-disable-filtered");
	var poiOnlyFiltered = document.getElementById("poi-only-filtered");
	var poiFilter = document.getElementById("poi-filter");
	var poiFilterSummary = document.getElementById("poi-filter-summary");
	var players = document.getElementById("active-players");
	var count = document.getElementById("player-count");
	var peakCount = document.getElementById("peak-player-count");
	var updated = document.getElementById("map-updated");
	var mapViewport = document.getElementById("hagga-map-viewport");
	var mapZoomIn = document.getElementById("map-zoom-in");
	var mapZoomOut = document.getElementById("map-zoom-out");
	var mapReset = document.getElementById("map-reset");
	if (typeof fetch !== "function") {
		return;
	}

	function clamp(value, min, max) {
		return Math.min(max, Math.max(min, value));
	}

	function clearNode(node) {
		while (node && node.firstChild) {
			node.removeChild(node.firstChild);
		}
	}

	function appendTextElement(parent, tagName, className, text) {
		var element = document.createElement(tagName);
		if (className) {
			element.className = className;
		}
		element.textContent = String(text || "");
		parent.appendChild(element);
		return element;
	}

	function replaceWithSanitizedHtml(targetNode, html) {
		var parser = new DOMParser();
		var doc = parser.parseFromString(String(html || ""), "text/html");
		doc.querySelectorAll("script, iframe, object, embed, link, meta, style").forEach(function (node) {
			node.remove();
		});
		doc.body.querySelectorAll("*").forEach(function (node) {
			Array.prototype.slice.call(node.attributes).forEach(function (attribute) {
				var name = attribute.name.toLowerCase();
				var value = String(attribute.value || "").trim().toLowerCase();
				if (name.indexOf("on") === 0 || value.indexOf("javascript:") === 0) {
					node.removeAttribute(attribute.name);
				}
			});
		});
		clearNode(targetNode);
		Array.prototype.slice.call(doc.body.childNodes).forEach(function (node) {
			targetNode.appendChild(document.importNode(node, true));
		});
	}

	function safeJson(response, maxBytes) {
		var length = Number(response.headers.get("Content-Length") || 0);
		if (length && length > maxBytes) {
			throw new Error("response too large");
		}
		return response.text().then(function (text) {
			if (text.length > maxBytes) {
				throw new Error("response too large");
			}
			return JSON.parse(text);
		});
	}

	var poiPalette = ["#d9a63c", "#78cf7a", "#6fb6ff", "#e08585", "#c98dff", "#72d6c9", "#f0d77a", "#ff9d5c"];
	var poiStorageKey = "dunePublicPoiGroups";
	var poiPresetGroups = {"Shipwrecks": true, "Caves": true, "TradingPosts": true, "Outposts": true, "Aql": true, "Trainers": true};

	function initPanZoom(viewport, content, zoomIn, zoomOut, reset) {
		if (!viewport || !content) {
			return;
		}
		var state = { scale: 1, x: 0, y: 0 };
		var drag = null;

		function bounds() {
			var rect = viewport.getBoundingClientRect();
			var maxX = Math.max(0, (rect.width * state.scale - rect.width) / 2);
			var maxY = Math.max(0, (rect.height * state.scale - rect.height) / 2);
			state.x = clamp(state.x, -maxX, maxX);
			state.y = clamp(state.y, -maxY, maxY);
		}

		function apply() {
			bounds();
			content.style.transform = "translate(" + state.x + "px, " + state.y + "px) scale(" + state.scale + ")";
		}

		function zoomAt(nextScale, clientX, clientY) {
			var rect = viewport.getBoundingClientRect();
			var oldScale = state.scale;
			var newScale = clamp(nextScale, 1, 6);
			var px = clientX - rect.left - rect.width / 2 - state.x;
			var py = clientY - rect.top - rect.height / 2 - state.y;
			state.x -= px * (newScale / oldScale - 1);
			state.y -= py * (newScale / oldScale - 1);
			state.scale = newScale;
			apply();
		}

		viewport.addEventListener("wheel", function (event) {
			event.preventDefault();
			zoomAt(state.scale * (event.deltaY < 0 ? 1.18 : 0.84), event.clientX, event.clientY);
		}, { passive: false });

		viewport.addEventListener("pointerdown", function (event) {
			drag = { id: event.pointerId, x: event.clientX, y: event.clientY, startX: state.x, startY: state.y };
			viewport.classList.add("is-dragging");
			viewport.setPointerCapture(event.pointerId);
		});
		viewport.addEventListener("pointermove", function (event) {
			if (!drag || drag.id !== event.pointerId) {
				return;
			}
			state.x = drag.startX + event.clientX - drag.x;
			state.y = drag.startY + event.clientY - drag.y;
			apply();
		});
		function endDrag(event) {
			if (drag && drag.id === event.pointerId) {
				drag = null;
				viewport.classList.remove("is-dragging");
			}
		}
		viewport.addEventListener("pointerup", endDrag);
		viewport.addEventListener("pointercancel", endDrag);
		viewport.addEventListener("dblclick", function (event) {
			zoomAt(state.scale < 2 ? 2 : 1, event.clientX, event.clientY);
		});
		if (zoomIn) {
			zoomIn.addEventListener("click", function () {
				var rect = viewport.getBoundingClientRect();
				zoomAt(state.scale * 1.35, rect.left + rect.width / 2, rect.top + rect.height / 2);
			});
		}
		if (zoomOut) {
			zoomOut.addEventListener("click", function () {
				var rect = viewport.getBoundingClientRect();
				zoomAt(state.scale / 1.35, rect.left + rect.width / 2, rect.top + rect.height / 2);
			});
		}
		if (reset) {
			reset.addEventListener("click", function () {
				state = { scale: 1, x: 0, y: 0 };
				apply();
			});
		}
		window.addEventListener("resize", apply);
		apply();
	}

	function refreshStatus() {
		if (!target) {
			return;
		}
		fetch("/status.html", { cache: "no-store" })
			.then(function (response) {
				if (!response.ok) {
					throw new Error("status fetch failed");
				}
				return response.text();
			})
			.then(function (html) {
				if (html.indexOf("<script") !== -1) {
					return;
				}
				replaceWithSanitizedHtml(target, html);
			})
			.catch(function () {
				// Keep the last rendered static status if refresh fails.
			});
	}

	function renderPlayers(data) {
		var list = Array.isArray(data.players) ? data.players : [];
		if (count) {
			count.textContent = String(data.onlineCount || list.length || 0) + " online";
		}
		if (peakCount) {
			var peak = Number(data.peakToday || 0);
			peakCount.textContent = "peak today " + String(peak);
		}
		if (updated) {
			updated.textContent = data.generatedAt ? "updated " + data.generatedAt : "snapshot unavailable";
		}
		if (!players) {
			return;
		}
		clearNode(players);
		if (!list.length) {
			appendTextElement(players, "li", "", "No active players reported.");
			return;
		}
		list.forEach(function (player) {
			var item = document.createElement("li");
			var meta = document.createElement("span");
			meta.className = "player-meta";
			var nameLine = document.createElement("strong");
			appendTextElement(nameLine, "span", "", "Name:");
			nameLine.appendChild(document.createTextNode(" " + String(player.name || "Player")));
			var mapLine = document.createElement("small");
			appendTextElement(mapLine, "span", "", "Map:");
			mapLine.appendChild(document.createTextNode(" " + String(player.location || "Unknown")));
			meta.appendChild(nameLine);
			meta.appendChild(mapLine);
			item.appendChild(meta);
			appendTextElement(item, "span", "map-chip", "Online");
			players.appendChild(item);
		});
	}

	function refreshSnapshot() {
		var stamp = String(Date.now());
		if (map) {
			map.src = "/hagga-map.svg?v=" + stamp;
		}
		fetch("/players.json?v=" + stamp, { cache: "no-store" })
			.then(function (response) {
				if (!response.ok) {
					throw new Error("players fetch failed");
				}
				return safeJson(response, 64000);
			})
			.then(renderPlayers)
			.catch(function () {
				if (updated) {
					updated.textContent = "snapshot unavailable";
				}
			});
	}

	function escapeHtml(value) {
		return String(value || "").replace(/[&<>"']/g, function (ch) {
			return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch];
		});
	}

	function selectedPoiGroups(groups) {
		var stored = {};
		try {
			stored = JSON.parse(sessionStorage.getItem(poiStorageKey) || "{}");
		} catch (e) {
			stored = {};
		}
		var selected = {};
		Object.keys(groups || {}).forEach(function (group) {
			selected[group] = Object.prototype.hasOwnProperty.call(stored, group) ? stored[group] === true : false;
		});
		return selected;
	}

	function savePoiGroups(selected) {
		sessionStorage.setItem(poiStorageKey, JSON.stringify(selected));
	}

	function updatePoiSummary(selected, data) {
		if (!poiSummary) {
			return;
		}
		var enabled = Object.keys(selected || {}).filter(function (group) {
			return selected[group] === true;
		}).length;
		var markerCount = Array.isArray(data && data.markers) ? data.markers.filter(function (marker) {
			return selected[marker.group] === true;
		}).length : 0;
		poiSummary.textContent = enabled ? String(enabled) + " layer" + (enabled === 1 ? "" : "s") + " / " + String(markerCount) + " markers" : "POI layers off";
	}

	function renderPoiOverlay(data, selected) {
		if (!poiOverlay) {
			return;
		}
		clearNode(poiOverlay);
		var markers = Array.isArray(data.markers) ? data.markers : [];
		var groupKeys = Object.keys(data.groups || {});
		var colors = {};
		groupKeys.forEach(function (group, index) {
			colors[group] = poiPalette[index % poiPalette.length];
		});
		markers.filter(function (marker) {
			return selected[marker.group] === true;
		}).forEach(function (marker) {
			var x = Math.max(0, Math.min(1000, Number(marker.x || 0) / 100));
			var y = Math.max(0, Math.min(1000, Number(marker.y || 0) / 100));
			var name = String(marker.name || marker.group || "");
			var group = String((data.groups[marker.group] || {}).name || marker.group || "");
			var color = colors[marker.group] || "#d9a63c";
			var item = document.createElementNS("http://www.w3.org/2000/svg", "g");
			item.setAttribute("class", "poi-marker");
			item.setAttribute("transform", "translate(" + x.toFixed(1) + " " + y.toFixed(1) + ")");
			var title = document.createElementNS("http://www.w3.org/2000/svg", "title");
			title.textContent = group + ": " + name;
			var circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
			circle.setAttribute("r", "4.5");
			circle.setAttribute("fill", color);
			var label = document.createElementNS("http://www.w3.org/2000/svg", "text");
			label.setAttribute("x", "8");
			label.setAttribute("y", "-8");
			label.textContent = name;
			item.appendChild(title);
			item.appendChild(circle);
			item.appendChild(label);
			poiOverlay.appendChild(item);
		});
	}

	function renderPoiToggles(data) {
		if (!poiToggles) {
			return;
		}
		var groups = data.groups || {};
		var selected = selectedPoiGroups(groups);
		var groupKeys = Object.keys(groups).filter(function (group) {
			return Number(groups[group].count || 0) > 0;
		}).sort(function (a, b) {
			return String((groups[a] || {}).name || a).localeCompare(String((groups[b] || {}).name || b), undefined, { sensitivity: "base" });
		});
		var colors = {};
		groupKeys.forEach(function (group, index) {
			colors[group] = poiPalette[index % poiPalette.length];
		});
		clearNode(poiToggles);
		groupKeys.forEach(function (group) {
			var info = groups[group] || {};
			var label = String(info.name || group);
			var row = document.createElement("label");
			row.setAttribute("data-filter-text", (label + " " + group).toLowerCase());
			var toggleLabel = document.createElement("span");
			toggleLabel.className = "poi-toggle-label";
			var input = document.createElement("input");
			input.type = "checkbox";
			input.value = group;
			input.checked = selected[group] === true;
			var swatch = document.createElement("span");
			swatch.className = "poi-swatch";
			swatch.style.backgroundColor = colors[group];
			toggleLabel.appendChild(input);
			toggleLabel.appendChild(swatch);
			appendTextElement(toggleLabel, "span", "", label);
			row.appendChild(toggleLabel);
			appendTextElement(row, "span", "poi-count", String(info.count || 0));
			poiToggles.appendChild(row);
		});
		renderPoiOverlay(data, selected);
		updatePoiSummary(selected, data);
		function applyFilter() {
			var term = poiFilter ? poiFilter.value.trim().toLowerCase() : "";
			var visible = 0;
			var total = 0;
			poiToggles.querySelectorAll("label[data-filter-text]").forEach(function (label) {
				label.hidden = term && label.getAttribute("data-filter-text").indexOf(term) === -1;
				total += 1;
				if (!label.hidden) {
					visible += 1;
				}
			});
			if (poiFilterSummary) {
				poiFilterSummary.textContent = term ? "Showing " + visible + " of " + total + " POI layers" : "Showing all " + total + " POI layers";
			}
		}
		poiToggles.querySelectorAll("input[type=checkbox]").forEach(function (input) {
			input.addEventListener("change", function () {
				selected[input.value] = input.checked;
				savePoiGroups(selected);
				renderPoiOverlay(data, selected);
				updatePoiSummary(selected, data);
			});
		});
		if (poiFilter && !poiFilter.dataset.bound) {
			poiFilter.dataset.bound = "true";
			poiFilter.addEventListener("input", applyFilter);
		}
		applyFilter();
		if (poiAll) {
			poiAll.onclick = function () {
				Object.keys(selected).forEach(function (group) {
					selected[group] = true;
				});
				savePoiGroups(selected);
				renderPoiToggles(data);
			};
		}
		if (poiClear) {
			poiClear.onclick = function () {
				Object.keys(selected).forEach(function (group) {
					selected[group] = false;
				});
				savePoiGroups(selected);
				renderPoiToggles(data);
			};
		}
		function setFiltered(enabled) {
			poiToggles.querySelectorAll("label[data-filter-text]").forEach(function (label) {
				if (!label.hidden) {
					var input = label.querySelector("input[type=checkbox]");
					if (input) {
						selected[input.value] = enabled;
					}
				}
			});
			savePoiGroups(selected);
			renderPoiToggles(data);
		}
		function onlyFiltered() {
			Object.keys(selected).forEach(function (group) {
				selected[group] = false;
			});
			poiToggles.querySelectorAll("label[data-filter-text]").forEach(function (label) {
				if (!label.hidden) {
					var input = label.querySelector("input[type=checkbox]");
					if (input) {
						selected[input.value] = true;
					}
				}
			});
			savePoiGroups(selected);
			renderPoiToggles(data);
		}
		if (poiEnableFiltered) {
			poiEnableFiltered.onclick = function () {
				setFiltered(true);
			};
		}
		if (poiDisableFiltered) {
			poiDisableFiltered.onclick = function () {
				setFiltered(false);
			};
		}
		if (poiOnlyFiltered) {
			poiOnlyFiltered.onclick = onlyFiltered;
		}
		if (poiPreset) {
			poiPreset.onclick = function () {
				Object.keys(selected).forEach(function (group) {
					selected[group] = poiPresetGroups[group] === true;
				});
				savePoiGroups(selected);
				renderPoiToggles(data);
			};
		}
	}

	function loadPois() {
		if (!poiOverlay || !poiToggles) {
			return;
		}
		fetch("/hagga-pois.json", { cache: "no-store" })
			.then(function (response) {
				if (!response.ok) {
					throw new Error("poi fetch failed");
				}
				return safeJson(response, 512000);
			})
			.then(renderPoiToggles)
			.catch(function () {
				clearNode(poiToggles);
				clearNode(poiOverlay);
			});
	}

	refreshStatus();
	refreshSnapshot();
	loadPois();
	initPanZoom(mapViewport, mapContent || map, mapZoomIn, mapZoomOut, mapReset);
	window.setInterval(refreshStatus, 60000);
	window.setInterval(refreshSnapshot, 60000);
})();
