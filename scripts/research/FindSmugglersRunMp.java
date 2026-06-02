// Ghidra headless script for SmugglersRunMP native discovery.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -noanalysis \
//     -postScript FindSmugglersRunMp.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/smugglers-run-mp-ghidra.log
//
// Output:
//   /tmp/ghidra-work/smugglers-run-mp-findings.txt
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

public class FindSmugglersRunMp extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/smugglers-run-mp-findings.txt";
    private static final int MAX_DECOMPILES = 160;

    private static final String[] NEEDLES = new String[] {
        "CB_Overland_S_06",
        "GroundVehicleTimeTrialIsland",
        "GroundVehicleTimeTrial",
        "TimeTrial",
        "Time Trial",
        "Smugglers",
        "Smuggler",
        "Race",
        "Checkpoint",
        "Lap",
        "Leaderboard",
        "Winner",
        "Loser",
        "StartRace",
        "FinishRace",
        "VehicleOwnership",
        "OwnerVehicle",
        "m_OwnerVehicle",
        "DropVehicle",
        "RecoverVehicle",
        "RecoveredVehicles",
        "BackupVehicle",
        "restore_recovered_vehicle",
        "restore_backup_vehicle",
        "store_recovered_vehicle",
        "get_player_owned_vehicles_data",
        "SpawnVehicle",
        "SpawnVehicleAt"
    };

    private PrintWriter out;
    private ReferenceManager refs;
    private DecompInterface decomp;
    private final Map<Address, String> interestingFunctions = new LinkedHashMap<>();

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
            dumpNeedles(loadNeedles());
            decompileInterestingFunctions();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private List<String> loadNeedles() {
        LinkedHashSet<String> values = new LinkedHashSet<>();
        for (String needle : NEEDLES) values.add(needle);
        String extra = System.getenv("DUNE_SMUGGLERS_RUN_EXTRA_NEEDLES");
        if (extra != null) {
            for (String item : extra.split(",")) {
                String trimmed = item.trim();
                if (!trimmed.isEmpty()) values.add(trimmed);
            }
        }
        return new ArrayList<>(values);
    }

    private void dumpNeedles(List<String> needles) throws Exception {
        log("");
        log("== named needle xrefs");
        for (String needle : needles) {
            List<StringHit> hits = findStringBytes(needle);
            hits.sort(Comparator.comparing(h -> h.address));
            log("");
            log("-- " + needle + " hits=" + hits.size());
            int xrefHits = 0;
            for (StringHit hit : hits) {
                if (logStringHit(hit)) xrefHits++;
            }
            log("xref_hits=" + xrefHits + " no_xref_hits=" + (hits.size() - xrefHits));
        }
    }

    private List<StringHit> findStringBytes(String needle) {
        List<StringHit> hits = new ArrayList<>();
        Memory mem = currentProgram.getMemory();
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
        ReferenceIterator rit = refs.getReferencesTo(hit.address);
        List<String> froms = new ArrayList<>();
        Set<Address> entries = new LinkedHashSet<>();
        while (rit.hasNext()) {
            Reference ref = rit.next();
            Address from = ref.getFromAddress();
            Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
            String fdesc = f == null ? "" : " func=" + f.getName() + " entry=" + f.getEntryPoint();
            froms.add(from + " " + ref.getReferenceType() + fdesc);
            if (f != null) entries.add(f.getEntryPoint());
        }
        if (froms.isEmpty()) return false;
        log("string " + hit.address + " encoding=" + hit.encoding + " refs=" + froms.size() + " value=\"" + clean(hit.value) + "\"");
        for (String from : froms) log("  ref " + from);
        for (Address entry : entries) {
            if (interestingFunctions.size() >= MAX_DECOMPILES) break;
            String prev = interestingFunctions.get(entry);
            interestingFunctions.put(entry, prev == null ? clean(hit.value) : prev + ", " + clean(hit.value));
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
                for (String needle : loadNeedles()) {
                    if (lower.contains(needle.toLowerCase())) {
                        for (int j = Math.max(0, i - 8); j <= Math.min(lines.size() - 1, i + 12); j++) {
                            selected.add(j);
                        }
                    }
                }
            }
            for (Integer idx : selected) {
                log(String.format("%5d: %s", idx + 1, lines.get(idx)));
            }
        }
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
