# Ghidra Python script — locate the per-player subfief/totem cap comparison
# inside DuneSandboxServer-Linux-Shipping.
#
# Usage (inside Ghidra):
#   1. File > Import File > DuneSandboxServer-Linux-Shipping
#   2. Let auto-analysis complete (1-2 hours for a 374MB stripped PIE)
#   3. Window > Script Manager > Manage Script Directories > add this script's
#      directory (or copy the file into ~/ghidra_scripts/)
#   4. Run "ghidra-find-subfief-cap.py"
#
# What it does:
#   1. Finds the string "Fail_DisallowedBuildLimit" in .rodata.
#   2. Finds all code references to that string.
#   3. Walks back from each reference looking for the FName-init pattern that
#      registers this enum value with reflection (one-time at static init).
#   4. Falls back to: find the enum's int32 value (by parsing the UEnum
#      metadata table), then search for `MOV [mem], <imm>` writes of that
#      value that are downstream of conditional branches.
#   5. For each candidate, prints the function symbol/address, the comparison
#      instruction, and the surrounding 32 bytes (a signature suitable for
#      sigscan re-patching).
#
# Output is suitable for direct paste into scripts/patch-subfief-cap-binary.py.
#
# Limitations:
#   - Ghidra's default auto-analysis may not name C++ symbols; you may need to
#     manually rename based on RTTI vtable references.
#   - The enum int value lookup assumes the UEnum metadata follows UE5's
#     standard layout (a TArray of pairs <FName, int64>).
#
# This script targets Ghidra 11.x with Python (Jython) interpreter.

# @category Reverse Engineering
# @author Dune self-host research
# @runtime PyGhidra

from ghidra.program.model.symbol import RefType
from ghidra.program.model.listing import CodeUnit
from ghidra.program.model.lang import OperandType
from ghidra.app.decompiler import DecompInterface
from ghidra.util.task import ConsoleTaskMonitor


TARGET_ENUM_NAME = "Fail_DisallowedBuildLimit"
CANDIDATE_FUNC_HINTS = (
    "OnInstigatorServerBeforeValidation_Internal",
    "PlaceBuildable",
    "SpawnBuildable",
    "TotemCanBePlaced",
    "BuildingSystemPlacementUtils",
)


def find_string_addr(program, needle):
    listing = program.getListing()
    mem = program.getMemory()
    for block in mem.getBlocks():
        if not block.isInitialized():
            continue
        if block.getName() != ".rodata":
            continue
        addr = block.getStart()
        end = block.getEnd()
        # Linear search for the substring
        bytes_needed = bytearray(needle, "ascii") + b"\x00"
        chunk_size = 0x100000
        offset = 0
        while addr.add(offset).compareTo(end) < 0:
            try:
                chunk = bytearray(chunk_size)
                read = mem.getBytes(addr.add(offset), chunk)
                pos = bytes(chunk[:read]).find(bytes(bytes_needed))
                if pos >= 0:
                    return addr.add(offset + pos)
                offset += chunk_size - len(bytes_needed)
            except Exception:
                offset += chunk_size
    return None


def find_xrefs(program, addr):
    rm = program.getReferenceManager()
    refs = []
    for ref in rm.getReferencesTo(addr):
        refs.append(ref)
    return refs


def walk_for_cap_cmp(program, listing, ref_addr, monitor):
    """From a reference site, walk backward in the same basic block / function
    looking for CMP / UCOMISS / VUCOMISS that gates entry to the fail branch."""
    fm = program.getFunctionManager()
    func = fm.getFunctionContaining(ref_addr)
    if func is None:
        return None, None
    body = func.getBody()
    # Disassemble between function entry and ref_addr; collect comparisons
    candidates = []
    instr = listing.getInstructionAt(func.getEntryPoint())
    while instr is not None and body.contains(instr.getAddress()):
        if monitor.isCancelled():
            return None, None
        if instr.getAddress().compareTo(ref_addr) > 0:
            break
        mnem = instr.getMnemonicString()
        if mnem in ("CMP", "UCOMISS", "COMISS", "VUCOMISS", "VCOMISS"):
            opnd_count = instr.getNumOperands()
            for i in range(opnd_count):
                ot = instr.getOperandType(i)
                if (ot & OperandType.SCALAR) != 0:
                    val = instr.getScalar(i)
                    if val is not None:
                        v = val.getValue()
                        if 1 <= v <= 50:
                            candidates.append((instr.getAddress(), instr, v))
                            break
        instr = instr.getNext()
    return func, candidates


def decompile_function(program, func):
    decomp = DecompInterface()
    decomp.openProgram(program)
    res = decomp.decompileFunction(func, 60, ConsoleTaskMonitor())
    if res.decompileCompleted():
        return res.getDecompiledFunction().getC()
    return None


def main():
    program = getCurrentProgram()
    listing = program.getListing()
    monitor = ConsoleTaskMonitor()

    print("=" * 70)
    print("Subfief / Totem placement cap locator")
    print("=" * 70)

    print("\nSearching .rodata for %r..." % TARGET_ENUM_NAME)
    full_string = "EBuildingSystemActionResult::" + TARGET_ENUM_NAME
    addr = find_string_addr(program, full_string)
    if addr is None:
        print("  not found — fall back to bare enum name")
        addr = find_string_addr(program, TARGET_ENUM_NAME)
    if addr is None:
        print("  FATAL: enum string not found")
        return
    print("  found @ %s" % addr)

    refs = find_xrefs(program, addr)
    print("\nReferences to enum string: %d" % len(refs))
    for ref in refs:
        print("  - %s (%s)" % (ref.getFromAddress(), ref.getReferenceType()))

    print("\nCmp/UCOMISS candidates in each referencing function:")
    seen_funcs = set()
    for ref in refs:
        from_addr = ref.getFromAddress()
        func, cmps = walk_for_cap_cmp(program, listing, from_addr, monitor)
        if func is None or func.getEntryPoint() in seen_funcs:
            continue
        seen_funcs.add(func.getEntryPoint())
        if not cmps:
            continue
        name = func.getName()
        print("\n  Function %s @ %s" % (name, func.getEntryPoint()))
        for caddr, instr, val in cmps[-6:]:
            sig_bytes = []
            cur = caddr.subtract(16)
            for _ in range(32):
                try:
                    sig_bytes.append("%02x" % (program.getMemory().getByte(cur) & 0xFF))
                except Exception:
                    sig_bytes.append("??")
                cur = cur.add(1)
            print("    @ %s : %s  imm=%d  sig=%s" %
                  (caddr, instr, val, " ".join(sig_bytes)))
            # Also print a few preceding instructions for context
            cur = caddr
            preceding = []
            for _ in range(6):
                p = listing.getInstructionBefore(cur)
                if p is None:
                    break
                preceding.append(p)
                cur = p.getAddress()
            preceding.reverse()
            for p in preceding:
                print("       %s : %s" % (p.getAddress(), p))

    print("\nDone. Inspect candidates above. The most likely patch site is a")
    print("CMP/UCOMISS against a small int (3) that branches into a block that")
    print("writes the Fail_DisallowedBuildLimit enum value to a result struct.")


main()
