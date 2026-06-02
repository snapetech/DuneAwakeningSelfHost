// Ghidra headless script for the native GM notification receive callbacks.
//
// This follows the path discovered after FUN_09ede9a0 was identified as an
// outbound AMQP publisher. The useful receive-side evidence is now the
// NotificationSystemListenQueue callback functions and their message handoff to
// FUN_09f8cf00.
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpNativeGmReceiveCallbacks.java
//
// Output:
//   /tmp/ghidra-work/native-gm-receive-callbacks.txt
//
// @category Reverse Engineering

import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileResults;
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.Instruction;
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

public class DumpNativeGmReceiveCallbacks extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/native-gm-receive-callbacks.txt";
    private static final int MAX_POINTER_HITS = 16;
    private static final int MAX_DECOMPILES = 48;
    private static final boolean DUMP_FOCUS_REFS = false;
    private static final boolean DUMP_STRINGS = false;

    private static final long[] FOCUS_ADDRESSES = new long[] {
        0x09ed8710L, // RMQ listen loop with virtual receive/dispatch calls
        0x0a05c400L, // FNotificationsSystemMessage delegate table entry
        0x0a05c580L, // paired delegate cleanup/copy helper
        0x0a05c590L, // paired delegate cleanup/copy helper
        0x0a05c5b0L, // NotificationSystemListenQueue callback, calls FUN_09f8cf00
        0x0a05c6f0L, // paired delegate helper near message-receive log
        0x0a05c7a0L, // bool-returning listen callback table entry
        0x0a05c950L, // paired delegate cleanup/copy helper
        0x0a05c960L, // paired delegate cleanup/copy helper
        0x0a05c980L, // paired catch/continuation callback
        0x0a05ce10L, // delegate helper adjacent to failure-in-creation log table
        0x0a05cf20L, // FNotificationsSystemMessage delegate table entry
        0x0a05d040L, // paired delegate cleanup/copy helper
        0x0a05d050L, // paired delegate cleanup/copy helper
        0x0a05d070L, // NotificationSystemListenQueue callback, calls FUN_09f8cf00
        0x09fa5a70L, // notification queue/work-item setup callback
        0x09fa63c0L, // wrapper/owner near queue setup callback
        0x0a05bfb0L, // wrapper/owner near queue setup callback
        0x09f8cf00L, // message object handoff used by receive callbacks
        0x09f6ecb0L, // callee from FUN_09f8cf00
        0x09f3ff90L, // decoded notification dispatch
        0x09ee73c0L  // server-command notification handler
    };

    private static final String[] NEEDLES = new String[] {
        "NotificationSystemListenQueue failed for queue",
        "NotificationSystemListenQueue message receive failed for queue",
        "NotificationSystemHandleServerMessages",
        "ServerRequestEventNotifications",
        "Server command received. Raw Content:"
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
            dumpFocus();
            if (DUMP_STRINGS) {
                dumpNeedles();
            } else {
                log("");
                log("== bounded string refs skipped; set DUMP_STRINGS=true for full table scan");
            }
            decompileCollected();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpFocus() throws Exception {
        log("");
        log("== focus addresses");
        for (long value : FOCUS_ADDRESSES) {
            Address addr = toAddr(value);
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("");
            log("-- 0x" + Long.toHexString(value) + " " + addr +
                (fn == null ? " function=<none>" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (fn != null) {
                addFunction(fn, "focus");
                if (DUMP_FOCUS_REFS) {
                    dumpFunctionCalls(fn);
                }
            } else {
                dumpInstructions(addr, 80);
            }
            if (DUMP_FOCUS_REFS) {
                dumpRefsTo(addr, "refs to address", true);
                findPointersTo(addr, "ptr-to-address");
            }
        }
    }

    private void dumpNeedles() throws Exception {
        log("");
        log("== bounded string refs");
        for (String needle : NEEDLES) {
            log("");
            log("-- needle " + needle);
            dumpNeedle(needle, false);
            dumpNeedle(needle, true);
        }
    }

    private void dumpNeedle(String needle, boolean utf16) throws Exception {
        byte[] pattern = utf16 ? utf16le(needle) : needle.getBytes(StandardCharsets.UTF_8);
        Address cursor = mem.getMinAddress();
        Address max = mem.getMaxAddress();
        int hits = 0;
        while (cursor != null && cursor.compareTo(max) <= 0) {
            Address hit = mem.findBytes(cursor, max, pattern, null, true, monitor);
            if (hit == null) {
                break;
            }
            hits++;
            if (hits <= 8) {
                log("  hit " + hit + " encoding=" + (utf16 ? "utf16le" : "ascii") +
                    " inline=" + readInlineString(hit, utf16, 160));
                dumpRefsTo(hit, "direct refs", false);
                findPointersTo(hit, "ptr-to-string");
            }
            cursor = hit.add(1);
        }
        log("  hits=" + hits + " encoding=" + (utf16 ? "utf16le" : "ascii"));
    }

    private void dumpFunctionCalls(Function fn) {
        log("  body=" + fn.getBody().getMinAddress() + ".." + fn.getBody().getMaxAddress());
        Instruction instr = currentProgram.getListing().getInstructionAt(fn.getEntryPoint());
        int count = 0;
        while (instr != null && fn.getBody().contains(instr.getAddress())) {
            Reference[] from = refs.getReferencesFrom(instr.getAddress());
            if (instr.getFlowType().isCall() || from.length != 0) {
                log("  insn " + instr.getAddress() + " " + instr);
                for (Reference ref : from) {
                    Address to = ref.getToAddress();
                    Function targetFn = currentProgram.getFunctionManager().getFunctionContaining(to);
                    log("    ref-to " + to + " type=" + ref.getReferenceType() +
                        (targetFn == null ? "" : " function=" + targetFn.getName() + " @ " + targetFn.getEntryPoint()));
                    if (targetFn != null && isInterestingTarget(targetFn.getEntryPoint())) {
                        addFunction(targetFn, "interesting-call");
                    }
                }
            }
            instr = instr.getNext();
            count++;
            if (count > 2000) {
                log("  truncated instruction walk at 2000 instructions");
                break;
            }
        }
    }

    private boolean isInterestingTarget(Address entry) {
        long off = entry.getOffset();
        return off == 0x09f8cf00L || off == 0x09f3ff90L || off == 0x09ee73c0L ||
            off == 0x09ee7970L || off == 0x09eb7e60L || off == 0x09f13850L;
    }

    private void findPointersTo(Address target, String label) throws Exception {
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
                log("    " + label + " at " + hit);
                dumpNearbyPointers(hit, 6);
                dumpRefsTo(hit, "refs to ptr", true);
            }
            cursor = hit.add(1);
        }
        log("    " + label + " hits=" + hits);
    }

    private void dumpNearbyPointers(Address ptrAddr, int radius) {
        for (int i = -radius; i <= radius; i++) {
            try {
                Address slot = ptrAddr.add((long)i * 8L);
                long raw = mem.getLong(slot);
                Address pointed = toAddr(raw);
                Function fn = currentProgram.getFunctionManager().getFunctionContaining(pointed);
                log("      slot" + signed(i) + " " + slot + " -> 0x" + Long.toHexString(raw) + " " + pointed +
                    (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()) +
                    " ascii=" + readInlineString(pointed, false, 72) +
                    " utf16=" + readInlineString(pointed, true, 72));
            } catch (Exception e) {
                log("      slot" + signed(i) + " <unreadable> " + e.getMessage());
            }
        }
    }

    private void dumpRefsTo(Address addr, String label, boolean collect) {
        ReferenceIterator it = refs.getReferencesTo(addr);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            log("    " + label + " " + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (collect && fn != null) {
                addFunction(fn, label);
            }
        }
        if (count == 0) {
            log("    " + label + "=0");
        }
    }

    private void dumpInstructions(Address start, int maxInstructions) {
        Instruction instr = currentProgram.getListing().getInstructionAt(start);
        if (instr == null) {
            instr = currentProgram.getListing().getInstructionAfter(start);
        }
        int count = 0;
        while (instr != null && count < maxInstructions) {
            log("  insn " + instr.getAddress() + " " + instr);
            instr = instr.getNext();
            count++;
        }
    }

    private void addFunction(Function fn, String reason) {
        if (decompileQueue.size() < MAX_DECOMPILES && decompileQueue.add(fn.getEntryPoint())) {
            log("    queued-decompile " + fn.getName() + " @ " + fn.getEntryPoint() + " reason=" + reason);
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
                int c;
                if (utf16) {
                    c = mem.getShort(addr.add((long)i * 2L)) & 0xffff;
                } else {
                    c = mem.getByte(addr.add(i)) & 0xff;
                }
                if (c == 0) {
                    break;
                }
                if (c < 0x20 || c > 0x7e) {
                    sb.append("\\x").append(Integer.toHexString(c));
                } else {
                    sb.append((char)c);
                }
            }
            return "\"" + sb.toString() + "\"";
        } catch (Exception e) {
            return "<unreadable>";
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

    private static String signed(int value) {
        return value < 0 ? Integer.toString(value) : "+" + value;
    }

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }
}
