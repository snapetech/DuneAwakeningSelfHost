// Ghidra headless script to enumerate Dune GM/cheat/server-command strings,
// xrefs, and decompiled caller snippets.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -noanalysis \
//     -postScript DumpGmCommandSurface.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/gm-command-surface-ghidra.log
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

public class DumpGmCommandSurface extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/gm-command-surface-findings.txt";
    private static final int MAX_DECOMPILES = 180;

    private static final String[] DEFAULT_NEEDLES = new String[] {
        "UDuneServerCommandSubsystem",
        "UDuneServerCommandsCheatManager",
        "DuneServerCommandsCheatManager",
        "DuneCheatManager",
        "S2sCheatManager",
        "FlsCheatManager",
        "AdminLogin",
        "PrintAllowedCommands",
        "PrintPos",
        "ServerCommand",
        "SendDuneServerCommand",
        "ServerExecRPC",
        "ServiceBroadcastServerCommand",
        "UServiceMessageCommand",
        "AddItemToInventory",
        "AddBasicInventoryToCharacter",
        "AddItemToVehicleInventory",
        "AddItemsToInventory",
        "AwardXP",
        "AwardXPByEventTag",
        "SpawnVehicle",
        "SpawnVehicleAt",
        "TeleportTo",
        "TeleportToExact",
        "TeleportToMap",
        "TeleportToPlayer",
        "TeleportToSandworm",
        "TeleportToPersonalMarker",
        "TeleportToVehicleSpawner",
        "TeleportToClosestSurveyPoint",
        "TeleportToClosestUnrevealedSurveyPoint",
        "TeleportToNearestExplorationVolume",
        "TeleportToNearestNpc",
        "TeleportToSpawnLocation",
        "TravelTo",
        "TravelToDimension",
        "TravelToLocation",
        "TravelToOverland",
        "Fly",
        "Ghost",
        "Walk",
        "DestroyTargetVehicle",
        "DestroyBuildingPiece",
        "DestroyEntireBuilding",
        "DestroyPlaceable",
        "DestroyTotem",
        "DestroyAllNpcs",
        "DestroyAllSandStorms",
        "DestroyAllVehicles",
        "DestroyPawns",
        "KickPlayer",
        "ClientWasKicked",
        "ClientReturnToMainMenu",
        "ClientReturnToMainMenuWithTextReason",
        "ClientLogOff",
        "RemoveSessionMember",
        "KickLobbyMember",
        "BattlEyeMegaKick"
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
        for (String needle : DEFAULT_NEEDLES) values.add(needle);
        String extra = System.getenv("DUNE_GM_SURFACE_EXTRA_NEEDLES");
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
            log("");
            log("-- " + needle + " hits=" + hits.size());
            int printed = 0;
            hits.sort(Comparator.comparing(h -> h.address));
            for (StringHit hit : hits) {
                if (logStringHit(hit)) {
                    printed++;
                }
            }
            log("xref_hits=" + printed + " no_xref_hits=" + (hits.size() - printed));
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
        Address addr = hit.address;
        ReferenceIterator rit = refs.getReferencesTo(addr);
        List<String> froms = new ArrayList<>();
        Set<Address> entries = new LinkedHashSet<>();
        while (rit.hasNext()) {
            Reference ref = rit.next();
            Address from = ref.getFromAddress();
            Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
            String fdesc = f == null ? "" : " func=" + f.getName() + " entry=" + f.getEntryPoint();
            froms.add(from + " " + ref.getReferenceType() + fdesc);
            if (f != null) {
                entries.add(f.getEntryPoint());
            }
        }
        if (froms.isEmpty()) {
            return false;
        }
        log("string " + addr + " encoding=" + hit.encoding + " refs=" + froms.size() + " value=\"" + clean(hit.value) + "\"");
        for (String from : froms) {
            log("  ref " + from);
        }
        for (Address entry : entries) {
            if (interestingFunctions.size() >= MAX_DECOMPILES) break;
            String prev = interestingFunctions.get(entry);
            String label = clean(hit.value);
            interestingFunctions.put(entry, prev == null ? label : prev + ", " + label);
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
                String line = lines.get(i);
                if (isInterestingLine(line)) {
                    for (int j = Math.max(0, i - 4); j <= Math.min(lines.size() - 1, i + 8); j++) {
                        selected.add(j);
                    }
                }
            }
            if (selected.isEmpty()) {
                for (int i = 0; i < Math.min(80, lines.size()); i++) selected.add(i);
            }
            int last = -2;
            for (Integer idx : selected) {
                if (idx > last + 1) log("  ...");
                log(String.format("  %04d %s", idx + 1, lines.get(idx)));
                last = idx;
            }
        }
    }

    private boolean isInterestingLine(String line) {
        for (String needle : DEFAULT_NEEDLES) {
            if (line.contains(needle)) return true;
        }
        return line.contains("ServerCommand") || line.contains("Cheat") ||
            line.contains("Command") || line.contains("Admin") ||
            line.contains("Kick") || line.contains("Teleport");
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }

    private String clean(String s) {
        if (s == null) return "";
        return s.replace("\\", "\\\\").replace("\n", "\\n").replace("\r", "\\r");
    }

    private static final class StringHit {
        final Address address;
        final String value;
        final String encoding;

        StringHit(Address address, String value, String encoding) {
            this.address = address;
            this.value = value;
            this.encoding = encoding;
        }
    }

    private enum Encoding {
        ASCII("ascii") {
            byte[] bytes(String s) {
                return s.getBytes(java.nio.charset.StandardCharsets.US_ASCII);
            }
        },
        UTF16LE("utf16le") {
            byte[] bytes(String s) {
                return s.getBytes(java.nio.charset.StandardCharsets.UTF_16LE);
            }
        };

        final String name;

        Encoding(String name) {
            this.name = name;
        }

        abstract byte[] bytes(String s);
    }
}
