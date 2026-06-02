// Ghidra headless script to dump Dune server-command payload evidence.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -noanalysis \
//     -postScript DumpServerCommandPayload.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/server-command-payload-ghidra.log
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
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashSet;
import java.util.Set;

public class DumpServerCommandPayload extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/server-command-payload-findings.txt";
    private static final int MAX_REFS_PER_TARGET = 80;

    private static final long[] OFFSETS = new long[] {
        0x09ee83c0L, // subsystem/settings setup, ServerCommandsAuthToken
        0x12f2f980L, // wrapper/native dispatch reached by server-command thunk
        0x0da5c3c0L, // DuneServerCommandSubsystem command execution target
        0x0da5bee0L, // SendDuneServerCommand cheat path
        0x0da5cea0L, // ServerCommand field serialization evidence
        0x0da5cad0L, // DuneServerCommandSubsystem registration-adjacent
        0x0da5cae0L,
        0x0da5cb20L,
        0x0da5cbf0L,
        0x0da5cc00L,
        0x0da5cb10L,
        0x0da984a0L,
        0x0da5c1c0L,
        0x0da5c110L
    };

    private static final long[] REF_TARGETS = new long[] {
        0x12f2f980L,
        0x0da5c3c0L,
        0x0da5bee0L,
        0x0da5cea0L,
        0x0da5cae0L,
        0x154a5a88L
    };

    private static final long[] VTABLES = new long[] {
        0x154a56e0L, // UDuneServerCommandSubsystem vtable observed in constructor
        0x154a5a88L, // data pointer to "Now running ServerCommand" log text
        0x154a5608L,
        0x154a5628L,
        0x154a5648L
    };

    private static final String[] NEEDLES = new String[] {
        "DuneServerCommandSubsystem.cpp",
        "ServiceBroadcastServerCommand.cpp",
        "DuneServerCommandsUtils.cpp",
        "FServerBroadcastPayload",
        "FGenericBroadcastPayload",
        "FLocalizedServerBroadcastPayload",
        "FServerShutdownBroadcastPayload",
        "ServerCommandsAuthToken",
        "api/Auth_VerifyFlsServerToken",
        "ServiceBroadcastServerCommand",
        "ServerCommand",
        "SendDuneServerCommand",
        "Could not send DuneServerCommand",
        "Now running ServerCommand",
        "JsonObjectStringToUStruct",
        "ServerBroadcast",
        "GenericBroadcast",
        "LocalizedServerBroadcast"
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
            dumpOffsetFunctions();
            dumpRefTargets();
            dumpVtablesAndDataRefs();
            dumpNeedleXrefs();
            decompileCollectedFunctions();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpRefTargets() throws Exception {
        log("");
        log("== explicit references-to targets");
        for (long offset : REF_TARGETS) {
            Address addr = toAddr(offset);
            Function target = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("");
            log("-- refs to 0x" + Long.toHexString(offset) + " " + addr +
                (target == null ? "" : " target_function=" + target.getName() + " @ " + target.getEntryPoint()));
            ReferenceIterator it = refs.getReferencesTo(addr);
            int count = 0;
            while (it.hasNext()) {
                Reference ref = it.next();
                count++;
                if (count > MAX_REFS_PER_TARGET) {
                    continue;
                }
                Function from = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                log("  ref " + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                    (from == null ? "" : " function=" + from.getName() + " @ " + from.getEntryPoint()));
                if (from != null && offset != 0x12f2f980L) {
                    functions.add(from.getEntryPoint());
                }
            }
            log("  refs=" + count);
        }
    }

    private void dumpVtablesAndDataRefs() throws Exception {
        log("");
        log("== vtables/data refs");
        Memory mem = currentProgram.getMemory();
        for (long value : VTABLES) {
            Address table = toAddr(value);
            log("");
            log("-- address 0x" + Long.toHexString(value) + " " + table);
            ReferenceIterator refsTo = refs.getReferencesTo(table);
            int refCount = 0;
            while (refsTo.hasNext()) {
                Reference ref = refsTo.next();
                refCount++;
                Function f = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                log("  ref " + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                    (f == null ? "" : " function=" + f.getName() + " @ " + f.getEntryPoint()));
                if (f != null) {
                    functions.add(f.getEntryPoint());
                }
            }
            log("  refs=" + refCount);
            for (int i = 0; i < 16; i++) {
                try {
                    Address slot = table.add((long)i * 8L);
                    Address target = toAddr(mem.getLong(slot));
                    Function f = currentProgram.getFunctionManager().getFunctionContaining(target);
                    log("  slot[" + i + "] " + slot + " -> " + target +
                        (f == null ? "" : " function=" + f.getName() + " @ " + f.getEntryPoint()));
                    if (f != null) {
                        functions.add(f.getEntryPoint());
                    }
                } catch (Exception e) {
                    break;
                }
            }
        }
    }

    private void dumpOffsetFunctions() throws Exception {
        log("");
        log("== explicit offsets");
        for (long offset : OFFSETS) {
            Address addr = toAddr(offset);
            Function f = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("offset 0x" + Long.toHexString(offset) + " addr " + addr + " function " +
                (f == null ? "<none>" : f.getName() + " @ " + f.getEntryPoint()));
            if (f != null) {
                functions.add(f.getEntryPoint());
            }
        }
    }

    private void dumpNeedleXrefs() throws Exception {
        log("");
        log("== needle xrefs");
        for (String needle : NEEDLES) {
            log("");
            log("-- " + needle);
            dumpNeedle(needle, false);
            dumpNeedle(needle, true);
        }
    }

    private void dumpNeedle(String needle, boolean utf16) throws Exception {
        byte[] pattern = utf16 ? utf16le(needle) : needle.getBytes(StandardCharsets.UTF_8);
        Memory mem = currentProgram.getMemory();
        Address cursor = mem.getMinAddress();
        Address max = mem.getMaxAddress();
        int hits = 0;
        while (cursor != null && cursor.compareTo(max) <= 0) {
            Address hit = mem.findBytes(cursor, max, pattern, null, true, monitor);
            if (hit == null) {
                break;
            }
            hits++;
            log("hit " + hit + " encoding=" + (utf16 ? "utf16le" : "ascii"));
            ReferenceIterator it = refs.getReferencesTo(hit);
            int refsCount = 0;
            while (it.hasNext()) {
                Reference ref = it.next();
                refsCount++;
                Function f = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
                log("  ref " + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                    (f == null ? "" : " function=" + f.getName() + " @ " + f.getEntryPoint()));
                if (f != null) {
                    functions.add(f.getEntryPoint());
                }
            }
            log("  refs=" + refsCount);
            cursor = hit.add(1);
        }
        log("hits=" + hits + " encoding=" + (utf16 ? "utf16le" : "ascii"));
    }

    private void decompileCollectedFunctions() throws Exception {
        log("");
        log("== decompile collected functions count=" + functions.size());
        for (Address entry : functions) {
            Function f = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (f == null) {
                continue;
            }
            log("");
            log("-- function " + f.getName() + " @ " + entry);
            DecompileResults res = decomp.decompileFunction(f, 120, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
                continue;
            }
            log(res.getDecompiledFunction().getC());
        }
    }

    private static byte[] utf16le(String value) {
        byte[] out = new byte[value.length() * 2];
        for (int i = 0; i < value.length(); i++) {
            char c = value.charAt(i);
            out[i * 2] = (byte)(c & 0xff);
            out[i * 2 + 1] = (byte)((c >> 8) & 0xff);
        }
        return out;
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }
}
