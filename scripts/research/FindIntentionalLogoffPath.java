// Ghidra headless script to locate the deliberate client/menu logoff path.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -noanalysis \
//     -postScript FindIntentionalLogoffPath.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/intentional-logoff-ghidra.log
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.data.DataUtilities;
import ghidra.program.model.data.StringDataType;
import ghidra.program.model.listing.Function;
import ghidra.program.model.mem.Memory;
import ghidra.program.model.mem.MemoryBlock;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;

public class FindIntentionalLogoffPath extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/intentional-logoff-findings.txt";
    private static final String[] NEEDLES = new String[] {
        "ServerStartLogOffTimer",
        "ADunePlayerControllerBase::ServerStartLogOffTimer_Implementation",
        "ServerInitiateLogOffDialog",
        "ClientOnServerStartedLogOffTimer",
        "ClientCancelLogOffTimer",
        "ClientRequestLogOffDialog",
        "ClientLogOff",
        "CancelClientLogOff",
        "InitiateLeaveGame",
        "OpenLeaveGameDialog",
        "OpenQuitToMainMenuDialog",
        "QuitToMainMenu",
        "LeaveGame",
        "LogOffSystem",
        "IsServerLogOffTimerActive",
        "HandleDamageOnServerWhileLeavingGame",
        "m_AllowedInputsDuringLogOffSequence"
    };

    private PrintWriter out;
    private final Set<Address> functions = new LinkedHashSet<>();

    @Override
    public void run() throws Exception {
        out = new PrintWriter(new FileWriter(OUT));
        try {
            log("Output: " + OUT);
            log("Program: " + currentProgram.getName());
            log("Image base: " + currentProgram.getImageBase());
            for (String needle : NEEDLES) {
                scanString(needle);
            }
            addExtraFunctions();
            decompileCollectedFunctions();
        } finally {
            out.close();
        }
    }

    private void addExtraFunctions() {
        String extra = System.getenv("DUNE_INTENTIONAL_LOGOFF_EXTRA_FUNCTIONS");
        if (extra == null || extra.trim().isEmpty()) return;
        for (String item : extra.split(",")) {
            String value = item.trim();
            if (value.isEmpty()) continue;
            try {
                Address addr = toAddr(Long.parseUnsignedLong(value.replaceFirst("^0x", ""), 16));
                Function f = currentProgram.getFunctionManager().getFunctionContaining(addr);
                if (f != null) {
                    functions.add(f.getEntryPoint());
                    log("extra function " + f.getName() + " @ " + f.getEntryPoint());
                } else {
                    log("extra address has no containing function: " + addr);
                }
            } catch (Exception e) {
                log("bad extra function address: " + value + " error=" + e);
            }
        }
    }

    private void scanString(String needle) throws Exception {
        log("");
        log("== string: " + needle);
        Memory mem = currentProgram.getMemory();
        byte[] bytes = needle.getBytes("UTF-8");
        int hits = 0;
        for (MemoryBlock block : mem.getBlocks()) {
            if (!block.isInitialized()) continue;
            Address found = mem.findBytes(block.getStart(), block.getEnd(), bytes, null, true, monitor);
            while (found != null) {
                hits++;
                log("hit " + found + " block=" + block.getName());
                try {
                    DataUtilities.createData(
                        currentProgram,
                        found,
                        StringDataType.dataType,
                        bytes.length + 1,
                        false,
                        DataUtilities.ClearDataMode.CLEAR_ALL_UNDEFINED_CONFLICT_DATA
                    );
                } catch (Exception ignored) {
                }
                collectRefs(found);
                if (found.add(1).compareTo(block.getEnd()) >= 0) break;
                found = mem.findBytes(found.add(1), block.getEnd(), bytes, null, true, monitor);
            }
        }
        log("hits=" + hits);
    }

    private void collectRefs(Address target) {
        ReferenceManager rm = currentProgram.getReferenceManager();
        ReferenceIterator refs = rm.getReferencesTo(target);
        int count = 0;
        while (refs.hasNext()) {
            Reference ref = refs.next();
            count++;
            Address from = ref.getFromAddress();
            log("  ref " + from + " type=" + ref.getReferenceType());
            Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
            if (f != null) {
                functions.add(f.getEntryPoint());
                log("    function " + f.getName() + " @ " + f.getEntryPoint());
            }
        }
        log("refs=" + count);
    }

    private void decompileCollectedFunctions() throws Exception {
        log("");
        log("== decompile collected functions: " + functions.size());
        DecompInterface dec = new DecompInterface();
        dec.openProgram(currentProgram);
        for (Address entry : functions) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (f == null) continue;
            log("");
            log("-- function " + f.getName() + " @ " + entry);
            DecompileResults res = dec.decompileFunction(f, 90, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
                continue;
            }
            String[] lines = res.getDecompiledFunction().getC().split("\n");
            for (int i = 0; i < lines.length; i++) {
                String line = lines[i];
                if (line.contains("LogOff") ||
                    line.contains("Logoff") ||
                    line.contains("Logout") ||
                    line.contains("Leaving") ||
                    line.contains("Client") ||
                    line.contains("Server") ||
                    line.contains("Timer") ||
                    line.contains("300") ||
                    line.contains("0x43960000") ||
                    line.contains("5")) {
                    int start = Math.max(0, i - 6);
                    int end = Math.min(lines.length, i + 7);
                    log("context line " + i);
                    for (int j = start; j < end; j++) {
                        log("  " + lines[j]);
                    }
                }
            }
        }
        dec.dispose();
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }
}
