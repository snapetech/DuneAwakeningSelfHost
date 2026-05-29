# Cap-check binary locations (Ghidra-confirmed)

Build hash: `9bf5fbdef43a6d6d64459df973f3d252c01ab4ad`
Captured: 2026-05-29

Ghidra ran full auto-analysis on the server binary (3h 23m), then a follow-up
decompile pass searched every function containing immediate writes of
`0x6b` (= `Fail_DisallowedBuildLimit` enum value, per
[`subfief-cap-enum-table.md`](subfief-cap-enum-table.md)) and decompiled the
first 60. Two functions contain the **fail-path write pattern**
`mov byte ptr [reg+0x18], 0x6b` — i.e. setting the 1-byte status field of an
`FBuildingSystemActionResult` struct to the cap-fail enum value.

> **Ghidra address note.** Ghidra adds `+0x100000` image base. Subtract
> `0x100000` to get the file offset / runtime VMA in this PIE binary. So
> Ghidra's `FUN_0d148810` lives at file offset / VMA `0xd048810`.

## Confirmed fail-path writes

| Function (file_off) | size | 0x6b write sites | Notes |
|---|---:|---|---|
| `0xcddc9d0`  | 6892 b | `0xcdddb9c`, `0xcdddd93` | Object-validity-style fail. Branches in via `call 0xedf0f20; test al,al; je 0xcdddd6e`. The cap math is **inside `0xedf0f20`** (validity stub) or deeper. |
| `0xd048810`  | 7668 b | `0xd049d85`, `0xd049f1c` | Has a **float-based threshold check** at `0xd049d39` (see below). The fail-path enters when the computed float exceeds the threshold. |

Both functions write the enum byte at struct offset `+0x18`, then zero out a
qword at `+0x20` and a byte at `+0x28` — that's the layout of
`FBuildingSystemActionResult { void*, void*, uint8 status, uint8 pad[7], ... }`.

## Smoking-gun float check in `0xd048810`

```
0xd049d13: vmovsd     xmm0, qword ptr [rsp + 0x100]           ; load fp64 A
0xd049d1c: vaddsd     xmm0, xmm0, qword ptr [rsp + 0x80]      ; A + B
0xd049d25: vdivsd     xmm0, xmm0, qword ptr [rip - 0x7e6529d] ; / 2.0  (or other const)
0xd049d2d: vcvtsd2ss  xmm0, xmm0, xmm0                        ; fp64 -> fp32
0xd049d31: mov        rax, qword ptr [rsp + 0x1a0]            ; load object pointer
0xd049d39: vucomiss   xmm0, dword ptr [rax + 0x79c]           ; ★ COMPARE vs threshold
0xd049d41: jbe        0xd049e62                                ; ★ jbe = success
...
0xd049d85: mov        byte ptr [rsp + 0x88], 0x6b              ; ★ Fail_DisallowedBuildLimit
```

The threshold lives at struct offset `+0x79c` of whatever object is at
`[rsp+0x1a0]` at this point. If `xmm0 <= threshold` the `jbe` jumps to the
success label; otherwise we fall through and set Fail_DisallowedBuildLimit.

### Patch — bypass this check entirely

Change `jbe rel32` (`0f 86 1b 01 00 00`, 6 bytes) → `nop ; jmp rel32`
(`90 e9 1b 01 00 00`, 6 bytes). Same total size, same target VMA
(`next_instr + 0x11b = 0xd049d47 + 0x11b = 0xd049e62`).

```python
# scripts/patch-subfief-cap-binary.py
SIGNATURE = [
    0xc5, 0xfb, 0x5a, 0xc0,                               # vcvtsd2ss xmm0, xmm0
    0x48, 0x8b, 0x84, 0x24, 0xa0, 0x01, 0x00, 0x00,       # mov rax, [rsp+0x1a0]
    0xc5, 0xf8, 0x2e, 0x80, 0x9c, 0x07, 0x00, 0x00,       # vucomiss xmm0, [rax+0x79c]
    0x0f, 0x86, None, None, None, None,                   # jbe rel32 (any target)
]
PATCH_OFFSETS = {
    20: lambda _cap: 0x90,  # 0x0f -> 0x90 (NOP)
    21: lambda _cap: 0xe9,  # 0x86 -> 0xe9 (JMP near; same rel32 keeps same target)
}
OLD_CAP = 3   # nominal; cap is float at member +0x79c, not literal in this op
```

This is **one of multiple `Fail_DisallowedBuildLimit` paths** — likely a
distance/proximity check (the averaging math points to "midpoint vs max
distance"), not the per-player count cap. Patching it bypasses *that*
specific check; the subfief count check almost certainly lives elsewhere
(probably deeper in `0xedf0f20` → its inner callees `0xfa7ec90` and
`0x12e2d140`, which `0xfa7ec90` itself wraps as a 631 b helper with no
direct count comparisons).

## What's still open

- The exact **subfief count arithmetic** (`count >= 3 + bonus`) has not been
  isolated as a numeric compare; no literal `3` surfaced in this path. The
  practical bypass point is known, though: the call to `0xedf0f20` followed by
  `test al, al; je <0x6b fail block>` at file offset `0xcdddb6a`.
- The decompile pass for `0x7e` / `0x7f` (building-piece map / server caps)
  completed; the patch points are recorded below.

## Follow-up: build-piece binary cap bypasses

The completed decompile pass found the two building-piece binary cap checks.
Both share the same validity-helper shape as the subfief/totem path:
`call 0xedf0f20; test al, al; je <fail block>`.

| Target | `je` file offset | Original bytes | Fail enum | Patch |
|---|---:|---|---:|---|
| Server-wide building-piece cap | `0xcf01466` | `0f 84 aa 00 00 00` | `0x7e` | `90 90 90 90 90 90` |
| Map-wide building-piece cap | `0xcf027e6` | `0f 84 ca 00 00 00` | `0x7f` | `90 90 90 90 90 90` |

`scripts/patch-subfief-cap-binary.py` now accepts `--target building` to patch
both building-piece binary checks, or `--target all` to patch subfief plus both
building-piece checks. The script filters original candidate sites by the enum
written at the fail target and also recognizes already-patched NOP sites.

## Callee taxonomy

- `0xedf0f20` (283 b): validity stub — calls `0x12e9fa70`, builds args,
  calls `0xfa7ec90`, walks an object table at `[rcx+0x38..0x40]`, calls
  `0x12e2d140`, returns `byte [rax+0x38]`.
- `0xfa7ec90` (631 b): wrapper, no `cmp imm` or SSE compares.
- `0x12e2d140`: not yet inspected.

To pin the subfief count cap byte, the next step is to decompile
`0xedf0f20`'s inner callees with full type inference (which Ghidra has now
done; rerun the decompile script with a wider value range to include
SubfiefCount/SubfiefLimitBonus float patterns).
