// Ghidra headless script for the native GM notification envelope.
//
// This focuses on the notification path that reaches
// FUN_09f3ff90 -> FUN_09ee73c0 -> FUN_09ee7970/FUN_09eb7e60.
//
// Run:
//   scripts/research/run-ghidra-headless.sh --script DumpNativeGmNotificationLayout.java
//
// Output:
//   /tmp/ghidra-work/native-gm-notification-layout.txt
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

public class DumpNativeGmNotificationLayout extends GhidraScript {
    private static final String OUT = "/tmp/ghidra-work/native-gm-notification-layout.txt";
    private static final int MAX_STRING_HITS = 40;
    private static final int MAX_DECOMPILES = 80;

    private static final long[] ADDRESSES = new long[] {
        0x09f3ff90L, // outer notification dispatch callback
        0x09ee73c0L, // server-command notification handler
        0x09ee7970L, // auth/content extraction wrapper
        0x09eb7e60L, // extraction implementation, signature is larger than current decompile
        0x09ed8ed0L, // notification message copy/initialization, touches outer prefilter globals
        0x09691b80L, // raw command-content parser
        0x13db62f0L, // versioned JSON gate, logs missing/unsupported Version
        0x137af590L, // EventContents parse/JSON surface, references EventNamespace
        0x1385a4f0L, // notification JSON serializer evidence
        0x121360e0L, // EngineServiceNotification event-name surface
        0x0da61730L, // service-broadcast command handler
        0x0da61aa0L, // service-broadcast shutdown handler
        0x0da5cea0L, // ServerCommand field extraction
        0x09ee83c0L  // FLS settings setup, includes ServerCommandsAuthToken
    };

    private static final long[] DATA_ADDRESSES = new long[] {
        0x16562160L, // static string pointer used by FUN_09f3ff90 prefilter
        0x16562168L, // static string length used by FUN_09f3ff90 prefilter
        0x1490e380L,
        0x1490e3a0L,
        0x1490e3c0L,
        0x1490e3e0L,
        0x1490e400L,
        0x05509c38L  // UTF-16 ServerCommandsAuthToken string
    };

    private static final String[] NEEDLES = new String[] {
        "AuthToken",
        "NotificationSystem message parsing failed. Failed to deserialize.",
        "NotificationSystem message ignored. Outdated message version:",
        "NotificationSystem message handling failed. Empty message content.",
        "NotificationSystem message handling failed. Invalid Auth Token.",
        "NotificationSystem message handling failed. Invalid Sender ID, we only accept server commands from 'fls'.",
        "Server command received. Raw Content:",
        "ServerRequestEventNotifications",
        "ClientGenericNotification",
        "ClientGenericNotifications",
        "EngineServiceNotification",
        "EventNamespace",
        "OriginalId",
        "OriginalTimestamp",
        "PayloadJSON",
        "Version",
        "Field 'Version' is absent",
        "Field 'Version' equal",
        "ServerCommand",
        "ServerCommandsAuthToken",
        "ServiceBroadcast",
        "BroadcastType",
        "BroadcastPayload",
        "Handling ServiceBroadcast Server command:"
    };

    private PrintWriter out;
    private Memory mem;
    private ReferenceManager refs;
    private DecompInterface decomp;
    private final Set<Address> toDecompile = new LinkedHashSet<>();

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
            dumpAddresses();
            dumpDataAddresses();
            dumpNeedles();
            decompileCollected();
        } finally {
            decomp.dispose();
            out.close();
        }
    }

    private void dumpAddresses() {
        log("");
        log("== functions and instructions");
        for (long value : ADDRESSES) {
            Address addr = toAddr(value);
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(addr);
            log("");
            log("-- 0x" + Long.toHexString(value) + " " + addr +
                (fn == null ? " function=<none>" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (fn != null) {
                toDecompile.add(fn.getEntryPoint());
                dumpRefsTo(fn.getEntryPoint(), "refs to function entry", true);
            }
            dumpInstructions(addr, 90);
        }
    }

    private void dumpDataAddresses() throws Exception {
        log("");
        log("== data addresses");
        for (long value : DATA_ADDRESSES) {
            Address addr = toAddr(value);
            log("");
            log("-- 0x" + Long.toHexString(value) + " " + addr);
            dumpRefsTo(addr, "refs to data", true);
            dumpScalarInterpretation(addr);
            dumpPointerString(addr);
            dumpInlineString(addr);
        }
    }

    private void dumpNeedles() throws Exception {
        log("");
        log("== strings");
        for (String needle : NEEDLES) {
            log("");
            log("-- " + needle);
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
                log("hit " + hit + " encoding=" + (utf16 ? "utf16le" : "ascii") +
                    " inline=" + readInlineString(hit, utf16, 180));
                dumpRefsTo(hit, "direct refs", false);
                ReferenceIterator it = refs.getReferencesTo(hit);
                while (it.hasNext()) {
                    dumpRefsTo(it.next().getFromAddress(), "indirect refs from direct-ref site", false);
                }
            }
            cursor = hit.add(1);
        }
        log("hits=" + hits + " encoding=" + (utf16 ? "utf16le" : "ascii"));
    }

    private void dumpRefsTo(Address addr, String label, boolean collect) {
        ReferenceIterator it = refs.getReferencesTo(addr);
        int count = 0;
        while (it.hasNext()) {
            Reference ref = it.next();
            count++;
            Function fn = currentProgram.getFunctionManager().getFunctionContaining(ref.getFromAddress());
            log("  " + label + " " + ref.getFromAddress() + " type=" + ref.getReferenceType() +
                (fn == null ? "" : " function=" + fn.getName() + " @ " + fn.getEntryPoint()));
            if (collect && fn != null && toDecompile.size() < MAX_DECOMPILES) {
                toDecompile.add(fn.getEntryPoint());
            }
        }
        if (count == 0) {
            log("  " + label + "=0");
        }
    }

    private void dumpScalarInterpretation(Address addr) {
        try {
            long qword = mem.getLong(addr);
            int dword0 = mem.getInt(addr);
            int dword4 = mem.getInt(addr.add(4));
            log("  qword=0x" + Long.toHexString(qword) + " dword0=" + dword0 + " dword4=" + dword4);
        } catch (Exception e) {
            log("  scalar=<unreadable> " + e.getMessage());
        }
    }

    private void dumpPointerString(Address addr) {
        try {
            long pointerValue = mem.getLong(addr);
            Address pointed = toAddr(pointerValue);
            log("  pointer=0x" + Long.toHexString(pointerValue) + " " + pointed);
            log("  pointer ascii=" + readInlineString(pointed, false, 180));
            log("  pointer utf16=" + readInlineString(pointed, true, 180));
        } catch (Exception e) {
            log("  pointer=<unreadable> " + e.getMessage());
        }
    }

    private void dumpInlineString(Address addr) {
        log("  inline ascii=" + readInlineString(addr, false, 180));
        log("  inline utf16=" + readInlineString(addr, true, 180));
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

    private void decompileCollected() throws Exception {
        log("");
        log("== decompile collected functions count=" + toDecompile.size());
        for (Address entry : toDecompile) {
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

    private void log(String s) {
        println(s);
        out.println(s);
        out.flush();
    }
}
