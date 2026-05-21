# AMP Borrowing Notes

Confidence: high.

This repo uses CubeCoders AMP as a reference source only. It does not vendor AMP scripts, runtime wrappers, or generated files.

Inspected upstream:

- AMP template repo: https://github.com/CubeCoders/AMPTemplates
- Commit: `24d767fcaa69ec7e10a7ce163326b82d97b1eef7`
- Dune template root: https://raw.githubusercontent.com/CubeCoders/AMPTemplates/main/duneawakening.kvp
- Dune settings manifest: https://raw.githubusercontent.com/CubeCoders/AMPTemplates/main/duneawakeningconfig.json

Useful patterns borrowed into DASH-native code:

- FLS environment is explicit. DASH now passes `DefaultFlsEnvironment` through `DUNE_FLS_ENV`, defaulting to `retail`, in game-server command lines and service-layer FuncomLiveServices environment. Use a beta/test value only with a matching PTC/test server build and token authorization.
- The AMP manifest treats the FLS world name as a reclaimable battlegroup identity. DASH keeps `WORLD_UNIQUE_NAME` as the durable identity and preflight now flags unchanged example names.
- AMP solved the same class of UE5 saved-config placement problem. DASH already copies generated `Engine.ini`/`Game.ini` into saved config paths, keeps the Unreal `Saved/UserSettings` symlink, and appends `-IGWBindAddress`; focused tests now cover that wrapper behavior.
- AMP exposes game RabbitMQ as the client-facing broker endpoint. DASH now has a read-only RabbitMQ TLS SAN checker so operators can see whether the certificate covers `GAME_RMQ_PUBLIC_HOST`, `game-rmq`, `localhost`, and `127.0.0.1`.

Not borrowed:

- AMP's on-demand instance manager. DASH remains a Compose-first standing-farm architecture.
- AMP template packaging, AMP config manifests, AMP console wrappers, or shell bodies.
- Native GM, teleport, item grant, or kick execution. The public AMP template does not expose those payloads or a verified execution path.

Operational decision: confidence high. Reimplement the useful settings and checks in DASH-native Compose, scripts, tests, and docs. Do not add AMP as a runtime dependency.
