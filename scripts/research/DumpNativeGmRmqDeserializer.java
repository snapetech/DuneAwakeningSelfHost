// Ghidra headless script for the native GM notification RMQ receive/deserializer path.
//
// This focuses on the RMQ listen/publish helpers and the listener callbacks
// that appear to turn a broker message into the notification object later
// consumed by FUN_09f3ff90 -> FUN_09ee73c0.
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpNativeGmRmqDeserializer.java
//
// Output:
//   /tmp/ghidra-work/native-gm-rmq-deserializer.txt
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

public class DumpNativeGmRmqDeserializer extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/native-gm-rmq-deserializer.txt";
    private static final int MAX_POINTER_HITS = 8;
    private static final int MAX_STRING_HITS = 8;
    private static final int MAX_DECOMPILES = 50;

    private static final long[] FOCUS_ADDRESSES = new long[] {
        0x09ed8710L, // RMQ runnable/listen loop
        0x09ed8920L, // connection/consumer creation wrapper
        0x09ed8ed0L, // periodic outbound gate reached from the listen loop
        0x09ede9a0L, // outbound AMQP publish helper reached from the loop
        0x09f3ff50L, // callback thunk to notification dispatch
        0x09f3ff60L, // callback thunk to notification dispatch
        0x09f3ff90L, // notification dispatch callback
        0x09ee73c0L, // server-command notification handler
        0x09ee7970L, // auth/content extractor wrapper
        0x09eb7e60L  // auth/content extractor implementation
    };

    private static final long[] DATA_ADDRESSES = new long[] {
        0x16562160L, // static sender/name pointer used by receive and dispatch prefilters
        0x16562168L, // static sender/name length used by receive and dispatch prefilters
        0x1490e380L, // server-command handler log pointer table
        0x1490e3a0L,
        0x1490e3c0L,
        0x1490e3e0L,
        0x1490e400L,
        0x1490e420L  // receive-side deserialize failure log pointer table
    };

    private static final String[] NEEDLES = new String[] {
        "NotificationSystemListenQueue failed for queue",
        "NotificationSystemListenQueue message receive failed for queue",
        "NotificationSystemHandleServerMessages",
        "NotificationSystem message parsing failed. Failed to deserialize.",
        "NotificationSystem message ignored. Outdated message version:",
        "NotificationSystem message handling failed. Invalid Sender ID, we only accept server commands from 'fls'.",
        "NotificationSystem message handling failed. Invalid Auth Token.",
        "NotificationSystem message handling failed. Empty message content.",
        "Server command received. Raw Content:",
        "JsonObjectStringToUStruct",
        "Deserialized message has unknown Server Command",
        "ServerRequestEventNotifications",
        "EngineServiceNotification",
        "ClientGenericNotification",
        "ClientGenericNotifications"
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
            dumpFocusFunctions();
            dumpDataAddresses();
            dumpNeedles();
            decompileCollected();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpFocusFunctions() {
        log("");
        log("== focus functions");
        for (long value : FOCUS_ADDRESSES) {
            Address addr = toAddr(value);
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("");
            log("-- 0x" + Long.toHexString(value) + " " + addr +
                (fn == null ? " function=<none>" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (fn == null) {
                dumpInstructions(addr, 80);
                continue;
            }
            decompileQueue.add(fn.getEntryPoint());
            dumpRefsTo(fn.getEntryPoint(), "refs to function entry", true);
            dumpFunctionRefsFrom(fn);
        }
    }

    private void dumpFunctionRefsFrom(Function fn) {
        log("  body=" + fn.getBody().getMinAddress() + ".." + fn.getBody().getMaxAddress());
        Instruction instr = currentProgram.getListing().getInstructionAt(fn.getEntryPoint());
        int count = 0;
        while (instr != null && fn.getBody().contains(instr.getAddress())) {
            Reference[] from = refs.getReferencesFrom(instr.getAddress());
            boolean interesting = instr.getFlowType().isCall() || from.length != 0;
            if (interesting) {
                log("  insn " + instr.getAddress() + " " + instr);
                for (Reference ref : from) {
                    Address to = ref.getToAddress();
                    Function targetFn = currentProgram.getFunctionManager().getFunctionContaining(to);
                    log("    ref-to " + to + " type=" + ref.getReferenceType() +
                        (targetFn == null ? "" : " function=" + targetFn.getName() + " @ " + targetFn.getEntryPoint()));
                    // Do not automatically decompile target helpers here. The
                    // notification path shares generic string and allocator
                    // helpers with much of the binary.
                }
            }
            instr = instr.getNext();
            count++;
            if (count > 1500) {
                log("  truncated function instruction walk at 1500 instructions");
                break;
            }
        }
    }

    private void dumpDataAddresses() throws Exception {
        log("");
        log("== data addresses");
        for (long value : DATA_ADDRESSES) {
            Address addr = toAddr(value);
            log("");
            log("-- data 0x" + Long.toHexString(value) + " " + addr);
            dumpScalar(addr);
            dumpRefsTo(addr, "refs to data", true);
            dumpPointerString(addr);
            findPointersTo(addr);
        }
    }

    private void dumpNeedles() throws Exception {
        log("");
        log("== bounded strings and pointer-table refs");
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
            if (hits <= MAX_STRING_HITS) {
                log("  hit " + hit + " encoding=" + (utf16 ? "utf16le" : "ascii") +
                    " inline=" + readInlineString(hit, utf16, 180));
                dumpRefsTo(hit, "direct refs", false);
                findPointersTo(hit);
            }
            cursor = hit.add(1);
        }
        log("  hits=" + hits + " encoding=" + (utf16 ? "utf16le" : "ascii"));
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
                log("    ptr-to-target at " + hit);
                dumpNearbyPointers(hit, 3);
                dumpRefsTo(hit, "refs to ptr", true);
            }
            cursor = hit.add(1);
        }
        if (hits != 0) {
            log("    ptr-to-target hits=" + hits);
        }
    }

    private void dumpNearbyPointers(Address ptrAddr, int radius) {
        for (int i = -radius; i <= radius; i++) {
            try {
                Address slot = ptrAddr.add((long)i * 8L);
                long raw = mem.getLong(slot);
                Address pointed = toAddr(raw);
                Function fn = currentProgram.getFunctionManager().getFunctionContaining(pointed);
                String ascii = readInlineString(pointed, false, 80);
                String utf16 = readInlineString(pointed, true, 80);
                log("      slot" + signed(i) + " " + slot + " -> 0x" + Long.toHexString(raw) + " " + pointed +
                    (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()) +
                    " ascii=" + ascii + " utf16=" + utf16);
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
            if (collect && fn != null && decompileQueue.size() < MAX_DECOMPILES) {
                decompileQueue.add(fn.getEntryPoint());
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

    private void dumpScalar(Address addr) {
        try {
            long qword = mem.getLong(addr);
            int dword0 = mem.getInt(addr);
            int dword4 = mem.getInt(addr.add(4));
            log("    qword=0x" + Long.toHexString(qword) + " dword0=" + dword0 + " dword4=" + dword4);
        } catch (Exception e) {
            log("    scalar=<unreadable> " + e.getMessage());
        }
    }

    private void dumpPointerString(Address addr) {
        try {
            long pointerValue = mem.getLong(addr);
            Address pointed = toAddr(pointerValue);
            log("    pointer=0x" + Long.toHexString(pointerValue) + " " + pointed);
            log("    pointer ascii=" + readInlineString(pointed, false, 180));
            log("    pointer utf16=" + readInlineString(pointed, true, 180));
        } catch (Exception e) {
            log("    pointer=<unreadable> " + e.getMessage());
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
