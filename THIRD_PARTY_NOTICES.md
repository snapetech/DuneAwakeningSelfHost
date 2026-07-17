# Third-Party Notices

## Vendored static command-line tools

DASH distributes four static x86_64 helpers under `vendor/bin/` for official
container images that do not provide the commands required by guarded startup
and diagnostics. Exact versions, upstream artifacts, hashes, corresponding
source, and rebuild instructions are recorded in [`vendor/README.md`](vendor/README.md).

- BusyBox 1.36.1 is GPL-2.0-only. The complete corresponding source archive,
  exact `.config`, build script, and GPL text accompany the binary under
  `vendor/source/`, `vendor/build-busybox.sh`, and `vendor/licenses/`.
- curl 8.17.0 uses the curl license. The static upstream artifact reports
  OpenSSL 3.5.4, zlib 1.3.1, libssh2 1.11.1, nghttp2 1.65.0, and musl; their
  license texts accompany the binary.
- jq 1.7.1 is distributed under its MIT license.
- ripgrep 15.1.0 is distributed under the user's choice of MIT or the Unlicense.

These components and their linked libraries are not relicensed under DASH's
MIT license. See the complete texts in `vendor/licenses/`.

## Sponge Dune Awakening Server Tools

The static console-variable registration-call extraction approach in
`scripts/build-cvar-catalog.py` is adapted from
[`Sponge/Dune-Awakening-Server-Tools`](https://git.unityailab.com/Sponge/Dune-Awakening-Server-Tools)
revision `04689ba704a3f6dd2d19db89a8df3b6d6a2424b2`, used under the MIT
License. DASH independently emits a versioned, binary-hash-bound catalogue from
an operator-owned local server ELF. Funcom-origin names, help text, defaults,
and symbols remain property of their respective owner and are not relicensed by
this notice.

```text
MIT License

Copyright (c) 2026 Sponge

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## DuneAwakening-Wormageddon

The curated `calm`, `standard`, and `wormageddon` gameplay preset values in
`config/gameplay-presets.json` are adapted from
SetsuaD/DuneAwakening-Wormageddon revision
`62ef3890886b8c7ddb5b764f36e5f83189ca7515`, used under the MIT License.
```text
MIT License

Copyright (c) 2026 Wormageddon contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## RedBlink Dune Awakening Self-Host Docker

Parts of the DASH blueprint archive schema mapping, validation behavior,
transform normalization, augment compatibility data, structured augment stat
construction, augment-slot prerequisite mapping, community addon lifecycle,
native Version 2 player-command notification path, player skill/vehicle
catalogs, offline vehicle repair semantics, Landsraad reward/contribution
writes, player Intel/recipe/research and gear/login-queue maintenance
semantics, Sietch dimension/settings lifecycle concepts, and Director
travel-demand patterns are adapted from
[`Red-Blink/dune-awakening-selfhost-docker`](https://github.com/Red-Blink/dune-awakening-selfhost-docker),
pinned at commit `12ac3b8b30a0dac3d728a37db65cad4a292750b6` for the parity audit.

```text
MIT License

Copyright (c) 2026 RedBlink

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
