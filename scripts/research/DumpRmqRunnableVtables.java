// Ghidra headless script for RMQ runnable vtable slots.
//
// FUN_09ed8710 drives the RMQ loop and calls virtual slots +0x40 and +0x48
// after the outbound maintenance gate. This script finds pointer tables around
// FUN_09ed8710 and decompiles nearby slot functions so the inbound consumer
// path can be separated from outbound task handling.
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpRmqRunnableVtables.java
//
// Output:
//   /tmp/ghidra-work/rmq-runnable-vtables.txt
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

public class DumpRmqRunnableVtables extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/rmq-runnable-vtables.txt";
    private static final int MAX_POINTER_HITS = 32;
    private static final int MAX_DECOMPILES = 48;

    private static final long[] TARGETS = new long[] {
        0x09ed8710L, // RMQ loop
        0x09ed8ed0L, // outbound maintenance gate
        0x0a05c5b0L, // generated decoded-message receive delegate
        0x0a05d070L, // generated decoded-message receive delegate
        0x09f8cf00L  // decoded-message dispatcher
    };

    private PrintWriter out;
    private Memory mem;
    private ReferenceManager refs;
    private DecompInterface decomp;
    private final Set<Address> decompileQueue = new LinkedHashSet<>();

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
            dumpTargets();
            decompileCollected();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpTargets() throws Exception {
        log("");
        log("== target pointer tables");
        for (long value : TARGETS) {
            Address target = toAddr(value);
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(target);
            log("");
            log("-- target 0x" + Long.toHexString(value) + " " + target +
                (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (fn != null) {
                queue(fn, "target");
            }
            dumpRefsTo(target, true);
            findPointersTo(target);
        }
    }

    private void findPointersTo(Address target) throws Exception {
        long value = target.getOffset();
        byte[] pattern = new byte[8];
        for (int i = 0; i < 8; i++) {
            pattern[i] = (byte)((value >>> (8 * i)) & 0xff);
        }
        Address cursor = mem.getMinAddress();
        Address max = mem.getMaxAddress();
        int hits = 0;
        while (cursor != null && cursor.compareTo(max) <= 0) {
            Address hit = mem.findBytes(cursor, max, pattern, null, true, monitor);
            if (hit == null) {
                break;
            }
            hits++;
            if (hits <= MAX_POINTER_HITS) {
                log("  pointer-hit " + hit);
                dumpTableAround(hit, 10);
                dumpRefsTo(hit, false);
            }
            cursor = hit.add(1);
        }
        log("  pointer-hit count=" + hits);
    }

    private void dumpTableAround(Address slot, int radius) {
        for (int i = -radius; i <= radius; i++) {
            try {
                Address entry = slot.add((long)i * 8L);
                long raw = mem.getLong(entry);
                Address pointed = toAddr(raw);
                Function fn = currentProgram.getFunctionManager().getFunctionContaining(pointed);
                log("    slot" + signed(i) + " " + entry + " -> 0x" + Long.toHexString(raw) + " " + pointed +
                    (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()) +
                    " ascii=" + readInlineString(pointed, false, 120) +
                    " utf16=" + readInlineString(pointed, true, 120));
                if (fn != null) {
                    queue(fn, "pointer-table-slot");
                }
            } catch (Exception e) {
                log("    slot" + signed(i) + " <unreadable> " + e.getMessage());
            }
        }
    }

    private void dumpRefsTo(Address addr, boolean collect) {
        ReferenceIterator it = refs.getReferencesTo(addr);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            log("  ref " + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (collect && fn != null) {
                queue(fn, "xref");
            }
        }
        if (count == 0) {
            log("  refs=0");
        }
    }

    private void queue(Function fn, String reason) {
        if (decompileQueue.size() < MAX_DECOMPILES && decompileQueue.add(fn.getEntryPoint())) {
            log("    queued " + fn.getName() + " @ " + fn.getEntryPoint() + " reason=" + reason);
        }
    }

    private void decompileCollected() throws Exception {
        log("");
        log("== decompile collected functions count=" + decompileQueue.size());
        for (Address entry : decompileQueue) {
            Function fn = currentProgram.getFunctionManager().getFunctionAt(entry);
            if (fn == null) {
                continue;
            }
            log("");
            log("-- function " + fn.getName() + " @ " + fn.getEntryPoint());
            DecompileResults res = decomp.decompileFunction(fn, 120, new ConsoleTaskMonitor());
            if (!res.decompileCompleted()) {
                log("decompile failed: " + res.getErrorMessage());
            } else {
                log(res.getDecompiledFunction().getC());
            }
        }
    }

    private String readInlineString(Address addr, boolean utf16, int maxChars) {
        try {
            StringBuilder sb = new StringBuilder();
            for (int i = 0; i < maxChars; i++) {
                int c = utf16 ? mem.getShort(addr.add((long)i * 2L)) & 0xffff : mem.getByte(addr.add(i)) & 0xff;
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

    private static String signed(int value) {
        return value < 0 ? Integer.toString(value) : "+" + value;
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }
}
