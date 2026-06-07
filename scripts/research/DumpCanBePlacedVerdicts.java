// Ghidra headless script: enumerate the building-placement verdict enum
// (EBuildingBlueprintCanBePlacedType) and every site that emits each verdict,
// for docs/brt-deep-desert-plan.md Phase 2 ("find the true reject emitter").
//
// Why this instead of grepping for an English string: the player-visible
// "not allowed in the region" text is almost certainly FText localization in a
// client .locres, not a literal in the server binary. The server side keys off
// the verdict enum value (Fail_InvalidMap = 0x88, Success = 0x01 are already
// known from the patch scripts). This script reports:
//   1. the enum's (name -> value) map when the type is present;
//   2. for each verdict-name string, the functions that reference it;
//   3. for the DD-relevant verdicts, the immediate-byte store sites
//      (mov byte ptr [reg+disp], imm) that write that value, as image-relative
//      offsets, so they can be compared against the four sites
//      patch-brt-dd-invalid-map-binary.py currently flips.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin -noanalysis \
//     -postScript DumpCanBePlacedVerdicts.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/canbeplaced-verdicts-ghidra.log
//
// Output:
//   /tmp/ghidra-work/canbeplaced-verdicts.txt
//
// @category Reverse Engineering

import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.DataType;
import ghidra.program.model.data.Enum;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.scalar.Scalar;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class DumpCanBePlacedVerdicts extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/canbeplaced-verdicts.txt";
    private static final String ENUM_NAME = "EBuildingBlueprintCanBePlacedType";

    // Verdict variants worth resolving by name string (the enum may not be a
    // recovered type, so we also xref the namespaced strings directly).
    private static final String[] VERDICTS = new String[] {
        "Success",
        "Fail_InvalidMap",
        "Fail_DisallowedBuildArea",
        "Fail_DisallowedLocation",
        "Fail_DisallowedBuildLimit",
        "Fail_NoLandClaim",
        "IsInHeightLimit",
        "IsLandclaimInsideServerBoundaries",
    };

    // DD-relevant verdicts whose immediate-store sites we additionally scan for.
    // Value map is filled from the recovered enum if present; otherwise only the
    // known Fail_InvalidMap=0x88 is scanned.
    private PrintWriter out;
    private ReferenceManager refs;
    private long imageBase;

    @Override
    public void run() throws Exception {
        out = new PrintWriter(new FileWriter(OUT));
        refs = currentProgram.getReferenceManager();
        imageBase = currentProgram.getImageBase().getOffset();
        try {
            log("Output: " + OUT);
            log("Program: " + currentProgram.getName());
            log("Image base: 0x" + Long.toHexString(imageBase));
            Enum verdictEnum = findEnum();
            dumpEnum(verdictEnum);
            dumpVerdictStringXrefs();
            dumpInvalidMapStores();
        } finally {
            out.close();
        }
    }

    private Enum findEnum() {
        Iterator<DataType> it = currentProgram.getDataTypeManager().getAllDataTypes();
        while (it.hasNext()) {
            DataType dt = it.next();
            if (dt instanceof Enum && dt.getName().contains(ENUM_NAME)) {
                return (Enum) dt;
            }
        }
        return null;
    }

    private void dumpEnum(Enum verdictEnum) {
        log("");
        log("== enum " + ENUM_NAME);
        if (verdictEnum == null) {
            log("   enum type not recovered; values inferred only from patch scripts");
            log("   known: Success=0x01, Fail_InvalidMap=0x88");
            return;
        }
        for (String name : verdictEnum.getNames()) {
            long value = verdictEnum.getValue(name);
            log(String.format("   %-40s = 0x%x (%d)", name, value, value));
        }
    }

    private void dumpVerdictStringXrefs() throws Exception {
        log("");
        log("== verdict-name string xrefs (offsets image-base-relative)");
        for (String verdict : VERDICTS) {
            String needle = ENUM_NAME + "::" + verdict;
            List<Address> hits = findStringBytes(needle);
            if (hits.isEmpty()) {
                // Some builds store the bare variant name without the enum prefix.
                hits = findStringBytes(verdict);
                needle = verdict + " (bare)";
            }
            log("");
            log("-- " + needle + " hits=" + hits.size());
            Set<Long> entries = new LinkedHashSet<>();
            for (Address hit : hits) {
                for (Address entry : xrefFunctionEntries(hit, needle)) {
                    entries.add(entry.getOffset() - imageBase);
                }
            }
            if (entries.isEmpty()) {
                log("   no function xref");
            } else {
                for (long rel : entries) log(String.format("   func entry 0x%x", rel));
            }
        }
    }

    // Scan for `mov byte ptr [reg + disp], 0x88` style stores of Fail_InvalidMap
    // across all functions, reporting each as an image-relative offset. This
    // generalizes patch-brt-dd-invalid-map-binary.py, which scopes to one
    // function; cross-check the four it patches against the full set here.
    private void dumpInvalidMapStores() {
        log("");
        log("== Fail_InvalidMap (0x88) immediate-store sites (image-base-relative)");
        int count = 0;
        Instruction insn = getFirstInstruction();
        while (insn != null) {
            if ("MOV".equalsIgnoreCase(insn.getMnemonicString()) && writesImmByte(insn, 0x88)) {
                Function f = getFunctionContaining(insn.getAddress());
                long rel = insn.getAddress().getOffset() - imageBase;
                String fdesc = f == null ? "" : " in func 0x" + Long.toHexString(f.getEntryPoint().getOffset() - imageBase);
                log(String.format("   store @ 0x%x%s : %s", rel, fdesc, insn.toString()));
                count++;
            }
            insn = insn.getNext();
            if (monitor.isCancelled()) break;
        }
        log("   total 0x88 byte-store sites: " + count);
    }

    private boolean writesImmByte(Instruction insn, int value) {
        // crude: a byte MOV with a scalar source equal to `value` and a memory dest.
        int n = insn.getNumOperands();
        if (n < 2) return false;
        Object[] src = insn.getOpObjects(n - 1);
        boolean immMatch = false;
        for (Object o : src) {
            if (o instanceof Scalar && ((Scalar) o).getUnsignedValue() == value) immMatch = true;
        }
        if (!immMatch) return false;
        // Heuristic: destination operand 0 is dynamic (memory) reference.
        return insn.getOperandRefType(0).isWrite();
    }

    private Set<Address> xrefFunctionEntries(Address stringAddr, String needle) {
        Set<Address> entries = new LinkedHashSet<>();
        int span = needle.length() + 1;
        for (int i = 0; i <= span; i++) {
            ReferenceIterator rit = refs.getReferencesTo(stringAddr.add(i));
            while (rit.hasNext()) {
                Reference ref = rit.next();
                Function f = getFunctionContaining(ref.getFromAddress());
                if (f != null) entries.add(f.getEntryPoint());
            }
        }
        return entries;
    }

    private Function getFunctionContaining(Address a) {
        return currentProgram.getFunctionManager().getFunctionContaining(a);
    }

    private List<Address> findStringBytes(String needle) {
        List<Address> hits = new ArrayList<>();
        Memory mem = currentProgram.getMemory();
        for (byte[] pattern : new byte[][] {asciiBytes(needle), utf16Bytes(needle)}) {
            Address start = mem.getMinAddress();
            Address max = mem.getMaxAddress();
            while (start != null && start.compareTo(max) <= 0) {
                Address hit = mem.findBytes(start, max, pattern, null, true, monitor);
                if (hit == null) break;
                hits.add(hit);
                start = hit.add(1);
            }
        }
        return hits;
    }

    private byte[] asciiBytes(String value) {
        try { return value.getBytes("US-ASCII"); } catch (Exception e) { throw new RuntimeException(e); }
    }

    private byte[] utf16Bytes(String value) {
        try { return value.getBytes("UTF-16LE"); } catch (Exception e) { throw new RuntimeException(e); }
    }

    private void log(String line) {
        println(line);
        out.println(line);
    }
}
