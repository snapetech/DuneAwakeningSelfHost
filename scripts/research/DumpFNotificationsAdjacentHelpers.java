// Ghidra headless script for helpers adjacent to FNotificationsSystemMessage.
//
// This follows the functions around FUN_09ec9f00 and the RMQ operation
// state-machine that were not fully covered by the compact acceptance-gate
// script. The goal is to identify whether any are inbound body deserializers or
// just outbound/queue-operation helpers.
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpFNotificationsAdjacentHelpers.java
//
// Output:
//   /tmp/ghidra-work/fnotifications-adjacent-helpers.txt
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

public class DumpFNotificationsAdjacentHelpers extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/fnotifications-adjacent-helpers.txt";

    private static final long[] FUNCTIONS = new long[] {
        0x09ec59f0L,
        0x09ec5b60L,
        0x09ec8390L,
        0x09ec9730L,
        0x09ec9b30L,
        0x09ec9f00L,
        0x09eca180L,
        0x09eca430L,
        0x09ed72c0L,
        0x09ed82d0L,
        0x09ed8ed0L,
        0x09ede1c0L,
        0x09ede9a0L
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
            log("");
            log("== interpretation hints");
            log("FUN_09ede1c0 switch cases are AMQP operation kinds; case 1 reaches outbound publish.");
            log("FUN_09ec9f00 copies decoded FNotificationsSystemMessage fields.");
            log("Any inbound candidate should populate +0x48/+0x50, +0x58/+0x60, and +0x78/+0x80 before FUN_09f3ff90.");
            dumpFunctions();
        } finally {
            decomp.dispose();
            out.close();
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

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }
}
