(function () {
	"use strict";

	var target = document.getElementById("server-status");
	var map = document.getElementById("hagga-map");
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
				target.innerHTML = html;
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
		if (!list.length) {
			players.innerHTML = "<li>No active players reported.</li>";
			return;
		}
		players.innerHTML = list.map(function (player) {
			var name = String(player.name || "Player").replace(/[&<>"']/g, function (ch) {
				return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch];
			});
			var location = String(player.location || "Unknown").replace(/[&<>"']/g, function (ch) {
				return {"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[ch];
			});
				return '<li><span class="player-meta"><strong><span>Name:</span> ' + name + '</strong><small><span>Map:</span> ' + location + '</small></span><span class="map-chip">Online</span></li>';
			}).join("");
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
				return response.json();
			})
			.then(renderPlayers)
			.catch(function () {
				if (updated) {
					updated.textContent = "snapshot unavailable";
				}
			});
	}

	refreshStatus();
	refreshSnapshot();
	initPanZoom(mapViewport, map, mapZoomIn, mapZoomOut, mapReset);
	window.setInterval(refreshStatus, 60000);
	window.setInterval(refreshSnapshot, 60000);
})();
