// Ghidra headless script to dump/decompile the Online Services logout,
// lobby-kick, and session-remove operation-handler vtables.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -noanalysis \
//     -postScript DumpDisconnectOperationHandlers.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/disconnect-handlers-ghidra.log
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
import java.util.LinkedHashSet;
import java.util.Set;

public class DumpDisconnectOperationHandlers extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/disconnect-handlers-findings.txt";

    private static final Target[] TARGETS = new Target[] {
        new Target("FAuthLogout exec handler vtable", 0x148c59d0L),
        new Target("FKickLobbyMember exec handler vtable", 0x148cda28L),
        new Target("FRemoveSessionMember exec handler vtable", 0x148d3c10L),
        new Target("FKickLobbyMember async op vtable", 0x148cfc00L),
        new Target("FRemoveSessionMember async op vtable", 0x148d7c50L),
        new Target("ULogoutCallbackProxy vtable", 0x148a81a0L),
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
            dumpTargets();
            addExtraFunctions();
            decompileCollectedFunctions();
        } finally {
            out.close();
        }
    }

    private void dumpTargets() throws Exception {
        Memory mem = currentProgram.getMemory();
        for (Target target : TARGETS) {
            Address table = toAddr(target.address);
            log("");
            log("== " + target.name + " @ " + table);
            dumpRefsTo(table);
            for (int i = 0; i < 16; i++) {
                Address slot = table.add((long) i * 8L);
                long raw;
                try {
                    raw = mem.getLong(slot);
                } catch (Exception e) {
                    log("slot[" + i + "] " + slot + " unreadable: " + e);
                    continue;
                }
                Address value = toAddr(raw);
                Function f = currentProgram.getFunctionManager().getFunctionContaining(value);
                String fdesc = f == null ? "" : " function=" + f.getName() + " entry=" + f.getEntryPoint();
                log("slot[" + i + "] " + slot + " -> " + value + fdesc);
                if (f != null) {
                    functions.add(f.getEntryPoint());
                }
            }
        }
    }

    private void dumpRefsTo(Address target) {
        ReferenceManager rm = currentProgram.getReferenceManager();
        ReferenceIterator refs = rm.getReferencesTo(target);
        int count = 0;
        while (refs.hasNext()) {
            Reference ref = refs.next();
            count++;
            Address from = ref.getFromAddress();
            Function f = currentProgram.getFunctionManager().getFunctionContaining(from);
            log("  ref " + from + " type=" + ref.getReferenceType() +
                (f == null ? "" : " function=" + f.getName() + " entry=" + f.getEntryPoint()));
        }
        log("refs=" + count);
    }

    private void addExtraFunctions() {
        String extra = System.getenv("DUNE_DISCONNECT_EXTRA_FUNCTIONS");
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
            for (String line : lines) {
                log("  " + line);
            }
        }
        dec.dispose();
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }

    private static final class Target {
        final String name;
        final long address;

        Target(String name, long address) {
            this.name = name;
            this.address = address;
        }
    }
}
