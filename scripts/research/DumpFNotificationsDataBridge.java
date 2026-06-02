// Ghidra headless script for checking candidate FNotificationsSystemMessage
// data/bridge paths.
//
// The previous layout pass showed that live native GM commands require an
// already decoded Dreamworld::FNotificationsSystemMessage. This pass focuses on
// candidate generated data-function/UStruct bridge code, especially
// FUN_09e05650 and FUN_09e067f0. The first run proved those two functions are
// OptimusNode_DataInterface support code, not the PlayFab/FLS notification
// deserializer.
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpFNotificationsDataBridge.java
//
// Output:
//   /tmp/ghidra-work/fnotifications-data-bridge.txt
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

public class DumpFNotificationsDataBridge extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/fnotifications-data-bridge.txt";
    private static final int MAX_DECOMPILES = 80;
    private static final int MAX_POINTER_HITS = 12;
    private static final int MAX_STRING_HITS = 16;
    private static final int MAX_REFS_TO_DATA = 80;
    private static final boolean DUMP_NEEDLES = false;
    private static final boolean DUMP_POINTERS_TO_NEEDLES = false;
    private static final boolean DUMP_POINTERS_TO_DATA = false;

    private static final long[] FOCUS_FUNCTIONS = new long[] {
        0x09e05650L, // generated data-function bridge
        0x09e067f0L, // data-function lookup helper
        0x09ec9f00L, // decoded message copy helper
        0x09ee7970L, // auth/content extractor wrapper
        0x09eb7e60L, // auth/content extractor implementation
        0x09f3ff90L, // dispatch gate
        0x09ee73c0L, // server-command handler
        0x09ede9a0L  // outbound serializer/publisher
    };

    private static final long[] FOCUS_DATA = new long[] {
        0x1655c760L, // data-function registry used by FUN_09e05650/FUN_09e067f0
        0x1655c7d8L, // guard byte for the generated bridge
        0x1655c5ccL, // logging level/data-function diagnostics
        0x148e60f8L, // data-function diagnostics
        0x148e6118L,
        0x148e6138L,
        0x148e6158L,
        0x148e6178L,
        0x148e6198L,
        0x1490e380L,
        0x1490e3a0L,
        0x1490e3c0L,
        0x1490e3e0L,
        0x1490e400L,
        0x1490e420L
    };

    private static final String[] NEEDLES = new String[] {
        "FNotificationsSystemMessage",
        "NotificationSystemHandleServerMessages",
        "NotificationSystemListenQueue",
        "NotificationSystem message parsing failed. Failed to deserialize.",
        "Server command received. Raw Content:",
        "JsonObjectStringToUStruct",
        "ServerRequestEventNotifications",
        "EngineServiceNotification",
        "EventNamespace",
        "EventName",
        "EventData",
        "EventSettings",
        "PayloadJSON",
        "Payload",
        "OriginalId",
        "OriginalTimestamp",
        "SenderId",
        "SenderID",
        "Sender",
        "AuthToken",
        "AuthorizationToken",
        "Content",
        "MessageType",
        "Version",
        "fls"
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
            dumpFocusData();
            if (DUMP_NEEDLES) {
                dumpNeedles();
            } else {
                log("");
                log("== bounded strings skipped; set DUMP_NEEDLES=true for string scans");
            }
            decompileCollected();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpFocusFunctions() {
        log("");
        log("== focus functions");
        for (long value : FOCUS_FUNCTIONS) {
            Address addr = toAddr(value);
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("");
            log("-- 0x" + Long.toHexString(value) + " " + addr +
                (fn == null ? " function=<none>" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (fn == null) {
                dumpInstructions(addr, 48);
                continue;
            }
            addFunction(fn, "focus");
            dumpRefsTo(fn.getEntryPoint(), "refs to function entry", true);
            dumpFunctionRefsFrom(fn, 2600);
        }
    }

    private void dumpFocusData() throws Exception {
        log("");
        log("== focus data");
        for (long value : FOCUS_DATA) {
            Address addr = toAddr(value);
            log("");
            log("-- data 0x" + Long.toHexString(value) + " " + addr);
            dumpNearbyPointers(addr, 8);
            dumpRefsTo(addr, "refs to data", true);
            if (DUMP_POINTERS_TO_DATA) {
                findPointersTo(addr, "ptr-to-data");
            }
        }
    }

    private void dumpNeedles() throws Exception {
        log("");
        log("== bounded strings");
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
                if (DUMP_POINTERS_TO_NEEDLES) {
                    findPointersTo(hit, "ptr-to-string");
                }
            }
            cursor = hit.add(1);
        }
        log("  hits=" + hits + " encoding=" + (utf16 ? "utf16le" : "ascii"));
    }

    private void dumpFunctionRefsFrom(Function fn, int maxInstructions) {
        log("  body=" + fn.getBody().getMinAddress() + ".." + fn.getBody().getMaxAddress());
        Instruction instr = currentProgram.getListing().getInstructionAt(fn.getEntryPoint());
        int count = 0;
        while (instr != null && fn.getBody().contains(instr.getAddress()) && count < maxInstructions) {
            Reference[] from = refs.getReferencesFrom(instr.getAddress());
            boolean interesting = instr.getFlowType().isCall() || from.length != 0 ||
                mentionsBridgeData(instr.toString());
            if (interesting) {
                log("  insn " + instr.getAddress() + " " + instr);
                for (Reference ref : from) {
                    Address to = ref.getToAddress();
                    Function targetFn = currentProgram.getFunctionManager().getFunctionContaining(to);
                    log("    ref-to " + to + " type=" + ref.getReferenceType() +
                        (targetFn == null ? "" : " function=" + targetFn.getName() + " @ " + targetFn.getEntryPoint()));
                    if (targetFn != null && isInterestingCallee(targetFn.getEntryPoint())) {
                        addFunction(targetFn, "interesting-callee");
                    }
                }
            }
            instr = instr.getNext();
            count++;
        }
        if (count >= maxInstructions) {
            log("  truncated instruction walk at " + maxInstructions + " instructions");
        }
    }

    private boolean mentionsBridgeData(String text) {
        return text.indexOf("0x1655c760") >= 0 || text.indexOf("0x1655c7d8") >= 0 ||
            text.indexOf("0x1655c5cc") >= 0 || text.indexOf("+ 0x48]") >= 0 ||
            text.indexOf("+ 0x50]") >= 0 || text.indexOf("+ 0x58]") >= 0 ||
            text.indexOf("+ 0x60]") >= 0 || text.indexOf("+ 0x78]") >= 0 ||
            text.indexOf("+ 0x80]") >= 0;
    }

    private boolean isInterestingCallee(Address entry) {
        long off = entry.getOffset();
        return off == 0x09e05650L || off == 0x09e067f0L || off == 0x09ec9f00L ||
            off == 0x09ee7970L || off == 0x09eb7e60L || off == 0x09f3ff90L ||
            off == 0x09ee73c0L || off == 0x09ede9a0L || off == 0x09f13850L ||
            off == 0x0f959ca0L || off == 0x0fa74430L || off == 0x0fa75500L ||
            off == 0x0fa70620L || off == 0x09e742c0L;
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
                dumpNearbyPointers(hit, 5);
                dumpRefsTo(hit, "refs to ptr", true);
            }
            cursor = hit.add(1);
        }
        if (hits != 0) {
            log("    " + label + " hits=" + hits);
        }
    }

    private void dumpRefsTo(Address addr, String label, boolean collect) {
        ReferenceIterator it = refs.getReferencesTo(addr);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            if (count > MAX_REFS_TO_DATA) {
                log("    " + label + " truncated at " + MAX_REFS_TO_DATA);
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
