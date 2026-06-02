// Ghidra headless script to inspect Base Reconstruction Tool native class
// symbols, RTTI/vtables, callback thunks, and decompiled snippets.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -noanalysis \
//     -postScript DumpBaseBackupClassSurface.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/base-backup-class-surface-ghidra.log
//
// Output:
//   /tmp/ghidra-work/base-backup-class-surface-findings.txt
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
import java.util.Arrays;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class DumpBaseBackupClassSurface extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/base-backup-class-surface-findings.txt";
    private static final int MAX_DECOMPILES = 260;
    private static final int MAX_VTABLE_ENTRIES = 90;

    private static final String[] SYMBOL_TERMS = new String[] {
        "BaseBackupActionPlace",
        "BaseBackupActionBackup",
        "BaseBackupActionForget",
        "BaseBackupActionRecycle",
        "BaseBackupActionPlaceResponse",
        "BuildingBlueprintBackupToolPlayerCharacterComponent",
        "BuildingReplicationComponent",
        "ServerRequestBaseBackup",
        "PlaceBlueprint",
        "BackupBlueprint",
        "ForgetBlueprint",
        "RecycleBlueprint",
        "StartBuilding",
        "LoadAvailableBaseBackups",
        "UpdateNearbyTotem",
        "OnReceivedDeployableRestrictionsResponse"
    };

    private static final String[] STRING_TERMS = new String[] {
        "UBaseBackupActionPlace",
        "UBaseBackupActionBackup",
        "UBaseBackupActionPlaceResponse",
        "UBuildingBlueprintBackupToolPlayerCharacterComponent",
        "ServerRequestBaseBackup_Implementation",
        "PlaceBlueprint",
        "BackupBlueprint",
        "StartBuilding",
        "UpdateNearbyTotem",
        "OnReceivedDeployableRestrictionsResponse",
        "TryPerformActionWithCallback",
        "IsLandclaimInsideServerBoundaries",
        "EBuildingBlueprintCanBePlacedType",
        "m_SoftBuildableMapRegionDataTable",
        "m_BuildingsForValidation",
        "m_MaxLandclaimSegmentsPerMap",
        "m_bEnableBuildingRestrictionLimitsCheat",
        "SetBuildingRestrictionLimitsEnabled",
        "DeepDesert",
        "HaggaBasin",
        "Survival_1"
    };

    private PrintWriter out;
    private Memory mem;
    private ReferenceManager refs;
    private DecompInterface decomp;
    private final Map<Address, String> interestingFunctions = new LinkedHashMap<>();

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
            log("Pointer size: " + currentProgram.getDefaultPointerSize());
            dumpSymbols();
            dumpStrings();
            decompileInterestingFunctions();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpSymbols() throws Exception {
        log("");
        log("== matching symbols");
        List<Symbol> matches = new ArrayList<>();
        SymbolIterator iter = currentProgram.getSymbolTable().getAllSymbols(true);
        while (iter.hasNext()) {
            Symbol symbol = iter.next();
            String name = symbol.getName();
            String demangled = symbol.getName(true);
            String combined = name + " " + demangled;
            if (containsAny(combined, SYMBOL_TERMS)) {
                matches.add(symbol);
            }
        }
        matches.sort(Comparator.comparing(Symbol::getAddress));
        for (Symbol symbol : matches) {
            String name = symbol.getName();
            String demangled = symbol.getName(true);
            Address addr = symbol.getAddress();
            log("symbol " + addr + " type=" + symbol.getSymbolType() + " name=" + name + " demangled=" + demangled);
            Function f = currentProgram.getFunctionManager().getFunctionContaining(addr);
            if (f != null) addFunction(f, "symbol:" + name);
            if (name.startsWith("_ZTV") || name.contains("vtable")) dumpVtable(symbol);
            dumpRefsToRange(addr, 16, "symbol:" + name);
        }
    }

    private void dumpVtable(Symbol symbol) throws Exception {
        Address base = symbol.getAddress();
        int pointerSize = currentProgram.getDefaultPointerSize();
        boolean decompileTargets = shouldDecompileVtable(symbol.getName(true));
        log("  vtable-dump base=" + base + " entries=" + MAX_VTABLE_ENTRIES);
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
                if (decompileTargets) addFunction(f, "vtable:" + symbol.getName(true) + "[" + i + "]");
            }
            log("    [" + i + "] " + slot + " -> " + target + fdesc);
        }
    }

    private void dumpRefsToRange(Address base, int span, String label) throws Exception {
        Set<Address> entries = new LinkedHashSet<>();
        List<String> froms = new ArrayList<>();
        for (int i = 0; i < span; i++) {
            Address addr = base.add(i);
            ReferenceIterator rit = refs.getReferencesTo(addr);
            while (rit.hasNext()) {
                Reference ref = rit.next();
                Address from = ref.getFromAddress();
                Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
                String fdesc = f == null ? "" : " func=" + f.getName() + " entry=" + f.getEntryPoint();
                froms.add(from + " -> " + addr + " " + ref.getReferenceType() + fdesc);
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

    private void dumpStrings() throws Exception {
        log("");
        log("== string xrefs");
        for (String term : STRING_TERMS) {
            List<StringHit> hits = findStringBytes(term);
            hits.sort(Comparator.comparing(h -> h.address));
            log("");
            log("-- " + term + " hits=" + hits.size());
            int xrefHits = 0;
            for (StringHit hit : hits) {
                if (logStringHit(hit)) xrefHits++;
            }
            log("xref_hits=" + xrefHits + " no_xref_hits=" + (hits.size() - xrefHits));
        }
    }

    private List<StringHit> findStringBytes(String needle) {
        List<StringHit> hits = new ArrayList<>();
        for (Encoding encoding : new Encoding[] {Encoding.ASCII, Encoding.UTF16LE}) {
            byte[] pattern = encoding.bytes(needle);
            Address start = mem.getMinAddress();
            Address max = mem.getMaxAddress();
            while (start != null && start.compareTo(max) <= 0) {
                Address hit = mem.findBytes(start, max, pattern, null, true, monitor);
                if (hit == null) break;
                hits.add(new StringHit(hit, needle, encoding.name));
                start = hit.add(1);
            }
        }
        return hits;
    }

    private boolean logStringHit(StringHit hit) throws Exception {
        int span = hit.encoding.equals("utf16le") ? hit.value.length() * 2 : hit.value.length();
        List<String> froms = new ArrayList<>();
        Set<Address> entries = new LinkedHashSet<>();
        for (int i = 0; i <= span; i++) {
            Address addr = hit.address.add(i);
            ReferenceIterator rit = refs.getReferencesTo(addr);
            while (rit.hasNext()) {
                Reference ref = rit.next();
                Address from = ref.getFromAddress();
                Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
                String fdesc = f == null ? "" : " func=" + f.getName() + " entry=" + f.getEntryPoint();
                froms.add(from + " -> " + addr + " " + ref.getReferenceType() + fdesc);
                if (f != null) entries.add(f.getEntryPoint());
            }
        }
        if (froms.isEmpty()) return false;
        log("string " + hit.address + " encoding=" + hit.encoding + " refs=" + froms.size()
                + " value=\"" + clean(hit.value) + "\"");
        for (String from : froms) log("  ref " + from);
        for (Address entry : entries) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (f != null) addFunction(f, "string:" + clean(hit.value));
        }
        return true;
    }

    private void decompileInterestingFunctions() throws Exception {
        log("");
        log("== decompile interesting functions count=" + interestingFunctions.size());
        for (Map.Entry<Address, String> item : interestingFunctions.entrySet()) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(item.getKey());
            if (f == null) continue;
            log("");
            log("-- function " + f.getName() + " @ " + f.getEntryPoint() + " labels=" + item.getValue());
            DecompileResults res = decomp.decompileFunction(f, 90, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
                continue;
            }
            String c = res.getDecompiledFunction().getC();
            List<String> lines = Arrays.asList(c.split("\n"));
            Set<Integer> selected = new LinkedHashSet<>();
            for (int i = 0; i < lines.size(); i++) {
                String lower = lines.get(i).toLowerCase();
                if (containsAny(lower, lowerTerms(STRING_TERMS)) || containsAny(lower, lowerTerms(SYMBOL_TERMS)) ||
                        lower.contains("landclaim") || lower.contains("buildable") || lower.contains("backup") ||
                        lower.contains("deepdesert") || lower.contains("hagga") || lower.contains("survival_1") ||
                        lower.contains("restriction") || lower.contains("permission") || lower.contains("totem")) {
                    for (int j = Math.max(0, i - 8); j <= Math.min(lines.size() - 1, i + 14); j++) {
                        selected.add(j);
                    }
                }
            }
            if (selected.isEmpty() && item.getValue().contains("vtable:")) {
                for (int j = 0; j < Math.min(lines.size(), 35); j++) selected.add(j);
            }
            for (Integer idx : selected) {
                log(String.format("%5d: %s", idx + 1, lines.get(idx)));
            }
        }
    }

    private void addFunction(Function f, String label) {
        if (interestingFunctions.size() >= MAX_DECOMPILES && !interestingFunctions.containsKey(f.getEntryPoint())) return;
        String prev = interestingFunctions.get(f.getEntryPoint());
        interestingFunctions.put(f.getEntryPoint(), prev == null ? label : prev + ", " + label);
    }

    private boolean shouldDecompileVtable(String name) {
        if (name.contains("TBaseUObjectMethodDelegateInstance")) return false;
        return name.contains("BaseBackupAction") ||
                name.contains("BuildingBlueprintBackupToolPlayerCharacterComponent");
    }

    private Address readPointer(Address slot) throws Exception {
        long raw;
        int pointerSize = currentProgram.getDefaultPointerSize();
        if (pointerSize == 8) {
            raw = mem.getLong(slot);
        } else {
            raw = Integer.toUnsignedLong(mem.getInt(slot));
        }
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
        String[] lowered = new String[terms.length];
        for (int i = 0; i < terms.length; i++) lowered[i] = terms[i].toLowerCase();
        return lowered;
    }

    private void log(String line) {
        println(line);
        out.println(line);
    }

    private String clean(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private enum Encoding {
        ASCII("ascii"),
        UTF16LE("utf16le");

        final String name;
        Encoding(String name) {
            this.name = name;
        }

        byte[] bytes(String value) {
            try {
                if (this == UTF16LE) return value.getBytes("UTF-16LE");
                return value.getBytes("US-ASCII");
            } catch (Exception exc) {
                throw new RuntimeException(exc);
            }
        }
    }

    private static class StringHit {
        final Address address;
        final String value;
        final String encoding;

        StringHit(Address address, String value, String encoding) {
            this.address = address;
            this.value = value;
            this.encoding = encoding;
        }
    }
}
