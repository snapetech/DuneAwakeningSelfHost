// Focused Ghidra headless script for UGameItemBaseBackupToolActions.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -noanalysis \
//     -postScript DumpGameItemBaseBackupToolActions.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/gameitem-basebackup-actions-ghidra.log
//
// Output:
//   /tmp/ghidra-work/gameitem-basebackup-actions.txt
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.program.model.symbol.Symbol;
import ghidra.program.model.symbol.SymbolIterator;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class DumpGameItemBaseBackupToolActions extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/gameitem-basebackup-actions.txt";
    private static final int MAX_VTABLE_ENTRIES = 140;
    private static final int MAX_DECOMPILES = 160;

    private static final String[] TERMS = new String[] {
        "UGameItemBaseBackupToolActions",
        "GameItemBaseBackupToolActions",
        "BaseBackupTool",
        "BaseBackup",
        "BackupTool",
        "m_BaseBackupToolMapRestriction",
        "m_BaseBackupToolTimeRestrictionInSeconds",
        "DeepDesert",
        "DeepDesert_1",
        "HaggaBasin",
        "Survival_1",
        "CanBeUsed",
        "CanUse",
        "UseItem",
        "TryUse",
        "Restriction",
        "Region"
    };

    private PrintWriter out;
    private Memory mem;
    private ReferenceManager refs;
    private DecompInterface decomp;
    private final Map<Address, String> functions = new LinkedHashMap<>();

    @Override
    public void run() throws Exception {
        out = new PrintWriter(new FileWriter(OUT));
        mem = currentProgram.getMemory();
        refs = currentProgram.getReferenceManager();
        decomp = new DecompInterface();
        decomp.openProgram(currentProgram);
        try {
            log("Output: " + OUT);
            log("Program: " + currentProgram.getName());
            log("Image base: " + currentProgram.getImageBase());
            dumpMatchingSymbols();
            dumpStringXrefs();
            decompileFunctions();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpMatchingSymbols() throws Exception {
        log("");
        log("== matching symbols");
        List<Symbol> matches = new ArrayList<>();
        SymbolIterator iter = currentProgram.getSymbolTable().getAllSymbols(true);
        while (iter.hasNext()) {
            Symbol s = iter.next();
            String combined = s.getName() + " " + s.getName(true);
            if (containsAny(combined, TERMS)) {
                matches.add(s);
            }
        }
        matches.sort(Comparator.comparing(Symbol::getAddress));
        for (Symbol s : matches) {
            log("symbol " + s.getAddress() + " type=" + s.getSymbolType()
                    + " name=" + s.getName() + " demangled=" + s.getName(true));
            Function f = currentProgram.getFunctionManager().getFunctionContaining(s.getAddress());
            if (f != null) addFunction(f, "symbol:" + s.getName(true));
            if (s.getName(true).contains("vtable for UGameItemBaseBackupToolActions")
                    || s.getName().contains("ZTV30UGameItemBaseBackupToolActions")) {
                dumpVtable(s);
            }
            dumpRefsToRange(s.getAddress(), 16, "symbol:" + s.getName(true));
        }
    }

    private void dumpVtable(Symbol s) throws Exception {
        Address base = s.getAddress();
        int pointerSize = currentProgram.getDefaultPointerSize();
        log("  vtable base=" + base + " entries=" + MAX_VTABLE_ENTRIES);
        for (int i = 0; i < MAX_VTABLE_ENTRIES; i++) {
            Address slot = base.add((long) i * pointerSize);
            if (!mem.contains(slot)) break;
            Address target = readPointer(slot);
            if (target == null) {
                log("    [" + i + "] " + slot + " -> <null/unmapped>");
                continue;
            }
            Function f = currentProgram.getFunctionManager().getFunctionContaining(target);
            String fdesc = "";
            if (f != null) {
                fdesc = " func=" + f.getName() + " entry=" + f.getEntryPoint();
                addFunction(f, "vtable[" + i + "]");
            }
            log("    [" + i + "] " + slot + " -> " + target + fdesc);
        }
    }

    private void dumpStringXrefs() throws Exception {
        log("");
        log("== string xrefs");
        for (String term : TERMS) {
            List<Address> hits = findAscii(term);
            log("-- " + term + " hits=" + hits.size());
            for (Address hit : hits) {
                dumpRefsToRange(hit, term.length(), "string:" + term + "@" + hit);
            }
        }
    }

    private List<Address> findAscii(String value) throws Exception {
        List<Address> hits = new ArrayList<>();
        byte[] pattern = value.getBytes("US-ASCII");
        Address start = mem.getMinAddress();
        Address max = mem.getMaxAddress();
        while (start != null && start.compareTo(max) <= 0) {
            Address hit = mem.findBytes(start, max, pattern, null, true, monitor);
            if (hit == null) break;
            hits.add(hit);
            start = hit.add(1);
        }
        return hits;
    }

    private void dumpRefsToRange(Address base, int span, String label) throws Exception {
        List<String> froms = new ArrayList<>();
        Set<Address> entries = new LinkedHashSet<>();
        for (int i = 0; i <= span; i++) {
            ReferenceIterator rit = refs.getReferencesTo(base.add(i));
            while (rit.hasNext()) {
                Reference ref = rit.next();
                Address from = ref.getFromAddress();
                Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
                String fdesc = f == null ? "" : " func=" + f.getName() + " entry=" + f.getEntryPoint();
                froms.add(from + " -> " + base.add(i) + " " + ref.getReferenceType() + fdesc);
                if (f != null) entries.add(f.getEntryPoint());
            }
        }
        if (froms.isEmpty()) return;
        log("  refs label=" + label + " count=" + froms.size());
        for (String from : froms) log("    ref " + from);
        for (Address entry : entries) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (f != null) addFunction(f, label);
        }
    }

    private void decompileFunctions() throws Exception {
        log("");
        log("== decompile functions count=" + functions.size());
        for (Map.Entry<Address, String> item : functions.entrySet()) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(item.getKey());
            if (f == null) continue;
            log("");
            log("-- function " + f.getName() + " @ " + f.getEntryPoint() + " labels=" + item.getValue());
            DecompileResults res = decomp.decompileFunction(f, 90, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
                continue;
            }
            String[] lines = res.getDecompiledFunction().getC().split("\n");
            Set<Integer> selected = new LinkedHashSet<>();
            for (int i = 0; i < lines.length; i++) {
                String lower = lines[i].toLowerCase();
                if (containsAny(lower, lowerTerms(TERMS)) ||
                        lower.contains("backup") ||
                        lower.contains("region") ||
                        lower.contains("restriction") ||
                        lower.contains("map") ||
                        lower.contains("use")) {
                    for (int j = Math.max(0, i - 8); j <= Math.min(lines.length - 1, i + 14); j++) {
                        selected.add(j);
                    }
                }
            }
            if (selected.isEmpty() && item.getValue().contains("vtable[")) {
                for (int i = 0; i < Math.min(lines.length, 40); i++) selected.add(i);
            }
            for (Integer i : selected) log(String.format("%5d: %s", i + 1, lines[i]));
        }
    }

    private void addFunction(Function f, String label) {
        if (functions.size() >= MAX_DECOMPILES && !functions.containsKey(f.getEntryPoint())) return;
        String prev = functions.get(f.getEntryPoint());
        functions.put(f.getEntryPoint(), prev == null ? label : prev + ", " + label);
    }

    private Address readPointer(Address slot) throws Exception {
        long raw = currentProgram.getDefaultPointerSize() == 8 ? mem.getLong(slot) : Integer.toUnsignedLong(mem.getInt(slot));
        if (raw == 0) return null;
        Address target = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(raw);
        if (!mem.contains(target)) return null;
        return target;
    }

    private boolean containsAny(String value, String[] terms) {
        for (String term : terms) {
            if (value.contains(term)) return true;
        }
        return false;
    }

    private String[] lowerTerms(String[] terms) {
        String[] out = new String[terms.length];
        for (int i = 0; i < terms.length; i++) out[i] = terms[i].toLowerCase();
        return out;
    }

    private void log(String line) {
        println(line);
        out.println(line);
    }
}
