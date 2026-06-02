// Ghidra headless script for DuneServerCommands ServiceBroadcast payload shape.
//
// This focuses on positive parser surfaces for native GM/server-command probes:
// BroadcastType, BroadcastPayload, ServerCommand, and the concrete
// ServiceBroadcast handlers that log "Handling ServiceBroadcast Server command:".
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpServiceBroadcastPayloadShape.java
//
// Output:
//   /tmp/ghidra-work/service-broadcast-payload-shape.txt
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

public class DumpServiceBroadcastPayloadShape extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/service-broadcast-payload-shape.txt";
    private static final int MAX_DECOMPILES = 80;
    private static final int MAX_REFS = 120;
    private static final boolean DUMP_POINTERS_TO_STRINGS = false;

    private static final long[] FOCUS_FUNCTIONS = new long[] {
        0x0da5fd90L, // BroadcastType field parser xref
        0x0da61a40L, // ServiceBroadcast unknown-type/error table function
        0x0da61730L, // generic service-broadcast handler
        0x0da61aa0L, // server-shutdown service-broadcast handler
        0x0da689b0L, // adjacent ServiceBroadcast error table function
        0x0da5cea0L, // ServerCommand field extractor
        0x0da5c3c0L, // UDuneServerCommandSubsystem execution thunk
        0x0da5bee0L, // SendDuneServerCommand cheat/player-controller path
        0x0f1bf7b0L, // payload parse/convert helper used before generic handler
        0x0f1bfb30L, // payload parse/convert helper used before shutdown handler
        0x0f1bcd20L, // generic ServiceBroadcast payload dispatch helper
        0x0f1c0a70L, // applies parsed generic broadcast to server subsystem
        0x0d8d4e30L  // applies parsed shutdown broadcast
    };

    private static final String[] NEEDLES = new String[] {
        "BroadcastType",
        "BroadcastPayload",
        "BroadcastType: Generic,",
        "BroadcastType: ServerShutdown,",
        "ServiceBroadcast Payload has unknown Broadcast type.",
        "Deserialized ServiceBroadcast Payload has unknown Broadcast type.",
        "Handling ServiceBroadcast Server command:",
        "ServerCommand",
        "ServerBroadcast",
        "GenericBroadcast",
        "LocalizedServerBroadcast",
        "ServerShutdown",
        "ShutdownType",
        "ShutdownTimestamp",
        "ShutdownDuration",
        "DateTimestamp",
        "LocalizedText"
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
            dumpFunctions();
            dumpNeedles();
            decompileCollected();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpFunctions() {
        log("");
        log("== focus functions");
        for (long value : FOCUS_FUNCTIONS) {
            Address addr = toAddr(value);
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("");
            log("-- 0x" + Long.toHexString(value) + " " + addr +
                (fn == null ? " function=<none>" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (fn == null) {
                dumpInstructions(addr, 64);
                continue;
            }
            addFunction(fn, "focus");
            dumpRefsTo(fn.getEntryPoint(), "refs to function entry", true);
            dumpFunctionRefsFrom(fn, 1800);
        }
    }

    private void dumpNeedles() throws Exception {
        log("");
        log("== string/data refs");
        for (String needle : NEEDLES) {
            log("");
            log("-- " + needle);
            if (scanAscii(needle)) {
                dumpNeedle(needle, false);
            } else {
                log("  ascii scan skipped for noisy symbol fragment");
            }
            dumpNeedle(needle, true);
        }
    }

    private boolean scanAscii(String needle) {
        return !(needle.equals("ServerCommand") || needle.equals("BroadcastPayload") ||
            needle.equals("ServerBroadcast") || needle.equals("GenericBroadcast") ||
            needle.equals("LocalizedServerBroadcast") || needle.equals("ServerShutdown"));
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
            if (hits <= 24) {
                log("  hit " + hit + " encoding=" + (utf16 ? "utf16le" : "ascii") +
                    " inline=" + readInlineString(hit, utf16, 180));
                dumpRefsTo(hit, "direct refs", true);
                if (utf16 && DUMP_POINTERS_TO_STRINGS) {
                    dumpRefsToPointers(hit);
                }
            }
            cursor = hit.add(1);
        }
        log("  hits=" + hits + " encoding=" + (utf16 ? "utf16le" : "ascii"));
    }

    private void dumpRefsToPointers(Address target) throws Exception {
        byte[] pattern = pointerPattern(target.getOffset());
        Address cursor = mem.getMinAddress();
        Address max = mem.getMaxAddress();
        int hits = 0;
        while (cursor != null && cursor.compareTo(max) <= 0) {
            Address hit = mem.findBytes(cursor, max, pattern, null, true, monitor);
            if (hit == null) {
                break;
            }
            hits++;
            if (hits <= 12) {
                log("    ptr-to-string " + hit);
                dumpNearbyPointers(hit, 4);
                dumpRefsTo(hit, "refs to ptr", true);
            }
            cursor = hit.add(1);
        }
        if (hits != 0) {
            log("    ptr-to-string hits=" + hits);
        }
    }

    private void dumpFunctionRefsFrom(Function fn, int maxInstructions) {
        log("  body=" + fn.getBody().getMinAddress() + ".." + fn.getBody().getMaxAddress());
        Instruction instr = currentProgram.getListing().getInstructionAt(fn.getEntryPoint());
        int count = 0;
        while (instr != null && fn.getBody().contains(instr.getAddress()) && count < maxInstructions) {
            Reference[] from = refs.getReferencesFrom(instr.getAddress());
            if (instr.getFlowType().isCall() || from.length != 0) {
                log("  insn " + instr.getAddress() + " " + instr);
                for (Reference ref : from) {
                    Address to = ref.getToAddress();
                    Function targetFn = currentProgram.getFunctionManager().getFunctionContaining(to);
                    log("    ref-to " + to + " type=" + ref.getReferenceType() +
                        (targetFn == null ? "" : " function=" + targetFn.getName() + " @ " + targetFn.getEntryPoint()));
                    if (targetFn != null && isInteresting(targetFn.getEntryPoint())) {
                        addFunction(targetFn, "callee");
                    }
                }
            }
            instr = instr.getNext();
            count++;
        }
        if (count >= maxInstructions) {
            log("  truncated instruction walk at " + maxInstructions);
        }
    }

    private boolean isInteresting(Address entry) {
        long off = entry.getOffset();
        return (off >= 0x0da5b000L && off <= 0x0da62000L) ||
            off == 0x0f1bf7b0L || off == 0x0f1bfb30L || off == 0x0f1bcd20L ||
            off == 0x0f1c0a70L || off == 0x0d8d4e30L || off == 0x0fa94500L ||
            off == 0x0fa94190L || off == 0x0fa94010L || off == 0x0fa94310L ||
            off == 0x0fa94290L;
    }

    private void dumpRefsTo(Address addr, String label, boolean collect) {
        ReferenceIterator it = refs.getReferencesTo(addr);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            if (count > MAX_REFS) {
                log("    " + label + " truncated at " + MAX_REFS);
                break;
            }
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

    private void dumpNearbyPointers(Address ptrAddr, int radius) {
        for (int i = -radius; i <= radius; i++) {
            try {
                Address slot = ptrAddr.add((long)i * 8L);
                long raw = mem.getLong(slot);
                Address pointed = toAddr(raw);
                Function fn = currentProgram.getFunctionManager().getFunctionContaining(pointed);
                log("      slot" + signed(i) + " " + slot + " -> 0x" + Long.toHexString(raw) + " " + pointed +
                    (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()) +
                    " ascii=" + readInlineString(pointed, false, 96) +
                    " utf16=" + readInlineString(pointed, true, 96));
            } catch (Exception e) {
                log("      slot" + signed(i) + " <unreadable> " + e.getMessage());
            }
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

    private static byte[] pointerPattern(long value) {
        byte[] pattern = new byte[8];
        for (int i = 0; i < 8; i++) {
            pattern[i] = (byte)((value >>> (8 * i)) & 0xff);
        }
        return pattern;
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
