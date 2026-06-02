// Ghidra headless script for the native server-command notification gates.
//
// This is the compact companion to DumpFNotificationsSystemMessageLayout.java.
// It focuses only on the decoded FNotificationsSystemMessage fields that must
// be populated before ServiceBroadcast command content can run.
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpFNotificationsCommandAcceptance.java
//
// Output:
//   /tmp/ghidra-work/fnotifications-command-acceptance.txt
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import ghidra.program.model.symbol.ReferenceManager;
import ghidra.util.task.ConsoleTaskMonitor;

import java.io.FileWriter;
import java.io.PrintWriter;

public class DumpFNotificationsCommandAcceptance extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/fnotifications-command-acceptance.txt";

    private static final long[] FUNCTIONS = new long[] {
        0x09f3ff90L, // event discriminator gate, then calls server-command handler
        0x09ee73c0L, // sender/auth/content gates
        0x09ee7970L, // auth/content extractor wrapper
        0x09eb7e60L, // auth/content extractor implementation
        0x09ec9f00L, // decoded-message copy helper
        0x09ede9a0L, // outbound AMQP publisher for same message family
        0x09ee83c0L, // loads FuncomLiveServices.ServerCommandsAuthToken
        0x0da61730L, // proven Generic ServiceBroadcast command handler
        0x0da5cea0L  // ServerCommand JSON field extractor
    };

    private static final long[] DATA = new long[] {
        0x1490e380L, // outdated version log table
        0x1490e3a0L, // invalid sender log table
        0x1490e3c0L, // invalid auth log table
        0x1490e3e0L, // empty content log table
        0x1490e400L, // accepted raw content log table
        0x1490e420L  // deserialize failure log table
    };

    private PrintWriter out;
    private ReferenceManager refs;
    private DecompInterface decomp;

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
            dumpAcceptanceSummary();
            dumpDataRefs();
            dumpFunctions();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpAcceptanceSummary() {
        log("");
        log("== decoded-message acceptance checklist");
        log("1. FUN_09f3ff90 compares decoded string at param_2+0x48/0x50 with DAT_16562160/DAT_16562168.");
        log("2. FUN_09f3ff90 calls FUN_09ee73c0 only after that discriminator check passes.");
        log("3. FUN_09ee73c0 compares decoded string at param_2+0x78/0x80 with subsystem fields +0x210/+0x218.");
        log("4. FUN_09ee73c0 copies the decoded message through FUN_09ec9f00 when the +0x78/0x80 gate matches.");
        log("5. FUN_09ee73c0 calls FUN_09ee7970(param_2+0x48, &version, auth, content).");
        log("6. version/status below 2 logs the outdated-message branch.");
        log("7. sender check compares param_2+0x58/0x60 with subsystem fields +0x220/+0x228; invalid sender says only fls is accepted.");
        log("8. auth check compares extracted auth with configured token fields +0x230/+0x238 and +0x240/+0x248.");
        log("9. non-empty extracted content logs Server command received. Raw Content and calls FUN_09691b80.");
        log("10. Generic ServiceBroadcast content reaches FUN_0da61730, which logs Handling ServiceBroadcast Server command.");
    }

    private void dumpDataRefs() throws Exception {
        log("");
        log("== log/data table refs");
        for (long value : DATA) {
            Address addr = toAddr(value);
            log("");
            log("-- data 0x" + Long.toHexString(value) + " " + addr);
            try {
                long ptr = currentProgram.getMemory().getLong(addr);
                Address pointed = toAddr(ptr);
                log("  pointer=0x" + Long.toHexString(ptr) + " " + pointed +
                    " utf16=" + readUtf16(pointed, 220));
            } catch (Exception e) {
                log("  pointer=<unreadable> " + e.getMessage());
            }
            dumpRefsTo(addr);
        }
    }

    private void dumpFunctions() {
        log("");
        log("== focused decompile");
        for (long value : FUNCTIONS) {
            Address addr = toAddr(value);
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("");
            log("-- 0x" + Long.toHexString(value) + " " + addr +
                (fn == null ? " function=<none>" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (fn == null) {
                continue;
            }
            dumpRefsTo(fn.getEntryPoint());
            DecompileResults res = decomp.decompileFunction(fn, 120, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
            } else {
                log(res.getDecompiledFunction().getC());
            }
        }
    }

    private void dumpRefsTo(Address addr) {
        ReferenceIterator it = refs.getReferencesTo(addr);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            log("  ref " + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
        }
        if (count == 0) {
            log("  refs=0");
        }
    }

    private String readUtf16(Address addr, int maxChars) {
        try {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < maxChars; i++) {
                int c = currentProgram.getMemory().getShort(addr.add((long)i * 2L)) & 0xffff;
                if (c == 0) {
                    break;
                }
                if (c < 0x20 || c > 0x7e) {
                    sb.append("\\x").append(Integer.toHexString(c));
                } else {
                    sb.append((char)c);
                }
            }
            return "\"" + sb + "\"";
        } catch (Exception e) {
            return "<unreadable>";
        }
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }
}
