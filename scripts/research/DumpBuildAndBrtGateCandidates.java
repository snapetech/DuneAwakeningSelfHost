// Ghidra headless script to dump focused decompilation and branch context for
// the currently open build/BRT gates:
//   - player-visible subfief/totem 3/3 count cap
//   - Base Reconstruction Tool "not allowed in this region" gating
//
// Output:
//   /tmp/ghidra-work/build-brt-gate-candidates.txt
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.Arrays;
import java.util.LinkedHashSet;
import java.util.Set;

public class DumpBuildAndBrtGateCandidates extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/build-brt-gate-candidates.txt";

    private static final long[] FOCUS_ADDRS = new long[] {
        0x0cf70210L, // BuildingSystemActionPlaceBuildable.cpp large validator
        0x0cf7ac80L, // BuildingSystemActionSpawnBuildable.cpp
        0x0cedcb40L, // DuneTotemCanBePlaced.cpp
        0x0d04d020L, // InsideLandclaimCanBePlaced.cpp
        0x0cddc9d0L, // Fail_DisallowedBuildLimit writer path
        0x0d048810L, // second Fail_DisallowedBuildLimit writer path
        0x0edf0f20L, // validity stub from prior notes
        0x0fa7ec90L, // validity wrapper from prior notes
        0x12e2d140L  // inner validity callee from prior notes
    };

    private static final String[] NEEDLES = new String[] {
        "Fail_DisallowedBuildLimit",
        "Fail_DisallowedBuildArea",
        "Fail_DisallowedLocation",
        "Fail_NoLandClaim",
        "BaseBackupActionPlace",
        "BuildingBlueprintBackupToolPlayerCharacterComponent",
        "ServerRequestBaseBackup_Implementation",
        "m_BaseBackupToolMapRestriction",
        "m_SoftBuildableMapRegionDataTable",
        "BuildableMapRegionDataRow",
        "MapRegionBuildablesData",
        "MapAreaBuildableRestrictionData",
        "DeepDesert",
        "HaggaBasin",
        "SubfiefCount",
        "SubfiefLimitBonus"
    };

    private PrintWriter out;
    private ReferenceManager refs;
    private DecompInterface decomp;
    private final Set<Address> functions = new LinkedHashSet<>();

    @Override
    public void run() throws Exception {
        out = new PrintWriter(new FileWriter(OUT));
        refs = currentProgram.getReferenceManager();
        decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        try {
            log("Output: " + OUT);
            log("Program: " + currentProgram.getName());
            log("Image base: " + currentProgram.getImageBase());

            for (long off : FOCUS_ADDRS) {
                addFunctionAt(off, "focus");
            }
            scanNeedles();
            dumpFunctions();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void addFunctionAt(long off, String reason) {
        Address addr = toAddr(off);
        Function f = currentProgram.getFunctionManager().getFunctionContaining(addr);
        if (f == null) {
            log("no function for " + reason + " @ " + addr);
            return;
        }
        functions.add(f.getEntryPoint());
        log("add " + reason + " addr=" + addr + " func=" + f.getName() + " entry=" + f.getEntryPoint());
    }

    private void scanNeedles() throws Exception {
        Memory mem = currentProgram.getMemory();
        log("");
        log("== string xrefs");
        for (String needle : NEEDLES) {
            log("-- " + needle);
            int hits = 0;
            for (Encoding enc : new Encoding[] {Encoding.ASCII, Encoding.UTF16LE}) {
                byte[] pattern = enc.bytes(needle);
                Address start = mem.getMinAddress();
                Address max = mem.getMaxAddress();
                while (start != null && start.compareTo(max) <= 0) {
                    Address hit = mem.findBytes(start, max, pattern, null, true, monitor);
                    if (hit == null) break;
                    hits++;
                    collectRefs(hit, enc.name + ":" + needle, enc.span(needle));
                    start = hit.add(1);
                }
            }
            log("hits=" + hits);
        }
    }

    private void collectRefs(Address hit, String label, int span) {
        int count = 0;
        for (int i = 0; i <= span; i++) {
            ReferenceIterator it = refs.getReferencesTo(hit.add(i));
            while (it.hasNext()) {
                Reference ref = it.next();
                count++;
                Address from = ref.getFromAddress();
                Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
                log("  ref " + from + " -> " + hit.add(i) + " " + ref.getReferenceType()
                        + (f == null ? "" : " func=" + f.getName() + " entry=" + f.getEntryPoint()));
                if (f != null) functions.add(f.getEntryPoint());
            }
        }
        if (count == 0) {
            log("  no refs " + hit + " " + label);
        }
    }

    private void dumpFunctions() throws Exception {
        log("");
        log("== functions " + functions.size());
        for (Address entry : functions) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (f == null) continue;
            log("");
            log("-- function " + f.getName() + " @ " + entry + " size=" + f.getBody().getNumAddresses());
            dumpBranchContext(f);
            dumpDecompile(f);
        }
    }

    private void dumpBranchContext(Function f) {
        log("  branch/context instructions:");
        Instruction ins = currentProgram.getListing().getInstructionAt(f.getEntryPoint());
        while (ins != null && f.getBody().contains(ins.getAddress())) {
            String mnemonic = ins.getMnemonicString().toLowerCase();
            String text = ins.toString().toLowerCase();
            boolean interesting = mnemonic.startsWith("j")
                    || mnemonic.equals("cmp")
                    || mnemonic.contains("comiss")
                    || mnemonic.equals("test")
                    || text.contains("0x6b")
                    || text.contains("0x7e")
                    || text.contains("0x7f");
            if (interesting) {
                log("    " + ins.getAddress() + ": " + ins);
            }
            ins = ins.getNext();
        }
    }

    private void dumpDecompile(Function f) throws Exception {
        DecompileResults res = decomp.decompileFunction(f, 120, new ConsoleTaskMonitor());
        if (!res.decompileCompleted()) {
            log("  decompile failed: " + res.getErrorMessage());
            return;
        }
        String[] lines = res.getDecompiledFunction().getC().split("\n");
        boolean full = f.getBody().getNumAddresses() <= 9000
                || f.getEntryPoint().equals(toAddr(0x0cf70210L))
                || f.getEntryPoint().equals(toAddr(0x0cedcb40L));
        if (full) {
            for (int i = 0; i < lines.length; i++) {
                log(String.format("  %04d: %s", i + 1, lines[i]));
            }
            return;
        }
        Set<Integer> selected = new LinkedHashSet<>();
        for (int i = 0; i < lines.length; i++) {
            String lower = lines[i].toLowerCase();
            for (String n : NEEDLES) {
                if (lower.contains(n.toLowerCase())) {
                    for (int j = Math.max(0, i - 12); j <= Math.min(lines.length - 1, i + 20); j++) {
                        selected.add(j);
                    }
                }
            }
        }
        if (selected.isEmpty()) {
            selected.addAll(Arrays.asList(0, 1, 2, 3, 4, Math.max(0, lines.length - 2), Math.max(0, lines.length - 1)));
        }
        for (int i : selected) {
            log(String.format("  %04d: %s", i + 1, lines[i]));
        }
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }

    private static class Encoding {
        static final Encoding ASCII = new Encoding("ascii");
        static final Encoding UTF16LE = new Encoding("utf16le");
        final String name;
        Encoding(String name) { this.name = name; }
        byte[] bytes(String s) throws Exception {
            return name.equals("utf16le") ? s.getBytes("UTF-16LE") : s.getBytes("UTF-8");
        }
        int span(String s) {
            return name.equals("utf16le") ? s.length() * 2 : s.length();
        }
    }
}
