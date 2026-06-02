// Ghidra headless script to inspect notification/service-broadcast server
// command parsing evidence.
//
// Run example:
//   /opt/ghidra/support/analyzeHeadless /tmp/ghidra-work/project DuneServer \
//     -process server-bin \
//     -noanalysis \
//     -postScript DumpNotificationServerCommandSurface.java \
//     -scriptPath scripts/research \
//     -log /tmp/ghidra-work/notification-server-command-surface-ghidra.log
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

public class DumpNotificationServerCommandSurface extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/notification-server-command-surface-findings.txt";
    private static final int MAX_DECOMPILES = 80;

    private static final String[] NEEDLES = new String[] {
        "NotificationSystem message handling failed. Empty message content.",
        "NotificationSystem message handling failed. Invalid Auth Token.",
        "Handling ServiceBroadcast Server command:",
        "Deserialized ServiceBroadcast Payload has unknown Broadcast type.",
        "FServerShutdownBroadcastPayload parsing failed. ShutdownType field does not exist.",
        "FServerShutdownBroadcastPayload parsing failed. ShutdownTimestamp field does not exist.",
        "FServerShutdownBroadcastPayload parsing failed. ShutdownType `%s` is invalid. Defaulting to `Restart`.",
        "ServerBroadcast",
        "LocalizedServerBroadcast",
        "GenericBroadcast",
        "ServerCommand",
        "BroadcastPayload",
        "PayloadJSON",
        "PayloadType",
        "ShutdownType",
        "ShutdownTimestamp"
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
            dumpNeedles();
            decompileCollected();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpNeedles() throws Exception {
        log("");
        log("== notification/server-command strings");
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
                if (f != null && functions.size() < MAX_DECOMPILES) {
                    functions.add(f.getEntryPoint());
                }
                dumpIndirectRefs(ref.getFromAddress());
            }
            log("  refs=" + refsCount);
            cursor = hit.add(1);
        }
        log("hits=" + hits + " encoding=" + (utf16 ? "utf16le" : "ascii"));
    }

    private void dumpIndirectRefs(Address pointerAddress) {
        ReferenceIterator it = refs.getReferencesTo(pointerAddress);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            Function f = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            log("    indirect ref " + ref.getFromAddress() + " -> " + pointerAddress +
                " type=" + ref.getReferenceType() +
                (f == null ? "" : " function=" + f.getName() + " @ " + f.getEntryPoint()));
            if (f != null && functions.size() < MAX_DECOMPILES) {
                functions.add(f.getEntryPoint());
            }
        }
        if (count != 0) {
            log("    indirect refs=" + count);
        }
    }

    private void decompileCollected() throws Exception {
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
