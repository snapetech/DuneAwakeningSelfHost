(function () {
	"use strict";

	var target = document.getElementById("server-status");
	var map = document.getElementById("hagga-map");
	var players = document.getElementById("active-players");
	var count = document.getElementById("player-count");
	var updated = document.getElementById("map-updated");
	if (typeof fetch !== "function") {
		return;
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
			var marker = player.onHaggaMap ? '<span class="map-chip">mapped</span>' : '<span class="map-chip dim">active</span>';
			return '<li><span><strong>' + name + '</strong><small>' + location + '</small></span>' + marker + '</li>';
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
	window.setInterval(refreshStatus, 60000);
	window.setInterval(refreshSnapshot, 60000);
})();
