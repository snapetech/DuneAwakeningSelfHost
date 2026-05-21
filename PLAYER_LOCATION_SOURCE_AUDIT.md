# Player Location Source Audit

This note tracks the admin panel location investigation. The short version: the current DB-backed location is a persisted actor position, not a proven live client position. The map should label it that way until we find a live runtime source.

## Tested Sources

| Source | How to query | Result | Verdict |
| --- | --- | --- | --- |
| `dune.actors.transform` for `player_pawn_id` | Join `dune.player_state.player_pawn_id -> dune.actors.id` | For test player, returns about `21723, 219189`, next to the base/sandbike. | Available and persistent, but does not match the in-game purple arrow screenshot. Not reliable as live map location. |
| `dune.actors.transform` for `player_controller_id` | Join `dune.player_state.player_controller_id -> dune.actors.id` | Same as pawn for test player. | Same persistence source, not live enough for current map use. |
| `dune.actors.transform` for `player_state_id` | Join `dune.player_state.player_state_id -> dune.actors.id` | Same as pawn/controller when present. | Same persistence source. |
| `dune.load_travel_to_player_info(controller_id)` | `select * from dune.load_travel_to_player_info(17)` | Same base-adjacent transform as actors. | Useful server helper, but still persistence-backed. Not a new live source. |
| `dune.travel_return_info` | Join by `player_controller_id` | For test player, returns about `20544, 218552`. | Return/teleport anchor, not current position. |
| `dune.player_respawn_locations` | Query by `account_id` | Has checkpoint names plus locator actors for vehicle/beacon. test player vehicle locator actor `110` is about `21181, 218960`. | Context only. Vehicle/beacon can be near a player sometimes but is not current player position. |
| `dune.overmap_players` | Query by player actor ids | Empty for current Hagga Basin player. | Only relevant to overmap/deep-desert style travel, not current Hagga position. |
| `dune.actor_state` | Query by actor ids | No rows for test player/controller/pawn. | No usable current transform here. |
| `dune.game_events` | Query by actor ids | Historical base/building events only; latest test player events are older and not movement samples. | Historical/audit data, not live position. |
| `dune.get_actors_location_data_with_permission(...)` | Call with controller/pawn ids | Same persisted transforms as `actors`. | Wrapper over same persisted data. |
| `dune.get_all_online_or_recently_disconnected_player_online_state()` | Server online helper | Gives online state and `(map, partition, dimension)`, no x/y/z. | Good for presence, not location. |
| Survival container logs | Search recent logs | Shows periodic `SavePlayer` for test player, but no x/y/z in normal logging. | Confirms periodic persistence happens, but does not expose location. |
| Game-server listening ports | `ss` inside survival | UDP gameplay ports and localhost TCP 10000 only. | No confirmed documented HTTP/RCON location API yet. |

## Current Interpretation

The current admin panel marker is not an accurate live player marker. It is plotting persisted DB actor transforms. That data can be useful for last-save/last-known context, offline moves, and diagnostics, but the live client can clearly be elsewhere.

The screenshot comparison suggests the actual live arrow is closer to DB objects around `x ~80k`, `y ~239k` in the current Hagga Basin South coordinate frame. Two nearby DB actors are respawn beacons `137` and `175`, but those are not linked to test player and must not be treated as player position without proof.

## Next Viable Paths

1. Find a native live GM/admin command that returns a player's current transform. Candidate names to test through the existing GM command envelope include location/where/pos variants, but execution is still gated until the payload route is proven.
2. Inspect RabbitMQ gameplay/admin traffic for authoritative live position messages. If the server publishes movement/session telemetry, this is the best non-invasive live source.
3. Increase server logging for player movement/telemetry if a console variable exists. Current default logs only show periodic `SavePlayer` lines without coordinates.
4. Use a client-assisted calibration/debug path: let an admin click their current in-game map location or send a chat command with known/current coordinates if the client displays them. This would be an operator-assisted correction, not automatic live tracking.
5. Keep DB actor transforms as `last persisted position` and remove/avoid the word `live` for the marker until one of the above is proven.

## Coordinate-Grid Validation

The admin map should be validated in two separate steps:

1. Fit the map image to an explicit world-coordinate grid.
2. Validate the data source being plotted onto that grid.

The panel now uses a clean composite of the public `survival_1` raw map tiles with bounds `X -457200..355600`, `Y -457200..355600`. DB POI/waypoint/landmark overlays are intentionally disabled so player-position testing is not obscured by unrelated markers. The current display maps world Y downward, which places test player's observed persistence coordinates in the south-central half of the full map instead of north-central. If this still disagrees with the in-game arrow, the remaining issue is the player location source or a finer post-intake transform, not POI clutter.

This separation matters because our current tested player source is `dune.actors.transform` and related DB helper functions. Those are persistence-layer coordinates. For test player they remain base-adjacent while the in-game arrow screenshot is elsewhere.

## Panel Behavior

The admin map API now returns `diagnostics` alongside `players`. The UI shows candidate sources so we can compare actor transforms, travel return info, respawn locations, and historical events for each online player without guessing.
